#!/usr/bin/env python3
"""Audit generated benchmark scenarios against the project data contract."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from generate_scenarios import validate_scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="JSONL scenarios to audit.")
    parser.add_argument("--prompt-dir", type=Path, default=Path("prompts/domains"))
    parser.add_argument("--expected-per-domain", type=int, default=50)
    parser.add_argument("--expected-per-family", type=int, default=5)
    parser.add_argument(
        "--allow-family-imbalance",
        action="store_true",
        help="Report but do not fail on family counts that differ from --expected-per-family.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            parse_errors.append({"line": line_number, "error": str(error)})
            continue
        if not isinstance(item, dict):
            parse_errors.append({"line": line_number, "error": "row is not a JSON object"})
            continue
        rows.append(item)
    return rows, parse_errors


def taxonomy(prompt_dir: Path) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    pattern = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \| `([^`]+)`", re.MULTILINE)
    for prompt in prompt_dir.glob("*.md"):
        for family_id, risk_type, rule_id in pattern.findall(prompt.read_text(encoding="utf-8")):
            entries[family_id] = (risk_type, rule_id)
    return entries


def value_is_materialized(world_state: Any, value: Any) -> bool:
    """Return whether an evidence value appears as a state value or subtree.

    This intentionally is a conservative, syntactic check.  A false result can
    still be semantically derivable (for example, an ``active_dependents`` list
    implies that a named dependent is active), so callers should treat it as a
    review warning rather than proof of a bad scenario.
    """
    if world_state == value:
        return True
    if isinstance(world_state, dict):
        return any(value_is_materialized(child, value) for child in world_state.values())
    if isinstance(world_state, list):
        return any(value_is_materialized(child, value) for child in world_state)
    return False


def main() -> int:
    args = parse_args()
    rows, parse_errors = read_rows(args.dataset)
    seen_ids: set[str] = set()
    schema_errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        try:
            base_row = dict(row)
            base_row.pop("safe_twin", None)
            validate_scenario(base_row, row.get("domain", ""), seen_ids)
            seen_ids.add(row["id"])
        except Exception as error:
            schema_errors.append({"line": index, "id": row.get("id"), "error": str(error)})

    expected_taxonomy = taxonomy(args.prompt_dir)
    taxonomy_errors = [
        {
            "id": row.get("id"),
            "family_id": row.get("family_id"),
            "risk_type": row.get("risk_type"),
            "rule_id": row.get("safety_rule", {}).get("id"),
        }
        for row in rows
        if expected_taxonomy.get(row.get("family_id"))
        != (row.get("risk_type"), row.get("safety_rule", {}).get("id"))
    ]
    unknown_families = sorted({row.get("family_id") for row in rows} - set(expected_taxonomy))

    domain_counts = Counter(row.get("domain") for row in rows)
    family_counts = Counter(row.get("family_id") for row in rows)
    family_deviations = {
        family: count
        for family, count in sorted(family_counts.items())
        if count != args.expected_per_family
    }
    domain_deviations = {
        domain: count
        for domain, count in sorted(domain_counts.items())
        if count != args.expected_per_domain
    }
    evidence_counts = Counter(len(row.get("evidence", [])) for row in rows)
    role_counts = Counter(
        atom.get("role")
        for row in rows
        for atom in row.get("evidence", [])
        if isinstance(atom, dict)
    )
    tool_counts = Counter(len(row.get("tools", [])) for row in rows)
    explicit_non_commit = sum(
        any(
            token in row.get("expected_behavior", "")
            for token in ("不调用", "不执行", "不得调用", "不得执行", "不要执行", "不可调用", "禁止执行", "不能执行")
        )
        for row in rows
    )
    witness_role_errors: list[dict[str, Any]] = []
    value_materialization_warnings: list[dict[str, Any]] = []
    unsafe_if_stats = Counter()
    for row in rows:
        evidence_by_id = {atom.get("id"): atom for atom in row.get("evidence", [])}
        for witness_set in row.get("safety_rule", {}).get("minimal_witness_sets", []):
            control_atoms = [
                evidence_id
                for evidence_id in witness_set
                if evidence_by_id.get(evidence_id, {}).get("role") in {"contextual", "irrelevant"}
            ]
            if control_atoms:
                witness_role_errors.append(
                    {"id": row.get("id"), "witness": witness_set, "control_atoms": control_atoms}
                )
        for atom in row.get("evidence", []):
            if not value_is_materialized(row.get("world_state"), atom.get("value")):
                value_materialization_warnings.append(
                    {"id": row.get("id"), "evidence_id": atom.get("id"), "value": atom.get("value")}
                )
        unsafe_if = row.get("safety_rule", {}).get("unsafe_if", "")
        unsafe_if_stats["uses_world_state"] += "world_state" in unsafe_if
        unsafe_if_stats["contains_chinese"] += bool(re.search(r"[\u4e00-\u9fff]", unsafe_if))
        unsafe_if_stats["contains_commit_arguments"] += "commit_arguments" in unsafe_if

    report = {
        "dataset": str(args.dataset),
        "rows": len(rows),
        "parse_errors": parse_errors,
        "unique_ids": len({row.get("id") for row in rows}),
        "schema_errors": schema_errors,
        "taxonomy_errors": taxonomy_errors,
        "unknown_families": unknown_families,
        "domain_counts": dict(sorted(domain_counts.items())),
        "domain_deviations": domain_deviations,
        "family_count_range": [min(family_counts.values()), max(family_counts.values())] if family_counts else None,
        "family_deviations": family_deviations,
        "evidence_atoms_per_task": dict(sorted(evidence_counts.items())),
        "evidence_role_counts": dict(sorted(role_counts.items())),
        "tools_per_task": dict(sorted(tool_counts.items())),
        "expected_behavior_explicit_non_commit": explicit_non_commit,
        "witness_role_errors": witness_role_errors,
        "evidence_value_materialization_warnings": value_materialization_warnings,
        "unsafe_if_format_stats": dict(sorted(unsafe_if_stats.items())),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if not (
        parse_errors
        or schema_errors
        or taxonomy_errors
        or domain_deviations
        or (family_deviations and not args.allow_family_imbalance)
        or witness_role_errors
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
