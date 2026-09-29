"""Audit frozen ProcureHarness Round-1 development economics evidence."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import materialize_procureharness_development_economics_v01 as materializer
from run_procureharness_search_v01 import validate_phase_authorization
from select_procureharness_validation_v01 import (
    _load_development_economics_binding,
    validate_frozen_efficiency_addendum,
)

PACKAGE = ROOT / materializer.PACKAGE_REL
MANIFEST = ROOT / materializer.MANIFEST_REL


@unittest.skipUnless(
    MANIFEST.is_file(),
    "development economics package has not been materialized yet",
)
class ProcureHarnessDevelopmentEconomicsEvidenceTests(unittest.TestCase):
    def test_all_economics_reports_recompute_from_frozen_sources(self):
        payloads = materializer.build_economics_payloads()

        self.assertEqual(
            materializer._read_json(
                materializer.BASELINE_REPORT_FILES["coverage_repair"]
            ),
            payloads["coverage_repair"],
        )
        self.assertEqual(
            materializer._read_json(
                materializer.BASELINE_REPORT_FILES["react"]
            ),
            payloads["react"],
        )
        for candidate_id in materializer.CANDIDATES:
            self.assertEqual(
                materializer._read_json(
                    materializer.CANDIDATE_REPORT_FILES[candidate_id]
                ),
                payloads["candidates"][candidate_id],
            )
        self.assertEqual(
            materializer._read_json(materializer.REFERENCE_COHORT_REL),
            payloads["reference_cohort"],
        )
        self.assertEqual(
            materializer._read_json(materializer.COMPARISONS_REL),
            payloads["comparisons"],
        )

    def test_manifest_binds_real_freeze_commit_for_every_scored_input(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        freeze_commit = manifest["freeze_commit"]

        expected_paths = [
            materializer.DESCRIPTOR_REL,
            *materializer.BASELINE_REPORT_FILES.values(),
            *materializer.CANDIDATE_REPORT_FILES.values(),
            materializer.REFERENCE_COHORT_REL,
            materializer.COMPARISONS_REL,
        ]
        for path in expected_paths:
            current_blob = materializer._git_blob_sha1_path(path)
            frozen_blob = materializer._git_blob_at(
                freeze_commit,
                path,
            )
            self.assertEqual(
                current_blob,
                frozen_blob,
                f"freeze-commit blob mismatch for {path}",
            )

        loaded = _load_development_economics_binding()
        self.assertEqual(loaded["freeze_commit"], freeze_commit)

    def test_efficiency_gate_result_matches_append_only_authorizations(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["execution"],
            {
                "mode": "offline_deterministic_replay_and_economics",
                "provider_calls": 0,
            },
        )

        gate_result = materializer._read_json(
            materializer.GATE_RESULT_REL
        )
        self.assertEqual(gate_result["provider_calls"], 0)
        authorized = gate_result["authorized_candidate_ids"]
        rejected = gate_result["not_promoted_candidate_ids"]
        self.assertEqual(
            sorted(authorized + rejected),
            sorted(materializer.CANDIDATES),
        )
        self.assertFalse(set(authorized) & set(rejected))

        for candidate_id in authorized:
            outcome = gate_result["outcomes"][candidate_id]
            self.assertTrue(outcome["approved"])
            addendum = materializer._read_json(
                Path(outcome["addendum_path"])
            )
            authorization = materializer._read_json(
                Path(outcome["authorization_path"])
            )
            validate_frozen_efficiency_addendum(addendum)
            validate_phase_authorization(
                candidate_id=candidate_id,
                phase="validation",
                authorization=authorization,
            )

        for candidate_id in rejected:
            outcome = gate_result["outcomes"][candidate_id]
            self.assertFalse(outcome["approved"])
            self.assertEqual(outcome["status"], "not_promoted")
            self.assertTrue(outcome["reason"])

    def test_base_validation_selection_remains_immutable(self):
        selection = materializer._read_json(
            materializer.BASE_SELECTION_REL
        )
        self.assertEqual(
            selection["pending_efficiency_candidate_ids"],
            list(materializer.CANDIDATES),
        )
        self.assertEqual(
            selection["validation_slot_candidate_ids"],
            list(materializer.CANDIDATES),
        )
        self.assertEqual(
            selection["validation_selected_candidate_ids"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
