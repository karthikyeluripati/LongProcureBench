"""Regression tests for Benchmark Runner v0.1."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import ValidationError

from longprocurebench import BenchmarkRunner, ScriptedReferencePolicy
from run_reference import run_all_reference


class BadPolicy:
    policy_id = "bad-policy"
    policy_kind = "test"
    def reset(self, state):
        pass
    def act(self, state):
        raise RuntimeError("policy exploded")


class LoopPolicy:
    policy_id = "loop-policy"
    policy_kind = "test"
    def reset(self, state):
        pass
    def act(self, state):
        return {"type": "identify_suppliers", "supplier_id": None, "arguments": {}}


class MalformedPolicy:
    policy_id = "malformed-policy"
    policy_kind = "test"
    def reset(self, state):
        pass
    def act(self, state):
        return {"action_id": "policy-owned-id", "type": "identify_suppliers"}



class BogusActionPolicy:
    policy_id = "bogus-action-policy"
    policy_kind = "test"
    def reset(self, state):
        pass
    def act(self, state):
        return {"type": "bogus", "supplier_id": None, "arguments": {}}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = BenchmarkRunner()

    def test_reference_control_passes_all_five_episodes(self):
        for episode_id in ScriptedReferencePolicy.episode_ids():
            with self.subTest(episode_id=episode_id):
                result = self.runner.run(ScriptedReferencePolicy(), episode_id)
                self.assertEqual(result["status"], "completed")
                self.assertTrue(result["evaluation"]["episode_success"])
                self.assertTrue(result["evaluation"]["terminated"])
                self.assertGreater(len(result["trajectory"]), 0)

    def test_runner_owns_action_ids(self):
        result = self.runner.run(ScriptedReferencePolicy(), "electrical-bongabon-generator-001")
        ids = [row["action"]["action_id"] for row in result["trajectory"]]
        self.assertEqual(ids, [f"a{i}" for i in range(1, len(ids) + 1)])

    def test_policy_cannot_inject_action_or_episode_ids(self):
        result = self.runner.run(MalformedPolicy(), "electrical-bongabon-generator-001")
        self.assertEqual(result["status"], "policy_error")
        self.assertEqual(result["trajectory"], [])
        self.assertIn("runner owns episode_id/action_id", result["error"]["message"])

    def test_policy_error_is_captured(self):
        result = self.runner.run(BadPolicy(), "electrical-bongabon-generator-001")
        self.assertEqual(result["status"], "policy_error")
        self.assertFalse(result["evaluation"]["episode_success"])
        self.assertEqual(result["error"]["type"], "RuntimeError")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertFalse(result["attempts"][0]["accepted"])

    def test_max_actions_stops_nonterminating_policy(self):
        result = self.runner.run(LoopPolicy(), "electrical-bongabon-generator-001", max_actions=2)
        self.assertEqual(result["status"], "max_actions")
        self.assertEqual(len(result["trajectory"]), 2)
        self.assertEqual(result["evaluation"]["efficiency"]["accepted_actions"], 2)
        self.assertFalse(result["evaluation"]["episode_success"])

    def test_saved_result_is_stable_json_and_schema_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "result.json"
            result = self.runner.run(
                ScriptedReferencePolicy(),
                "electrical-bongabon-generator-001",
                run_id="test-run-001",
                result_path=path,
            )
            self.assertTrue(path.is_file())
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, result)
            self.assertEqual(loaded["schema_version"], "0.1.0")
            self.assertEqual(loaded["policy"]["policy_kind"], "reference_control")

    def test_result_contains_attempts_trajectory_and_evaluation(self):
        result = self.runner.run(ScriptedReferencePolicy(), "electrical-national-museum-lighting-002")
        self.assertEqual(len(result["attempts"]), len(result["trajectory"]))
        self.assertTrue(all(x["accepted"] for x in result["attempts"]))
        self.assertEqual(result["evaluation"]["episode_id"], result["episode_id"])


    def test_unsupported_policy_action_is_policy_error(self):
        result = self.runner.run(
            BogusActionPolicy(),
            "electrical-bongabon-generator-001",
        )
        self.assertEqual(result["status"], "policy_error")
        self.assertEqual(result["trajectory"], [])
        self.assertEqual(result["attempts"][0]["accepted"], False)
        self.assertEqual(result["error"]["type"], "ValidationError")
        self.assertIsNotNone(result["evaluation"])

    def test_unknown_episode_returns_setup_error_result(self):
        result = self.runner.run(
            LoopPolicy(),
            "does-not-exist",
        )
        self.assertEqual(result["status"], "setup_error")
        self.assertIsNone(result["evaluation"])
        self.assertEqual(result["trajectory"], [])
        self.assertEqual(result["error"]["type"], "EnvironmentError")

    def test_evaluation_failure_returns_result_instead_of_raising(self):
        with patch(
            "longprocurebench.runner.LongProcureBenchEvaluator.evaluate_actions",
            side_effect=ValueError("Missing evaluation config"),
        ):
            result = self.runner.run(
                LoopPolicy(),
                "electrical-bongabon-generator-001",
                max_actions=1,
            )
        self.assertEqual(result["status"], "max_actions")
        self.assertIsNone(result["evaluation"])
        self.assertIsNone(result["error"])
        self.assertEqual(
            result["evaluation_error"]["type"], "ValueError"
        )
        self.assertEqual(len(result["trajectory"]), 1)


    def test_invalid_episode_identifier_still_returns_failure_record(self):
        result = self.runner.run(
            LoopPolicy(),
            "INVALID_episode",
        )
        self.assertEqual(result["status"], "setup_error")
        self.assertEqual(result["episode_id"], "INVALID_episode")
        self.assertIsNone(result["evaluation"])
        self.assertIsNone(result["evaluation_error"])
        self.assertEqual(result["error"]["type"], "EnvironmentError")

    def test_evaluation_failure_does_not_hide_policy_failure(self):
        with patch(
            "longprocurebench.runner.LongProcureBenchEvaluator.evaluate_actions",
            side_effect=ValueError("Missing evaluation config"),
        ):
            result = self.runner.run(
                BadPolicy(),
                "electrical-bongabon-generator-001",
            )
        self.assertEqual(result["status"], "policy_error")
        self.assertEqual(result["error"]["type"], "RuntimeError")
        self.assertEqual(
            result["evaluation_error"]["type"], "ValueError"
        )
        self.assertIsNone(result["evaluation"])

    def test_reference_batch_continues_when_one_evaluation_is_missing(self):
        episode_ids = ScriptedReferencePolicy.episode_ids()
        class StubRunner:
            def __init__(self):
                self.calls = []
            def run(self, policy, episode_id, result_path=None):
                self.calls.append(episode_id)
                if len(self.calls) == 1:
                    return {
                        "status": "evaluation_error",
                        "evaluation": None,
                        "trajectory": [{"step": 1}],
                    }
                return {
                    "status": "completed",
                    "evaluation": {
                        "episode_success": True,
                        "efficiency": {"accepted_actions": 3},
                    },
                    "trajectory": [],
                }

        stub = StubRunner()
        with tempfile.TemporaryDirectory() as tmp:
            failures = run_all_reference(Path(tmp), runner=stub)
        self.assertEqual(stub.calls, episode_ids)
        self.assertEqual(failures, 1)


if __name__ == "__main__":
    unittest.main()
