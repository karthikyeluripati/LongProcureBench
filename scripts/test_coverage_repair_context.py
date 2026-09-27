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
        state = env.reset("electrical-bongabon-generator-001")
        episode_id = state["episode_id"]

        state = env.step(_env_action(
            episode_id,
            1,
            _model_action("identify_suppliers"),
        ))

        client = SequenceActionClient([
            _model_action("send_rfq", "syn-gen-a"),
            _model_action("evaluate_quotes"),
        ])
        policy = CoverageRepairContextPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        first = policy.act(state)
        self.assertEqual(first["type"], "send_rfq")
        self.assertEqual(first["supplier_id"], "syn-gen-a")
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 2, first))

        second = policy.act(state)
        self.assertEqual(second, {
            "type": "send_rfq",
            "supplier_id": "syn-gen-b",
            "arguments": {},
        })
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 3, second))

        third = policy.act(state)
        self.assertEqual(third, {
            "type": "send_rfq",
            "supplier_id": "syn-gen-c",
            "arguments": {},
        })
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 4, third))

        fourth = policy.act(state)
        self.assertEqual(fourth, {
            "type": "send_follow_up",
            "supplier_id": "syn-gen-c",
            "arguments": {},
        })
        self.assertEqual(len(client.calls), 1)
        state = env.step(_env_action(episode_id, 5, fourth))

        fifth = policy.act(state)
        self.assertEqual(fifth["type"], "evaluate_quotes")
        self.assertEqual(len(client.calls), 2)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["coverage_repair_interventions"], 3)
        self.assertEqual(metrics["coverage_forced_rfqs"], 2)
        self.assertEqual(metrics["coverage_forced_followups"], 1)
        self.assertEqual(metrics["coverage_forced_answers"], 0)
        self.assertEqual(metrics["model_calls"], 2)

    def test_supplier_question_repair_is_once_and_precedes_coverage(self):
        policy = CoverageRepairContextPolicy(
            "fake/test-model",
            client=SequenceActionClient([]),
        )
        compiled = {
            "visible_suppliers": [
                {"supplier_id": "syn-a"},
                {"supplier_id": "syn-b"},
            ],
            "action_history": [
                {
                    "sequence": 1,
                    "type": "identify_suppliers",
                    "supplier_id": None,
                    "arguments": {},
                },
                {
                    "sequence": 2,
                    "type": "send_rfq",
                    "supplier_id": "syn-a",
                    "arguments": {},
                },
            ],
            "event_history": [
                {
                    "event_id": "e1",
                    "type": "supplier_question",
                    "supplier_id": "syn-a",
                    "observation": "Supplier asks a visible requirement question.",
                    "details": {},
                },
            ],
        }

        event_id, repair = policy._unresolved_visible_repair(compiled)
        self.assertEqual(event_id, "e1")
        self.assertEqual(repair, {
            "type": "answer_supplier_question",
            "supplier_id": "syn-a",
            "arguments": {},
        })

        policy._handled_repair_event_ids.add("e1")
        self.assertIsNone(policy._unresolved_visible_repair(compiled))
        self.assertEqual(
            policy._uncovered_supplier_action(compiled),
            {
                "type": "send_rfq",
                "supplier_id": "syn-b",
                "arguments": {},
            },
        )

    def test_controller_does_not_start_sourcing_on_its_own(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bongabon-generator-001")
        episode_id = state["episode_id"]
        state = env.step(_env_action(
            episode_id,
            1,
            _model_action("identify_suppliers"),
        ))

        client = SequenceActionClient([
            _model_action("evaluate_quotes"),
        ])
        policy = CoverageRepairContextPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        decision = policy.act(state)
        self.assertEqual(decision["type"], "evaluate_quotes")
        self.assertEqual(len(client.calls), 1)
        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["coverage_repair_interventions"], 0)

    def test_controller_receives_only_compiled_event_fields(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bongabon-generator-001")
        episode_id = state["episode_id"]
        state = env.step(_env_action(
            episode_id,
            1,
            _model_action("identify_suppliers"),
        ))
        state = env.step(_env_action(
            episode_id,
            2,
            _model_action("send_rfq", "syn-gen-c"),
        ))

        client = SequenceActionClient([])
        policy = CoverageRepairContextPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        # The visible raw runtime event contains trigger metadata, but the
        # controller's behavior must be derivable from the compiled view only.
        compiled = policy._prompt_state(state)
        event = next(
            row for row in compiled["event_history"]
            if row["event_id"] == "e3"
        )
        self.assertNotIn("trigger", event)
        repair = policy._unresolved_visible_repair(compiled)
        self.assertEqual(repair[0], "e3")
        self.assertEqual(repair[1]["type"], "send_follow_up")


if __name__ == "__main__":
    unittest.main()
