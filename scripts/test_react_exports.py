"""Regression checks for ReAct aggregate/export diagnostics."""
import csv
from pathlib import Path
import tempfile
import unittest

from rescore_pilot import (
    flatten_audited_result,
    write_audit_csv,
)
from run_reactive_pilot import (
    flatten_result,
    summarize,
    write_csv,
)


def evaluation():
    return {
        "episode_success": False,
        "episode_success_v02": True,
        "feasible_process_success": False,
        "feasible_obligation_success": True,
        "terminal_outcome": {"correct": True},
        "economic_objective": {"satisfied": True},
        "hard_constraints": {"passed": 1, "total": 1},
        "required_checkpoints": {
            "completed": 0,
            "total": 0,
            "results": [],
        },
        "obligations": {
            "actionable": 1,
            "resolved": 1,
            "unresolved": 0,
            "no_opportunity": 0,
            "not_applicable": 0,
            "resolution_rate": 1.0,
            "results": [],
        },
        "constraint_violations": [],
        "efficiency": {"accepted_actions": 2},
    }


def result(audit_status=None):
    row = {
        "run_id": "react-run",
        "episode_id": "episode-one",
        "status": "completed",
        "trajectory": [],
        "evaluation": evaluation(),
        "policy_metrics": {
            "model_calls_attempted": 2,
            "total_tokens": 200,
            "latency_ms": 20.0,
            "cost_usd": 0.02,
            "usage_incomplete": False,
            "agent_pattern": "react_v0.1",
            "react_steps_proposed": 2,
            "react_steps_accepted": 2,
            "react_thought_chars_total": 120,
            "react_thought_chars_mean": 60.0,
            "react_thought_chars_max": 75,
        },
        "error": None,
        "evaluation_error": None,
    }
    if audit_status is not None:
        row["audit_status"] = audit_status
        row["audit_error"] = (
            {"type": "ValueError", "message": "forced"}
            if audit_status != "success"
            else None
        )
        row["source_status"] = "completed"
    return row


class ReActExportTests(unittest.TestCase):
    def test_flatten_result_preserves_react_diagnostics(self):
        row = flatten_result(result(), "m", 1)
        self.assertEqual(row["agent_pattern"], "react_v0.1")
        self.assertEqual(row["react_steps_proposed"], 2)
        self.assertEqual(row["react_steps_accepted"], 2)
        self.assertEqual(row["react_thought_chars_total"], 120)
        self.assertEqual(row["react_thought_chars_mean"], 60.0)
        self.assertEqual(row["react_thought_chars_max"], 75)

    def test_summary_aggregates_react_diagnostics(self):
        first = flatten_result(result(), "m", 1)
        second_result = result()
        second_result["policy_metrics"].update({
            "react_steps_proposed": 3,
            "react_steps_accepted": 3,
            "react_thought_chars_total": 150,
            "react_thought_chars_mean": 50.0,
            "react_thought_chars_max": 80,
        })
        second = flatten_result(second_result, "m", 2)

        summary = summarize([first, second])["by_model"]["m"]
        self.assertEqual(summary["total_react_steps_proposed"], 5)
        self.assertEqual(summary["total_react_steps_accepted"], 5)
        self.assertEqual(summary["runs_with_react_steps"], 2)
        self.assertEqual(summary["total_react_thought_chars"], 270)
        self.assertEqual(summary["mean_react_thought_chars"], 54.0)
        self.assertEqual(summary["max_react_thought_chars"], 80)

    def test_failed_audit_preserves_react_diagnostics(self):
        failed = result(audit_status="evaluation_error")
        failed["evaluation"] = None
        failed["evaluation_error"] = {
            "type": "ValueError",
            "message": "forced",
        }
        row = flatten_audited_result(
            failed,
            model="m",
            repeat=1,
        )
        self.assertEqual(row["agent_pattern"], "react_v0.1")
        self.assertEqual(row["react_steps_proposed"], 2)
        self.assertEqual(row["react_steps_accepted"], 2)
        self.assertEqual(row["react_thought_chars_total"], 120)
        self.assertEqual(row["react_thought_chars_mean"], 60.0)
        self.assertEqual(row["react_thought_chars_max"], 75)

    def test_csv_writers_accept_react_columns(self):
        flat = flatten_result(result(), "m", 1)
        audited = flatten_audited_result(
            result(audit_status="success"),
            model="m",
            repeat=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pilot_path = root / "pilot.csv"
            audit_path = root / "audit.csv"
            write_csv([flat], pilot_path)
            write_audit_csv([audited], audit_path)

            for path in (pilot_path, audit_path):
                with path.open(newline="", encoding="utf-8") as handle:
                    header = next(csv.reader(handle))
                for field in (
                    "agent_pattern",
                    "react_steps_proposed",
                    "react_steps_accepted",
                    "react_thought_chars_total",
                    "react_thought_chars_mean",
                    "react_thought_chars_max",
                ):
                    with self.subTest(path=path.name, field=field):
                        self.assertIn(field, header)


if __name__ == "__main__":
    unittest.main()
