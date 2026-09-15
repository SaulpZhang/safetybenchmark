from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .agents import Agent
from .environment import SafetyEnvironment
from .models import AgentContext, EpisodeRecord, FinalResponse, RunSpec


def run_episode(agent: Agent, environment: SafetyEnvironment, run_spec: RunSpec,
                recorder: Callable[[dict[str, object]], None] | None = None) -> EpisodeRecord:
    session = environment.reset(run_spec)
    if recorder:
        recorder({"type": "session", "session": session.model_dump(mode="json"),
                  "run_spec": run_spec.model_dump(mode="json")})
    history: list[dict[str, object]] = []
    for step_index in range(run_spec.max_steps + 1):
        event = agent.next_event(
            AgentContext(session=session, history=history, step_index=step_index)
        )
        result = environment.step(event)
        history.append(
            {"event": event.model_dump(mode="json"), "result": result.model_dump(mode="json")}
        )
        if recorder:
            recorder({"type": "step", "step_index": step_index, **history[-1]})
        if result.terminal:
            break
    if not environment.grade().terminal:
        event = FinalResponse(text="达到运行步数限制。", disposition="abstained")
        result = environment.step(event)
        history.append(
            {"event": event.model_dump(mode="json"), "result": result.model_dump(mode="json")}
        )
    return EpisodeRecord(
        run_spec=run_spec,
        session=session,
        history=history,
        grade=environment.grade(),
    )


def append_record(path: str | Path, record: EpisodeRecord | dict[str, object]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json") if isinstance(record, EpisodeRecord) else record
    with output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
