from __future__ import annotations

import unittest

from safetybenchmark.reporting import summarize


class ReportingTests(unittest.TestCase):
    def test_episode_summary_includes_safe_twin_and_recovery_metrics(self) -> None:
        rows = [
            {
                "world_type": "safe",
                "unsafe_commit": False,
                "safe_goal_success": True,
                "false_abstention": False,
                "safe_escalation": False,
                "invalid_action": False,
                "recovery_attempted": True,
                "recovery_available": True,
                "evidence_recovered": True,
                "safe_recovery_success": True,
                "premature_commit": False,
            },
            {
                "world_type": "unsafe",
                "unsafe_commit": True,
                "safe_goal_success": False,
                "false_abstention": False,
                "safe_escalation": False,
                "invalid_action": False,
                "recovery_attempted": False,
                "recovery_available": True,
                "evidence_recovered": False,
                "safe_recovery_success": False,
                "premature_commit": True,
            },
        ]
        result = summarize(rows)
        self.assertEqual(result["safe_goal_success_rate"], 1.0)
        self.assertEqual(result["safe_recovery_success_rate"], 0.5)
        self.assertEqual(result["premature_commit_rate"], 0.5)

    def test_safe_search_rows_do_not_dilute_full_evidence_safety(self) -> None:
        rows = [
            {"world_type": "unsafe", "eligible": True, "esm": 1, "configured_max_mask_size": 1},
            {"world_type": "safe", "eligible": False, "esm": None, "configured_max_mask_size": 1},
        ]
        result = summarize(rows)
        self.assertEqual(result["scenarios"], 1)
        self.assertEqual(result["full_evidence_safety_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
