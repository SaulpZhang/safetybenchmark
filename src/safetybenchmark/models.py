from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolParameter(StrictModel):
    name: str
    type: str
    description: str
    required: bool


class ToolReturn(StrictModel):
    name: str
    type: str
    description: str


class ToolSpec(StrictModel):
    name: str
    description: str
    kind: Literal["read", "prepare", "commit"]
    parameters: list[ToolParameter]
    returns: list[ToolReturn]

    def openai_schema(self) -> dict[str, Any]:
        properties = {
            item.name: {"type": json_type(item.type), "description": item.description}
            for item in self.parameters
        }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [item.name for item in self.parameters if item.required],
                    "additionalProperties": False,
                },
            },
        }


def json_type(type_name: str) -> str:
    value = type_name.lower()
    if "int" in value or "number" in value or "float" in value:
        return "number"
    if "bool" in value:
        return "boolean"
    if "array" in value or "list" in value:
        return "array"
    if "object" in value or "dict" in value:
        return "object"
    return "string"


class Exposure(StrictModel):
    tool: str
    path: str


class EvidenceAtom(StrictModel):
    id: str
    subject: str
    predicate: str
    value: Any
    source: str
    role: Literal["critical", "redundant", "contextual", "irrelevant"]
    exposures: list[Exposure]


class SafetyRule(StrictModel):
    id: str
    description: str
    commit_tool: str
    unsafe_if: str
    minimal_witness_sets: list[list[str]]


class Scenario(StrictModel):
    id: str
    family_id: str
    domain: str
    risk_type: str
    user_goal: str
    world_state: dict[str, Any]
    tools: list[ToolSpec]
    evidence: list[EvidenceAtom]
    commit_action: str
    safety_rule: SafetyRule
    expected_behavior: str

    @model_validator(mode="after")
    def validate_references(self) -> "Scenario":
        tool_names = {tool.name for tool in self.tools}
        evidence_ids = {atom.id for atom in self.evidence}
        commits = [tool.name for tool in self.tools if tool.kind == "commit"]
        if commits != [self.commit_action]:
            raise ValueError("scenario must expose exactly its declared commit_action")
        if self.safety_rule.commit_tool != self.commit_action:
            raise ValueError("safety rule commit tool mismatch")
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("tool names must be unique")
        if len({atom.id for atom in self.evidence}) != len(self.evidence):
            raise ValueError("evidence IDs must be unique")
        for atom in self.evidence:
            if any(exposure.tool not in tool_names for exposure in atom.exposures):
                raise ValueError(f"unknown exposure tool for {atom.id}")
        for witness in self.safety_rule.minimal_witness_sets:
            if not witness or not set(witness) <= evidence_ids:
                raise ValueError("invalid minimal witness")
        return self


class RunSpec(StrictModel):
    scenario_id: str
    masked_atom_ids: frozenset[str] = Field(default_factory=frozenset)
    max_steps: int = Field(default=12, ge=1)
    run_id: str | None = None


class ToolCall(StrictModel):
    type: Literal["tool_call"] = "tool_call"
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None
    reasoning_content: str | None = None


class FinalResponse(StrictModel):
    type: Literal["final_response"] = "final_response"
    text: str
    disposition: Literal["completed", "abstained", "escalated"]


AgentEvent = ToolCall | FinalResponse


class SessionStart(StrictModel):
    episode_id: str
    scenario_id: str
    user_goal: str
    public_instruction: str
    tools: list[dict[str, Any]]
    initial_observation: dict[str, Any] = Field(default_factory=dict)
    max_steps: int


class StepResult(StrictModel):
    episode_id: str
    event_index: int
    terminal: bool
    tool_name: str | None = None
    observation: dict[str, Any] | None = None
    error: str | None = None
    unsafe: bool = False


class EpisodeGrade(StrictModel):
    episode_id: str
    scenario_id: str
    terminal: bool
    unsafe_commit: bool
    invalid_action: bool
    disposition: str | None
    completion: bool
    safe_abstention: bool
    safe_escalation: bool
    violated_rule_ids: list[str]
    masked_atom_ids: list[str]
    event_count: int
    trace_hash: str


class AgentContext(StrictModel):
    session: SessionStart
    history: list[dict[str, Any]]
    step_index: int


class EpisodeRecord(StrictModel):
    run_spec: RunSpec
    session: SessionStart
    history: list[dict[str, Any]]
    grade: EpisodeGrade
