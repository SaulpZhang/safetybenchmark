from __future__ import annotations

import copy
import re
import unittest
from pathlib import Path

from safetybenchmark.agents import BlindCommitAgent, SafeReferenceAgent
from safetybenchmark.data import ScenarioRepository
from safetybenchmark.environment import SafetyEnvironment
from safetybenchmark.models import RunSpec, ToolCall, json_type
from safetybenchmark.projection import jsonpath_tokens
from safetybenchmark.runner import run_episode


DATASET = Path("data/generated/v1-300.jsonl")


def lookup(value: object, path: str) -> object:
    current = value
    for token in jsonpath_tokens(path):
        current = current[token]  # type: ignore[index]
    return current


class EnvironmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = ScenarioRepository.from_jsonl(DATASET)
        cls.scenario = cls.repository.list("finance")[0]

    def test_all_generated_scenarios_load(self) -> None:
        self.assertEqual(len(self.repository), 300)
        self.assertEqual(self.repository.summary()["families"], 60)

    def test_all_full_evidence_exposures_are_renderable(self) -> None:
        for scenario in self.repository.list():
            for atom in scenario.evidence:
                for exposure in atom.exposures:
                    environment = SafetyEnvironment(self.repository)
                    environment.reset(RunSpec(scenario_id=scenario.id))
                    tool = next(item for item in scenario.tools if item.name == exposure.tool)
                    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", atom.subject.split(":", 1)[-1])
                    subject_value = candidates[0] if candidates else "target"
                    arguments = {
                        item.name: ({"number": 0, "boolean": False, "array": [], "object": {}}.get(
                            json_type(item.type), subject_value
                        ))
                        for item in tool.parameters
                        if item.required
                    }
                    observation = environment.step(
                        ToolCall(name=tool.name, arguments=arguments)
                    ).observation or {}
                    with self.subTest(scenario=scenario.id, atom=atom.id, path=exposure.path):
                        self.assertEqual(lookup(observation, exposure.path), atom.value)

    def test_all_single_atom_masks_remove_their_exposures(self) -> None:
        for scenario in self.repository.list():
            for atom in scenario.evidence:
                environment = SafetyEnvironment(self.repository)
                environment.reset(
                    RunSpec(scenario_id=scenario.id, masked_atom_ids=frozenset({atom.id}))
                )
                for exposure in atom.exposures:
                    tool = next(item for item in scenario.tools if item.name == exposure.tool)
                    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", atom.subject.split(":", 1)[-1])
                    subject_value = candidates[0] if candidates else "target"
                    arguments = {
                        item.name: ({"number": 0, "boolean": False, "array": [], "object": {}}.get(
                            json_type(item.type), subject_value
                        ))
                        for item in tool.parameters
                        if item.required
                    }
                    observation = environment.step(
                        ToolCall(name=tool.name, arguments=arguments)
                    ).observation or {}
                    full_environment = SafetyEnvironment(self.repository)
                    full_environment.reset(RunSpec(scenario_id=scenario.id))
                    full_observation = full_environment.step(
                        ToolCall(name=tool.name, arguments=arguments)
                    ).observation or {}
                    path_tokens = jsonpath_tokens(exposure.path)
                    if isinstance(path_tokens[-1], int):
                        parent_path = "$." + ".".join(
                            str(token) if isinstance(token, str) else f"[{token}]"
                            for token in path_tokens[:-1]
                        ).replace(".[", "[")
                        with self.subTest(scenario=scenario.id, atom=atom.id, path=exposure.path):
                            self.assertEqual(
                                len(lookup(observation, parent_path)),
                                len(lookup(full_observation, parent_path)) - 1,
                            )
                        continue
                    try:
                        visible_value = lookup(observation, exposure.path)
                    except (KeyError, IndexError, TypeError):
                        continue
                    with self.subTest(scenario=scenario.id, atom=atom.id, path=exposure.path):
                        self.assertNotEqual(visible_value, atom.value)

    def test_mask_hides_every_declared_exposure_without_changing_true_state(self) -> None:
        atom = self.scenario.evidence[0]
        exposure = atom.exposures[0]
        full = SafetyEnvironment(self.repository)
        full.reset(RunSpec(scenario_id=self.scenario.id))
        initial_state = full.true_state_snapshot()
        tool = next(item for item in self.scenario.tools if item.name == exposure.tool)
        arguments = {item.name: "target" for item in tool.parameters if item.required}
        full_result = full.step(ToolCall(name=tool.name, arguments=arguments))
        self.assertEqual(lookup(full_result.observation or {}, exposure.path), atom.value)

        masked = SafetyEnvironment(self.repository)
        masked.reset(RunSpec(scenario_id=self.scenario.id, masked_atom_ids=frozenset({atom.id})))
        masked_result = masked.step(ToolCall(name=tool.name, arguments=arguments))
        with self.assertRaises((KeyError, IndexError, TypeError)):
            lookup(masked_result.observation or {}, exposure.path)
        self.assertEqual(masked.true_state_snapshot(), initial_state)

    def test_commit_safety_is_invariant_to_observation_mask(self) -> None:
        atom_id = self.scenario.evidence[0].id
        full = run_episode(
            BlindCommitAgent(),
            SafetyEnvironment(self.repository),
            RunSpec(scenario_id=self.scenario.id, max_steps=1),
        )
        masked = run_episode(
            BlindCommitAgent(),
            SafetyEnvironment(self.repository),
            RunSpec(scenario_id=self.scenario.id, masked_atom_ids=frozenset({atom_id}), max_steps=1),
        )
        self.assertTrue(full.grade.unsafe_commit)
        self.assertTrue(masked.grade.unsafe_commit)
        self.assertFalse(full.grade.invalid_action)
        self.assertFalse(masked.grade.invalid_action)
        self.assertEqual(full.grade.violated_rule_ids, masked.grade.violated_rule_ids)

    def test_safe_reference_agent_escalates_without_commit(self) -> None:
        record = run_episode(
            SafeReferenceAgent(),
            SafetyEnvironment(self.repository),
            RunSpec(scenario_id=self.scenario.id, max_steps=12),
        )
        self.assertFalse(record.grade.unsafe_commit)
        self.assertTrue(record.grade.safe_escalation)


if __name__ == "__main__":
    unittest.main()
