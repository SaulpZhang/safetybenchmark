from __future__ import annotations

import unittest
from pathlib import Path

from safetybenchmark.data import ScenarioRepository
from safetybenchmark.models import Scenario, json_type
from safetybenchmark.oracle import DEFAULT_ORACLE, SafetyOracle
from safetybenchmark.rule_predicates import audit_rule_inversions


DATASET = Path("data/generated/v1-300.jsonl")


def commit_arguments(scenario: Scenario) -> dict[str, object]:
    tool = next(item for item in scenario.tools if item.name == scenario.commit_action)
    return {
        parameter.name: {
            "number": 0,
            "boolean": False,
            "array": [],
            "object": {},
        }.get(json_type(parameter.type), "benchmark-target")
        for parameter in tool.parameters
        if parameter.required
    }


class ExecutableOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = ScenarioRepository.from_jsonl(DATASET)

    def test_oracle_result_is_independent_of_world_type_label(self) -> None:
        base = self.repository.get("finance.payment.approval_limit.001")
        twin = self.repository.get(base.paired_scenario_id or "")

        relabeled_base = base.model_copy(update={"world_type": "safe"})
        relabeled_twin = twin.model_copy(update={"world_type": "unsafe"})

        self.assertTrue(
            DEFAULT_ORACLE.assess(
                relabeled_base,
                next(tool for tool in base.tools if tool.name == base.commit_action),
                commit_arguments(base),
            ).unsafe
        )
        self.assertEqual(
            DEFAULT_ORACLE.assess(
                relabeled_twin,
                next(tool for tool in twin.tools if tool.name == twin.commit_action),
                commit_arguments(twin),
            ).status,
            "safe",
        )

    def test_every_matched_pair_inverts_its_executable_rule(self) -> None:
        bases = [item for item in self.repository.list() if item.world_type == "unsafe"]
        self.assertEqual(len(bases), 300)
        for base in bases:
            twin = self.repository.get(base.paired_scenario_id or "")
            tool = next(item for item in base.tools if item.name == base.commit_action)
            arguments = commit_arguments(base)
            with self.subTest(scenario=base.id):
                self.assertEqual(DEFAULT_ORACLE.assess(base, tool, arguments).status, "unsafe")
                self.assertEqual(DEFAULT_ORACLE.assess(twin, tool, arguments).status, "safe")

    def test_suite_rule_inversion_audit_covers_all_pairs_and_families(self) -> None:
        self.assertEqual(
            audit_rule_inversions(self.repository.list()),
            {"executable_rule_families": 60, "rule_inversion_pairs": 300},
        )

    def test_missing_executable_rule_is_invalid_instead_of_using_label(self) -> None:
        base = self.repository.get("finance.payment.approval_limit.001")
        unknown = base.model_copy(
            update={
                "family_id": "unknown.family",
                "safety_rule": base.safety_rule.model_copy(update={"id": "unknown.rule"}),
            }
        )
        tool = next(item for item in base.tools if item.name == base.commit_action)
        assessment = SafetyOracle().assess(unknown, tool, commit_arguments(unknown))
        self.assertEqual(assessment.status, "invalid")
        self.assertIn("no executable predicate", assessment.reason or "")


if __name__ == "__main__":
    unittest.main()
