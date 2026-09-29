"""Offline regression tests for ProcureHarness architecture harness v0.1."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from longprocurebench import BenchmarkRunner, LongProcureBenchEnv
from longprocurebench.procureharness import (
    CANDIDATE_CONFIGS,
    MAX_LOCAL_PLAN_STEPS,
    MAX_MODEL_CALLS_BETWEEN_ACCEPTED_ACTIONS,
    MAX_REACT_FALLBACK_ACTIONS,
    ProcureHarnessConfig,
    ProcureHarnessPolicy,
    ProcureHarnessProtocolError,
    candidate_registry,
    get_candidate,
    validate_candidate_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "procureharness-candidate-registry-v0.1.json"


class SequenceStructuredClient:
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
            "prompt_tokens": 40,
            "completion_tokens": 8,
            "total_tokens": 48,
            "cost_usd": 0.001,
        }


def terminal_award(supplier_id="syn-31-c", quote_event_id="e5"):
    return {
        "type": "award_supplier",
        "supplier_id": supplier_id,
        "arguments": {
            "awards": [
                {
                    "scope": "package",
                    "supplier_id": supplier_id,
                    "quote_event_id": quote_event_id,
                }
            ],
            "reason": None,
        },
    }


class ProcureHarnessArchitectureTests(unittest.TestCase):
    def test_registry_is_exactly_three_rounds_by_six_candidates(self):
        validate_candidate_registry()
        self.assertEqual(len(CANDIDATE_CONFIGS), 18)
        for round_id in (1, 2, 3):
            self.assertEqual(
                len([c for c in CANDIDATE_CONFIGS if c.round == round_id]),
                6,
            )

    def test_registry_json_matches_code_configs(self):
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        observed = []
        for row in payload["candidates"]:
            observed.append({
                key: row[key]
                for key in (
                    "candidate_id",
                    "round",
                    "obligation_routing",
                    "local_planning",
                    "skill_reasoning",
                    "verification",
                    "fallback",
                )
            })
        self.assertEqual(observed, candidate_registry())
        self.assertEqual(
            payload["hard_complexity_limits"],
            {
                "max_model_calls_between_accepted_actions": 3,
                "max_local_plan_steps": 4,
                "max_react_fallback_actions": 3,
                "multi_agent": False,
                "persistent_cross_episode_memory": False,
            },
        )

    def test_registry_records_parent_candidates_and_module_deltas(self):
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        seen = set()
        for row in payload["candidates"]:
            self.assertIn("parent_candidates", row)
            self.assertIn("module_deltas", row)
            self.assertIsInstance(row["parent_candidates"], list)
            self.assertIsInstance(row["module_deltas"], list)
            for parent_id in row["parent_candidates"]:
                self.assertIn(parent_id, seen)
            if row["candidate_id"] == "ph-r1-c01":
                self.assertEqual(row["parent_candidates"], [])
                self.assertEqual(len(row["module_deltas"]), 5)
            else:
                self.assertGreaterEqual(len(row["parent_candidates"]), 1)
                self.assertGreaterEqual(len(row["module_deltas"]), 1)
            seen.add(row["candidate_id"])

    def test_unknown_candidate_is_rejected(self):
        with self.assertRaisesRegex(
            ProcureHarnessProtocolError,
            "unknown ProcureHarness candidate",
        ):
            get_candidate("not-a-candidate")

    def test_hard_limits_are_frozen(self):
        self.assertEqual(MAX_MODEL_CALLS_BETWEEN_ACCEPTED_ACTIONS, 3)
        self.assertEqual(MAX_LOCAL_PLAN_STEPS, 4)
        self.assertEqual(MAX_REACT_FALLBACK_ACTIONS, 3)

    def test_deterministic_controller_handles_clear_obligations_before_model(self):
        client = SequenceStructuredClient([terminal_award()])
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r1-c02",
            client=client,
            temperature=None,
            reasoning_effort="medium",
        )
        result = BenchmarkRunner().run(
            policy,
            "electrical-imperial-ev-phase1-031",
            max_actions=20,
        )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["evaluation"]["episode_success"])
        self.assertTrue(result["evaluation"]["feasible_obligation_success"])
        self.assertTrue(result["evaluation"]["episode_success_v02"])

        actions = [
            row["action"]["type"]
            for row in result["trajectory"]
        ]
        self.assertEqual(
            actions[:7],
            [
                "request_buyer_clarification",
                "identify_suppliers",
                "send_rfq",
                "send_rfq",
                "send_rfq",
                "send_follow_up",
                "request_quote_revision",
            ],
        )
        self.assertEqual(actions[-2:], ["evaluate_quotes", "award_supplier"])
        self.assertEqual(len(client.calls), 1)

        metrics = result["policy_metrics"]
        self.assertEqual(metrics["model_calls"], 1)
        self.assertEqual(metrics["accepted_actions_seen"], len(actions))
        self.assertEqual(metrics["deterministic_actions_accepted"], len(actions) - 1)
        self.assertAlmostEqual(
            metrics["deterministic_action_fraction"],
            (len(actions) - 1) / len(actions),
        )

    def test_requirement_change_forces_quote_refresh_before_leveling(self):
        for episode_id in (
            "electrical-lewiston-ev-chargers-033",
            "electrical-philadelphia-led-phase5-037",
        ):
            with self.subTest(episode_id=episode_id):
                env = LongProcureBenchEnv()
                state = env.reset(episode_id)

                def accepted(number, action_type, supplier_id=None):
                    nonlocal state
                    action = {
                        "action_id": f"a{number}",
                        "episode_id": episode_id,
                        "type": action_type,
                        "supplier_id": supplier_id,
                        "arguments": {},
                    }
                    state = env.step(action)

                accepted(1, "identify_suppliers")
                suppliers = [
                    row["supplier_id"]
                    for row in state["visible_suppliers"]
                ]
                accepted(2, "send_rfq", suppliers[0])
                accepted(3, "send_rfq", suppliers[1])
                accepted(4, "send_rfq", suppliers[2])

                policy = ProcureHarnessPolicy(
                    "fake/test-model",
                    config="ph-r1-c02",
                    client=SequenceStructuredClient([]),
                )
                policy.reset(state)
                compiled = policy._prompt_state(state)
                candidates = policy._build_candidates(compiled)

                amendment = [
                    row for row in candidates
                    if row["skill"] == "amendment_handling"
                ]
                refresh = [
                    row for row in candidates
                    if row["skill"] == "quote_revision"
                    and row["forced"] is True
                ]
                self.assertEqual(len(amendment), 1)
                self.assertEqual(
                    {row["supplier_id"] for row in refresh},
                    set(suppliers),
                )
                self.assertFalse(
                    any(
                        row["skill"] == "quote_leveling"
                        for row in candidates
                    )
                )

    def test_versioned_quote_arriving_after_change_is_still_stale(self):
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r1-c02",
            client=SequenceStructuredClient([]),
        )
        compiled = {
            "visible_suppliers": [{"supplier_id": "syn-a"}],
            "action_history": [],
            "event_history": [
                {
                    "event_id": "change",
                    "type": "requirement_change",
                    "supplier_id": None,
                    "details": {
                        "old_requirement_version": 0,
                        "new_requirement_version": 1,
                    },
                },
                {
                    "event_id": "q0",
                    "type": "quote_received",
                    "supplier_id": "syn-a",
                    "details": {"requirement_version": 0},
                    "offer_scope": {"kind": "package"},
                },
            ],
            "latest_offers": [
                {
                    "event_id": "q0",
                    "type": "quote_received",
                    "supplier_id": "syn-a",
                    "details": {"requirement_version": 0},
                    "offer_scope": {"kind": "package"},
                }
            ],
            "initial_state": {
                "operational_missing_information": [],
            },
        }
        candidates = policy._build_candidates(compiled)
        refresh = [
            row for row in candidates
            if row["skill"] == "quote_revision"
        ]
        self.assertEqual(len(refresh), 1)
        self.assertTrue(refresh[0]["forced"])
        self.assertEqual(refresh[0]["event_id"], "q0")

    def test_award_validation_requires_quote_scope_coverage(self):
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r1-c02",
            client=SequenceStructuredClient([]),
        )
        state = {
            "initial_state": {
                "line_items": [
                    {"item_id": "2904"},
                    {"item_id": "79"},
                    {"item_id": "80"},
                    {"item_id": "4523"},
                    {"item_id": "59"},
                ]
            }
        }
        compiled = {
            "visible_suppliers": [{"supplier_id": "syn-hpc-c"}],
            "latest_offers": [
                {
                    "event_id": "e4",
                    "supplier_id": "syn-hpc-c",
                    "details": {},
                    "offer_scope": {
                        "kind": "items",
                        "item_ids": ["4523", "59"],
                    },
                }
            ],
            "event_history": [],
        }
        selected = {"skill": "terminal_decision"}

        invalid = {
            "type": "award_supplier",
            "supplier_id": "syn-hpc-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-hpc-c",
                        "quote_event_id": "e4",
                    }
                ]
            },
        }
        ok, reason = policy._basic_visible_validation(
            invalid,
            state,
            compiled,
            selected,
        )
        self.assertFalse(ok)
        self.assertIn("does not cover", reason)

        valid = deepcopy(invalid)
        valid["arguments"]["awards"][0]["scope"] = "lot-4523"
        ok, _ = policy._basic_visible_validation(
            valid,
            state,
            compiled,
            selected,
        )
        self.assertTrue(ok)

    def test_withdrawal_recovery_is_model_reasoned_not_forced(self):
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r1-c02",
            client=SequenceStructuredClient([]),
        )
        pending = policy._candidate(
            skill="withdrawal_recovery",
            supplier_id="syn-a",
            reason="visible withdrawal",
            forced=False,
            event_id="w1",
        )
        compiled = {
            "visible_suppliers": [
                {"supplier_id": "syn-a"},
                {"supplier_id": "syn-b"},
                {"supplier_id": "syn-c"},
            ],
            "event_history": [
                {
                    "event_id": "w1",
                    "type": "supplier_withdrawal",
                    "supplier_id": "syn-a",
                }
            ],
            "latest_offers": [
                {"event_id": "q-b", "supplier_id": "syn-b", "details": {}},
                {"event_id": "q-c", "supplier_id": "syn-c", "details": {}},
            ],
        }
        candidate = policy._withdrawal_recovery_candidate(
            pending,
            compiled,
        )
        self.assertFalse(candidate["forced"])
        self.assertIsNone(candidate["supplier_id"])
        self.assertIsNone(
            policy._deterministic_action(candidate, compiled)
        )

    def test_quote_revision_attempt_is_one_shot_per_visible_offer(self):
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r1-c02",
            client=SequenceStructuredClient([]),
        )
        compiled = {
            "latest_offers": [
                {
                    "event_id": "q1",
                    "supplier_id": "syn-a",
                    "details": {"meets_public_requirement": False},
                }
            ]
        }
        first = policy._offer_revision_candidates(compiled)
        self.assertEqual(len(first), 1)
        policy._handled_event_ids.add("q1")
        self.assertEqual(policy._offer_revision_candidates(compiled), [])

    def test_mini_react_returns_nested_action_and_counts_one_call(self):
        client = SequenceStructuredClient([
            {
                "thought_summary": "Current offers have been leveled; select a visible current quote.",
                "action": terminal_award(),
            }
        ])
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r1-c05",
            client=client,
        )
        state = LongProcureBenchEnv().reset(
            "electrical-imperial-ev-phase1-031"
        )
        compiled = {
            "latest_offers": [],
        }
        action = policy._reasoned_action(
            state,
            compiled,
            {
                "skill": "terminal_decision",
                "candidate_id": "terminal_decision:-:-",
                "supplier_id": None,
                "reason": "test",
                "forced": False,
                "event_id": None,
                "priority": 90,
            },
            None,
        )
        self.assertEqual(action["type"], "award_supplier")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            policy.get_run_metadata()["model_call_purposes"],
            {"skill_reasoning_mini_react": 1},
        )

    def test_terminal_plan_mini_react_critique_uses_at_most_three_calls(self):
        client = SequenceStructuredClient([
            {
                "steps": [
                    {
                        "skill": "terminal_decision",
                        "supplier_id": None,
                        "objective": "Choose an award supported by visible current quotes.",
                    }
                ]
            },
            {
                "thought_summary": "A current quote supports terminal award.",
                "action": terminal_award(),
            },
            {
                "approve": True,
                "concern": None,
                "replacement_action": terminal_award(),
            },
        ])
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r3-c18",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-imperial-ev-phase1-031")

        # Construct a terminal-ready visible state using accepted environment
        # actions only; then mark the revealed offer set as already leveled.
        def step(number, action_type, supplier_id=None):
            nonlocal state
            state = env.step({
                "action_id": f"a{number}",
                "episode_id": state["episode_id"],
                "type": action_type,
                "supplier_id": supplier_id,
                "arguments": {},
            })

        step(1, "request_buyer_clarification")
        step(2, "identify_suppliers")
        step(3, "send_rfq", "syn-31-a")
        step(4, "send_rfq", "syn-31-b")
        step(5, "send_rfq", "syn-31-c")
        step(6, "send_follow_up", "syn-31-c")
        step(7, "request_quote_revision", "syn-31-b")
        step(8, "evaluate_quotes")

        policy.reset(state)
        compiled = policy._prompt_state(state)
        policy._seen_event_ids = {
            event["event_id"]
            for event in compiled["event_history"]
        }
        policy._handled_event_ids = {"e4", "e3"}
        policy._last_evaluated_offer_ids = {
            row["event_id"]
            for row in compiled["latest_offers"]
        }

        decision = policy.act(state)
        self.assertEqual(decision["type"], "award_supplier")
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(policy._calls_between_actions, 3)
        policy.on_action_accepted(
            {
                "action_id": "a9",
                "episode_id": state["episode_id"],
                **decision,
            },
            {
                **state,
                "step": 9,
            },
        )
        metrics = policy.get_run_metadata()
        self.assertEqual(
            metrics["max_model_calls_between_accepted_actions_observed"],
            3,
        )

    def test_prompts_receive_compiled_visible_state_not_oracle_payload(self):
        client = SequenceStructuredClient([terminal_award()])
        policy = ProcureHarnessPolicy(
            "fake/test-model",
            config="ph-r1-c02",
            client=client,
        )
        result = BenchmarkRunner().run(
            policy,
            "electrical-imperial-ev-phase1-031",
            max_actions=20,
        )
        self.assertEqual(result["status"], "completed")
        user_payload = client.calls[0]["messages"][1]["content"]
        self.assertIn('"context_view": "factual_compiled_v0.1"', user_payload)
        self.assertNotIn('"oracle":', user_payload)
        self.assertNotIn('"evaluation":', user_payload)
        self.assertNotIn('"trigger":', user_payload)

    def test_deferred_axes_are_not_present_in_candidate_config(self):
        forbidden = {
            "memory",
            "knowledge_graph",
            "forecasting",
            "model_routing",
            "multi_agent",
            "checkpoint_rehydration",
        }
        for row in candidate_registry():
            self.assertTrue(forbidden.isdisjoint(row))


if __name__ == "__main__":
    unittest.main()
