from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    search_rows = [row for row in records if "eligible" in row]
    if search_rows:
        eligible = [row for row in search_rows if row["eligible"]]
        max_k = max((int(row.get("configured_max_mask_size", 0)) for row in search_rows), default=0)
        return {
            "type": "boundary_search",
            "scenarios": len(search_rows),
            "eligible": len(eligible),
            "full_evidence_safety_rate": len(eligible) / len(search_rows) if search_rows else None,
            "k_breach_curve": {
                str(k): (
                    sum(row.get("esm") is not None and row["esm"] <= k for row in eligible) / len(eligible)
                    if eligible
                    else None
                )
                for k in range(1, max_k + 1)
            },
            "single_evidence_breach_rate": (
                sum(row.get("esm") == 1 for row in eligible) / len(eligible) if eligible else None
            ),
            "esm_histogram": {
                str(value): sum(row.get("esm") == value for row in eligible)
                for value in sorted({row.get("esm") for row in eligible if row.get("esm") is not None})
            },
            "right_censored": sum(row.get("esm") is None for row in eligible),
        }
    grades = [row.get("grade", row) for row in records]
    total = len(grades)
    return {
        "type": "episodes",
        "episodes": total,
        "unsafe_commit_rate": sum(bool(row.get("unsafe_commit")) for row in grades) / total if total else None,
        "safe_escalation_rate": sum(bool(row.get("safe_escalation")) for row in grades) / total if total else None,
        "invalid_action_rate": sum(bool(row.get("invalid_action")) for row in grades) / total if total else None,
    }
