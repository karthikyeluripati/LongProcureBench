"""Tests for repeated reactive baseline pilot harness."""
import json
from pathlib import Path
import tempfile
import unittest

from run_reactive_pilot import model_slug, run_pilot, summarize


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
                "terminal_outcome": {"correct": success},
                "hard_constraints": {"passed": 4 if success else 3, "total": 4},
                "required_checkpoints": {"completed": 3 if success else 2, "total": 3, "results": [{"checkpoint": "evaluate_quotes", "complete": success}]},
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
            {"model":"m","episode_success":True,"terminal_correct":True,"status":"completed","constraint_violations":[],"incomplete_checkpoints":[],"accepted_actions":5,"total_tokens":100,"latency_ms":20.0,"cost_usd":0.01,"usage_incomplete":False},
            {"model":"m","episode_success":False,"terminal_correct":False,"status":"completed","constraint_violations":["c2"],"incomplete_checkpoints":["evaluate_quotes"],"accepted_actions":7,"total_tokens":200,"latency_ms":40.0,"cost_usd":0.02,"usage_incomplete":False},
        ]
        s = summarize(rows)["by_model"]["m"]
        self.assertEqual(s["episode_success_rate"], 0.5)
        self.assertEqual(s["constraint_failure_counts"], {"c2": 1})
        self.assertEqual(s["checkpoint_failure_counts"], {"evaluate_quotes": 1})
        self.assertEqual(s["mean_accepted_actions"], 6.0)
        self.assertEqual(s["mean_total_tokens"], 150.0)


if __name__ == "__main__":
    unittest.main()
