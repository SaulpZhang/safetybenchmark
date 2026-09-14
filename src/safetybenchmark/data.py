from __future__ import annotations

import json
from pathlib import Path

from .models import Scenario


class ScenarioRepository:
    """Loads and indexes an immutable JSONL scenario suite."""

    def __init__(self, scenarios: list[Scenario], source: Path | None = None):
        self._by_id = {scenario.id: scenario for scenario in scenarios}
        if len(self._by_id) != len(scenarios):
            raise ValueError("scenario IDs must be unique")
        self.source = source

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "ScenarioRepository":
        source = Path(path)
        scenarios: list[Scenario] = []
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                scenarios.append(Scenario.model_validate_json(line))
            except Exception as error:
                raise ValueError(f"invalid scenario at {source}:{line_number}: {error}") from error
        return cls(scenarios, source)

    def get(self, scenario_id: str) -> Scenario:
        try:
            return self._by_id[scenario_id]
        except KeyError as error:
            raise KeyError(f"unknown scenario: {scenario_id}") from error

    def list(self, domain: str | None = None) -> list[Scenario]:
        values = self._by_id.values()
        return sorted(
            (scenario for scenario in values if domain is None or scenario.domain == domain),
            key=lambda scenario: scenario.id,
        )

    def __len__(self) -> int:
        return len(self._by_id)

    def summary(self) -> dict[str, object]:
        domains: dict[str, int] = {}
        families: set[str] = set()
        for scenario in self._by_id.values():
            domains[scenario.domain] = domains.get(scenario.domain, 0) + 1
            families.add(scenario.family_id)
        return {"scenarios": len(self), "domains": dict(sorted(domains.items())), "families": len(families)}
