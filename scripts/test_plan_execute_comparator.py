"""Tests for the static Plan-and-Execute comparator."""
from copy import deepcopy
import unittest

from longprocurebench import LongProcureBenchEnv
from longprocurebench.plan_execute_comparator import (
    PlanExecuteLLMPolicy,
    PlanExecuteProtocolError,
)


class SequenceClient:
    model = "fake/test-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_action(self, *, messages, action_schema):
        self.calls.append({
            "messages": deepcopy(messages),
            "action_schema": deepcopy(action_schema),
        })
        if not self.responses:
            raise AssertionError("Unexpected model call")
        response = deepcopy(self.responses.pop(0))
        return response, {
            "model": self.model,
            "latency_ms": 1.0,
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "cost_usd": 0.001,
            "usage_available": True,
        }


def _plan():
    return {
        "objective": "Complete the visible procurement correctly.",
        "steps": [
            {
                "step_id": 1,
                "operation": "request_buyer_clarification",
                "purpose": "Resolve visible prerequisite gaps.",
                "condition": "Use when required commercial information is missing.",
            },
            {
                "step_id": 2,
                "operation": "identify_suppliers",
                "purpose": "Reveal the supplier directory.",
                "condition": "Use after prerequisite information is sufficient.",
            },
            {
                "step_id": 3,
                "operation": "send_rfq",
                "purpose": "Solicit visible suppliers.",
                "condition": "Use for visible suppliers that still need an RFQ.",
            },
            {
                "step_id": 4,
                "operation": "evaluate_quotes",
                "purpose": "Compare currently visible offers.",
                "condition": "Use when enough current offers are available.",
            },
            {
                "step_id": 5,
                "operation": "award_supplier",
                "purpose": "Make the terminal award.",
                "condition": "Use when a feasible award is supported by visible evidence.",
            },
        ],
        "completion_condition": "A supported terminal award or no-award is reached.",
    }


def _executor(step, action_type, supplier_id=None, awards=None):
    return {
        "plan_step_index": step,
        "action": {
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": {
                "awards": awards,
                "reason": None,
            },
        },
    }


def _accepted(episode_id, number, decision):
    return {
        "action_id": f"a{number}",
        "episode_id": episode_id,
        "type": decision["type"],
        "supplier_id": decision.get("supplier_id"),
        "arguments": deepcopy(decision.get("arguments") or {}),
    }


class PlanExecuteComparatorTests(unittest.TestCase):
    def test_generates_one_fixed_plan_then_executes_multiple_actions(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-transformer-013")
        episode_id = state["episode_id"]

        client = SequenceClient([
            _plan(),
            _executor(1, "request_buyer_clarification"),
            _executor(2, "identify_suppliers"),
        ])
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        first = policy.act(state)
        self.assertEqual(first["type"], "request_buyer_clarification")
        self.assertEqual(len(client.calls), 2)
        state = env.step(_accepted(episode_id, 1, first))
        policy.on_action_accepted(
            _accepted(episode_id, 1, first),
            state,
        )

        second = policy.act(state)
        self.assertEqual(second["type"], "identify_suppliers")
        self.assertEqual(len(client.calls), 3)
        state = env.step(_accepted(episode_id, 2, second))
        policy.on_action_accepted(
            _accepted(episode_id, 2, second),
            state,
        )

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["planner_calls"], 1)
        self.assertEqual(metrics["executor_calls"], 2)
        self.assertEqual(metrics["model_calls"], 3)
        self.assertEqual(metrics["plan_steps"], 5)
        self.assertEqual(metrics["unplanned_exceptions"], 0)
        self.assertEqual(metrics["plan_step_usage"], {"1": 1, "2": 1})
        self.assertEqual(metrics["fixed_plan"], _plan())

    def test_selected_plan_step_must_match_action_type(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-transformer-013"
        )
        client = SequenceClient([
            _plan(),
            _executor(2, "request_buyer_clarification"),
        ])
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        with self.assertRaises(PlanExecuteProtocolError):
            policy.act(state)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["model_calls"], 2)
        self.assertEqual(metrics["model_calls_failed"], 1)

    def test_plan_step_zero_allows_unplanned_visible_recovery(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-transformer-013")
        episode_id = state["episode_id"]

        client = SequenceClient([
            _plan(),
            _executor(0, "request_buyer_clarification"),
        ])
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        decision = policy.act(state)
        state = env.step(_accepted(episode_id, 1, decision))
        policy.on_action_accepted(
            _accepted(episode_id, 1, decision),
            state,
        )

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["unplanned_exceptions"], 1)
        self.assertEqual(metrics["plan_step_usage"], {"0": 1})

    def test_planner_receives_compiled_visible_state_without_oracle(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-transformer-013"
        )
        client = SequenceClient([
            _plan(),
            _executor(1, "request_buyer_clarification"),
        ])
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)
        policy.act(state)

        planner_user = client.calls[0]["messages"][1]["content"]
        self.assertIn("operational_missing_information", planner_user)
        self.assertNotIn("source_provenance", planner_user)
        self.assertNotIn('"oracle"', planner_user)
        self.assertNotIn("required_checkpoints", planner_user)


if __name__ == "__main__":
    unittest.main()
