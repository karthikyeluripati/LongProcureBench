"""Regression tests for Evaluator v0.1."""
import copy
import unittest

from longprocurebench import LongProcureBenchEnv, LongProcureBenchEvaluator
from validate_evaluation import validate_config


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = LongProcureBenchEvaluator()

    @staticmethod
    def action(n, episode_id, action_type, supplier_id=None, **arguments):
        return {
            "action_id": f"a{n}",
            "episode_id": episode_id,
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": arguments,
        }

    def _actions(self, episode_id, specs, awards):
        actions = []
        for n, (action_type, supplier_id) in enumerate(specs, start=1):
            actions.append(self.action(n, episode_id, action_type, supplier_id))
        actions.append(self.action(
            len(actions) + 1,
            episode_id,
            "award_supplier",
            awards[0]["supplier_id"] if len(awards) == 1 else None,
            awards=awards,
        ))
        return actions

    def reference_traces(self):
        return {
            "electrical-bongabon-generator-001": self._actions(
                "electrical-bongabon-generator-001",
                [
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-gen-a"),
                    ("send_rfq", "syn-gen-b"),
                    ("send_rfq", "syn-gen-c"),
                    ("send_follow_up", "syn-gen-c"),
                    ("request_quote_revision", "syn-gen-c"),
                    ("evaluate_quotes", None),
                ],
                [{"scope":"package","supplier_id":"syn-gen-c","quote_event_id":"e5"}],
            ),
            "electrical-national-museum-lighting-002": self._actions(
                "electrical-national-museum-lighting-002",
                [
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-light-a"),
                    ("send_rfq", "syn-light-b"),
                    ("send_rfq", "syn-light-c"),
                    ("request_quote_revision", "syn-light-c"),
                    ("evaluate_quotes", None),
                ],
                [
                    {"scope":"lot-1","supplier_id":"syn-light-a","quote_event_id":"e1"},
                    {"scope":"lot-2","supplier_id":"syn-light-c","quote_event_id":"e4"},
                ],
            ),
            "electrical-neust-cable-003": self._actions(
                "electrical-neust-cable-003",
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
                [{"scope":"package","supplier_id":"syn-wire-c","quote_event_id":"e7"}],
            ),
            "electrical-dla-breaker-004": self._actions(
                "electrical-dla-breaker-004",
                [
                    ("identify_suppliers", None),
                    ("send_rfq", "syn-breaker-a"),
                    ("send_rfq", "syn-breaker-b"),
                    ("send_rfq", "syn-breaker-c"),
                    ("evaluate_quotes", None),
                    ("request_quote_revision", "syn-breaker-c"),
                    ("evaluate_quotes", None),
                ],
                [{"scope":"package","supplier_id":"syn-breaker-c","quote_event_id":"e5"}],
            ),
            "electrical-barrie-transformer-005": self._actions(
                "electrical-barrie-transformer-005",
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
                [{"scope":"package","supplier_id":"syn-xfmr-b","quote_event_id":"e5"}],
            ),
        }

    def test_reference_traces_pass_all_dimensions(self):
        for episode_id, actions in self.reference_traces().items():
            with self.subTest(episode_id=episode_id):
                report = self.evaluator.evaluate_actions(episode_id, actions)
                self.assertTrue(report["episode_success"])
                self.assertTrue(report["terminal_outcome"]["correct"])
                self.assertTrue(report["hard_constraints"]["all_passed"])
                self.assertTrue(report["required_checkpoints"]["all_completed"])
                self.assertEqual(report["constraint_violations"], [])
                self.assertEqual(report["efficiency"]["accepted_actions"], len(actions))

    def test_wrong_generator_award_fails_terminal_and_lead_time(self):
        eid="electrical-bongabon-generator-001"
        actions=[
            self.action(1,eid,"identify_suppliers"),
            self.action(2,eid,"send_rfq","syn-gen-a"),
            self.action(3,eid,"send_rfq","syn-gen-b"),
            self.action(4,eid,"send_rfq","syn-gen-c"),
            self.action(5,eid,"award_supplier","syn-gen-b",awards=[
                {"scope":"package","supplier_id":"syn-gen-b","quote_event_id":"e2"}
            ]),
        ]
        report=self.evaluator.evaluate_actions(eid,actions)
        self.assertFalse(report["episode_success"])
        self.assertFalse(report["terminal_outcome"]["correct"])
        self.assertIn("c2",report["constraint_violations"])

    def test_ineligible_dla_award_is_constraint_violation(self):
        eid="electrical-dla-breaker-004"
        actions=[
            self.action(1,eid,"identify_suppliers"),
            self.action(2,eid,"send_rfq","syn-breaker-a"),
            self.action(3,eid,"send_rfq","syn-breaker-b"),
            self.action(4,eid,"send_rfq","syn-breaker-c"),
            self.action(5,eid,"award_supplier","syn-breaker-b",awards=[
                {"scope":"package","supplier_id":"syn-breaker-b","quote_event_id":"e2"}
            ]),
        ]
        report=self.evaluator.evaluate_actions(eid,actions)
        self.assertIn("c1",report["constraint_violations"])

    def test_missing_required_process_checkpoint_blocks_success(self):
        eid="electrical-dla-breaker-004"
        actions=[
            self.action(1,eid,"identify_suppliers"),
            self.action(2,eid,"send_rfq","syn-breaker-a"),
            self.action(3,eid,"send_rfq","syn-breaker-b"),
            self.action(4,eid,"send_rfq","syn-breaker-c"),
            self.action(5,eid,"request_quote_revision","syn-breaker-c"),
            self.action(6,eid,"award_supplier","syn-breaker-c",awards=[
                {"scope":"package","supplier_id":"syn-breaker-c","quote_event_id":"e5"}
            ]),
        ]
        report=self.evaluator.evaluate_actions(eid,actions)
        self.assertTrue(report["terminal_outcome"]["correct"])
        self.assertTrue(report["hard_constraints"]["all_passed"])
        self.assertFalse(report["required_checkpoints"]["all_completed"])
        self.assertFalse(report["episode_success"])

    def test_evaluate_state_replays_runtime_history(self):
        eid="electrical-bongabon-generator-001"
        env=LongProcureBenchEnv()
        state=env.reset(eid)
        for action in self.reference_traces()[eid]:
            state=env.step(action)
        report=self.evaluator.evaluate_state(state)
        self.assertTrue(report["episode_success"])


    def test_amendment_checkpoint_requires_awarded_quote_after_amendment(self):
        eid = "electrical-neust-cable-003"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-wire-a"),
            self.action(3, eid, "send_rfq", "syn-wire-b"),
            self.action(4, eid, "send_rfq", "syn-wire-c"),
            self.action(5, eid, "send_follow_up", "syn-wire-c"),
            self.action(6, eid, "issue_amendment"),
            self.action(7, eid, "request_quote_revision", "syn-wire-a"),
            self.action(8, eid, "evaluate_quotes"),
            self.action(
                9,
                eid,
                "award_supplier",
                "syn-wire-c",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-wire-c",
                    "quote_event_id": "e7",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        self.assertTrue(report["terminal_outcome"]["correct"])
        self.assertTrue(report["hard_constraints"]["all_passed"])
        checkpoints = {
            item["checkpoint"]: item
            for item in report["required_checkpoints"]["results"]
        }
        self.assertFalse(checkpoints["handle_amendment"]["complete"])
        self.assertFalse(report["episode_success"])

    def test_withdrawal_recovery_requires_new_quote_then_reevaluation(self):
        eid = "electrical-dla-breaker-004"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-breaker-a"),
            self.action(3, eid, "send_rfq", "syn-breaker-b"),
            self.action(4, eid, "send_rfq", "syn-breaker-c"),
            self.action(5, eid, "request_quote_revision", "syn-breaker-c"),
            self.action(6, eid, "evaluate_quotes"),
            self.action(7, eid, "evaluate_quotes"),
            self.action(
                8,
                eid,
                "award_supplier",
                "syn-breaker-c",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-breaker-c",
                    "quote_event_id": "e5",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        self.assertTrue(report["terminal_outcome"]["correct"])
        self.assertTrue(report["hard_constraints"]["all_passed"])
        checkpoints = {
            item["checkpoint"]: item
            for item in report["required_checkpoints"]["results"]
        }
        self.assertFalse(checkpoints["recover_from_withdrawal"]["complete"])
        self.assertFalse(report["episode_success"])

    def test_award_quote_equals_requires_non_null_value(self):
        config = copy.deepcopy(
            self.evaluator.load_config(
                "electrical-bongabon-generator-001"
            )
        )
        equals_check = next(
            check
            for rule in config["constraint_rules"]
            for check in rule["checks"]
            if check["kind"] == "award_quote_equals"
        )
        equals_check["value"] = None
        with self.assertRaisesRegex(
            ValueError, "award_quote_equals requires value"
        ):
            validate_config(config)

    def test_feasible_but_more_expensive_bongabon_award_is_not_terminally_wrong(self):
        eid = "electrical-bongabon-generator-001"
        actions = self._actions(
            eid,
            [
                ("identify_suppliers", None),
                ("send_rfq", "syn-gen-a"),
                ("send_rfq", "syn-gen-b"),
                ("send_rfq", "syn-gen-c"),
                ("send_follow_up", "syn-gen-c"),
                ("request_quote_revision", "syn-gen-c"),
                ("evaluate_quotes", None),
            ],
            [{"scope":"package","supplier_id":"syn-gen-a","quote_event_id":"e1"}],
        )
        report = self.evaluator.evaluate_actions(eid, actions)
        self.assertTrue(report["terminal_outcome"]["correct"])
        self.assertEqual(report["terminal_outcome"]["matched_outcome_id"], "o2")
        self.assertTrue(report["hard_constraints"]["all_passed"])
        self.assertTrue(report["required_checkpoints"]["all_completed"])
        self.assertTrue(report["feasible_process_success"])
        self.assertFalse(report["economic_objective"]["satisfied"])
        self.assertFalse(report["episode_success"])

    def test_reference_trace_satisfies_economic_objective(self):
        eid = "electrical-bongabon-generator-001"
        report = self.evaluator.evaluate_actions(eid, self.reference_traces()[eid])
        self.assertTrue(report["economic_objective"]["satisfied"])
        self.assertTrue(report["feasible_process_success"])
        self.assertTrue(report["episode_success"])

if __name__ == "__main__":
    unittest.main()
