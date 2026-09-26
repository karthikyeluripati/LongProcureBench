"""Tests for repeated reactive baseline pilot harness."""
import json
from pathlib import Path
import tempfile
import unittest

from run_reactive_pilot import (
    DEVELOPMENT_EPISODES,
    flatten_result,
    model_slug,
    resolve_sampling_options,
    run_pilot,
    summarize,
    validate_episode_id,
)
from validate_live_pilot_statuses import invalid_rows


class StubPolicy:
    policy_kind = "stub"
    def __init__(self, model):
        self.model = model
        self.policy_id = f"stub--{model}"


class StubRunner:
    def __init__(self):
        self.calls = []
    def run(self, policy, episode_id, *, max_actions, run_id, result_path):
        self.calls.append((policy.model, episode_id, run_id, result_path))
        repeat = int(result_path.stem.split("-")[-1])
        success = repeat % 2 == 1
        result = {
            "run_id": run_id,
            "episode_id": episode_id,
            "status": "completed",
            "trajectory": [{"step": 1}],
            "evaluation": {
                "episode_id": episode_id,
                "episode_success": success,
                "episode_success_v02": success,
                "feasible_process_success": success,
                "feasible_obligation_success": success,
                "terminal_outcome": {"correct": success},
                "economic_objective": {"satisfied": success},
                "hard_constraints": {"passed": 4 if success else 3, "total": 4},
                "required_checkpoints": {"completed": 3 if success else 2, "total": 3, "results": [{"checkpoint": "evaluate_quotes", "complete": success}]},
                "obligations": {
                    "actionable": 2,
                    "resolved": 2 if success else 1,
                    "unresolved": 0 if success else 1,
                    "no_opportunity": 0,
                    "not_applicable": 1,
                    "resolution_rate": 1.0 if success else 0.5,
                    "results": [] if success else [{
                        "checkpoint": "follow_up_nonresponse",
                        "status": "unresolved",
                    }],
                },
                "constraint_violations": [] if success else ["c2"],
                "efficiency": {"accepted_actions": 1},
                "terminated": True,
            },
            "policy_metrics": {"model_calls_attempted": 1, "total_tokens": 110, "latency_ms": 20.0, "cost_usd": 0.01, "usage_incomplete": False},
            "error": None,
        }
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result), encoding="utf-8")
        return result


class PilotTests(unittest.TestCase):
    def test_pilot_writes_unique_replicates_and_aggregates(self):
        runner = StubRunner()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rows, summary = run_pilot(["provider/a", "provider/b"], ["episode-one"], 3, out, runner=runner, policy_factory=StubPolicy)
            self.assertEqual(len(rows), 6)
            self.assertEqual(summary["runs"], 6)
            self.assertTrue((out / "summary.json").is_file())
            self.assertTrue((out / "runs.csv").is_file())
            for model in ["provider/a", "provider/b"]:
                d = out / model_slug(model) / "episode-one"
                self.assertTrue((d / "run-001.json").is_file())
                self.assertTrue((d / "run-002.json").is_file())
                self.assertTrue((d / "run-003.json").is_file())

    def test_summary_preserves_failure_counts(self):
        rows = [
            {"model":"m","episode_success":True,"feasible_process_success":True,"terminal_feasible":True,"economic_objective_satisfied":True,"status":"completed","constraint_violations":[],"incomplete_checkpoints":[],"accepted_actions":5,"total_tokens":100,"latency_ms":20.0,"cost_usd":0.01,"usage_incomplete":False},
            {"model":"m","episode_success":False,"feasible_process_success":False,"terminal_feasible":False,"economic_objective_satisfied":False,"status":"completed","constraint_violations":["c2"],"incomplete_checkpoints":["evaluate_quotes"],"accepted_actions":7,"total_tokens":200,"latency_ms":40.0,"cost_usd":0.02,"usage_incomplete":False},
        ]
        s = summarize(rows)["by_model"]["m"]
        self.assertEqual(s["episode_success_rate"], 0.5)
        self.assertEqual(s["terminal_feasible_rate"], 0.5)
        self.assertEqual(s["feasible_process_success_rate"], 0.5)
        self.assertEqual(s["economic_objective_rate"], 0.5)
        self.assertEqual(s["constraint_failure_counts"], {"c2": 1})
        self.assertEqual(s["checkpoint_failure_counts"], {"evaluate_quotes": 1})
        self.assertEqual(s["mean_accepted_actions"], 6.0)
        self.assertEqual(s["mean_total_tokens"], 150.0)


    def test_summary_includes_v02_obligation_metrics(self):
        rows = [
            {
                "model": "m",
                "episode_success": False,
                "episode_success_v02": True,
                "feasible_process_success": False,
                "feasible_obligation_success": True,
                "terminal_feasible": True,
                "economic_objective_satisfied": True,
                "status": "completed",
                "constraint_violations": [],
                "incomplete_checkpoints": [],
                "obligations_actionable": 3,
                "obligations_resolved": 2,
                "obligations_unresolved": 1,
                "unresolved_obligations": ["handle_amendment"],
                "accepted_actions": 6,
                "total_tokens": 120,
                "latency_ms": 25.0,
                "cost_usd": 0.02,
                "usage_incomplete": False,
            }
        ]
        s = summarize(rows)["by_model"]["m"]
        self.assertEqual(s["episode_success_rate_v02"], 1.0)
        self.assertEqual(s["feasible_obligation_success_rate"], 1.0)
        self.assertEqual(s["actionable_obligations"], 3)
        self.assertEqual(s["resolved_obligations"], 2)
        self.assertEqual(s["unresolved_obligations"], 1)
        self.assertEqual(
            s["unresolved_obligation_counts"],
            {"handle_amendment": 1},
        )

    def test_summary_aggregates_optional_ledger_metrics(self):
        rows = [
            {
                "model": "m",
                "episode_success": False,
                "episode_success_v02": False,
                "feasible_process_success": False,
                "feasible_obligation_success": False,
                "terminal_feasible": True,
                "economic_objective_satisfied": False,
                "status": "completed",
                "constraint_violations": [],
                "incomplete_checkpoints": [],
                "obligations_actionable": 1,
                "obligations_resolved": 0,
                "obligations_unresolved": 1,
                "unresolved_obligations": ["follow_up_nonresponse"],
                "accepted_actions": 5,
                "total_tokens": 100,
                "latency_ms": 20.0,
                "cost_usd": 0.01,
                "usage_incomplete": False,
                "ledger_items_created": 4,
                "ledger_max_open_items": 2,
            },
            {
                "model": "m",
                "episode_success": True,
                "episode_success_v02": True,
                "feasible_process_success": True,
                "feasible_obligation_success": True,
                "terminal_feasible": True,
                "economic_objective_satisfied": True,
                "status": "completed",
                "constraint_violations": [],
                "incomplete_checkpoints": [],
                "obligations_actionable": 2,
                "obligations_resolved": 2,
                "obligations_unresolved": 0,
                "unresolved_obligations": [],
                "accepted_actions": 6,
                "total_tokens": 120,
                "latency_ms": 25.0,
                "cost_usd": 0.02,
                "usage_incomplete": False,
                "ledger_items_created": 6,
                "ledger_max_open_items": 4,
            },
        ]
        summary = summarize(rows)["by_model"]["m"]
        self.assertEqual(summary["mean_ledger_items_created"], 5.0)
        self.assertEqual(summary["mean_ledger_max_open_items"], 3.0)

    def test_development_suite_has_twenty_frozen_episodes(self):
        self.assertEqual(len(DEVELOPMENT_EPISODES), 20)
        self.assertEqual(len(set(DEVELOPMENT_EPISODES)), 20)
        self.assertTrue(
            all(episode.endswith(f"-{n:03d}") for n, episode in enumerate(
                DEVELOPMENT_EPISODES, start=1
            ))
        )

    def test_live_status_validator_allows_agent_rejection(self):
        rows = [{
            "status": "policy_error",
            "error_type": "ValidationError",
            "evaluation_error_type": "",
        }]
        self.assertEqual(invalid_rows(rows), [])

    def test_live_status_validator_allows_ledger_protocol_failure(self):
        rows = [{
            "status": "policy_error",
            "error_type": "OperationalLedgerError",
            "evaluation_error_type": "",
        }]
        self.assertEqual(invalid_rows(rows), [])

    def test_live_status_validator_allows_working_plan_failure(self):
        rows = [{
            "status": "policy_error",
            "error_type": "WorkingPlanError",
            "evaluation_error_type": "",
        }]
        self.assertEqual(invalid_rows(rows), [])

    def test_live_status_validator_rejects_model_failure(self):
        rows = [{
            "status": "policy_error",
            "error_type": "ModelCallError",
            "evaluation_error_type": "",
        }]
        self.assertEqual(invalid_rows(rows), rows)

    def test_live_status_validator_rejects_environment_failure(self):
        rows = [{
            "status": "environment_error",
            "error_type": "RuntimeError",
            "evaluation_error_type": "",
        }]
        self.assertEqual(invalid_rows(rows), rows)

    def test_live_status_validator_rejects_masked_evaluation_failure(self):
        rows = [{
            "status": "policy_error",
            "error_type": "ValidationError",
            "evaluation_error_type": "EvaluationError",
        }]
        self.assertEqual(invalid_rows(rows), rows)

    def test_flatten_result_preserves_optional_ledger_metrics(self):
        result = {
            "run_id": "r1",
            "episode_id": "episode-one",
            "status": "completed",
            "trajectory": [],
            "evaluation": {
                "episode_success": False,
                "episode_success_v02": False,
                "feasible_process_success": False,
                "feasible_obligation_success": False,
                "terminal_outcome": {"correct": True},
                "economic_objective": {"satisfied": False},
                "hard_constraints": {"passed": 1, "total": 1},
                "required_checkpoints": {
                    "completed": 0,
                    "total": 0,
                    "results": [],
                },
                "obligations": {
                    "actionable": 0,
                    "resolved": 0,
                    "unresolved": 0,
                    "no_opportunity": 0,
                    "not_applicable": 0,
                    "resolution_rate": None,
                    "results": [],
                },
                "constraint_violations": [],
                "efficiency": {"accepted_actions": 0},
            },
            "policy_metrics": {
                "model_calls_attempted": 2,
                "total_tokens": 200,
                "latency_ms": 30.0,
                "cost_usd": 0.02,
                "usage_incomplete": False,
                "state_strategy": "operational_ledger_v0.1",
                "ledger_open_items": 2,
                "ledger_resolved_items": 3,
                "ledger_items_created": 5,
                "ledger_max_open_items": 4,
            },
            "error": None,
            "evaluation_error": None,
        }
        row = flatten_result(result, "m", 1)
        self.assertEqual(
            row["state_strategy"],
            "operational_ledger_v0.1",
        )
        self.assertEqual(row["ledger_open_items"], 2)
        self.assertEqual(row["ledger_resolved_items"], 3)
        self.assertEqual(row["ledger_items_created"], 5)
        self.assertEqual(row["ledger_max_open_items"], 4)

    def test_flatten_result_preserves_optional_plan_metrics(self):
        result = {
            "run_id": "r1",
            "episode_id": "episode-one",
            "status": "completed",
            "trajectory": [],
            "evaluation": {
                "episode_success": False,
                "episode_success_v02": False,
                "feasible_process_success": False,
                "feasible_obligation_success": False,
                "terminal_outcome": {"correct": True},
                "economic_objective": {"satisfied": False},
                "hard_constraints": {"passed": 1, "total": 1},
                "required_checkpoints": {
                    "completed": 0,
                    "total": 0,
                    "results": [],
                },
                "obligations": {
                    "actionable": 0,
                    "resolved": 0,
                    "unresolved": 0,
                    "no_opportunity": 0,
                    "not_applicable": 0,
                    "resolution_rate": None,
                    "results": [],
                },
                "constraint_violations": [],
                "efficiency": {"accepted_actions": 0},
            },
            "policy_metrics": {
                "model_calls_attempted": 2,
                "total_tokens": 200,
                "latency_ms": 30.0,
                "cost_usd": 0.02,
                "usage_incomplete": False,
                "state_strategy": "maintained_working_plan_v0.1",
                "plan_updates": 3,
                "plan_rejections": 1,
                "mean_plan_steps": 1.5,
                "max_plan_steps": 4,
            },
            "error": None,
            "evaluation_error": None,
        }
        row = flatten_result(result, "m", 1)
        self.assertEqual(row["plan_updates"], 3)
        self.assertEqual(row["plan_rejections"], 1)
        self.assertEqual(row["mean_plan_steps"], 1.5)
        self.assertEqual(row["max_plan_steps"], 4)

    def test_summary_aggregates_optional_plan_metrics(self):
        rows = [
            {
                "model": "m",
                "episode_success": False,
                "episode_success_v02": False,
                "feasible_process_success": False,
                "feasible_obligation_success": False,
                "terminal_feasible": True,
                "economic_objective_satisfied": False,
                "status": "completed",
                "constraint_violations": [],
                "incomplete_checkpoints": [],
                "obligations_actionable": 0,
                "obligations_resolved": 0,
                "obligations_unresolved": 0,
                "unresolved_obligations": [],
                "accepted_actions": 5,
                "total_tokens": 100,
                "latency_ms": 20.0,
                "cost_usd": 0.01,
                "usage_incomplete": False,
                "plan_updates": 4,
                "plan_rejections": 1,
                "mean_plan_steps": 1.5,
                "max_plan_steps": 3,
            },
            {
                "model": "m",
                "episode_success": True,
                "episode_success_v02": True,
                "feasible_process_success": True,
                "feasible_obligation_success": True,
                "terminal_feasible": True,
                "economic_objective_satisfied": True,
                "status": "completed",
                "constraint_violations": [],
                "incomplete_checkpoints": [],
                "obligations_actionable": 0,
                "obligations_resolved": 0,
                "obligations_unresolved": 0,
                "unresolved_obligations": [],
                "accepted_actions": 6,
                "total_tokens": 120,
                "latency_ms": 25.0,
                "cost_usd": 0.02,
                "usage_incomplete": False,
                "plan_updates": 6,
                "plan_rejections": 0,
                "mean_plan_steps": 2.5,
                "max_plan_steps": 4,
            },
        ]
        summary = summarize(rows)["by_model"]["m"]
        self.assertEqual(summary["total_plan_updates"], 10)
        self.assertEqual(summary["mean_plan_updates"], 5.0)
        self.assertEqual(summary["total_plan_rejections"], 1)
        self.assertEqual(summary["runs_with_plan_rejections"], 1)
        self.assertEqual(summary["mean_plan_steps"], 2.0)
        self.assertEqual(summary["max_plan_steps"], 4)

    def test_live_status_validator_rejects_working_plan_error(self):
        rows = [{
            "status": "policy_error",
            "error_type": "WorkingPlanError",
            "evaluation_error_type": "",
        }]
        self.assertEqual(invalid_rows(rows), rows)

    def test_pilot_supports_matched_policy_run_identity(self):
        runner = StubRunner()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rows, summary = run_pilot(
                ["provider/a"],
                ["episode-one"],
                1,
                out,
                runner=runner,
                policy_factory=StubPolicy,
                run_prefix="context-compiled-reactive-v0.1",
                baseline_name="context-compiled-reactive-v0.1",
            )
            self.assertEqual(len(rows), 1)
            self.assertTrue(
                rows[0]["run_id"].startswith(
                    "context-compiled-reactive-v0.1--"
                )
            )
            self.assertEqual(
                summary["baseline"],
                "context-compiled-reactive-v0.1",
            )

    def test_repeated_invocation_refuses_nonempty_output_dir(self):
        runner = StubRunner()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pilot"
            run_pilot(
                ["provider/a"],
                ["episode-one"],
                1,
                out,
                runner=runner,
                policy_factory=StubPolicy,
            )
            with self.assertRaisesRegex(
                FileExistsError,
                "output directory is not empty",
            ):
                run_pilot(
                    ["provider/a"],
                    ["episode-one"],
                    1,
                    out,
                    runner=runner,
                    policy_factory=StubPolicy,
                )

    def test_summary_keeps_known_cost_when_some_costs_are_missing(self):
        rows = [
            {"model":"m","episode_success":True,"feasible_process_success":True,"terminal_feasible":True,"economic_objective_satisfied":True,"status":"completed","constraint_violations":[],"incomplete_checkpoints":[],"accepted_actions":5,"total_tokens":100,"latency_ms":20.0,"cost_usd":0.01,"usage_incomplete":False},
            {"model":"m","episode_success":False,"feasible_process_success":False,"terminal_feasible":False,"economic_objective_satisfied":False,"status":"completed","constraint_violations":[],"incomplete_checkpoints":[],"accepted_actions":6,"total_tokens":120,"latency_ms":25.0,"cost_usd":None,"usage_incomplete":False},
        ]
        s = summarize(rows)["by_model"]["m"]
        self.assertAlmostEqual(s["total_known_cost_usd"], 0.01)
        self.assertEqual(s["runs_with_unknown_cost_usd"], 1)

    def test_episode_id_rejects_path_traversal(self):
        for bad in ("../outside", "a/b", "UPPER", "a_b"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_episode_id(bad)

    def test_invalid_episode_is_rejected_before_runner_or_filesystem_use(self):
        runner = StubRunner()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pilot"
            with self.assertRaises(ValueError):
                run_pilot(
                    ["provider/a"],
                    ["../outside"],
                    1,
                    out,
                    runner=runner,
                    policy_factory=StubPolicy,
                )
            self.assertEqual(runner.calls, [])
            self.assertFalse(out.exists())


    def test_pilot_reasoning_effort_omits_temperature(self):
        self.assertIsNone(
            resolve_sampling_options(None, False, "medium")
        )

    def test_pilot_rejects_explicit_temperature_with_reasoning(self):
        with self.assertRaises(ValueError):
            resolve_sampling_options(0.0, False, "medium")

if __name__ == "__main__":
    unittest.main()
