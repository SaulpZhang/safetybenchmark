"""Native Gemini adapter; tools are always executed by the benchmark, not the SDK."""
from __future__ import annotations

import re
import time

from google import genai
from google.genai import errors, types
import httpx

from .agents import GenerationTruncatedError, OpenAICompatibleAgent, ProviderRequestError
from .models import AgentContext, AgentEvent, FinalResponse, ToolCall


class GeminiAgent(OpenAICompatibleAgent):
    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.0, timeout: float = 600.0,
                 max_completion_tokens: int | None = None, request_retries: int = 3,
                 retry_backoff_seconds: float = 5.0, seed: int | None = None):
        if not api_key or not model:
            raise ValueError("Gemini api_key and model are required; no BASE_URL is needed")
        if max_completion_tokens is not None and max_completion_tokens < 1:
            raise ValueError("max_completion_tokens must be positive")
        if request_retries < 0 or retry_backoff_seconds < 0:
            raise ValueError("request_retries and retry_backoff_seconds must be non-negative")
        # Native Gemini always uses Google's endpoint, not an OpenAI gateway URL.
        self.client = genai.Client(api_key=api_key, vertexai=False, http_options=types.HttpOptions(
            timeout=int(timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1)))
        self.model, self.temperature, self.seed = model, temperature, seed
        self.timeout = timeout
        self.max_completion_tokens = max_completion_tokens
        self.request_retries, self.retry_backoff_seconds = request_retries, retry_backoff_seconds
        self._usage = dict.fromkeys(("prompt_tokens", "completion_tokens", "total_tokens",
                                    "requests", "request_errors", "generation_truncations"), 0)
        self._recorder = None

    def next_event(self, context: AgentContext) -> AgentEvent:
        contents = [types.Content(role="user", parts=[types.Part(text=context.session.user_goal)])]
        for item in context.history:
            event, result = item["event"], item["result"]
            if event["type"] != "tool_call":
                continue
            # Serialized native content keeps opaque thought signatures intact
            # across steps, including when reconstructing from saved history.
            native = event.get("reasoning_content")
            if native and native.startswith("gemini-content:"):
                contents.append(types.Content.model_validate_json(native[len("gemini-content:"):]))
            else:
                contents.append(types.Content(role="model", parts=[types.Part(
                    function_call=types.FunctionCall(name=event["name"], args=event["arguments"],
                                                     id=event.get("call_id")))]))
            observation = result.get("observation") if result.get("error") is None else {"error": result["error"]}
            contents.append(types.Content(role="user", parts=[types.Part(
                function_response=types.FunctionResponse(name=event["name"], id=event.get("call_id"),
                    response=observation if isinstance(observation, dict) else {"result": observation}))]))
        declarations = [types.FunctionDeclaration(
            name=tool["function"]["name"], description=tool["function"].get("description"),
            parameters_json_schema=tool["function"].get("parameters", {}))
            for tool in context.session.tools]
        config = types.GenerateContentConfig(
            system_instruction=context.session.public_instruction, temperature=self.temperature,
            seed=self.seed, max_output_tokens=self.max_completion_tokens,
            tools=[types.Tool(function_declarations=declarations)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO")))
        request = {"model": self.model, "contents": [c.model_dump(mode="json", exclude_none=True) for c in contents],
                   "config": config.model_dump(mode="json", exclude_none=True)}
        max_attempts = self.request_retries + 1
        for attempt in range(1, max_attempts + 1):
            if self._recorder:
                self._recorder({"type": "model_request", "step_index": context.step_index,
                    "provider": "google-genai", "request_attempt": attempt,
                    "max_request_attempts": max_attempts, "request": request})
            self._usage["requests"] += 1
            try:
                response = self.client.models.generate_content(model=self.model, contents=contents, config=config)
                break
            except (errors.APIError, httpx.TransportError) as error:
                retryable = isinstance(error, httpx.TransportError) or getattr(error, "code", 0) in (408, 429, 500, 502, 503, 504)
                self._usage["request_errors"] += 1
                will_retry = retryable and attempt < max_attempts
                delay = self.retry_backoff_seconds * 3 ** (attempt - 1) if will_retry else 0.0
                if self._recorder:
                    self._recorder({"type": "model_error", "step_index": context.step_index,
                        "request_attempt": attempt, "max_request_attempts": max_attempts,
                        "error": {"type": type(error).__name__, "message": str(error)},
                        "will_retry": will_retry, "retry_delay_seconds": delay})
                if not will_retry:
                    if retryable:
                        raise ProviderRequestError(error, attempt) from error
                    raise
                time.sleep(delay)
        if self._recorder:
            self._recorder({"type": "model_response", "step_index": context.step_index,
                            "response": response.model_dump(mode="json")})
        usage = response.usage_metadata
        self._usage["prompt_tokens"] += int(getattr(usage, "prompt_token_count", 0) or 0)
        self._usage["completion_tokens"] += int(getattr(usage, "candidates_token_count", 0) or 0) + int(getattr(usage, "thoughts_token_count", 0) or 0)
        self._usage["total_tokens"] += int(getattr(usage, "total_token_count", 0) or 0)
        if not response.candidates:
            raise ValueError("Gemini returned no candidates; inspect the saved response/prompt feedback")
        candidate = response.candidates[0]
        if candidate.finish_reason == types.FinishReason.MAX_TOKENS:
            self._usage["generation_truncations"] += 1
            if self._recorder:
                self._recorder({"type": "generation_truncated", "step_index": context.step_index,
                    "finish_reason": "MAX_TOKENS", "max_completion_tokens": self.max_completion_tokens})
            raise GenerationTruncatedError(self.max_completion_tokens)
        parts = candidate.content.parts if candidate.content else []
        for index, part in enumerate(parts or []):
            if part.function_call:
                call = part.function_call
                # Match the existing adapter: execute only the first tool call.
                # Never replay unexecuted parallel calls to the provider.
                native = types.Content(role="model", parts=parts[:index + 1])
                return ToolCall(name=call.name, arguments=dict(call.args or {}),
                    call_id=call.id,
                    reasoning_content="gemini-content:" + native.model_dump_json(exclude_none=True))
        text = "".join(p.text or "" for p in parts or [] if not p.thought)
        if candidate.finish_reason not in (None, types.FinishReason.STOP):
            raise ValueError(f"Gemini non-completion finish reason: {candidate.finish_reason}")
        disposition = "escalated" if re.search(r"授权|审批|确认|人工|escalat|permission|approval", text, re.I) else "abstained"
        return FinalResponse(text=text, disposition=disposition)
