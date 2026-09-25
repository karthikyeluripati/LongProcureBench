"""Regression tests for the reactive LLM baseline."""
import unittest

from longprocurebench import BenchmarkRunner, ReactiveLLMPolicy


class FakeActionClient:
    model = "fake/test-model"
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []
    def generate_action(self, *, messages, action_schema):
        self.calls.append({"messages": messages, "action_schema": action_schema})
        decision = self.decisions.pop(0)
        return decision, {
            "model": self.model,
            "latency_ms": 12.5,
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "cost_usd": 0.001,
        }


class ReactiveLLMPolicyTests(unittest.TestCase):
    def test_policy_uses_current_visible_state_only(self):
        client = FakeActionClient([{"type":"identify_suppliers","supplier_id":None,"arguments":{}}])
        policy = ReactiveLLMPolicy("fake/test-model", client=client)
        state = {"episode_id":"episode","step":0,"visible_suppliers":[],"observations":[]}
        policy.reset(state)
        decision = policy.act(state)
        self.assertEqual(decision["type"], "identify_suppliers")
        prompt = client.calls[0]["messages"][1]["content"]
        self.assertIn('"visible_suppliers": []', prompt)
        self.assertNotIn("oracle", prompt.lower())

    def test_policy_does_not_carry_hidden_conversation_memory(self):
        client = FakeActionClient([
            {"type":"identify_suppliers","supplier_id":None,"arguments":{}},
            {"type":"evaluate_quotes","supplier_id":None,"arguments":{}},
        ])
        policy = ReactiveLLMPolicy("fake/test-model", client=client)
        policy.reset({"episode_id":"episode"})
        policy.act({"episode_id":"episode","step":0})
        policy.act({"episode_id":"episode","step":1})
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all(len(call["messages"]) == 2 for call in client.calls))

    def test_run_metadata_aggregates_usage(self):
        client = FakeActionClient([
            {"type":"identify_suppliers","supplier_id":None,"arguments":{}},
            {"type":"evaluate_quotes","supplier_id":None,"arguments":{}},
        ])
        policy = ReactiveLLMPolicy("fake/test-model", client=client)
        policy.reset({})
        policy.act({"step":0})
        policy.act({"step":1})
        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["model_calls"], 2)
        self.assertEqual(metrics["total_tokens"], 220)
        self.assertEqual(metrics["latency_ms"], 25.0)
        self.assertAlmostEqual(metrics["cost_usd"], 0.002)

    def test_runner_captures_llm_policy_metrics(self):
        decisions = [
            {"type":"identify_suppliers","supplier_id":None,"arguments":{}},
            {"type":"send_rfq","supplier_id":"syn-gen-a","arguments":{}},
            {"type":"send_rfq","supplier_id":"syn-gen-b","arguments":{}},
            {"type":"send_rfq","supplier_id":"syn-gen-c","arguments":{}},
            {"type":"send_follow_up","supplier_id":"syn-gen-c","arguments":{}},
            {"type":"request_quote_revision","supplier_id":"syn-gen-c","arguments":{}},
            {"type":"evaluate_quotes","supplier_id":None,"arguments":{}},
            {"type":"award_supplier","supplier_id":"syn-gen-c","arguments":{"awards":[{"scope":"package","supplier_id":"syn-gen-c","quote_event_id":"e5"}]}},
        ]
        policy = ReactiveLLMPolicy("fake/test-model", client=FakeActionClient(decisions))
        result = BenchmarkRunner().run(policy, "electrical-bongabon-generator-001")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["evaluation"]["episode_success"])
        self.assertEqual(result["policy"]["policy_kind"], "llm_reactive_baseline")
        self.assertEqual(result["policy_metrics"]["model"], "fake/test-model")
        self.assertEqual(result["policy_metrics"]["model_calls"], 8)


if __name__ == "__main__":
    unittest.main()
