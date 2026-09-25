"""Regression tests for the reactive LLM baseline."""
import unittest
from unittest.mock import patch

from longprocurebench import BenchmarkRunner, ReactiveLLMPolicy
from longprocurebench.reactive_llm import SEMANTIC_ACTION_SCHEMA
from longprocurebench.litellm_client import LiteLLMClient, ModelCallError
from run_reactive_llm import model_slug


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


    def test_structured_schema_is_strict_compatible(self):
        self.assertFalse(SEMANTIC_ACTION_SCHEMA["additionalProperties"])
        arguments = SEMANTIC_ACTION_SCHEMA["properties"]["arguments"]
        self.assertFalse(arguments["additionalProperties"])
        self.assertEqual(
            set(arguments["required"]), {"awards", "reason"}
        )
        award = arguments["properties"]["awards"]["items"]
        self.assertFalse(award["additionalProperties"])
        self.assertEqual(
            set(award["required"]),
            {"scope", "supplier_id", "quote_event_id"},
        )

    def test_runtime_decision_removes_null_argument_placeholders(self):
        decision = ReactiveLLMPolicy._runtime_decision({
            "type": "evaluate_quotes",
            "supplier_id": None,
            "arguments": {"awards": None, "reason": None},
        })
        self.assertEqual(decision["arguments"], {})

    def test_failed_model_call_is_counted(self):
        class FailingClient:
            model = "fake/failing"
            def generate_action(self, *, messages, action_schema):
                raise ModelCallError(
                    "boom",
                    metrics={
                        "model": self.model,
                        "success": False,
                        "latency_ms": 50.0,
                        "prompt_tokens": 12,
                        "completion_tokens": 0,
                        "total_tokens": 12,
                        "cost_usd": 0.0001,
                        "usage_available": True,
                        "error": {"type": "ProviderError", "message": "boom"},
                    },
                )

        policy = ReactiveLLMPolicy("fake/failing", client=FailingClient())
        policy.reset({})
        with self.assertRaises(ModelCallError):
            policy.act({"step": 0})
        metrics = policy.get_run_metadata()
        self.assertEqual(metrics["model_calls_attempted"], 1)
        self.assertEqual(metrics["model_calls_failed"], 1)
        self.assertEqual(metrics["total_tokens"], 12)
        self.assertEqual(metrics["latency_ms"], 50.0)


    def test_model_slug_is_collision_resistant(self):
        first = model_slug("provider/model")
        second = model_slug("provider-model")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("provider-model--"))
        self.assertTrue(second.startswith("provider-model--"))

    def test_missing_usage_is_marked_incomplete(self):
        client = LiteLLMClient("fake/model")
        metrics = client._metrics(
            response={"choices": []},
            latency_ms=1.0,
            success=True,
            error=None,
        )
        self.assertFalse(metrics["usage_available"])
        self.assertEqual(metrics["total_tokens"], 0)

        policy = ReactiveLLMPolicy(
            "fake/model",
            client=FakeActionClient([]),
        )
        policy._calls = [metrics]
        aggregate = policy.get_run_metadata()
        self.assertTrue(aggregate["usage_incomplete"])

    def test_partial_usage_is_marked_incomplete(self):
        client = LiteLLMClient("fake/model")
        metrics = client._metrics(
            response={"usage": {"prompt_tokens": 17}, "choices": []},
            latency_ms=1.0,
            success=True,
            error=None,
        )
        self.assertFalse(metrics["usage_available"])
        self.assertEqual(metrics["prompt_tokens"], 17)
        self.assertEqual(metrics["completion_tokens"], 0)
        self.assertEqual(metrics["total_tokens"], 17)
        policy = ReactiveLLMPolicy("fake/model", client=FakeActionClient([]))
        policy._calls = [metrics]
        self.assertTrue(policy.get_run_metadata()["usage_incomplete"])

    def test_model_slug_stays_within_filesystem_component_limit(self):
        slug = model_slug("provider/" + ("x" * 400))
        self.assertLessEqual(len(slug.encode("utf-8")), 120)
        self.assertRegex(slug, r"--[0-9a-f]{10}$")

    def test_litellm_client_preserves_provider_neutral_defaults(self):
        client = LiteLLMClient("fake/model")
        self.assertEqual(client.temperature, 0.0)
        self.assertIsNone(client.reasoning_effort)

    def test_policy_records_reasoning_configuration(self):
        client = FakeActionClient([
            {"type":"identify_suppliers","supplier_id":None,"arguments":{}},
        ])
        policy = ReactiveLLMPolicy(
            "fake/test-model",
            client=client,
            temperature=None,
            reasoning_effort="medium",
        )
        policy.reset({})
        policy.act({"step":0})
        metrics = policy.get_run_metadata()
        self.assertIsNone(metrics["temperature"])
        self.assertEqual(metrics["reasoning_effort"], "medium")

    @patch("longprocurebench.litellm_client.litellm.completion_cost", return_value=0.01)
    @patch("longprocurebench.litellm_client.litellm.completion")
    def test_default_request_forwards_temperature_without_reasoning(
        self, mock_completion, mock_cost
    ):
        mock_completion.return_value = {
            "choices": [{"message": {"content": "{\"type\": \"identify_suppliers\", \"supplier_id\": null, \"arguments\": {}}"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        client = LiteLLMClient("fake/model")
        client.generate_action(messages=[{"role":"user","content":"x"}], action_schema={"type":"object"})
        request = mock_completion.call_args.kwargs
        self.assertEqual(request["temperature"], 0.0)
        self.assertNotIn("reasoning_effort", request)

    @patch("longprocurebench.litellm_client.litellm.completion_cost", return_value=0.01)
    @patch("longprocurebench.litellm_client.litellm.completion")
    def test_openai_reasoning_request_omits_temperature_and_forwards_effort(
        self, mock_completion, mock_cost
    ):
        mock_completion.return_value = {
            "choices": [{"message": {"content": "{\"type\": \"identify_suppliers\", \"supplier_id\": null, \"arguments\": {}}"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        client = LiteLLMClient(
            "openai/gpt-5.6-sol",
            temperature=None,
            reasoning_effort="medium",
        )
        client.generate_action(messages=[{"role":"user","content":"x"}], action_schema={"type":"object"})
        request = mock_completion.call_args.kwargs
        self.assertNotIn("temperature", request)
        self.assertEqual(request["reasoning_effort"], "medium")

if __name__ == "__main__":
    unittest.main()
