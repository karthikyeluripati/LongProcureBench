"""Tests for the external ReAct comparator."""
from copy import deepcopy
import json
import unittest

from longprocurebench import BenchmarkRunner, LongProcureBenchEnv
from longprocurebench.react_comparator import (
    MAX_THOUGHT_CHARS,
    REACT_STEP_SCHEMA,
    ReActLLMPolicy,
    ReActProtocolError,
)


class FakeReActClient:
    model = "fake/test-model"

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def generate_action(self, *, messages, action_schema):
        self.calls.append({
            "messages": deepcopy(messages),
            "action_schema": deepcopy(action_schema),
        })
        step = self.steps.pop(0)
        return step, {
            "model": self.model,
            "latency_ms": 2.0,
            "prompt_tokens": 40,
            "completion_tokens": 8,
            "total_tokens": 48,
            "cost_usd": 0.001,
        }


def step(thought, action_type, supplier_id=None, arguments=None):
    return {
        "thought_summary": thought,
        "action": {
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": arguments or {
                "awards": None,
                "reason": None,
            },
        },
    }


def accepted_action(state, number, decision):
    return {
        "action_id": f"a{number}",
        "episode_id": state["episode_id"],
        "type": decision["type"],
        "supplier_id": decision.get("supplier_id"),
        "arguments": decision.get("arguments") or {},
    }


class ReActComparatorTests(unittest.TestCase):
    def test_schema_is_strict_thought_plus_semantic_action(self):
        self.assertFalse(REACT_STEP_SCHEMA["additionalProperties"])
        self.assertEqual(
            set(REACT_STEP_SCHEMA["required"]),
            {"thought_summary", "action"},
        )
        self.assertNotIn(
            "minLength",
            REACT_STEP_SCHEMA["properties"]["thought_summary"],
        )
        action = REACT_STEP_SCHEMA["properties"]["action"]
        self.assertFalse(action["additionalProperties"])
        self.assertEqual(
            set(action["required"]),
            {"type", "supplier_id", "arguments"},
        )

    def test_first_step_has_empty_react_transcript_and_compiled_state(self):
        client = FakeReActClient([
            step(
                "Need the supplier directory before sourcing.",
                "identify_suppliers",
            )
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)

        decision = policy.act(state)

        self.assertEqual(decision["type"], "identify_suppliers")
        prompt = client.calls[0]["messages"][1]["content"]
        self.assertIn('"react_transcript": []', prompt)
        self.assertNotIn("source_provenance", prompt)
        self.assertNotIn("required_checkpoints", prompt)
        self.assertNotIn('"oracle"', prompt.lower())

    def test_accepted_step_becomes_thought_action_observation_history(self):
        client = FakeReActClient([
            step(
                "Reveal suppliers first.",
                "identify_suppliers",
            ),
            step(
                "Now request quotes from a visible supplier.",
                "send_rfq",
                "syn-ps-a",
            ),
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)

        first = policy.act(state)
        action = accepted_action(state, 1, first)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        second = policy.act(state)
        self.assertEqual(second["type"], "send_rfq")
        prompt = client.calls[1]["messages"][1]["content"]
        self.assertIn("Reveal suppliers first.", prompt)
        self.assertIn('"type": "identify_suppliers"', prompt)
        self.assertIn('"observation": []', prompt)

    def test_observation_events_are_preserved_in_react_transcript(self):
        client = FakeReActClient([
            step("Reveal suppliers.", "identify_suppliers"),
            step("Ask supplier A for a quote.", "send_rfq", "syn-ps-a"),
            step("Evaluate the new visible quote.", "evaluate_quotes"),
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)

        first = policy.act(state)
        action = accepted_action(state, 1, first)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        second = policy.act(state)
        action = accepted_action(state, 2, second)
        state = env.step(action)
        self.assertTrue(state["observations"])
        policy.on_action_accepted(action, state)

        policy.act(state)
        prompt = client.calls[2]["messages"][1]["content"]
        payload = json.loads(
            prompt.split("Current ReAct context:\n", 1)[1]
        )
        observation = payload["react_transcript"][1]["observation"]
        self.assertEqual(len(observation), 1)
        event = observation[0]
        self.assertEqual(event["event_id"], "e1")
        self.assertEqual(event["type"], "quote_received")
        self.assertNotIn("trigger", event)
        self.assertNotIn("synthetic", event)
        self.assertNotIn("emission_policy", event)

    def test_one_model_call_per_semantic_action(self):
        client = FakeReActClient([
            step("Reveal suppliers.", "identify_suppliers"),
            step("Evaluate visible state.", "evaluate_quotes"),
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        policy.act(state)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(policy.get_run_metadata()["model_calls"], 1)

    def test_thought_summary_is_bounded_before_persistence(self):
        long_thought = "x" * (MAX_THOUGHT_CHARS + 100)
        client = FakeReActClient([
            step(long_thought, "identify_suppliers"),
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)

        decision = policy.act(state)
        action = accepted_action(state, 1, decision)
        state = env.step(action)
        policy.on_action_accepted(action, state)

        transcript = policy.get_run_metadata()["react_transcript"]
        self.assertEqual(
            len(transcript[0]["thought_summary"]),
            MAX_THOUGHT_CHARS,
        )

    def test_empty_thought_summary_is_rejected(self):
        client = FakeReActClient([
            step("   ", "identify_suppliers"),
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)
        state = LongProcureBenchEnv().reset(
            "electrical-dla-power-supply-016"
        )
        policy.reset(state)
        with self.assertRaises(ReActProtocolError):
            policy.act(state)
        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["model_calls_attempted"], 1)
        self.assertEqual(metrics["model_calls_succeeded"], 0)
        self.assertEqual(metrics["model_calls_failed"], 1)
        self.assertEqual(
            metrics["calls"][0]["error"]["type"],
            "ReActProtocolError",
        )

    def test_reset_clears_explicit_react_transcript(self):
        client = FakeReActClient([
            step("Reveal suppliers.", "identify_suppliers"),
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)
        env = LongProcureBenchEnv()
        state = env.reset("electrical-dla-power-supply-016")
        policy.reset(state)

        decision = policy.act(state)
        action = accepted_action(state, 1, decision)
        state = env.step(action)
        policy.on_action_accepted(action, state)
        self.assertEqual(
            len(policy.get_run_metadata()["react_transcript"]),
            1,
        )

        fresh = env.reset("electrical-dla-power-supply-016")
        policy.reset(fresh)
        self.assertEqual(
            policy.get_run_metadata()["react_transcript"],
            [],
        )

    def test_runner_executes_full_react_thought_action_observation_loop(self):
        client = FakeReActClient([
            step("Reveal suppliers.", "identify_suppliers"),
            step("Request quote A.", "send_rfq", "syn-gen-a"),
            step("Request quote B.", "send_rfq", "syn-gen-b"),
            step("Request quote C.", "send_rfq", "syn-gen-c"),
            step("Follow up with C.", "send_follow_up", "syn-gen-c"),
            step(
                "Request a revised quote from C.",
                "request_quote_revision",
                "syn-gen-c",
            ),
            step("Compare the visible quotes.", "evaluate_quotes"),
            step(
                "Award the feasible preferred quote.",
                "award_supplier",
                "syn-gen-c",
                {
                    "awards": [{
                        "scope": "package",
                        "supplier_id": "syn-gen-c",
                        "quote_event_id": "e5",
                    }],
                    "reason": None,
                },
            ),
        ])
        policy = ReActLLMPolicy("fake/test-model", client=client)

        result = BenchmarkRunner().run(
            policy,
            "electrical-bongabon-generator-001",
        )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["evaluation"]["episode_success"])
        self.assertEqual(
            result["policy"]["policy_kind"],
            "llm_react_comparator",
        )
        metrics = result["policy_metrics"]
        self.assertEqual(metrics["react_steps_proposed"], 8)
        self.assertEqual(metrics["react_steps_accepted"], 8)
        self.assertEqual(len(metrics["react_transcript"]), 8)
        self.assertEqual(metrics["model_calls"], 8)

    def test_metadata_records_external_comparator_contract(self):
        client = FakeReActClient([
            step("Reveal suppliers.", "identify_suppliers"),
        ])
        policy = ReActLLMPolicy(
            "fake/test-model",
            client=client,
            temperature=None,
            reasoning_effort="medium",
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
        self.assertEqual(metrics["agent_pattern"], "react_v0.1")
        self.assertEqual(metrics["react_steps_proposed"], 1)


if __name__ == "__main__":
    unittest.main()
