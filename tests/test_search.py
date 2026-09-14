from __future__ import annotations

import unittest

from safetybenchmark.agents import BlindCommitAgent, SafeReferenceAgent
from safetybenchmark.data import ScenarioRepository
from safetybenchmark.search import exact_boundary_search


class SearchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = ScenarioRepository.from_jsonl("data/generated/v1-300.jsonl")
        cls.scenario = cls.repository.list("finance")[0]

    def test_full_evidence_failure_is_not_esm_zero(self) -> None:
        result = exact_boundary_search(
            self.repository, self.scenario.id, BlindCommitAgent, max_mask_size=1
        )
        self.assertFalse(result["eligible"])
        self.assertIsNone(result["esm"])

    def test_no_breach_reports_right_censoring(self) -> None:
        result = exact_boundary_search(
            self.repository, self.scenario.id, SafeReferenceAgent, max_mask_size=1
        )
        self.assertTrue(result["eligible"])
        self.assertIsNone(result["esm"])
        self.assertEqual(result["censored_above"], 1)


if __name__ == "__main__":
    unittest.main()
