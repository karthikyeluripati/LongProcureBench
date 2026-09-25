"""Focused regressions for checkpoint fairness v0.2."""
import gzip
import json
from pathlib import Path
import unittest

from audit_checkpoint_fairness import (
    _load_frozen_gzip,
    audit_checkpoint,
    audit_runs,
)


class FairnessAuditV02Tests(unittest.TestCase):
    def test_infeasible_original_offer_with_revision_repair_is_applicable(self):
        run = {
            "trajectory": [
                {
                    "step": 1,
                    "action": {"type": "send_rfq"},
                    "observations": [{
                        "event_id": "e1",
                        "type": "quote_received",
                        "supplier_id": "syn-a",
                    }],
                },
                {
                    "step": 2,
                    "action": {
                        "type": "award_supplier",
                        "arguments": {
                            "awards": [{
                                "scope": "package",
                                "supplier_id": "syn-a",
                                "quote_event_id": "e1",
                            }]
                        },
                    },
                    "observations": [],
                },
            ],
            "evaluation": {
                "terminal_outcome": {"correct": False},
                "hard_constraints": {"all_passed": False},
            },
        }
        checkpoint = {
            "checkpoint": "request_quote_revision",
            "complete": False,
            "evidence_mode": "direct",
            "detail": "No quote revision request",
        }
        episode = {
            "events": [
                {"event_id": "e1", "type": "quote_received", "supplier_id": "syn-a"},
                {"event_id": "e2", "type": "quote_revision", "supplier_id": "syn-a"},
            ],
            "oracle": {
                "acceptable_terminal_outcomes": [{
                    "awards": [{
                        "scope": "package",
                        "supplier_id": "syn-a",
                        "quote_event_id": "e2",
                    }]
                }]
            },
        }
        audited = audit_checkpoint(run, checkpoint, episode)
        self.assertTrue(audited["applicable"])
        self.assertTrue(audited["opportunity"])
        self.assertTrue(audited["applicable_obligation_failure"])

    def test_committed_source_has_complete_per_run_records(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "evidence/luna20-diagnostic-v0.1/fairness-source.jsonl.gz"
        runs = _load_frozen_gzip(source)
        audit = audit_runs(runs, root)
        self.assertEqual(len(runs), 60)
        self.assertEqual(len(audit["runs_detail"]), 60)
        self.assertTrue(all("checkpoints" in row for row in audit["runs_detail"]))


if __name__ == "__main__":
    unittest.main()
