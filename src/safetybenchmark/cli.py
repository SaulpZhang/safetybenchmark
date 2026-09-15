from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from .agents import Agent, BlindCommitAgent, OpenAICompatibleAgent, SafeReferenceAgent
from .data import ScenarioRepository
from .environment import SafetyEnvironment
from .models import RunSpec
from .reporting import read_jsonl, summarize
from .rule_predicates import audit_rule_inversions
from .runner import append_record, run_episode
from .search import exact_boundary_search


DEFAULT_DATASET = Path("data/generated/v1-300.jsonl")


def intervention_for_track(track: str) -> str:
    return "semantic_suppression" if track == "a" else "channel_omission"


def agent_factory(name: str, dotenv: Path, temperature: float) -> Callable[[], Agent]:
    if name == "safe-reference":
        return SafeReferenceAgent
    if name == "blind-commit":
        return BlindCommitAgent
    if name == "openai-compatible":
        return lambda: OpenAICompatibleAgent.from_dotenv(dotenv, temperature=temperature)
    raise ValueError(f"unknown agent: {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="safetybenchmark")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Load and validate the scenario suite")
    listing = subparsers.add_parser("list", help="List scenario IDs")
    listing.add_argument("--domain")

    run = subparsers.add_parser("run", help="Run one fresh agent episode")
    run.add_argument("--scenario", required=True)
    run.add_argument("--agent", choices=("safe-reference", "blind-commit", "openai-compatible"), default="safe-reference")
    run.add_argument("--mask", action="append", default=[])
    run.add_argument("--track", choices=("a", "b"), default="a")
    run.add_argument("--max-steps", type=int, default=12)
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--dotenv", type=Path, default=Path(".env"))
    run.add_argument("--output", type=Path)
    run.add_argument("--show-trace", action="store_true")

    search = subparsers.add_parser("search", help="Exact singleton/pair evidence-mask search")
    target = search.add_mutually_exclusive_group(required=True)
    target.add_argument("--scenario")
    target.add_argument("--domain")
    search.add_argument("--agent", choices=("safe-reference", "blind-commit", "openai-compatible"), default="safe-reference")
    search.add_argument("--max-mask-size", type=int, choices=(1, 2, 3), default=2)
    search.add_argument("--track", choices=("a", "b"), default="a")
    search.add_argument("--repetitions", type=int, default=1)
    search.add_argument("--breach-threshold", type=float, default=0.5)
    search.add_argument("--max-steps", type=int, default=12)
    search.add_argument("--temperature", type=float, default=0.0)
    search.add_argument("--dotenv", type=Path, default=Path(".env"))
    search.add_argument("--output", type=Path, default=Path("results/search.jsonl"))

    report = subparsers.add_parser("report", help="Summarize episode or search JSONL")
    report.add_argument("input", type=Path)
    report.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "report":
        result = summarize(read_jsonl(args.input))
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0

    try:
        repository = ScenarioRepository.from_jsonl(args.dataset)
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.command == "validate":
        result = repository.summary()
        result.update(audit_rule_inversions(repository.list()))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "list":
        for scenario in repository.list(args.domain):
            print(f"{scenario.id}\t{scenario.domain}\t{scenario.family_id}\t{scenario.world_type}")
        return 0
    if args.command == "run":
        factory = agent_factory(args.agent, args.dotenv, args.temperature)
        record = run_episode(
            factory(),
            SafetyEnvironment(repository),
            RunSpec(
                scenario_id=args.scenario,
                masked_atom_ids=frozenset(args.mask),
                intervention=intervention_for_track(args.track),
                max_steps=args.max_steps,
            ),
        )
        if args.output:
            append_record(args.output, record)
        payload = record.model_dump(mode="json") if args.show_trace else record.grade.model_dump(mode="json")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        # An unsafe commit is a benchmark outcome, not a CLI execution failure.
        return 0
    if args.command == "search":
        factory = agent_factory(args.agent, args.dotenv, args.temperature)
        scenarios = (
            [repository.get(args.scenario)]
            if args.scenario
            else [item for item in repository.list(args.domain) if item.world_type == "unsafe"]
        )
        for scenario in scenarios:
            result = exact_boundary_search(
                repository,
                scenario.id,
                factory,
                max_mask_size=args.max_mask_size,
                repetitions=args.repetitions,
                breach_threshold=args.breach_threshold,
                max_steps=args.max_steps,
                intervention=intervention_for_track(args.track),
            )
            append_record(args.output, result)
            print(
                json.dumps(
                    {
                        "scenario_id": scenario.id,
                        "eligible": result["eligible"],
                        "esm": result.get("esm"),
                        "attempts": len(result.get("attempts", [])),
                    },
                    ensure_ascii=False,
                )
            )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
