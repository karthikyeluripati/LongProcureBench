"""Regression tests for the deterministic LongProcureBench runtime."""
import json
import unittest

from jsonschema import ValidationError

from longprocurebench import EnvironmentError, LongProcureBenchEnv


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env = LongProcureBenchEnv()

    @staticmethod
    def action(n, episode_id, action_type, supplier_id=None, **arguments):
        return {
            "action_id": f"a{n}",
            "episode_id": episode_id,
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": arguments,
        }

    def test_reset_exposes_initial_state_but_not_future_episode_state(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        self.assertEqual(state["step"], 0)
        self.assertFalse(state["terminated"])
        self.assertEqual(state["visible_suppliers"], [])
        self.assertEqual(state["observations"], [])
        self.assertEqual(state["revealed_events"], [])
        self.assertEqual(state["action_history"], [])
        serialized = json.dumps(state)
        self.assertNotIn("Synthetic Generator Supplier A", serialized)
        self.assertNotIn("Supplier A submits a PHP 382,000 quotation", serialized)
        self.assertEqual(
            state["initial_state"]["package_id"], "ph-bongabon-wd-13076574"
        )

    def test_identify_suppliers_reveals_directory(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        state = self.env.step(
            self.action(1, state["episode_id"], "identify_suppliers")
        )
        self.assertEqual(len(state["visible_suppliers"]), 3)
        self.assertEqual(
            {supplier["supplier_id"] for supplier in state["visible_suppliers"]},
            {"syn-gen-a", "syn-gen-b", "syn-gen-c"},
        )

    def test_supplier_action_requires_revealed_directory(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        with self.assertRaises(EnvironmentError):
            self.env.step(
                self.action(
                    1, state["episode_id"], "send_rfq", supplier_id="syn-gen-a"
                )
            )
        self.assertEqual(self.env.state["step"], 0)

    def test_supplier_scoped_trigger_and_one_shot_consumption(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        episode_id = state["episode_id"]
        self.env.step(self.action(1, episode_id, "identify_suppliers"))
        state = self.env.step(
            self.action(2, episode_id, "send_rfq", supplier_id="syn-gen-a")
        )
        self.assertEqual(
            [event["event_id"] for event in state["observations"]], ["e1"]
        )
        state = self.env.step(
            self.action(3, episode_id, "send_rfq", supplier_id="syn-gen-a")
        )
        self.assertEqual(state["observations"], [])
        self.assertEqual(
            [event["event_id"] for event in state["revealed_events"]], ["e1"]
        )

    def test_at_step_event_fires_after_after_action_event(self):
        state = self.env.reset("electrical-neust-cable-003")
        episode_id = state["episode_id"]
        self.env.step(self.action(1, episode_id, "identify_suppliers"))
        self.env.step(
            self.action(2, episode_id, "send_rfq", supplier_id="syn-wire-a")
        )
        self.env.step(
            self.action(3, episode_id, "send_rfq", supplier_id="syn-wire-b")
        )
        state = self.env.step(
            self.action(4, episode_id, "send_rfq", supplier_id="syn-wire-c")
        )
        self.assertEqual(
            [event["event_id"] for event in state["observations"]],
            ["e3", "e4"],
        )
        self.assertEqual(state["observations"][0]["type"], "supplier_non_response")
        self.assertEqual(state["observations"][1]["type"], "quantity_change")

    def test_invalid_action_is_rejected_without_advancing_time(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        with self.assertRaises(ValidationError):
            self.env.step(
                {
                    "action_id": "a1",
                    "episode_id": state["episode_id"],
                    "type": "not-an-action",
                    "supplier_id": None,
                    "arguments": {},
                }
            )
        self.assertEqual(self.env.state["step"], 0)
        self.assertEqual(self.env.state["action_history"], [])

    def test_award_terminates_and_future_actions_are_rejected(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        episode_id = state["episode_id"]
        actions = [
            self.action(1, episode_id, "identify_suppliers"),
            self.action(2, episode_id, "send_rfq", supplier_id="syn-gen-a"),
            self.action(3, episode_id, "send_rfq", supplier_id="syn-gen-b"),
            self.action(4, episode_id, "send_rfq", supplier_id="syn-gen-c"),
            self.action(5, episode_id, "send_follow_up", supplier_id="syn-gen-c"),
            self.action(
                6, episode_id, "request_quote_revision", supplier_id="syn-gen-c"
            ),
        ]
        for action in actions:
            state = self.env.step(action)
        state = self.env.step(
            self.action(
                7,
                episode_id,
                "award_supplier",
                supplier_id="syn-gen-c",
                awards=[
                    {
                        "scope": "package",
                        "supplier_id": "syn-gen-c",
                        "quote_event_id": "e5",
                    }
                ],
            )
        )
        self.assertTrue(state["terminated"])
        self.assertEqual(state["terminal"]["decision"], "award")
        with self.assertRaises(EnvironmentError):
            self.env.step(self.action(8, episode_id, "evaluate_quotes"))

    def test_no_award_is_a_terminal_action(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        state = self.env.step(
            self.action(
                1,
                state["episode_id"],
                "no_award",
                reason="No acceptable offer remains.",
            )
        )
        self.assertTrue(state["terminated"])
        self.assertEqual(state["terminal"]["decision"], "no_award")

    def test_award_cannot_reference_hidden_quote(self):
        state = self.env.reset("electrical-bongabon-generator-001")
        episode_id = state["episode_id"]
        self.env.step(self.action(1, episode_id, "identify_suppliers"))
        with self.assertRaises(EnvironmentError):
            self.env.step(
                self.action(
                    2,
                    episode_id,
                    "award_supplier",
                    supplier_id="syn-gen-c",
                    awards=[
                        {
                            "scope": "package",
                            "supplier_id": "syn-gen-c",
                            "quote_event_id": "e5",
                        }
                    ],
                )
            )
        self.assertEqual(self.env.state["step"], 1)

    def _run_trace(self, episode_id, specs, awards):
        state = self.env.reset(episode_id)
        for n, spec in enumerate(specs, start=1):
            action_type, supplier_id = spec
            state = self.env.step(
                self.action(
                    n,
                    episode_id,
                    action_type,
                    supplier_id=supplier_id,
                )
            )
        state = self.env.step(
            self.action(
                len(specs) + 1,
                episode_id,
                "award_supplier",
                supplier_id=(
                    awards[0]["supplier_id"] if len(awards) == 1 else None
                ),
                awards=awards,
            )
        )
        self.assertTrue(state["terminated"])
        self.assertEqual(state["terminal"]["decision"], "award")
        return state

    def test_all_five_frozen_episodes_execute_deterministically(self):
        traces = {
            "electrical-bongabon-generator-001": (
                [
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-gen-a"),
                    ("send_rfq", "syn-gen-b"),
                    ("send_rfq", "syn-gen-c"),
                    ("send_follow_up", "syn-gen-c"),
                    ("request_quote_revision", "syn-gen-c"),
                    ("evaluate_quotes", None),
                ],
                [
                    {
                        "scope": "package",
                        "supplier_id": "syn-gen-c",
                        "quote_event_id": "e5",
                    }
                ],
                5,
            ),
            "electrical-national-museum-lighting-002": (
                [
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-light-a"),
                    ("send_rfq", "syn-light-b"),
                    ("send_rfq", "syn-light-c"),
                    ("request_quote_revision", "syn-light-c"),
                    ("evaluate_quotes", None),
                ],
                [
                    {
                        "scope": "lot-1",
                        "supplier_id": "syn-light-a",
                        "quote_event_id": "e1",
                    },
                    {
                        "scope": "lot-2",
                        "supplier_id": "syn-light-c",
                        "quote_event_id": "e4",
                    },
                ],
                4,
            ),
            "electrical-neust-cable-003": (
                [
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-wire-a"),
                    ("send_rfq", "syn-wire-b"),
                    ("send_rfq", "syn-wire-c"),
                    ("issue_amendment", None),
                    ("request_quote_revision", "syn-wire-a"),
                    ("request_quote_revision", "syn-wire-b"),
                    ("send_follow_up", "syn-wire-c"),
                    ("evaluate_quotes", None),
                ],
                [
                    {
                        "scope": "package",
                        "supplier_id": "syn-wire-c",
                        "quote_event_id": "e7",
                    }
                ],
                7,
            ),
            "electrical-dla-breaker-004": (
                [
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-breaker-a"),
                    ("send_rfq", "syn-breaker-b"),
                    ("send_rfq", "syn-breaker-c"),
                    ("evaluate_quotes", None),
                    ("request_quote_revision", "syn-breaker-c"),
                    ("evaluate_quotes", None),
                ],
                [
                    {
                        "scope": "package",
                        "supplier_id": "syn-breaker-c",
                        "quote_event_id": "e5",
                    }
                ],
                5,
            ),
            "electrical-barrie-transformer-005": (
                [
                    ("request_buyer_clarification", None),
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-xfmr-a"),
                    ("send_rfq", "syn-xfmr-b"),
                    ("request_quote_revision", "syn-xfmr-b"),
                    ("answer_supplier_question", "syn-xfmr-b"),
                    ("send_rfq", "syn-xfmr-c"),
                    ("evaluate_quotes", None),
                ],
                [
                    {
                        "scope": "package",
                        "supplier_id": "syn-xfmr-b",
                        "quote_event_id": "e5",
                    }
                ],
                6,
            ),
        }

        for episode_id, (specs, awards, expected_events) in traces.items():
            with self.subTest(episode_id=episode_id):
                self.env = LongProcureBenchEnv()
                state = self._run_trace(episode_id, specs, awards)
                self.assertEqual(len(state["revealed_events"]), expected_events)


if __name__ == "__main__":
    unittest.main()
