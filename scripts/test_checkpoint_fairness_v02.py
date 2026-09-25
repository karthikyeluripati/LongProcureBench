"""Focused regressions for checkpoint fairness v0.2."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from audit_checkpoint_fairness import (
    _load_frozen_gzip,
    audit_checkpoint,
    audit_runs,
)


class FairnessAuditV02Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_input_jsonl_gz_uses_requested_file(self):
        record = {
            "episode_id": "electrical-bongabon-generator-001",
            "run_id": "custom-run",
            "trajectory": [],
            "evaluation": None,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "custom.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            runs = _load_frozen_gzip(path)
            self.assertEqual(runs, [record])
            audit = audit_runs(runs, self.root)
            self.assertEqual(audit["runs_detail"][0]["checkpoints"], [])
            self.assertFalse(audit["runs_detail"][0]["terminal_feasible"])
            with self.assertRaises(ValueError):
                _load_frozen_gzip(Path(temp_dir) / "missing.jsonl.gz")

    def test_dla_relay_underquantity_offer_requires_revision(self):
        episode = json.loads(
            (
                self.root
                / "data/episodes/electrical/electrical-dla-relay-012.json"
            ).read_text(encoding="utf-8")
        )
        run = {
            "trajectory": [
                {
                    "step": 1,
                    "action": {"type": "send_follow_up", "arguments": {}},
                    "observations": [{
                        "event_id": "e5",
                        "type": "quote_received",
                        "supplier_id": "syn-relay-c",
                    }],
                },
                {
                    "step": 2,
                    "action": {
                        "type": "award_supplier",
                        "arguments": {
                            "awards": [{
                                "scope": "package",
                                "supplier_id": "syn-relay-c",
                                "quote_event_id": "e5",
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
        audited = audit_checkpoint(run, checkpoint, episode)
        self.assertTrue(audited["applicable"])
        self.assertTrue(audited["opportunity"])
        self.assertTrue(audited["applicable_obligation_failure"])

    def test_audit_emits_complete_per_run_checkpoint_record(self):
        run = {
            "episode_id": "electrical-bongabon-generator-001",
            "run_id": "fairness-audit-test",
            "status": "completed",
            "trajectory": [],
            "evaluation": {
                "terminal_outcome": {"correct": False},
                "hard_constraints": {"all_passed": False},
                "feasible_process_success": False,
                "required_checkpoints": {
                    "results": [{
                        "checkpoint": "award_or_recommend",
                        "complete": False,
                        "evidence_mode": "direct",
                        "detail": "No terminal decision",
                    }]
                },
            },
        }
        audit = audit_runs([run], self.root)
        self.assertEqual(len(audit["runs_detail"]), 1)
        self.assertEqual(
            len(audit["runs_detail"][0]["checkpoints"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
