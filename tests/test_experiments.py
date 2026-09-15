from __future__ import annotations

import tempfile
import unittest
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
            self.assertEqual(len(rows), 1 + len(self.base.evidence))
            report = summarize(rows)
            self.assertEqual(report["boundary"]["eligible_scenarios"], 1)
            self.assertEqual(report["boundary"]["right_censored"], 1)


if __name__ == "__main__":
    unittest.main()
