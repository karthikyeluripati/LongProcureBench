"""Tests for the static Plan-and-Execute comparator."""
from copy import deepcopy
import unittest

from longprocurebench import LongProcureBenchEnv
from longprocurebench.plan_execute_comparator import (
    PlanExecuteLLMPolicy,
    PlanExecuteProtocolError,
)
from run_plan_execute_comparator import (
    TARGETED_PILOT_EPISODES,
    resolve_pilot_sampling,
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


def _accept_exception(policy, action, event_ids, *, state_step=1):
    policy._pending_execution = {
        "plan_step_index": 0,
        "action": deepcopy(action),
        "state_step": max(0, state_step - 1),
        "exception_event_ids": list(event_ids),
    }
    policy.on_action_accepted(
        deepcopy(action),
        {"step": state_step},
    )


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

    def test_planner_accepts_bounded_descriptive_step_text(self):
        plan = _plan()
        plan["steps"][0]["purpose"] = "p" * 400
        plan["steps"][0]["condition"] = "c" * 400
        PlanExecuteLLMPolicy._validate_plan(
            PlanExecuteLLMPolicy.__new__(PlanExecuteLLMPolicy),
            plan,
        )

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

    def test_plan_step_zero_rejects_planned_initial_action(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-transformer-013"
        )
        client = SequenceClient([
            _plan(),
            _executor(0, "request_buyer_clarification"),
        ])
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=client,
        )
        policy.reset(state)

        with self.assertRaises(PlanExecuteProtocolError):
            policy.act(state)

        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["model_calls_failed"], 1)

    def test_event_can_justify_exception_for_planned_operation(self):
        plan = _plan()
        plan["steps"].append({
            "step_id": 6,
            "operation": "send_follow_up",
            "purpose": "Recover a supplier that newly stops responding.",
            "condition": "Use after a visible supplier non-response.",
        })
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=SequenceClient([]),
        )
        policy._fixed_plan = plan
        policy._initial_event_ids = set()
        policy._event_first_seen = {"e-new": 1}
        policy._executor_decision_index = 1

        event_ids = policy._validate_unplanned_exception(
            {
                "type": "send_follow_up",
                "supplier_id": "syn-a",
                "arguments": {"awards": None, "reason": None},
            },
            {
                "event_history": [
                    {
                        "event_id": "e-new",
                        "type": "supplier_non_response",
                        "supplier_id": "syn-a",
                    },
                ],
            },
        )
        self.assertEqual(event_ids, ["e-new"])

    def test_withdrawal_recovery_attributes_new_cross_supplier_event(self):
        plan = _plan()
        plan["steps"].append({
            "step_id": 6,
            "operation": "request_quote_revision",
            "purpose": "Repair a remaining supplier offer after disruption.",
            "condition": "Use when a newly visible disruption makes revision useful.",
        })
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=SequenceClient([]),
        )
        policy._fixed_plan = plan
        policy._initial_event_ids = set()
        policy._event_first_seen = {
            "e-c-quote": 1,
            "e-a-withdrawal": 2,
        }
        policy._executor_decision_index = 2

        event_ids = policy._validate_unplanned_exception(
            {
                "type": "request_quote_revision",
                "supplier_id": "syn-burauen-c",
                "arguments": {"awards": None, "reason": None},
            },
            {
                "event_history": [
                    {
                        "event_id": "e-c-quote",
                        "type": "quote_received",
                        "supplier_id": "syn-burauen-c",
                    },
                    {
                        "event_id": "e-a-withdrawal",
                        "type": "supplier_withdrawal",
                        "supplier_id": "syn-burauen-a",
                    },
                ],
            },
        )
        self.assertEqual(event_ids, ["e-a-withdrawal"])

    def test_requirement_change_can_drive_amendment_then_supplier_revisions(self):
        plan = _plan()
        plan["steps"].extend([
            {
                "step_id": 6,
                "operation": "issue_amendment",
                "purpose": "Issue an amendment after a buyer change.",
                "condition": "Use when a visible requirement changes.",
            },
            {
                "step_id": 7,
                "operation": "request_quote_revision",
                "purpose": "Refresh supplier offers after an amendment.",
                "condition": "Use when changed requirements make prior offers stale.",
            },
        ])
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=SequenceClient([]),
        )
        policy._fixed_plan = plan
        policy._initial_event_ids = set()
        policy._event_first_seen = {
            "e-b-quote": 1,
            "e-change": 2,
        }
        policy._executor_decision_index = 3

        compiled = {
            "event_history": [
                {
                    "event_id": "e-b-quote",
                    "type": "quote_received",
                    "supplier_id": "syn-ps-b",
                },
                {
                    "event_id": "e-change",
                    "type": "requirement_change",
                    "supplier_id": None,
                },
            ],
        }

        amendment_action = {
            "type": "issue_amendment",
            "supplier_id": None,
            "arguments": {},
        }
        amendment_events = policy._validate_unplanned_exception(
            {
                "type": "issue_amendment",
                "supplier_id": None,
                "arguments": {"awards": None, "reason": None},
            },
            compiled,
        )
        self.assertEqual(amendment_events, ["e-change"])
        _accept_exception(
            policy,
            amendment_action,
            amendment_events,
            state_step=4,
        )

        revision_a_action = {
            "type": "request_quote_revision",
            "supplier_id": "syn-ps-a",
            "arguments": {},
        }
        revision_a_events = policy._validate_unplanned_exception(
            {
                "type": "request_quote_revision",
                "supplier_id": "syn-ps-a",
                "arguments": {"awards": None, "reason": None},
            },
            compiled,
        )
        self.assertEqual(revision_a_events, ["e-change"])
        _accept_exception(
            policy,
            revision_a_action,
            revision_a_events,
            state_step=5,
        )

        revision_b_action = {
            "type": "request_quote_revision",
            "supplier_id": "syn-ps-b",
            "arguments": {},
        }
        revision_b_events = policy._validate_unplanned_exception(
            {
                "type": "request_quote_revision",
                "supplier_id": "syn-ps-b",
                "arguments": {"awards": None, "reason": None},
            },
            compiled,
        )
        self.assertEqual(revision_b_events, ["e-change"])
        _accept_exception(
            policy,
            revision_b_action,
            revision_b_events,
            state_step=6,
        )

        self.assertEqual(
            policy._exception_causal_floor[
                ("request_quote_revision", "syn-ps-b")
            ],
            2,
        )
        with self.assertRaises(PlanExecuteProtocolError):
            policy._validate_unplanned_exception(
                {
                    "type": "request_quote_revision",
                    "supplier_id": "syn-ps-b",
                    "arguments": {"awards": None, "reason": None},
                },
                compiled,
            )

    def test_act_discovers_newer_event_before_reopening_revision(self):
        plan = _plan()
        plan["steps"].append({
            "step_id": 6,
            "operation": "request_quote_revision",
            "purpose": "Refresh a supplier offer after new evidence.",
            "condition": "Use when new visible evidence makes revision useful.",
        })

        revision_response = _executor(
            0,
            "request_quote_revision",
            supplier_id="syn-b",
        )
        client = SequenceClient([
            _executor(2, "identify_suppliers"),
            revision_response,
            revision_response,
            revision_response,
        ])
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=client,
        )
        base_state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(base_state)
        policy._fixed_plan = plan

        old_quote_state = deepcopy(base_state)
        old_quote_state["revealed_events"] = [
            {
                "event_id": "e-old",
                "type": "quote_received",
                "supplier_id": "syn-b",
                "observation": "Older visible quote.",
                "details": {},
                "offer_scope": {"kind": "package"},
            },
        ]

        planned_action = policy.act(old_quote_state)
        self.assertEqual(
            policy._event_first_seen,
            {"e-old": 1},
        )
        policy.on_action_accepted(
            {
                "type": planned_action["type"],
                "supplier_id": planned_action["supplier_id"],
                "arguments": deepcopy(planned_action["arguments"]),
            },
            {"step": 1},
        )

        change_state = deepcopy(old_quote_state)
        change_state["revealed_events"].append({
            "event_id": "e-change",
            "type": "requirement_change",
            "supplier_id": None,
            "observation": "Buyer changed the requirement.",
            "details": {},
        })

        first_revision = policy.act(change_state)
        self.assertEqual(
            policy._event_first_seen,
            {
                "e-old": 1,
                "e-change": 2,
            },
        )
        self.assertEqual(
            policy._pending_execution["exception_event_ids"],
            ["e-change"],
        )
        policy.on_action_accepted(
            {
                "type": first_revision["type"],
                "supplier_id": first_revision["supplier_id"],
                "arguments": deepcopy(first_revision["arguments"]),
            },
            {"step": 2},
        )
        self.assertEqual(
            policy._exception_causal_floor[
                ("request_quote_revision", "syn-b")
            ],
            2,
        )

        with self.assertRaises(PlanExecuteProtocolError):
            policy.act(change_state)
        self.assertNotIn("e-new", policy._event_first_seen)

        newer_state = deepcopy(change_state)
        newer_state["revealed_events"].append({
            "event_id": "e-new",
            "type": "lead_time_change",
            "supplier_id": "syn-b",
            "observation": "Supplier B reports a new lead-time change.",
            "details": {},
        })

        reopened_action = policy.act(newer_state)
        self.assertEqual(
            policy._event_first_seen["e-new"],
            4,
        )
        self.assertEqual(
            policy._pending_execution["exception_event_ids"],
            ["e-new"],
        )
        policy.on_action_accepted(
            {
                "type": reopened_action["type"],
                "supplier_id": reopened_action["supplier_id"],
                "arguments": deepcopy(reopened_action["arguments"]),
            },
            {"step": 3},
        )
        self.assertEqual(
            policy._exception_causal_floor[
                ("request_quote_revision", "syn-b")
            ],
            4,
        )

    def test_operation_absent_from_plan_can_be_exception(self):
        policy = PlanExecuteLLMPolicy(
            "fake/test-model",
            client=SequenceClient([]),
        )
        policy._fixed_plan = _plan()
        policy._initial_event_ids = set()

        event_ids = policy._validate_unplanned_exception(
            {
                "type": "issue_amendment",
                "supplier_id": None,
                "arguments": {"awards": None, "reason": None},
            },
            {"event_history": []},
        )
        self.assertEqual(event_ids, [])

    def test_default_runner_matches_frozen_targeted_pilot(self):
        self.assertEqual(
            TARGETED_PILOT_EPISODES,
            [
                "electrical-burauen-generator-008",
                "electrical-dla-transformer-013",
                "electrical-dla-power-supply-016",
            ],
        )
        temperature, reasoning_effort = resolve_pilot_sampling(
            None,
            False,
            None,
        )
        self.assertIsNone(temperature)
        self.assertEqual(reasoning_effort, "medium")

    def test_omit_temperature_alone_keeps_medium_reasoning(self):
        temperature, reasoning_effort = resolve_pilot_sampling(
            None,
            True,
            None,
        )
        self.assertIsNone(temperature)
        self.assertEqual(reasoning_effort, "medium")

    def test_explicit_temperature_still_overrides_default_sampling(self):
        temperature, reasoning_effort = resolve_pilot_sampling(
            0.2,
            False,
            None,
        )
        self.assertEqual(temperature, 0.2)
        self.assertIsNone(reasoning_effort)

    def test_executor_prompt_matches_exception_and_multi_award_contract(self):
        prompt = PlanExecuteLLMPolicy.EXECUTOR_PROMPT
        self.assertIn(
            "Do not label an ordinary planned action as an exception",
            prompt,
        )
        self.assertIn(
            "for multiple awards, top-level supplier_id must be",
            prompt,
        )
        self.assertIn("null.", prompt)

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
