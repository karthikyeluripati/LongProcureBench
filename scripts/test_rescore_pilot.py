"""Regression tests for saved-pilot trajectory rescoring."""
import json
from pathlib import Path
import tempfile
import unittest

from rescore_pilot import (
    accepted_actions,
    failure_taxonomy,
    rescore_directory,
    rescore_result,
)


class StubEvaluator:
    def evaluate_actions(self, episode_id, actions):
        return {
            "episode_id": episode_id,
            "episode_success": False,
            "feasible_process_success": True,
            "terminal_outcome": {
                "correct": True,
                "matched_outcome_id": "o2",
            },
            "economic_objective": {
                "satisfied": False,
                "kind": "minimize_total_price",
            },
            "hard_constraints": {
                "passed": 4,
                "total": 4,
                "all_passed": True,
                "results": [],
            },
            "required_checkpoints": {
                "completed": 2,
                "total": 2,
                "all_completed": True,
                "results": [],
            },
            "constraint_violations": [],
            "efficiency": {"accepted_actions": len(actions)},
            "terminated": True,
        }


def raw_result():
    return {
        "run_id": "raw-run",
        "episode_id": "electrical-bongabon-generator-001",
        "status": "completed",
        "trajectory": [
            {
                "step": 1,
                "action": {
                    "action_id": "a1",
                    "episode_id": "electrical-bongabon-generator-001",
                    "type": "identify_suppliers",
                    "supplier_id": None,
                    "arguments": {},
                },
                "observations": [],
            }
        ],
        "evaluation": {"episode_success": True, "legacy": True},
        "evaluation_error": {"type": "OldError", "message": "old"},
        "policy": {
            "policy_id": "reactive-llm--fake/model",
            "policy_kind": "llm_reactive_baseline",
        },
        "policy_metrics": {
            "model": "fake/model",
            "model_calls_attempted": 1,
            "total_tokens": 100,
            "latency_ms": 12.0,
            "cost_usd": 0.01,
            "usage_incomplete": False,
        },
        "error": None,
    }


class RescoreTests(unittest.TestCase):
    def test_rescore_replaces_evaluation_only(self):
        original = raw_result()
        rescored = rescore_result(original, StubEvaluator())
        self.assertEqual(
            rescored["evaluation"]["economic_objective"]["satisfied"],
            False,
        )
        self.assertIsNone(rescored["evaluation_error"])
        self.assertEqual(rescored["trajectory"], original["trajectory"])
        self.assertEqual(
            rescored["policy_metrics"],
            original["policy_metrics"],
        )
        self.assertEqual(
            original["evaluation"],
            {"episode_success": True, "legacy": True},
        )

    def test_accepted_actions_come_only_from_saved_trajectory(self):
        actions = accepted_actions(raw_result())
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "identify_suppliers")

    def test_directory_rescore_preserves_raw_and_writes_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            run = raw / "fake-model" / "episode" / "run-001.json"
            run.parent.mkdir(parents=True)
            run.write_text(json.dumps(raw_result()), encoding="utf-8")

            output = root / "audit"
            rows, summary, taxonomy = rescore_directory(
                raw,
                output,
                evaluator=StubEvaluator(),
            )
            self.assertEqual(len(rows), 1)
            self.assertTrue(run.is_file())
            self.assertTrue(
                (
                    output
                    / "rescored"
                    / "fake-model"
                    / "episode"
                    / "run-001.json"
                ).is_file()
            )
            self.assertTrue((output / "runs.csv").is_file())
            self.assertTrue((output / "summary.json").is_file())
            self.assertTrue((output / "failure-taxonomy.json").is_file())
            self.assertEqual(summary["runs"], 1)
            self.assertEqual(
                taxonomy[
                    "feasible_process_but_economically_suboptimal_runs"
                ],
                1,
            )

    def test_taxonomy_separates_failure_layers(self):
        base = {
            "constraint_violations": [],
            "incomplete_checkpoints": [],
        }
        rows = [
            {
                **base,
                "terminal_feasible": False,
                "feasible_process_success": False,
                "economic_objective_satisfied": False,
                "episode_success": False,
            },
            {
                **base,
                "terminal_feasible": True,
                "feasible_process_success": False,
                "economic_objective_satisfied": True,
                "episode_success": False,
                "incomplete_checkpoints": ["follow_up_nonresponse"],
            },
            {
                **base,
                "terminal_feasible": True,
                "feasible_process_success": True,
                "economic_objective_satisfied": False,
                "episode_success": False,
            },
            {
                **base,
                "terminal_feasible": True,
                "feasible_process_success": True,
                "economic_objective_satisfied": True,
                "episode_success": True,
            },
        ]
        taxonomy = failure_taxonomy(rows)
        self.assertEqual(taxonomy["terminal_infeasible_runs"], 1)
        self.assertEqual(
            taxonomy["feasible_but_process_incomplete_runs"], 1
        )
        self.assertEqual(
            taxonomy[
                "feasible_process_but_economically_suboptimal_runs"
            ],
            1,
        )
        self.assertEqual(taxonomy["strict_success_runs"], 1)


if __name__ == "__main__":
    unittest.main()
