from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from google.genai import errors, types

from safetybenchmark.agents import OpenAICompatibleAgent, ProviderRequestError, GenerationTruncatedError
from safetybenchmark.gemini import GeminiAgent
from safetybenchmark.data import ScenarioRepository
from safetybenchmark.environment import SafetyEnvironment
from safetybenchmark.models import AgentContext, RunSpec, FinalResponse


class GeminiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = ScenarioRepository.from_jsonl("data/generated/v1-300.jsonl")

    def setUp(self):
        self.client_patch = patch("safetybenchmark.gemini.genai.Client")
        self.client_constructor = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.agent = GeminiAgent("", "test-only", "gemini-test", seed=7, timeout=600)
        self.session = SafetyEnvironment(self.repository).reset(RunSpec(scenario_id=self.repository.list()[0].id))
        self.context = AgentContext(session=self.session, history=[], step_index=0)
        self.logs = []
        self.agent.set_recorder(self.logs.append)

    def respond(self, parts, finish="STOP"):
        self.agent.client.models.generate_content.return_value = types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=3, thoughts_token_count=2, total_token_count=15))

    def test_prefix_routing_without_url_and_google_key_aliases(self):
        for key in ("API_KEY", "LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / ".env"
                path.write_text(f"{key}=test-only\nMODEL=GeMiNi-test\n", encoding="utf-8")
                self.assertIsInstance(OpenAICompatibleAgent.from_dotenv(path), GeminiAgent)
        options = self.client_constructor.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, 600000)
        self.assertEqual(options.retry_options.attempts, 1)

    def test_gateway_gemini_and_other_models_stay_openai(self):
        with patch("safetybenchmark.agents.OpenAI"):
            for model in ("google/gemini-test", "gpt-test"):
                agent = OpenAICompatibleAgent.from_dotenv("missing.env", model=model,
                    base_url="https://gateway.invalid/v1", api_key="test-only")
                self.assertIs(type(agent), OpenAICompatibleAgent)

    def test_signature_history_and_usage_recording(self):
        name = self.session.tools[0]["function"]["name"]
        self.respond([types.Part(function_call=types.FunctionCall(name=name, args={}, id="call-1"),
                                 thought_signature=b"opaque-signature")])
        event = self.agent.next_event(self.context)
        self.assertEqual(event.name, name)
        self.respond([types.Part(text="Cannot safely proceed")])
        context = self.context.model_copy(update={"history": [{"event": event.model_dump(mode="json"),
            "result": {"observation": {"visible": True}, "error": None}}], "step_index": 1})
        self.assertIsInstance(self.agent.next_event(context), FinalResponse)
        sent = self.agent.client.models.generate_content.call_args.kwargs
        self.assertEqual(sent["contents"][1].parts[0].thought_signature, b"opaque-signature")
        self.assertEqual(sent["contents"][2].parts[0].function_response.id, "call-1")
        self.assertTrue(sent["config"].automatic_function_calling.disable)
        self.assertIsNone(sent["config"].max_output_tokens)
        self.assertEqual(self.agent.run_metrics()["completion_tokens"], 10)
        self.assertEqual(self.agent.run_metrics()["requests"], 2)
        self.assertNotIn("test-only", str(self.logs))

    def test_429_retries_are_visible_and_exhaustion_is_infrastructure(self):
        self.agent.client.models.generate_content.side_effect = errors.ClientError(429, {"error": {"message": "quota"}})
        with patch("safetybenchmark.gemini.time.sleep") as sleep:
            with self.assertRaises(ProviderRequestError):
                self.agent.next_event(self.context)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 15, 45])
        self.assertEqual(self.agent.run_metrics()["request_errors"], 4)
        self.assertEqual(len([r for r in self.logs if r["type"] == "model_error"]), 4)

    def test_auth_errors_are_not_retried(self):
        self.agent.client.models.generate_content.side_effect = errors.ClientError(401, {"error": {"message": "auth"}})
        with self.assertRaises(errors.ClientError):
            self.agent.next_event(self.context)
        self.assertEqual(self.agent.run_metrics()["requests"], 1)

    def test_truncation_is_not_abstention(self):
        self.respond([types.Part(text="partial")], finish="MAX_TOKENS")
        with self.assertRaises(GenerationTruncatedError):
            self.agent.next_event(self.context)
        self.assertEqual(self.agent.run_metrics()["generation_truncations"], 1)

    def test_every_task_schema_is_accepted(self):
        for scenario in self.repository.list():
            for tool in scenario.tools:
                types.FunctionDeclaration(name=tool.name, parameters_json_schema=tool.parameters)


if __name__ == "__main__":
    unittest.main()
