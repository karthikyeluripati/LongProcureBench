"""Regression tests for checkpoint fairness auditing."""
import unittest

from audit_checkpoint_fairness import audit_checkpoint


def make_run(checkpoint_name, observations, award_event=None):
    trajectory = [
        {
            "step": 1,
            "action": {
                "type": "identify_suppliers",
                "arguments": {},
            },
            "observations": observations,
        },
        {
            "step": 2,
            "action": {
                "type": "award_supplier",
                "arguments": {
                    "awards": (
                        [{
                            "scope": "package",
                            "supplier_id": "syn-a",
                            "quote_event_id": award_event,
                        }]
                        if award_event
                        else []
                    )
                },
            },
            "observations": [],
        },
    ]
    checkpoint = {
        "checkpoint": checkpoint_name,
        "complete": False,
        "evidence_mode": "direct",
        "detail": "test",
    }
    return {"trajectory": trajectory}, checkpoint


class FairnessAuditTests(unittest.TestCase):
    def test_unrevealed_nonresponse_is_not_applicable(self):
        run, checkpoint = make_run("follow_up_nonresponse", [])
        audited = audit_checkpoint(run, checkpoint)
        self.assertFalse(audited["applicable"])
        self.assertTrue(audited["non_applicable_failure"])

    def test_revealed_nonresponse_has_action_opportunity(self):
        run, checkpoint = make_run(
            "follow_up_nonresponse",
            [{
                "event_id": "e1",
                "type": "supplier_non_response",
                "supplier_id": "syn-a",
            }],
        )
        audited = audit_checkpoint(run, checkpoint)
        self.assertTrue(audited["applicable"])
        self.assertTrue(audited["opportunity"])
        self.assertTrue(audited["applicable_obligation_failure"])

    def test_terminal_step_trigger_has_no_opportunity(self):
        run, checkpoint = make_run("handle_amendment", [])
        run["trajectory"][1]["observations"] = [{
            "event_id": "e2",
            "type": "requirement_change",
            "supplier_id": None,
        }]
        audited = audit_checkpoint(run, checkpoint)
        self.assertTrue(audited["applicable"])
        self.assertFalse(audited["opportunity"])
        self.assertTrue(audited["no_opportunity_failure"])

    def test_revision_is_conditional_on_awarded_revision(self):
        run, checkpoint = make_run(
            "request_quote_revision",
            [{
                "event_id": "e1",
                "type": "quote_received",
                "supplier_id": "syn-a",
            }],
            award_event="e1",
        )
        audited = audit_checkpoint(run, checkpoint)
        self.assertFalse(audited["applicable"])
        self.assertTrue(audited["non_applicable_failure"])

        run["trajectory"][0]["observations"][0]["type"] = "quote_revision"
        audited = audit_checkpoint(run, checkpoint)
        self.assertTrue(audited["applicable"])


if __name__ == "__main__":
    unittest.main()
