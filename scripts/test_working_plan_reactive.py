"""Tests for the bounded maintained-working-plan reactive policy."""
from copy import deepcopy
import json
import unittest

from longprocurebench import BenchmarkRunner, LongProcureBenchEnv
from longprocurebench.working_plan_reactive import (
    WorkingPlanError,
    WorkingPlanReactiveLLMPolicy,
)


class FakePlanClient:
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


def _plan(
    objective,
    *,
    next_steps=None,
    stop_condition="Stop after a valid terminal decision.",
):
    return {
        "objective": objective,
        "next_steps": list(next_steps or []),
        "stop_condition": stop_condition,
    }


def _step(action_type, purpose, supplier_id=None):
    return {
        "action_type": action_type,
        "supplier_id": supplier_id,
        "purpose": purpose,
    }


def _response(
    action_type,
    *,
    supplier_id=None,
    awards=None,
    reason=None,
    next_plan=None,
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
        "next_plan": next_plan or _plan(
            "Continue procurement.",
            next_steps=[],
        ),
    }


def _action(episode_id, number, action_type, supplier_id=None, arguments=None):
    return {
        "action_id": f"a{number}",
        "episode_id": episode_id,
        "type": action_type,
        "supplier_id": supplier_id,
        "arguments": arguments or {},
    }


def _accept(policy, env, state, decision):
    number = len(state.get("action_history") or []) + 1
    action = _action(
        state["episode_id"],
        number,
        decision["type"],
        decision.get("supplier_id"),
        decision.get("arguments"),
    )
    next_state = env.step(action)
    policy.on_action_accepted(action, next_state)
    return next_state


class WorkingPlanPolicyTests(unittest.TestCase):
    def test_first_call_sees_no_plan_and_commits_only_after_acceptance(self):
        client = FakePlanClient([
            _response(
                "identify_suppliers",
                next_plan=_plan(
                    "Collect comparable offers.",
                    next_steps=[
                        _step(
                            "send_rfq",
                            "Request an offer after suppliers are visible.",
                        )
                    ],
                ),
            )
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bongabon-generator-001")
        policy.reset(state)

        decision = policy.act(state)
        prompt = client.calls[0]["messages"][1]["content"]
        self.assertIn('"current_working_plan": null', prompt)
        self.assertIsNone(policy.get_run_metadata()["final_plan"])

        state = _accept(policy, env, state, decision)
        metadata = policy.get_run_metadata()
        self.assertEqual(
            metadata["final_plan"]["objective"],
            "Collect comparable offers.",
        )
        self.assertEqual(metadata["plan_updates"], 1)

    def test_current_plan_is_visible_and_replaced_not_accumulated(self):
        first_plan = _plan(
            "Get supplier offers.",
            next_steps=[
                _step("send_rfq", "Request a quote."),
                _step("evaluate_quotes", "Compare received quotes."),
            ],
        )
        second_plan = _plan(
            "Evaluate what is now available.",
            next_steps=[
                _step("evaluate_quotes", "Compare revealed offers."),
            ],
        )
        client = FakePlanClient([
            _response("identify_suppliers", next_plan=first_plan),
            _response("request_buyer_clarification", next_plan=second_plan),
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bongabon-generator-001")
        policy.reset(state)

        first = policy.act(state)
        state = _accept(policy, env, state, first)
        second = policy.act(state)

        second_prompt = client.calls[1]["messages"][1]["content"]
        self.assertIn("Get supplier offers.", second_prompt)
        state = _accept(policy, env, state, second)

        metadata = policy.get_run_metadata()
        self.assertEqual(metadata["final_plan"], second_plan)
        self.assertNotIn(
            "send_rfq",
            [
                step["action_type"]
                for step in metadata["final_plan"]["next_steps"]
            ],
        )

    def test_invalid_supplier_plan_is_rejected_without_dropping_action(self):
        client = FakePlanClient([
            _response(
                "identify_suppliers",
                next_plan=_plan(
                    "Contact a hidden supplier.",
                    next_steps=[
                        _step(
                            "send_rfq",
                            "Request hidden supplier quote.",
                            supplier_id="syn-ps-a",
                        )
                    ],
                ),
            )
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)

        decision = policy.act(state)
        self.assertEqual(decision["type"], "identify_suppliers")
        state = _accept(policy, env, state, decision)

        metadata = policy.get_run_metadata()
        self.assertIsNone(metadata["final_plan"])
        self.assertEqual(metadata["plan_updates"], 0)
        self.assertEqual(metadata["plan_rejections"], 1)
        self.assertIn(
            "non-visible supplier",
            metadata["plan_rejection_trace"][0]["message"],
        )

    def test_overlong_plan_is_rejected_without_dropping_action(self):
        client = FakePlanClient([
            _response(
                "identify_suppliers",
                next_plan=_plan(
                    "Too long.",
                    next_steps=[
                        _step("evaluate_quotes", f"Step {index}")
                        for index in range(5)
                    ],
                ),
            )
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)

        decision = policy.act(state)
        self.assertEqual(decision["type"], "identify_suppliers")
        state = _accept(policy, env, state, decision)

        metadata = policy.get_run_metadata()
        self.assertIsNone(metadata["final_plan"])
        self.assertEqual(metadata["plan_updates"], 0)
        self.assertEqual(metadata["plan_rejections"], 1)
        self.assertIn(
            "more than 4",
            metadata["plan_rejection_trace"][0]["message"],
        )

    def test_runtime_rejected_action_does_not_commit_plan(self):
        client = FakePlanClient([
            _response(
                "award_supplier",
                supplier_id="syn-ps-a",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-ps-a",
                    "quote_event_id": "e1",
                }],
                next_plan=_plan(
                    "This plan must not survive rejection.",
                    next_steps=[],
                ),
            )
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        result = BenchmarkRunner().run(
            policy,
            "electrical-dla-power-supply-016",
            max_actions=1,
        )

        self.assertEqual(result["status"], "policy_error")
        self.assertEqual(result["trajectory"], [])
        metadata = result["policy_metrics"]
        self.assertIsNone(metadata["final_plan"])
        self.assertEqual(metadata["plan_trace"], [])
        self.assertEqual(metadata["plan_updates"], 0)

    def test_reset_clears_plan_between_episodes(self):
        client = FakePlanClient([
            _response(
                "identify_suppliers",
                next_plan=_plan(
                    "First episode only.",
                    next_steps=[],
                ),
            )
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)
        decision = policy.act(state)
        state = _accept(policy, env, state, decision)
        self.assertIsNotNone(policy.get_run_metadata()["final_plan"])

        second = LongProcureBenchEnv().reset(
            "electrical-vre-generator-020"
        )
        policy.reset(second)
        self.assertIsNone(policy.get_run_metadata()["final_plan"])
        self.assertEqual(policy.get_run_metadata()["plan_updates"], 0)

    def test_policy_uses_one_model_call_per_action(self):
        client = FakePlanClient([
            _response(
                "identify_suppliers",
                next_plan=_plan("Continue.", next_steps=[]),
            ),
            _response(
                "request_buyer_clarification",
                next_plan=_plan("Finish.", next_steps=[]),
            ),
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)

        first = policy.act(state)
        state = _accept(policy, env, state, first)
        second = policy.act(state)
        state = _accept(policy, env, state, second)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            policy.get_run_metadata()["model_calls_attempted"],
            2,
        )

    def test_response_schema_uses_provider_safe_subset(self):
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        schema = WorkingPlanReactiveLLMPolicy._response_schema(state)
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

    def test_metadata_records_plan_trace_without_prompt_history(self):
        first_plan = _plan(
            "Get offers.",
            next_steps=[
                _step("send_rfq", "Request an offer."),
            ],
        )
        second_plan = _plan(
            "Compare offers.",
            next_steps=[
                _step("evaluate_quotes", "Compare offers."),
            ],
        )
        client = FakePlanClient([
            _response("identify_suppliers", next_plan=first_plan),
            _response("request_buyer_clarification", next_plan=second_plan),
        ])
        policy = WorkingPlanReactiveLLMPolicy(
            "fake/test-model",
            client=client,
        )
        env = LongProcureBenchEnv()
        state = env.reset("electrical-bongabon-generator-001")
        policy.reset(state)

        first = policy.act(state)
        state = _accept(policy, env, state, first)
        second = policy.act(state)
        state = _accept(policy, env, state, second)

        metadata = policy.get_run_metadata()
        self.assertEqual(metadata["state_strategy"], "maintained_working_plan_v0.1")
        self.assertEqual(metadata["plan_updates"], 2)
        self.assertEqual(metadata["plan_rejections"], 0)
        self.assertEqual(metadata["max_plan_steps"], 1)
        self.assertEqual(len(metadata["plan_trace"]), 2)
        self.assertEqual(metadata["plan_rejection_trace"], [])

        second_prompt = client.calls[1]["messages"][1]["content"]
        self.assertIn("Get offers.", second_prompt)
        self.assertNotIn('"plan_trace"', second_prompt)

    def test_prompt_contains_no_evaluator_or_oracle_state(self):
        client = FakePlanClient([
            _response("identify_suppliers")
        ])
        policy = WorkingPlanReactiveLLMPolicy(
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
