"""Tests for the coverage + repair diagnostic policy."""
from copy import deepcopy
import unittest

from longprocurebench import LongProcureBenchEnv
from longprocurebench.coverage_repair_context import (
    CoverageRepairContextPolicy,
)


class SequenceActionClient:
    model = "fake/test-model"

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def generate_action(self, *, messages, action_schema):
        self.calls.append({
            "messages": deepcopy(messages),
            "action_schema": deepcopy(action_schema),
        })
        if not self.decisions:
            raise AssertionError("Unexpected model call")
        decision = self.decisions.pop(0)
        return deepcopy(decision), {
            "model": self.model,
            "latency_ms": 1.0,
            "prompt_tokens": 50,
            "completion_tokens": 5,
            "total_tokens": 55,
            "cost_usd": 0.001,
        }


def _model_action(action_type, supplier_id=None):
    return {
        "type": action_type,
        "supplier_id": supplier_id,
        "arguments": {"awards": None, "reason": None},
    }


def _env_action(episode_id, number, decision):
    return {
        "action_id": f"a{number}",
        "episode_id": episode_id,
        "type": decision["type"],
        "supplier_id": decision.get("supplier_id"),
        "arguments": deepcopy(decision.get("arguments") or {}),
    }


class CoverageRepairPolicyTests(unittest.TestCase):
    def test_finishes_supplier_coverage_and_nonresponse_without_extra_model_calls(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-columbus-switchgear-021")
        episode_id = state["episode_id"]

        state = env.step(_env_action(
            episode_id,
            1,
            _model_action("request_buyer_clarification"),
        ))
        state = env.step(_env_action(
            episode_id,
            2,
            _model_action("identify_suppliers"),
        ))

        client = SequenceActionClient([
            _model_action("send_rfq", "syn-columbus-a"),
            _model_action("evaluate_quotes"),
        ])
        policy = CoverageRepairContextPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        first = policy.act(state)
        self.assertEqual(first["type"], "send_rfq")
        self.assertEqual(first["supplier_id"], "syn-columbus-a")
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 3, first))

        second = policy.act(state)
        self.assertEqual(second, {
            "type": "send_rfq",
            "supplier_id": "syn-columbus-b",
            "arguments": {},
        })
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 4, second))

        third = policy.act(state)
        self.assertEqual(third, {
            "type": "send_rfq",
            "supplier_id": "syn-columbus-c",
            "arguments": {},
        })
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 5, third))

        fourth = policy.act(state)
        self.assertEqual(fourth, {
            "type": "send_follow_up",
            "supplier_id": "syn-columbus-c",
            "arguments": {},
        })
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 6, fourth))

        fifth = policy.act(state)
        self.assertEqual(fifth["type"], "evaluate_quotes")
        self.assertEqual(len(client.calls), 2)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["coverage_repair_interventions"], 3)
        self.assertEqual(metrics["coverage_forced_rfqs"], 2)
        self.assertEqual(metrics["coverage_forced_followups"], 1)
        self.assertEqual(metrics["coverage_forced_answers"], 0)
        self.assertEqual(metrics["coverage_forced_amendments"], 0)
        self.assertEqual(metrics["model_calls"], 2)

    def test_supplier_question_repair_precedes_remaining_coverage(self):
        state = {
            "visible_suppliers": [
                {"supplier_id": "syn-a"},
                {"supplier_id": "syn-b"},
            ],
            "action_history": [
                {
                    "type": "identify_suppliers",
                    "supplier_id": None,
                    "arguments": {},
                },
                {
                    "type": "send_rfq",
                    "supplier_id": "syn-a",
                    "arguments": {},
                },
            ],
            "revealed_events": [
                {
                    "event_id": "e1",
                    "type": "supplier_question",
                    "supplier_id": "syn-a",
                    "trigger": {
                        "kind": "after_action",
                        "action_type": "send_rfq",
                        "supplier_id": "syn-a",
                        "step": None,
                    },
                },
            ],
        }

        forced = CoverageRepairContextPolicy._forced_action(
            CoverageRepairContextPolicy.__new__(
                CoverageRepairContextPolicy
            ),
            state,
        )
        self.assertEqual(forced, {
            "type": "answer_supplier_question",
            "supplier_id": "syn-a",
            "arguments": {},
        })

    def test_requirement_change_is_amended_once_then_coverage_resumes(self):
        state = {
            "visible_suppliers": [
                {"supplier_id": "syn-a"},
                {"supplier_id": "syn-b"},
            ],
            "action_history": [
                {
                    "type": "send_rfq",
                    "supplier_id": "syn-a",
                    "arguments": {},
                },
            ],
            "revealed_events": [
                {
                    "event_id": "e-change",
                    "type": "requirement_change",
                    "supplier_id": None,
                    "trigger": {
                        "kind": "at_step",
                        "action_type": None,
                        "supplier_id": None,
                        "step": 1,
                    },
                },
            ],
        }

        policy = CoverageRepairContextPolicy.__new__(
            CoverageRepairContextPolicy
        )
        forced = policy._forced_action(state)
        self.assertEqual(forced, {
            "type": "issue_amendment",
            "supplier_id": None,
            "arguments": {},
        })

        state["action_history"].append({
            "type": "issue_amendment",
            "supplier_id": None,
            "arguments": {},
        })
        forced = policy._forced_action(state)
        self.assertEqual(forced, {
            "type": "send_rfq",
            "supplier_id": "syn-b",
            "arguments": {},
        })

    def test_controller_does_not_start_sourcing_on_its_own(self):
        state = {
            "visible_suppliers": [
                {"supplier_id": "syn-a"},
                {"supplier_id": "syn-b"},
            ],
            "action_history": [
                {
                    "type": "identify_suppliers",
                    "supplier_id": None,
                    "arguments": {},
                },
            ],
            "revealed_events": [],
        }
        policy = CoverageRepairContextPolicy.__new__(
            CoverageRepairContextPolicy
        )
        self.assertIsNone(policy._forced_action(state))


if __name__ == "__main__":
    unittest.main()
