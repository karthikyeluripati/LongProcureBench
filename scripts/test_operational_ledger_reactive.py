"""Tests for the persistent operational-ledger reactive policy."""
from copy import deepcopy
import json
import unittest

from longprocurebench import LongProcureBenchEnv
from longprocurebench.operational_ledger_reactive import (
    OperationalLedgerError,
    OperationalLedgerReactiveLLMPolicy,
)


class FakeLedgerClient:
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
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "cost_usd": 0.001,
        }


def _response(
    action_type,
    *,
    supplier_id=None,
    awards=None,
    reason=None,
    new_items=None,
    resolve_item_ids=None,
):
    return {
        "action": {
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": {
                "awards": awards,
                "reason": reason,
            },
        },
        "ledger_update": {
            "new_items": list(new_items or []),
            "resolve_item_ids": list(resolve_item_ids or []),
        },
    }


def _item(
    description,
    *,
    category="supplier",
    supplier_id=None,
    source_event_ids=None,
):
    return {
        "category": category,
        "supplier_id": supplier_id,
        "source_event_ids": list(source_event_ids or []),
        "description": description,
    }


def _action(episode_id, number, action_type, supplier_id=None, arguments=None):
    return {
        "action_id": f"a{number}",
        "episode_id": episode_id,
        "type": action_type,
        "supplier_id": supplier_id,
        "arguments": arguments or {},
    }


class OperationalLedgerPolicyTests(unittest.TestCase):
    def test_first_call_sees_empty_ledger_and_persists_new_item(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                new_items=[
                    _item(
                        "Clarify buyer budget before committing award.",
                        category="requirement",
                    )
                ],
            )
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-bongabon-generator-001"
        )
        policy.reset(state)
        decision = policy.act(state)

        self.assertEqual(decision["type"], "identify_suppliers")
        prompt = client.calls[0]["messages"][1]["content"]
        self.assertIn('"open_items": []', prompt)

        metadata = policy.get_run_metadata()
        ledger = metadata["final_ledger"]
        self.assertEqual(len(ledger["open_items"]), 1)
        self.assertEqual(ledger["open_items"][0]["item_id"], "l001")
        self.assertEqual(ledger["resolved_items"], [])

    def test_prior_open_item_is_visible_and_can_be_resolved(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                new_items=[
                    _item(
                        "Resolve buyer commercial clarification.",
                        category="requirement",
                    )
                ],
            ),
            _response(
                "request_buyer_clarification",
                resolve_item_ids=["l001"],
            ),
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-bongabon-generator-001"
        )
        policy.reset(state)
        first = policy.act(state)
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bongabon-generator-001")
        state = env.step(_action(
            state["episode_id"], 1, "identify_suppliers"
        ))
        second = policy.act(state)

        self.assertEqual(first["type"], "identify_suppliers")
        self.assertEqual(second["type"], "request_buyer_clarification")
        second_prompt = client.calls[1]["messages"][1]["content"]
        self.assertIn('"item_id": "l001"', second_prompt)
        metadata = policy.get_run_metadata()
        self.assertEqual(metadata["final_ledger"]["open_items"], [])
        self.assertEqual(
            metadata["final_ledger"]["resolved_items"][0]["item_id"],
            "l001",
        )

    def test_new_item_may_reference_only_revealed_events(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        episode_id = state["episode_id"]
        state = env.step(_action(episode_id, 1, "identify_suppliers"))
        state = env.step(_action(
            episode_id, 2, "send_rfq", "syn-ps-c"
        ))
        self.assertIn(
            "e3",
            [event["event_id"] for event in state["revealed_events"]],
        )

        client = FakeLedgerClient([
            _response(
                "send_follow_up",
                supplier_id="syn-ps-c",
                new_items=[
                    _item(
                        "Track response from supplier C.",
                        supplier_id="syn-ps-c",
                        source_event_ids=["e3"],
                    )
                ],
            )
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)
        policy.act(state)
        self.assertEqual(
            policy.get_run_metadata()["final_ledger"]["open_items"][0][
                "source_event_ids"
            ],
            ["e3"],
        )

    def test_unrevealed_event_reference_is_rejected(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                new_items=[
                    _item(
                        "Hallucinated future event.",
                        source_event_ids=["e99"],
                    )
                ],
            )
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        with self.assertRaisesRegex(
            OperationalLedgerError,
            "unrevealed event",
        ):
            policy.act(state)

    def test_invisible_supplier_reference_is_rejected(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                new_items=[
                    _item(
                        "Contact hidden supplier.",
                        supplier_id="syn-ps-a",
                    )
                ],
            )
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        with self.assertRaisesRegex(
            OperationalLedgerError,
            "non-visible supplier",
        ):
            policy.act(state)

    def test_unknown_ledger_item_cannot_be_resolved(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                resolve_item_ids=["l999"],
            )
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        with self.assertRaisesRegex(
            OperationalLedgerError,
            "unknown open ledger item",
        ):
            policy.act(state)

    def test_reset_clears_persistent_ledger_between_episodes(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                new_items=[
                    _item(
                        "Remember this only for the first episode.",
                        category="other",
                    )
                ],
            )
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        first = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(first)
        policy.act(first)
        self.assertEqual(
            policy.get_run_metadata()["ledger_open_items"],
            1,
        )

        second = LongProcureBenchEnv().reset(
            "electrical-vre-generator-020"
        )
        policy.reset(second)
        self.assertEqual(
            policy.get_run_metadata()["ledger_open_items"],
            0,
        )
        self.assertEqual(
            policy.get_run_metadata()["ledger_resolved_items"],
            0,
        )

    def test_policy_uses_one_model_call_per_action(self):
        client = FakeLedgerClient([
            _response("identify_suppliers"),
            _response("evaluate_quotes"),
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        policy.act(state)
        policy.act(state)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            policy.get_run_metadata()["model_calls_attempted"],
            2,
        )

    def test_ledger_schema_uses_provider_safe_json_schema_subset(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        schema = OperationalLedgerReactiveLLMPolicy._response_schema(state)
        encoded = json.dumps(schema, sort_keys=True)
        for unsupported in (
            "uniqueItems",
            "maxItems",
            "maxLength",
            "minLength",
            "pattern",
        ):
            with self.subTest(keyword=unsupported):
                self.assertNotIn(f'"{unsupported}"', encoded)

    def test_duplicate_resolve_ids_are_rejected_locally(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                new_items=[
                    _item(
                        "Track requirement.",
                        category="requirement",
                    )
                ],
            ),
            _response(
                "request_buyer_clarification",
                resolve_item_ids=["l001", "l001"],
            ),
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bongabon-generator-001")
        policy.reset(state)
        first = policy.act(state)
        state = env.step(_action(
            state["episode_id"],
            1,
            first["type"],
            first.get("supplier_id"),
            first.get("arguments"),
        ))
        with self.assertRaisesRegex(
            OperationalLedgerError,
            "duplicate ledger item",
        ):
            policy.act(state)

    def test_response_schema_embeds_same_semantic_action_contract(self):
        state = LongProcureBenchEnv().reset(
            "electrical-highpoint-cable-018"
        )
        schema = OperationalLedgerReactiveLLMPolicy._response_schema(state)
        nested = schema["properties"]["action"]
        expected = OperationalLedgerReactiveLLMPolicy._action_schema(state)
        self.assertEqual(nested, expected)
        self.assertFalse(schema["additionalProperties"])

    def test_metadata_records_auditable_ledger_trace(self):
        client = FakeLedgerClient([
            _response(
                "identify_suppliers",
                new_items=[
                    _item(
                        "Track unresolved requirement.",
                        category="requirement",
                    )
                ],
            )
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        policy.act(state)
        metadata = policy.get_run_metadata()

        self.assertEqual(
            metadata["context_strategy"],
            "factual_compiled_v0.1",
        )
        self.assertEqual(
            metadata["state_strategy"],
            "operational_ledger_v0.1",
        )
        self.assertEqual(metadata["ledger_open_items"], 1)
        self.assertEqual(metadata["ledger_resolved_items"], 0)
        self.assertEqual(len(metadata["ledger_trace"]), 1)
        self.assertEqual(
            metadata["ledger_trace"][0]["new_item_ids"],
            ["l001"],
        )

    def test_ledger_prompt_contains_no_evaluator_state_by_construction(self):
        client = FakeLedgerClient([
            _response("identify_suppliers")
        ])
        policy = OperationalLedgerReactiveLLMPolicy(
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
        self.assertNotIn("evaluator", prompt)


if __name__ == "__main__":
    unittest.main()
