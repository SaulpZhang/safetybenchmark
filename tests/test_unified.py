from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from safetybenchmark.data import ScenarioRepository
from safetybenchmark.experiments import ExperimentSettings, run_protocol
from safetybenchmark.models import FinalResponse, ToolCall
from safetybenchmark.reporting import read_jsonl
from safetybenchmark.unified_reporting import aggregate_tasks, summarize_unified


class UnifiedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = Path("data/generated/v1-300.jsonl")
        cls.repository = ScenarioRepository.from_jsonl(cls.dataset)

    def run_case(self, directory, limit=2, resume=False, workers=4):
        return run_protocol(self.repository, self.dataset, Path(directory) / "run.jsonl",
                            Path(directory) / "manifest.json",
                            ExperimentSettings(protocol="boundary-recovery", repetitions=1, limit=limit,
                                               workers=workers),
                            {"adapter": "test"}, lambda seed: object(), resume=resume,
                            wandb_project="test")

    def fake_episode(self, agent, environment, spec, recorder=None):
        scenario = self.repository.get(spec.scenario_id)
        # Fail on the FIRST pair in search order. All singleton cells complete.
        unsafe = (scenario.world_type == "unsafe" and spec.intervention == "semantic_suppression"
                  and len(spec.masked_atom_ids) >= 2)
        grade = {"unsafe_commit": unsafe, "safe_goal_success": scenario.world_type == "safe",
                 "false_abstention": False, "invalid_action": False,
                 "recovery_attempted": spec.intervention == "channel_omission",
                 "evidence_recovered": bool(spec.masked_atom_ids) and spec.intervention == "channel_omission",
                 "safe_recovery_success": bool(spec.masked_atom_ids) and spec.intervention == "channel_omission",
                 "premature_commit": False, "event_count": 1,
                 "disposition": "abstained" if scenario.world_type == "unsafe" else "completed"}
        environment.reset(spec)
        environment.step(FinalResponse(text="test", disposition="abstained"))
        if recorder:
            recorder({"type": "test_step"})
        return SimpleNamespace(grade=SimpleNamespace(model_dump=lambda **kw: grade),
                               model_dump=lambda **kw: {"grade": grade})

    def sink(self):
        self.logged = []
        class FakeSink:
            def __init__(inner, *args, **kw): pass
            def log_task(inner, task, aggregate):
                self.logged.append((task["task_index"], aggregate["completed_tasks"]))
            def log_task_error(inner, task, completed_task_count):
                self.logged.append((task["task_index"], completed_task_count))
            def finish(inner): pass
            def log_final_metrics(inner, metrics): pass
        return FakeSink

    def test_task_order_early_stop_pairing_raw_records_and_resume(self):
        with tempfile.TemporaryDirectory() as d, patch("safetybenchmark.experiments.WandbSink", self.sink()), \
             patch("safetybenchmark.unified.run_episode", side_effect=self.fake_episode), \
             contextlib.redirect_stdout(io.StringIO()):
            self.run_case(d)
            rows = read_jsonl(Path(d) / "run.jsonl")
            trials = [r for r in rows if r["record_type"] == "trial"]
            tasks = [r for r in rows if r["record_type"] == "task_completed"]
            self.assertEqual(self.logged, [(1, 1), (2, 2)])
            self.assertEqual([r["task_index"] for r in trials], sorted(r["task_index"] for r in trials))
            first_complete = next(i for i, r in enumerate(rows) if r["record_type"] == "task_completed")
            self.assertFalse(any(r.get("task_index") == 2 for r in rows[:first_complete]))
            for task in tasks:
                own = [r for r in trials if r["task_index"] == task["task_index"]]
                base = self.repository.get(task["pair_id"])
                count = sum(a.role in {"critical", "irrelevant"} for a in base.evidence)
                self.assertEqual(len(own), 4 * (1 + count) + 4)
                self.assertEqual(len({r["trial_key"] for r in own}), len(own))
                self.assertEqual(sum(r["phase"] == "boundary_search" for r in own), 1)
                self.assertEqual(sum(r["phase"] == "boundary_recovery" for r in own), 3)
                self.assertEqual(task["boundary"]["m"], 2)
                self.assertEqual(task["metrics"]["recovery/boundary/paired_useful_recovery"]["value"], 1)
                for r in own:
                    self.assertTrue((Path(d) / r["journal_path"]).exists())
                    self.assertTrue((Path(d) / r["trace_path"]).exists())
            report = summarize_unified(rows, draws=20)
            self.assertEqual(report["completed_tasks"], 2)
            self.assertEqual(report["metrics"]["boundary/sbm"]["tasks"], 2)
            # Offline computation must ignore cached score values.
            tasks[0]["boundary"]["sbm"] = 999
            tasks[0]["metrics"]["boundary/sbm"]["value"] = 999
            fresh = summarize_unified(rows, draws=0)
            self.assertLessEqual(fresh["metrics"]["boundary/sbm"]["estimate"], 1)
            before = (Path(d) / "run.jsonl").read_bytes()
            result = self.run_case(d, resume=True)
            self.assertEqual(result["executed_trials"], 0)
            self.assertEqual((Path(d) / "run.jsonl").read_bytes(), before)

    def test_pairs_overlap_on_workers_but_publish_in_source_task_order(self):
        """A blocked first pair must not stop another worker from beginning pair two."""
        first_base, second_base = [s for s in self.repository.list() if s.world_type == "unsafe"][:2]
        first_started, second_started = threading.Event(), threading.Event()
        once = threading.Event()
        original = self.fake_episode

        def episode(agent, environment, spec, recorder=None):
            if spec.scenario_id == first_base.id and not once.is_set():
                once.set()
                first_started.set()
                self.assertTrue(second_started.wait(timeout=5), "second worker never started")
            elif spec.scenario_id == second_base.id:
                second_started.set()
            return original(agent, environment, spec, recorder)

        with tempfile.TemporaryDirectory() as d, patch("safetybenchmark.experiments.WandbSink", self.sink()), \
             patch("safetybenchmark.unified.run_episode", side_effect=episode), \
             contextlib.redirect_stdout(io.StringIO()):
            self.run_case(d, workers=2)
        self.assertTrue(first_started.is_set())
        self.assertTrue(second_started.is_set())
        # The coordinator intentionally restores a monotonic public task axis.
        self.assertEqual(self.logged, [(1, 1), (2, 2)])

    def test_error_stops_current_task_and_preserves_retry_attempt(self):
        with tempfile.TemporaryDirectory() as d, patch("safetybenchmark.experiments.WandbSink", self.sink()), \
             contextlib.redirect_stdout(io.StringIO()):
            calls = 0
            def episode(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise ValueError("injected provider failure")
                return self.fake_episode(*args, **kwargs)
            with patch("safetybenchmark.unified.run_episode", side_effect=episode):
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    self.run_case(d)
            rows = read_jsonl(Path(d) / "run.jsonl")
            error = next(r for r in rows if r.get("status") == "error")
            error_index = error["task_index"]
            completed_indices = [r["task_index"] for r in rows if r.get("record_type") == "task_completed"]
            # A parallel worker may have completed an earlier pair, but the
            # coordinator never publishes a task after the failed prefix.
            self.assertEqual(completed_indices, list(range(1, error_index)))
            self.assertTrue(all(r["task_index"] <= error_index for r in rows if "task_index" in r))
            old_trace = (Path(d) / error["trace_path"]).read_bytes()
            with patch("safetybenchmark.unified.run_episode", side_effect=self.fake_episode):
                self.run_case(d, resume=True)
            self.assertEqual((Path(d) / error["trace_path"]).read_bytes(), old_trace)
            attempts = [r for r in read_jsonl(Path(d) / "run.jsonl")
                        if r["record_type"] == "trial" and r["trial_key"] == error["trial_key"]]
            self.assertEqual([r["status"] for r in attempts], ["error", "completed"])
            self.assertNotEqual(attempts[0]["attempt_id"], attempts[1]["attempt_id"])
            # Depending on whether worker one finished before the injected
            # failure reached the coordinator, resume may replay its completed
            # prefix into the new W&B run. The repaired public suffix is fixed.
            self.assertEqual(self.logged[-2:], [(1, 1), (2, 2)])

    def test_full_and_singleton_failures_still_finish_singleton_panel(self):
        original = self.fake_episode
        for failure_size in (0, 1):
            with self.subTest(size=failure_size), tempfile.TemporaryDirectory() as d, \
                 patch("safetybenchmark.experiments.WandbSink", self.sink()), \
                 contextlib.redirect_stdout(io.StringIO()):
                def episode(agent, env, spec, recorder=None):
                    output = original(agent, env, spec, recorder)
                    grade = output.grade.model_dump()
                    grade["unsafe_commit"] = (self.repository.get(spec.scenario_id).world_type == "unsafe"
                                               and spec.intervention == "semantic_suppression"
                                               and len(spec.masked_atom_ids) == failure_size)
                    return output
                with patch("safetybenchmark.unified.run_episode", side_effect=episode):
                    self.run_case(d, limit=1)
                rows = read_jsonl(Path(d) / "run.jsonl")
                task = next(r for r in rows if r["record_type"] == "task_completed")
                trials = [r for r in rows if r["record_type"] == "trial"]
                base = self.repository.get(task["pair_id"])
                count = sum(a.role in {"critical", "irrelevant"} for a in base.evidence)
                self.assertEqual(len(trials), 4 * (1 + count))
                self.assertEqual(task["boundary"]["m"], failure_size)

    def test_no_boundary_exhausts_beyond_legacy_k_two(self):
        original = self.repository
        base = next(s for s in original.list() if s.world_type == "unsafe"
                    and sum(a.role == "critical" for a in s.evidence) == 3)
        self.repository = ScenarioRepository([base, original.get(base.paired_scenario_id)])
        try:
            with tempfile.TemporaryDirectory() as d, patch("safetybenchmark.experiments.WandbSink", self.sink()), \
                 contextlib.redirect_stdout(io.StringIO()):
                def episode(agent, env, spec, recorder=None):
                    out = self.fake_episode(agent, env, spec, recorder)
                    out.grade.model_dump()["unsafe_commit"] = False
                    return out
                with patch("safetybenchmark.unified.run_episode", side_effect=episode):
                    self.run_case(d, limit=1)
                rows = read_jsonl(Path(d) / "run.jsonl")
                task = next(r for r in rows if r["record_type"] == "task_completed")
                search = [r for r in rows if r["record_type"] == "trial" and r["phase"] == "boundary_search"]
                self.assertEqual(sorted(r["mask_size"] for r in search), [2, 2, 2, 3])
                self.assertEqual(task["boundary"]["sbm"], 1)
        finally:
            self.repository = original

    def test_task_weights_and_missing_denominators(self):
        tasks = [{"family_id": f, "metrics": {"metric": {"value": v, "denominator": n}}}
                 for f, v, n in [("a", 1., 100), ("a", 1., 1), ("b", 0., 1), ("b", None, 0)]]
        metric = aggregate_tasks(tasks, draws=50)["metrics"]["metric"]
        self.assertAlmostEqual(metric["estimate"], 2 / 3)
        self.assertEqual(metric["tasks"], 3)
        self.assertEqual(metric["families"], 2)

    def test_wandb_task_axis_and_one_log_per_task(self):
        from safetybenchmark.experiments import WandbSink
        from unittest.mock import MagicMock
        fake = MagicMock()
        with patch.dict("sys.modules", {"wandb": fake}):
            sink = WandbSink("p", None, "r", {"settings": {"protocol": "boundary-recovery"}})
            sink.log_task({"task_index": 2, "metrics": {"m": {"value": .5}}},
                          {"metrics": {"m": {"estimate": .7, "tasks": 2}}})
        run = fake.init.return_value
        run.define_metric.assert_any_call("cumulative/*", step_metric="task_index")
        run.define_metric.assert_any_call("completed_task_count")
        run.log.assert_called_once()
        self.assertEqual(run.log.call_args.args[0]["task_index"], 2)
        self.assertEqual(run.log.call_args.args[0]["completed_task_count"], 2)
        self.assertEqual(run.log.call_args.args[0]["cumulative/m"], .7)

    def test_adapter_records_full_request_response_and_failed_request_count(self):
        from openai.types.chat import ChatCompletion
        from safetybenchmark.agents import OpenAICompatibleAgent
        from safetybenchmark.environment import SafetyEnvironment
        from safetybenchmark.models import AgentContext, RunSpec
        from unittest.mock import MagicMock
        agent = OpenAICompatibleAgent.__new__(OpenAICompatibleAgent)
        agent.model, agent.temperature, agent.seed = "fixture", 0., None
        agent._usage = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0, requests=0)
        records = []
        agent.set_recorder(records.append)
        response = ChatCompletion.model_validate({
            "id": "fixture-response", "created": 1, "model": "fixture", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "needs approval"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}})
        agent.client = MagicMock()
        agent.client.chat.completions.create.side_effect = [response, RuntimeError("provider down")]
        session = SafetyEnvironment(self.repository).reset(RunSpec(scenario_id=self.repository.list()[0].id))
        context = AgentContext(session=session, history=[], step_index=0)
        agent.next_event(context)
        with self.assertRaisesRegex(RuntimeError, "provider down"):
            agent.next_event(context)
        self.assertEqual([r["type"] for r in records], ["model_request", "model_response", "model_request"])
        self.assertIn("messages", records[0]["request"])
        self.assertIn("tools", records[0]["request"])
        self.assertEqual(records[1]["response"]["usage"]["total_tokens"], 13)
        self.assertEqual(agent.run_metrics()["requests"], 2)
        self.assertEqual(agent.run_metrics()["total_tokens"], 13)

    def test_adapter_retries_visible_provider_errors_and_marks_token_limit(self):
        from openai.types.chat import ChatCompletion
        from safetybenchmark.agents import GenerationTruncatedError, OpenAICompatibleAgent
        from safetybenchmark.environment import SafetyEnvironment
        from safetybenchmark.models import AgentContext, RunSpec
        from unittest.mock import MagicMock

        agent = OpenAICompatibleAgent.__new__(OpenAICompatibleAgent)
        agent.model, agent.temperature, agent.seed = "fixture", 0., None
        agent.max_completion_tokens, agent.request_retries, agent.retry_backoff_seconds = 65_536, 3, 5.
        agent._usage = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0, requests=0,
                            request_errors=0, generation_truncations=0)
        records = []
        agent.set_recorder(records.append)
        response = ChatCompletion.model_validate({
            "id": "fixture-response", "created": 1, "model": "fixture", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": "long"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 65_536, "total_tokens": 65_546}})
        agent.client = MagicMock()
        agent.client.chat.completions.create.side_effect = [RuntimeError("temporary"), response]
        session = SafetyEnvironment(self.repository).reset(RunSpec(scenario_id=self.repository.list()[0].id))
        context = AgentContext(session=session, history=[], step_index=0)
        with patch("safetybenchmark.agents.RETRYABLE_PROVIDER_ERRORS", (RuntimeError,)), \
             patch("safetybenchmark.agents.time.sleep") as sleep, \
             self.assertRaises(GenerationTruncatedError):
            agent.next_event(context)
        self.assertEqual(sleep.call_args.args[0], 5.)
        self.assertEqual([r["type"] for r in records], [
            "model_request", "model_error", "model_request", "model_response", "generation_truncated",
        ])
        self.assertEqual(records[0]["request"]["max_tokens"], 65_536)
        self.assertEqual(agent.run_metrics()["requests"], 2)
        self.assertEqual(agent.run_metrics()["request_errors"], 1)
        self.assertEqual(agent.run_metrics()["generation_truncations"], 1)

    def test_infrastructure_error_does_not_stop_later_tasks(self):
        from safetybenchmark.agents import ProviderRequestError

        with tempfile.TemporaryDirectory() as d, patch("safetybenchmark.experiments.WandbSink", self.sink()), \
             contextlib.redirect_stdout(io.StringIO()):
            calls = 0

            def episode(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise ProviderRequestError(RuntimeError("timeout"), 4)
                return self.fake_episode(*args, **kwargs)

            with patch("safetybenchmark.unified.run_episode", side_effect=episode):
                result = self.run_case(d, limit=2, workers=1)
            rows = read_jsonl(Path(d) / "run.jsonl")
            failures = [row for row in rows if row["record_type"] == "task_error"]
            completed = [row for row in rows if row["record_type"] == "task_completed"]
            self.assertEqual(result["failed_tasks"], 1)
            self.assertEqual(failures[0]["error_category"], "infrastructure")
            self.assertEqual([row["task_index"] for row in completed], [2])


if __name__ == "__main__":
    unittest.main()
