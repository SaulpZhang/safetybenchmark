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
                base = Scenario.model_validate_json(line)
                if base.safe_twin is None:
                    scenarios.append(base)
                    continue
                base_payload = base.model_dump(mode="python")
                base_payload["paired_scenario_id"] = base.safe_twin.id
                scenarios.append(Scenario.model_validate(base_payload))

                overrides = {item.id: item.value for item in base.safe_twin.evidence_overrides}
                twin_payload = base.model_dump(mode="python")
                twin_payload.update(
                    {
                        "id": base.safe_twin.id,
                        "world_state": base.safe_twin.world_state,
                        "expected_behavior": base.safe_twin.expected_behavior,
                        "world_type": "safe",
                        "paired_scenario_id": base.id,
                        "twin_changed_atom_ids": sorted(overrides),
                        "safe_twin": None,
                    }
                )
                for atom in twin_payload["evidence"]:
                    if atom["id"] in overrides:
                        atom["value"] = overrides[atom["id"]]
                scenarios.append(Scenario.model_validate(twin_payload))
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
        world_types: dict[str, int] = {}
        families: set[str] = set()
        for scenario in self._by_id.values():
            domains[scenario.domain] = domains.get(scenario.domain, 0) + 1
            world_types[scenario.world_type] = world_types.get(scenario.world_type, 0) + 1
            families.add(scenario.family_id)
        paired = sum(scenario.paired_scenario_id is not None for scenario in self._by_id.values())
        return {
            "scenarios": len(self),
            "domains": dict(sorted(domains.items())),
            "world_types": dict(sorted(world_types.items())),
            "paired_scenarios": paired,
            "families": len(families),
        }
