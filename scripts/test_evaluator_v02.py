"""Regression tests for Evaluator v0.2 obligation semantics."""
import unittest

from longprocurebench import LongProcureBenchEvaluator
from longprocurebench.reference import REFERENCE_DECISIONS


class EvaluatorV02Tests(unittest.TestCase):
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

    def decisions_to_actions(self, episode_id, decisions):
        actions = []
        for n, decision in enumerate(decisions, start=1):
            arguments = dict(decision.get("arguments") or {})
            actions.append(
                self.action(
                    n,
                    episode_id,
                    decision["type"],
                    decision.get("supplier_id"),
                    **arguments,
                )
            )
        return actions

    @staticmethod
    def obligation(report, checkpoint):
        matches = [
            item
            for item in report["obligations"]["results"]
            if item["checkpoint"] == checkpoint
        ]
        return matches

    def test_all_reference_controls_resolve_all_actionable_obligations(self):
        for episode_id, decisions in REFERENCE_DECISIONS.items():
            with self.subTest(episode_id=episode_id):
                report = self.evaluator.evaluate_actions(
                    episode_id,
                    self.decisions_to_actions(episode_id, decisions),
                )
                self.assertEqual(report["evaluation_version"], "0.2.0")
                self.assertEqual(report["obligations"]["unresolved"], 0)
                self.assertTrue(
                    report["obligations"]["all_actionable_resolved"]
                )
                self.assertTrue(report["feasible_obligation_success"])
                self.assertTrue(report["episode_success_v02"])

    def test_untriggered_nonresponse_is_not_applicable(self):
        eid = "electrical-bongabon-generator-001"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-gen-a"),
            self.action(
                3,
                eid,
                "award_supplier",
                "syn-gen-a",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-gen-a",
                    "quote_event_id": "e1",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        follow_up = self.obligation(report, "follow_up_nonresponse")
        self.assertEqual(len(follow_up), 1)
        self.assertEqual(follow_up[0]["status"], "not_applicable")
        self.assertEqual(report["obligations"]["unresolved"], 0)

    def test_terminal_step_requirement_change_has_no_opportunity(self):
        eid = "electrical-vre-generator-020"
        actions = [
            self.action(1, eid, "request_buyer_clarification"),
            self.action(2, eid, "identify_suppliers"),
            self.action(3, eid, "send_rfq", "syn-vre-a"),
            self.action(4, eid, "send_rfq", "syn-vre-b"),
            self.action(
                5,
                eid,
                "award_supplier",
                "syn-vre-a",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-vre-a",
                    "quote_event_id": "e2",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        amendment = self.obligation(report, "handle_amendment")
        self.assertEqual(len(amendment), 1)
        self.assertEqual(amendment[0]["status"], "no_opportunity")
        self.assertFalse(amendment[0]["actionable"])

    def test_optional_revision_is_not_applicable_on_feasible_original_path(self):
        eid = "electrical-bongabon-generator-001"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-gen-a"),
            self.action(
                3,
                eid,
                "award_supplier",
                "syn-gen-a",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-gen-a",
                    "quote_event_id": "e1",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        revision = self.obligation(report, "request_quote_revision")
        self.assertEqual(len(revision), 1)
        self.assertEqual(revision[0]["status"], "not_applicable")

    def test_infeasible_original_offer_with_repair_path_requires_revision(self):
        eid = "electrical-dla-relay-012"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-relay-a"),
            self.action(3, eid, "send_rfq", "syn-relay-b"),
            self.action(4, eid, "send_rfq", "syn-relay-c"),
            self.action(5, eid, "evaluate_quotes"),
            self.action(6, eid, "send_follow_up", "syn-relay-c"),
            self.action(
                7,
                eid,
                "award_supplier",
                "syn-relay-c",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-relay-c",
                    "quote_event_id": "e5",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        revision = self.obligation(report, "request_quote_revision")
        self.assertEqual(len(revision), 1)
        self.assertEqual(revision[0]["status"], "unresolved")
        self.assertTrue(revision[0]["actionable"])
        self.assertEqual(
            revision[0]["applicability_reason"],
            "selected_original_offer_has_revision_repair_path",
        )

    def test_revision_request_resolves_repair_obligation(self):
        eid = "electrical-dla-relay-012"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-relay-a"),
            self.action(3, eid, "send_rfq", "syn-relay-b"),
            self.action(4, eid, "send_rfq", "syn-relay-c"),
            self.action(5, eid, "evaluate_quotes"),
            self.action(6, eid, "send_follow_up", "syn-relay-c"),
            self.action(7, eid, "request_quote_revision", "syn-relay-c"),
            self.action(8, eid, "evaluate_quotes"),
            self.action(
                9,
                eid,
                "award_supplier",
                "syn-relay-c",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-relay-c",
                    "quote_event_id": "e6",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        revision = self.obligation(report, "request_quote_revision")
        self.assertEqual(len(revision), 1)
        self.assertEqual(revision[0]["status"], "resolved")
        self.assertIsNotNone(revision[0]["resolution_step"])

    def test_valid_fallback_resolves_withdrawal_without_forced_new_quote(self):
        eid = "electrical-dla-relay-012"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-relay-a"),
            self.action(3, eid, "send_rfq", "syn-relay-b"),
            self.action(4, eid, "send_rfq", "syn-relay-c"),
            self.action(5, eid, "evaluate_quotes"),
            self.action(
                6,
                eid,
                "award_supplier",
                "syn-relay-a",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-relay-a",
                    "quote_event_id": "e1",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        recovery = self.obligation(report, "recover_from_withdrawal")
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery[0]["status"], "resolved")
        self.assertTrue(report["terminal_outcome"]["correct"])
        self.assertTrue(report["hard_constraints"]["all_passed"])

        legacy = {
            item["checkpoint"]: item
            for item in report["required_checkpoints"]["results"]
        }
        self.assertFalse(legacy["recover_from_withdrawal"]["complete"])

    def test_proxy_failures_do_not_change_obligation_resolution(self):
        eid = "electrical-bongabon-generator-001"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-gen-a"),
            self.action(
                3,
                eid,
                "award_supplier",
                "syn-gen-a",
                awards=[{
                    "scope": "package",
                    "supplier_id": "syn-gen-a",
                    "quote_event_id": "e1",
                }],
            ),
        ]
        report = self.evaluator.evaluate_actions(eid, actions)
        self.assertTrue(report["obligations"]["all_actionable_resolved"])
        self.assertFalse(
            report["checkpoint_diagnostics"]["proxy"]["all_completed"]
        )


if __name__ == "__main__":
    unittest.main()
