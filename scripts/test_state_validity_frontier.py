"""Tests for State Validity Frontier v0.1 implementation."""
from copy import deepcopy
from pathlib import Path
import unittest

from longprocurebench import (
    LongProcureBenchEnv,
    StateValidityFrontierError,
    StateValidityFrontierPolicy,
)
from run_state_validity_frontier import (
    TARGETED_PILOT_EPISODES,
    TARGET_MAX_ACTIONS,
    TARGET_MODEL,
    TARGET_REASONING_EFFORT,
    TARGET_REPEATS,
    TARGET_TEMPERATURE,
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
        decision = deepcopy(self.decisions.pop(0))
        return decision, {
            "model": self.model,
            "latency_ms": 1.0,
            "prompt_tokens": 50,
            "completion_tokens": 5,
            "total_tokens": 55,
            "cost_usd": 0.001,
            "usage_available": True,
        }


def _model_action(action_type, supplier_id=None, awards=None, reason=None):
    return {
        "type": action_type,
        "supplier_id": supplier_id,
        "arguments": {
            "awards": awards,
            "reason": reason,
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


def _take(policy, env, state, episode_id, number):
    decision = policy.act(state)
    action = _accepted(episode_id, number, decision)
    next_state = env.step(action)
    policy.on_action_accepted(action, next_state)
    return decision, next_state


class StateValidityFrontierTests(unittest.TestCase):
    def test_013_clarification_then_revision_question_recovery(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-transformer-013")
        episode_id = state["episode_id"]

        client = SequenceActionClient([
            _model_action("request_buyer_clarification"),
            _model_action("send_rfq", "syn-dla-xfmr-a"),
            _model_action("request_quote_revision", "syn-dla-xfmr-c"),
            _model_action("evaluate_quotes"),
        ])
        policy = StateValidityFrontierPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        first, state = _take(policy, env, state, episode_id, 1)
        self.assertEqual(first["type"], "request_buyer_clarification")
        self.assertEqual({x["event_id"] for x in state["observations"]}, {"e1"})
        self.assertEqual(len(client.calls), 1)

        second, state = _take(policy, env, state, episode_id, 2)
        self.assertEqual(second["type"], "identify_suppliers")
        self.assertEqual(len(client.calls), 1)

        third, state = _take(policy, env, state, episode_id, 3)
        self.assertEqual(third, {
            "type": "send_rfq",
            "supplier_id": "syn-dla-xfmr-a",
            "arguments": {},
        })
        self.assertEqual(len(client.calls), 2)

        fourth, state = _take(policy, env, state, episode_id, 4)
        self.assertEqual(fourth["type"], "send_rfq")
        self.assertEqual(fourth["supplier_id"], "syn-dla-xfmr-b")

        fifth, state = _take(policy, env, state, episode_id, 5)
        self.assertEqual(fifth["type"], "send_rfq")
        self.assertEqual(fifth["supplier_id"], "syn-dla-xfmr-c")
        self.assertEqual(len(client.calls), 2)

        sixth, state = _take(policy, env, state, episode_id, 6)
        self.assertEqual(sixth, {
            "type": "request_quote_revision",
            "supplier_id": "syn-dla-xfmr-c",
            "arguments": {},
        })
        self.assertEqual({x["event_id"] for x in state["observations"]}, {"e5"})
        self.assertEqual(len(client.calls), 3)

        seventh, state = _take(policy, env, state, episode_id, 7)
        self.assertEqual(seventh, {
            "type": "answer_supplier_question",
            "supplier_id": "syn-dla-xfmr-c",
            "arguments": {},
        })
        self.assertEqual({x["event_id"] for x in state["observations"]}, {"e6"})
        self.assertEqual(len(client.calls), 3)

        eighth = policy.act(state)
        self.assertEqual(eighth["type"], "evaluate_quotes")
        self.assertEqual(len(client.calls), 4)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["clarification_epochs_used"], [0])
        self.assertEqual(metrics["coverage_forced_rfqs"], 2)
        self.assertEqual(metrics["coverage_forced_answers"], 1)
        self.assertIn("e4", metrics["revision_attempt_offer_ids"])
        self.assertGreater(metrics["validity_frontier_interventions"], 0)

        first_user_prompt = client.calls[0]["messages"][1]["content"]
        self.assertNotIn('"oracle"', first_user_prompt)
        self.assertNotIn("required_checkpoints", first_user_prompt)
        self.assertNotIn('"trigger"', first_user_prompt)

    def test_016_change_requires_amendment_then_repairs_stale_offers(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        episode_id = state["episode_id"]

        client = SequenceActionClient([
            _model_action("identify_suppliers"),
            _model_action("send_rfq", "syn-ps-a"),
            _model_action("request_quote_revision", "syn-ps-a"),
            _model_action("evaluate_quotes"),
        ])
        policy = StateValidityFrontierPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        first, state = _take(policy, env, state, episode_id, 1)
        self.assertEqual(first["type"], "identify_suppliers")

        second, state = _take(policy, env, state, episode_id, 2)
        self.assertEqual(second["type"], "send_rfq")
        self.assertEqual(second["supplier_id"], "syn-ps-a")

        third, state = _take(policy, env, state, episode_id, 3)
        self.assertEqual(third["supplier_id"], "syn-ps-b")

        fourth, state = _take(policy, env, state, episode_id, 4)
        self.assertEqual(fourth["supplier_id"], "syn-ps-c")
        self.assertEqual(
            {row["event_id"] for row in state["observations"]},
            {"e3", "e4"},
        )

        fifth, state = _take(policy, env, state, episode_id, 5)
        self.assertEqual(fifth["type"], "issue_amendment")
        self.assertEqual(len(client.calls), 2)

        sixth, state = _take(policy, env, state, episode_id, 6)
        self.assertEqual(sixth, {
            "type": "send_follow_up",
            "supplier_id": "syn-ps-c",
            "arguments": {},
        })
        self.assertEqual({x["event_id"] for x in state["observations"]}, {"e7"})

        seventh, state = _take(policy, env, state, episode_id, 7)
        self.assertEqual(seventh, {
            "type": "request_quote_revision",
            "supplier_id": "syn-ps-a",
            "arguments": {},
        })
        self.assertEqual({x["event_id"] for x in state["observations"]}, {"e5"})
        self.assertEqual(len(client.calls), 3)

        eighth, state = _take(policy, env, state, episode_id, 8)
        self.assertEqual(eighth, {
            "type": "request_quote_revision",
            "supplier_id": "syn-ps-b",
            "arguments": {},
        })
        self.assertEqual({x["event_id"] for x in state["observations"]}, {"e6"})
        self.assertEqual(len(client.calls), 3)

        ninth = policy.act(state)
        self.assertEqual(ninth["type"], "evaluate_quotes")
        self.assertEqual(len(client.calls), 4)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["requirement_epoch"], 1)
        self.assertEqual(metrics["amendment_required_epochs"], [1])
        self.assertEqual(metrics["amended_epochs"], [1])
        self.assertEqual(metrics["clarification_epochs_used"], [])
        self.assertEqual(metrics["coverage_forced_followups"], 1)
        self.assertGreaterEqual(metrics["requirement_invalidations"], 1)

    def test_008_withdrawal_recovery_can_acquire_new_quote_then_reevaluate(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-burauen-generator-008")
        episode_id = state["episode_id"]

        client = SequenceActionClient([
            _model_action("identify_suppliers"),
            _model_action("send_rfq", "syn-burauen-a"),
            _model_action("evaluate_quotes"),
            _model_action("request_quote_revision", "syn-burauen-c"),
        ])
        policy = StateValidityFrontierPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        first, state = _take(policy, env, state, episode_id, 1)
        self.assertEqual(first["type"], "identify_suppliers")

        second, state = _take(policy, env, state, episode_id, 2)
        self.assertEqual(second["supplier_id"], "syn-burauen-a")

        third, state = _take(policy, env, state, episode_id, 3)
        self.assertEqual(third["supplier_id"], "syn-burauen-b")

        fourth, state = _take(policy, env, state, episode_id, 4)
        self.assertEqual(fourth["supplier_id"], "syn-burauen-c")

        compiled = policy._prompt_state(state)
        graph = policy._validity_graph(compiled)
        pre_eval_frontier = policy._frontier(compiled, graph)
        revision_suppliers = {
            row["supplier_id"]
            for row in pre_eval_frontier
            if row["type"] == "request_quote_revision"
        }
        self.assertEqual(revision_suppliers, {"syn-burauen-b"})
        self.assertNotIn("syn-burauen-c", revision_suppliers)
        self.assertIn(
            "evaluate_quotes",
            {row["type"] for row in pre_eval_frontier},
        )

        fifth, state = _take(policy, env, state, episode_id, 5)
        self.assertEqual(fifth["type"], "evaluate_quotes")
        self.assertEqual(
            {row["event_id"] for row in state["observations"]},
            {"e4"},
        )

        compiled = policy._prompt_state(state)
        graph = policy._validity_graph(compiled)
        frontier = policy._frontier(compiled, graph)
        self.assertNotIn(
            "evaluate_quotes",
            {row["type"] for row in frontier},
        )
        self.assertEqual(
            {row["supplier_id"] for row in frontier},
            {"syn-burauen-b", "syn-burauen-c"},
        )

        sixth, state = _take(policy, env, state, episode_id, 6)
        self.assertEqual(sixth, {
            "type": "request_quote_revision",
            "supplier_id": "syn-burauen-c",
            "arguments": {},
        })
        self.assertEqual(
            {row["event_id"] for row in state["observations"]},
            {"e5"},
        )

        seventh = policy.act(state)
        self.assertEqual(seventh["type"], "evaluate_quotes")

        graph = policy.get_run_metadata()["validity_graph"]
        self.assertIn("syn-burauen-a", graph["withdrawn_supplier_ids"])
        self.assertNotIn("syn-burauen-a", graph["active_supplier_ids"])
        self.assertTrue(graph["post_withdrawal_new_offer"])

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["withdrawal_invalidations"], 1)
        self.assertEqual(metrics["clarification_epochs_used"], [])
        self.assertGreater(metrics["validity_frontier_interventions"], 0)

    def test_stale_revision_nonresponse_advances_to_other_supplier(self):
        env = LongProcureBenchEnv()
        episode = env.load_episode("electrical-dla-power-supply-016")
        episode = deepcopy(episode)
        episode["events"] = [
            event
            for event in episode["events"]
            if event["event_id"] != "e5"
        ]
        state = env.reset(episode)
        episode_id = state["episode_id"]

        client = SequenceActionClient([
            _model_action("identify_suppliers"),
            _model_action("send_rfq", "syn-ps-a"),
            _model_action("request_quote_revision", "syn-ps-a"),
        ])
        policy = StateValidityFrontierPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        _, state = _take(policy, env, state, episode_id, 1)
        _, state = _take(policy, env, state, episode_id, 2)
        _, state = _take(policy, env, state, episode_id, 3)
        _, state = _take(policy, env, state, episode_id, 4)
        _, state = _take(policy, env, state, episode_id, 5)
        _, state = _take(policy, env, state, episode_id, 6)

        seventh, state = _take(policy, env, state, episode_id, 7)
        self.assertEqual(seventh, {
            "type": "request_quote_revision",
            "supplier_id": "syn-ps-a",
            "arguments": {},
        })
        self.assertEqual(state["observations"], [])

        graph = policy.get_run_metadata()["validity_graph"]
        self.assertIn("syn-ps-a", graph["exhausted_stale_supplier_ids"])
        self.assertIn("syn-ps-b", graph["pending_stale_supplier_ids"])

        eighth = policy.act(state)
        self.assertEqual(eighth, {
            "type": "request_quote_revision",
            "supplier_id": "syn-ps-b",
            "arguments": {},
        })

    def test_model_choice_outside_frontier_is_rejected(self):
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-transformer-013")
        client = SequenceActionClient([
            _model_action("no_award", reason="too early"),
        ])
        policy = StateValidityFrontierPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        with self.assertRaises(Exception):
            policy.act(state)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["model_calls_failed"], 1)

    def test_source_contains_no_target_episode_or_supplier_rules(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "longprocurebench"
            / "state_validity_frontier.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "electrical-burauen-generator-008",
            "electrical-dla-transformer-013",
            "electrical-dla-power-supply-016",
            "syn-burauen-a",
            "syn-ps-a",
            "syn-dla-xfmr-a",
        ):
            self.assertNotIn(forbidden, source)

    def test_stage_one_runner_is_exactly_frozen_protocol(self):
        self.assertEqual(
            TARGETED_PILOT_EPISODES,
            [
                "electrical-burauen-generator-008",
                "electrical-dla-transformer-013",
                "electrical-dla-power-supply-016",
            ],
        )
        self.assertEqual(TARGET_MODEL, "openai/gpt-5.6-sol")
        self.assertEqual(TARGET_REASONING_EFFORT, "medium")
        self.assertIsNone(TARGET_TEMPERATURE)
        self.assertEqual(TARGET_REPEATS, 1)
        self.assertEqual(TARGET_MAX_ACTIONS, 50)


if __name__ == "__main__":
    unittest.main()
