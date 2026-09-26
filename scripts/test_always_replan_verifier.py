"""Tests for always-replan + pre-terminal verification."""
from copy import deepcopy
import unittest

from longprocurebench import LongProcureBenchEnv
from longprocurebench.always_replan_verifier import (
    AlwaysReplanVerifierLLMPolicy,
)


class FakeClient:
    model = "fake/test-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_action(self, *, messages, action_schema):
        self.calls.append({
            "messages": deepcopy(messages),
            "action_schema": deepcopy(action_schema),
        })
        response = self.responses.pop(0)
        return response, {
            "model": self.model,
            "latency_ms": 1.0,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost_usd": 0.001,
        }


def plan(action_type="identify_suppliers", supplier_id=None):
    return {
        "objective": "Advance procurement from visible facts.",
        "key_facts": ["Use the current visible state."],
        "risks": [],
        "recommended_action_type": action_type,
        "supplier_id": supplier_id,
    }


def action(action_type, supplier_id=None, awards=None, reason=None):
    return {
        "type": action_type,
        "supplier_id": supplier_id,
        "arguments": {
            "awards": awards,
            "reason": reason,
        },
    }


def verdict(approve, recommended="evaluate_quotes", supplier_id=None, issues=None):
    return {
        "approve": approve,
        "issues": list(issues or []),
        "recommended_action_type": recommended,
        "supplier_id": supplier_id,
    }


class AlwaysReplanVerifierTests(unittest.TestCase):
    def state(self):
        return LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )

    def test_nonterminal_action_uses_planner_then_action_only(self):
        client = FakeClient([
            plan("identify_suppliers"),
            action("identify_suppliers"),
        ])
        policy = AlwaysReplanVerifierLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = self.state()
        policy.reset(state)
        decision = policy.act(state)

        self.assertEqual(decision["type"], "identify_suppliers")
        self.assertEqual(len(client.calls), 2)
        metadata = policy.get_run_metadata()
        self.assertEqual(metadata["planner_calls"], 1)
        self.assertEqual(metadata["action_calls"], 1)
        self.assertEqual(metadata["verifier_calls"], 0)
        self.assertEqual(
            [x["call_role"] for x in metadata["calls"]],
            ["planner", "action"],
        )

    def test_terminal_action_requires_separate_verifier(self):
        client = FakeClient([
            plan("no_award"),
            action("no_award", reason="No visible compliant offer."),
            verdict(True, recommended="evaluate_quotes"),
        ])
        policy = AlwaysReplanVerifierLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = self.state()
        policy.reset(state)
        decision = policy.act(state)

        self.assertEqual(decision["type"], "no_award")
        metadata = policy.get_run_metadata()
        self.assertEqual(metadata["verifier_calls"], 1)
        self.assertEqual(metadata["verifier_rejections"], 0)
        self.assertEqual(len(client.calls), 3)

    def test_rejected_terminal_is_replaced_by_nonterminal_repair(self):
        client = FakeClient([
            plan("no_award"),
            action("no_award", reason="Stop."),
            verdict(
                False,
                recommended="identify_suppliers",
                issues=["Visible procurement path remains."],
            ),
            action("identify_suppliers"),
        ])
        policy = AlwaysReplanVerifierLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = self.state()
        policy.reset(state)
        decision = policy.act(state)

        self.assertEqual(decision["type"], "identify_suppliers")
        metadata = policy.get_run_metadata()
        self.assertEqual(metadata["verifier_rejections"], 1)
        self.assertEqual(metadata["repair_calls"], 1)
        repair_enum = client.calls[3]["action_schema"]["properties"]["type"]["enum"]
        self.assertNotIn("award_supplier", repair_enum)
        self.assertNotIn("no_award", repair_enum)

    def test_every_act_replans_from_current_compiled_state(self):
        client = FakeClient([
            plan("identify_suppliers"),
            action("identify_suppliers"),
            plan("request_buyer_clarification"),
            action("request_buyer_clarification"),
        ])
        policy = AlwaysReplanVerifierLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = self.state()
        policy.reset(state)
        policy.act(state)
        policy.act(state)

        metadata = policy.get_run_metadata()
        self.assertEqual(metadata["planner_calls"], 2)
        self.assertEqual(metadata["action_calls"], 2)
        self.assertEqual(len(metadata["deliberation_trace"]), 2)

    def test_prompts_do_not_expose_evaluator_or_oracle_state(self):
        client = FakeClient([
            plan("identify_suppliers"),
            action("identify_suppliers"),
        ])
        policy = AlwaysReplanVerifierLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = self.state()
        policy.reset(state)
        policy.act(state)
        prompt = "\n".join(
            message["content"]
            for call in client.calls
            for message in call["messages"]
        ).lower()
        self.assertNotIn("required_checkpoints", prompt)
        self.assertNotIn('"oracle"', prompt)
        self.assertNotIn('"evaluation"', prompt)

    def test_plan_rejects_hidden_supplier_reference(self):
        client = FakeClient([
            plan("send_rfq", supplier_id="hidden-supplier"),
        ])
        policy = AlwaysReplanVerifierLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = self.state()
        policy.reset(state)
        with self.assertRaisesRegex(ValueError, "non-visible supplier"):
            policy.act(state)


if __name__ == "__main__":
    unittest.main()
