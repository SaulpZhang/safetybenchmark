from __future__ import annotations

import tempfile
import unittest
from math import comb
from pathlib import Path

from safetybenchmark.agents import SafeReferenceAgent
from safetybenchmark.data import ScenarioRepository
from safetybenchmark.experiments import ExperimentSettings, run_protocol
from safetybenchmark.reporting import read_jsonl, summarize


class PaperExperimentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = Path("data/generated/v1-300.jsonl")
        cls.repository = ScenarioRepository.from_jsonl(cls.dataset)
        cls.base = next(item for item in cls.repository.list("finance") if item.world_type == "unsafe")

    def test_calibration_ledger_is_resume_safe_and_reports_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "calibration.jsonl"
            manifest = Path(directory) / "calibration.manifest.json"
            settings = ExperimentSettings(protocol="calibration", repetitions=1, scenario_id=self.base.id)
            result = run_protocol(
                self.repository,
                self.dataset,
                ledger,
                manifest,
                settings,
                {"adapter": "safe-reference"},
                lambda seed: SafeReferenceAgent(),
            )
            self.assertEqual(result["executed_trials"], 4)
            rows = read_jsonl(ledger)
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row["trace_path"] for row in rows))
            self.assertTrue(all(row["dataset_sha256"] for row in rows))
            self.assertTrue(all(row["scenario"]["pair_id"] == self.base.id for row in rows))
            resumed = run_protocol(
                self.repository,
                self.dataset,
                ledger,
                manifest,
                settings,
                {"adapter": "safe-reference"},
                lambda seed: SafeReferenceAgent(),
                resume=True,
            )
            self.assertEqual(resumed["executed_trials"], 0)
            self.assertEqual(resumed["skipped_completed_trials"], 4)
            report = summarize(rows)
            self.assertEqual(report["type"], "paper_trial_ledger")
            self.assertEqual(report["paired_calibration"]["semantic_suppression"]["complete_pairs"], 1)

    def test_resume_rejects_a_different_agent_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "calibration.jsonl"
            manifest = Path(directory) / "calibration.manifest.json"
            settings = ExperimentSettings(protocol="calibration", repetitions=1, scenario_id=self.base.id)
            run_protocol(
                self.repository,
                self.dataset,
                ledger,
                manifest,
                settings,
                {"adapter": "safe-reference"},
                lambda seed: SafeReferenceAgent(),
            )
            with self.assertRaisesRegex(ValueError, "agent"):
                run_protocol(
                    self.repository,
                    self.dataset,
                    ledger,
                    manifest,
                    settings,
                    {"adapter": "different-agent"},
                    lambda seed: SafeReferenceAgent(),
                    resume=True,
                )

    def test_boundary_ledger_records_full_and_singleton_trials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "boundary.jsonl"
            settings = ExperimentSettings(
                protocol="boundary", repetitions=1, max_mask_size=1, scenario_id=self.base.id
            )
            run_protocol(
                self.repository,
                self.dataset,
                ledger,
                Path(directory) / "boundary.manifest.json",
                settings,
                {"adapter": "safe-reference"},
                lambda seed: SafeReferenceAgent(),
            )
            rows = read_jsonl(ledger)
            masks = {tuple(row["condition"]["mask"]) for row in rows}
            self.assertIn((), masks)
            critical = [atom for atom in self.base.evidence if atom.role == "critical"]
            self.assertEqual(len(rows), 1 + len(critical))
            self.assertTrue(
                all(
                    not row["condition"]["mask"]
                    or row["scenario"]["mask_roles"] == {"critical": len(row["condition"]["mask"])}
                    for row in rows
                )
            )
            report = summarize(rows)
            self.assertEqual(report["boundary"]["eligible_scenarios"], 1)
            self.assertEqual(report["boundary"]["right_censored"], 1)

    def test_paper_protocol_combines_recovery_and_critical_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "paper.jsonl"
            settings = ExperimentSettings(
                protocol="paper", repetitions=1, max_mask_size=2, scenario_id=self.base.id
            )
            run_protocol(
                self.repository,
                self.dataset,
                ledger,
                Path(directory) / "paper.manifest.json",
                settings,
                {"adapter": "safe-reference"},
                lambda seed: SafeReferenceAgent(),
            )
            rows = read_jsonl(ledger)
            critical = [atom for atom in self.base.evidence if atom.role == "critical"]
            irrelevant = [atom for atom in self.base.evidence if atom.role == "irrelevant"]
            # The unified protocol reuses singleton/full and exhausts ALL
            # critical subsets, independently of the legacy max_mask_size.
            expected_recovery = 4 * (1 + len(critical) + len(irrelevant))
            expected_boundary = 2 ** len(critical) - 1 - len(critical)
            trials = [r for r in rows if r["record_type"] == "trial"]
            tasks = [r for r in rows if r["record_type"] == "task_completed"]
            self.assertEqual(len(trials), expected_recovery + expected_boundary)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["boundary"]["sbm"], 1)
            self.assertEqual({row["protocol"] for row in trials}, {"boundary-recovery"})


if __name__ == "__main__":
    unittest.main()
