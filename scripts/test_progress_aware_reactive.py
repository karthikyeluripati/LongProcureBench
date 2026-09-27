"""Tests for progress-aware reactive control."""
from copy import deepcopy
import unittest

from longprocurebench import LongProcureBenchEnv
from longprocurebench.progress_aware_reactive import (
    ProgressAwareReactiveLLMPolicy,
    action_signature,
    evidence_fingerprint,
)


class FakeClient:
    model = "fake/test-model"

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def generate_action(self, *, messages, action_schema):
        self.calls.append({
            "messages": deepcopy(messages),
            "action_schema": deepcopy(action_schema),
        })
        decision = self.decisions.pop(0)
        return decision, {
            "model": self.model,
            "latency_ms": 1.0,
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "cost_usd": 0.001,
        }


def decision(action_type, supplier_id=None, reason=None):
    return {
        "type": action_type,
        "supplier_id": supplier_id,
        "arguments": {
            "awards": None,
            "reason": reason,
        },
    }


def accepted_action(state, number, selected):
    return {
        "action_id": f"a{number}",
        "episode_id": state["episode_id"],
        "type": selected["type"],
        "supplier_id": selected.get("supplier_id"),
        "arguments": selected.get("arguments") or {},
    }


class ProgressAwareReactiveTests(unittest.TestCase):
    def test_evidence_fingerprint_ignores_action_history_only_change(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bfar-generator-006")
        before = evidence_fingerprint(state)
        action = {
            "action_id": "a1",
            "episode_id": state["episode_id"],
            "type": "request_buyer_clarification",
            "supplier_id": None,
            "arguments": {},
        }
        state = env.step(action)
        self.assertEqual(state["observations"], [])
        self.assertEqual(before, evidence_fingerprint(state))

    def test_evidence_fingerprint_changes_when_visible_suppliers_change(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        before = evidence_fingerprint(state)
        action = {
            "action_id": "a1",
            "episode_id": state["episode_id"],
            "type": "identify_suppliers",
            "supplier_id": None,
            "arguments": {},
        }
        state = env.step(action)
        self.assertNotEqual(before, evidence_fingerprint(state))

    def test_no_progress_information_action_is_marked_after_acceptance(self):
        client = FakeClient([
            decision("request_buyer_clarification"),
        ])
        policy = ProgressAwareReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bfar-generator-006")
        policy.reset(state)

        selected = policy.act(state)
        action = accepted_action(state, 1, selected)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["no_progress_marks"], 1)
        self.assertEqual(
            metrics["blocked_actions_final"],
            [{
                "action_type": "request_buyer_clarification",
                "supplier_id": None,
                "no_progress_count": 1,
            }],
        )

    def test_blocked_repeat_gets_one_guard_retry(self):
        client = FakeClient([
            decision("request_buyer_clarification"),
            decision("request_buyer_clarification"),
            decision("identify_suppliers"),
        ])
        policy = ProgressAwareReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bfar-generator-006")
        policy.reset(state)

        first = policy.act(state)
        action = accepted_action(state, 1, first)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        second = policy.act(state)
        self.assertEqual(second["type"], "identify_suppliers")
        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["guard_interventions"], 1)
        self.assertEqual(metrics["guard_retry_calls"], 1)
        self.assertEqual(metrics["guard_retry_noncompliance"], 0)
        self.assertEqual(len(client.calls), 3)
        retry_prompt = client.calls[2]["messages"][1]["content"]
        self.assertIn("guard_retry_blocked_action", retry_prompt)
        self.assertIn("request_buyer_clarification", retry_prompt)

    def test_retry_noncompliance_is_measured_not_fatal(self):
        client = FakeClient([
            decision("request_buyer_clarification"),
            decision("request_buyer_clarification"),
            decision("request_buyer_clarification"),
        ])
        policy = ProgressAwareReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bfar-generator-006")
        policy.reset(state)

        first = policy.act(state)
        action = accepted_action(state, 1, first)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        second = policy.act(state)
        self.assertEqual(second["type"], "request_buyer_clarification")
        self.assertEqual(
            policy.get_run_metadata()["guard_retry_noncompliance"],
            1,
        )

    def test_new_visible_evidence_clears_blocked_actions(self):
        client = FakeClient([
            decision("request_buyer_clarification"),
            decision("identify_suppliers"),
        ])
        policy = ProgressAwareReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bfar-generator-006")
        policy.reset(state)

        first = policy.act(state)
        action = accepted_action(state, 1, first)
        state = env.step(action)
        policy.on_action_accepted(action, state)
        self.assertTrue(policy.get_run_metadata()["blocked_actions_final"])

        second = policy.act(state)
        action = accepted_action(state, 2, second)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["blocked_actions_final"], [])
        self.assertEqual(metrics["progress_events"], 1)
        self.assertEqual(metrics["evidence_epoch"], 1)

    def test_non_information_action_is_not_marked_no_progress(self):
        client = FakeClient([decision("evaluate_quotes")])
        policy = ProgressAwareReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bfar-generator-006")
        policy.reset(state)

        selected = policy.act(state)
        action = accepted_action(state, 1, selected)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        self.assertEqual(
            policy.get_run_metadata()["no_progress_marks"],
            0,
        )
        self.assertEqual(
            policy.get_run_metadata()["blocked_actions_final"],
            [],
        )

    def test_prompt_contains_no_evaluator_or_oracle_state(self):
        client = FakeClient([decision("identify_suppliers")])
        policy = ProgressAwareReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        policy.act(state)

        prompt = client.calls[0]["messages"][1]["content"].lower()
        self.assertNotIn("required_checkpoints", prompt)
        self.assertNotIn('"oracle"', prompt)
        self.assertNotIn('"evaluation"', prompt)

    def test_signature_ignores_free_text_reason(self):
        a = decision(
            "request_buyer_clarification",
            reason="First wording",
        )
        b = decision(
            "request_buyer_clarification",
            reason="Different wording",
        )
        self.assertEqual(action_signature(a), action_signature(b))


if __name__ == "__main__":
    unittest.main()
