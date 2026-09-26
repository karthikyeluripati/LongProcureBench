"""Tests for the factual context-compiled reactive baseline."""
from copy import deepcopy
import json
import unittest

from longprocurebench import LongProcureBenchEnv, ReactiveLLMPolicy
from longprocurebench.context_compiled_reactive import (
    ContextCompiledReactiveLLMPolicy,
    compile_visible_state,
)


class FakeActionClient:
    model = "fake/test-model"

    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def generate_action(self, *, messages, action_schema):
        self.calls.append({
            "messages": messages,
            "action_schema": action_schema,
        })
        return self.decision, {
            "model": self.model,
            "latency_ms": 1.0,
            "prompt_tokens": 50,
            "completion_tokens": 5,
            "total_tokens": 55,
            "cost_usd": 0.001,
        }


def _action(episode_id, number, action_type, supplier_id=None, arguments=None):
    return {
        "action_id": f"a{number}",
        "episode_id": episode_id,
        "type": action_type,
        "supplier_id": supplier_id,
        "arguments": arguments or {},
    }


def _all_keys(value):
    keys = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_all_keys(child))
    return keys


class ContextCompilerTests(unittest.TestCase):
    def test_compiler_preserves_operational_requirements_and_strips_evidence_noise(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        compiled = compile_visible_state(state)

        self.assertEqual(compiled["episode_id"], state["episode_id"])
        initial = compiled["initial_state"]
        self.assertEqual(initial["line_items"][0]["quantity"], 57)
        self.assertEqual(
            initial["schedule"]["delivery_requirement"],
            "219 days ADO.",
        )
        self.assertIsNone(initial["total_estimated_budget"])
        missing_paths = {
            row["field_path"]
            for row in initial["operational_missing_information"]
        }
        self.assertIn("/total_estimated_budget", missing_paths)
        self.assertNotIn("supporting_documents", initial)
        self.assertNotIn("source_provenance", initial)
        spec = initial["line_items"][0]["technical_specifications"][0]
        self.assertEqual(
            spec["summary"],
            "Power supply, NSN 6130200055446",
        )
        self.assertNotIn("source_locator", spec)

    def test_compiler_groups_only_revealed_facts_and_latest_offers(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        episode_id = state["episode_id"]

        state = env.step(_action(
            episode_id, 1, "identify_suppliers"
        ))
        state = env.step(_action(
            episode_id, 2, "send_rfq", "syn-ps-a"
        ))
        state = env.step(_action(
            episode_id, 3, "send_rfq", "syn-ps-b"
        ))
        state = env.step(_action(
            episode_id, 4, "send_rfq", "syn-ps-c"
        ))

        compiled = compile_visible_state(state)
        event_ids = [
            event["event_id"] for event in compiled["event_history"]
        ]
        self.assertEqual(event_ids, ["e1", "e2", "e3", "e4"])
        self.assertEqual(
            [event["event_id"] for event in compiled["requirement_updates"]],
            ["e4"],
        )
        latest = {
            item["supplier_id"]: item["event_id"]
            for item in compiled["latest_offers"]
        }
        self.assertEqual(latest, {
            "syn-ps-a": "e1",
            "syn-ps-b": "e2",
        })

        state = env.step(_action(
            episode_id, 5, "request_quote_revision", "syn-ps-a"
        ))
        compiled = compile_visible_state(state)
        latest = {
            item["supplier_id"]: item["event_id"]
            for item in compiled["latest_offers"]
        }
        self.assertEqual(latest["syn-ps-a"], "e5")

    def test_compiler_does_not_add_obligation_or_oracle_fields(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        compiled = compile_visible_state(state)
        keys = [key.lower() for key in _all_keys(compiled)]
        self.assertFalse(any("obligation" in key for key in keys))
        self.assertNotIn("oracle", keys)
        self.assertNotIn("required_checkpoints", keys)

    def test_compiler_does_not_mutate_runtime_state(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        before = deepcopy(state)
        compile_visible_state(state)
        self.assertEqual(state, before)

    def test_compiled_state_is_smaller_than_raw_runtime_serialization(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        episode_id = state["episode_id"]
        state = env.step(_action(
            episode_id, 1, "identify_suppliers"
        ))
        state = env.step(_action(
            episode_id, 2, "send_rfq", "syn-ps-a"
        ))
        state = env.step(_action(
            episode_id, 3, "send_rfq", "syn-ps-b"
        ))
        compiled = compile_visible_state(state)
        raw_chars = len(json.dumps(state, sort_keys=True))
        compiled_chars = len(json.dumps(compiled, sort_keys=True))
        self.assertLess(compiled_chars, raw_chars)


class ContextCompiledPolicyTests(unittest.TestCase):
    def test_policy_changes_only_prompt_state_not_system_prompt_or_schema(self):
        decision = {
            "type": "identify_suppliers",
            "supplier_id": None,
            "arguments": {"awards": None, "reason": None},
        }
        raw_client = FakeActionClient(decision)
        compiled_client = FakeActionClient(decision)
        raw = ReactiveLLMPolicy("fake/test-model", client=raw_client)
        compiled = ContextCompiledReactiveLLMPolicy(
            "fake/test-model",
            client=compiled_client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )

        raw.reset(state)
        compiled.reset(state)
        raw.act(state)
        compiled.act(state)

        raw_call = raw_client.calls[0]
        compiled_call = compiled_client.calls[0]
        self.assertEqual(
            raw_call["messages"][0],
            compiled_call["messages"][0],
        )
        self.assertEqual(
            raw_call["action_schema"],
            compiled_call["action_schema"],
        )
        self.assertIn("source_provenance", raw_call["messages"][1]["content"])
        self.assertNotIn(
            "source_provenance",
            compiled_call["messages"][1]["content"],
        )

    def test_policy_records_context_strategy(self):
        decision = {
            "type": "identify_suppliers",
            "supplier_id": None,
            "arguments": {"awards": None, "reason": None},
        }
        policy = ContextCompiledReactiveLLMPolicy(
            "fake/test-model",
            client=FakeActionClient(decision),
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        policy.act(state)
        metrics = policy.get_run_metadata()
        self.assertEqual(
            metrics["context_strategy"],
            "factual_compiled_v0.1",
        )
        self.assertEqual(policy.policy_kind, "llm_context_compiled_reactive")


if __name__ == "__main__":
    unittest.main()
