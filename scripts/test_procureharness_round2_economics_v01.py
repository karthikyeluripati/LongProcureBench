"""Audit frozen ProcureHarness Round-2 economics evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import materialize_procureharness_round2_economics_v01 as materializer
from run_procureharness_search_v01 import validate_phase_authorization
from select_procureharness_validation_v01 import (
    evaluate_efficiency_promotion,
    validate_frozen_efficiency_addendum,
    validate_frozen_validation_selection,
)

MANIFEST_PATH = ROOT / materializer.MANIFEST_REL
GATE_RESULT_PATH = ROOT / materializer.GATE_RESULT_REL


class ProcureHarnessRound2EconomicsEvidenceTests(unittest.TestCase):
    def setUp(self):
        manifest_exists = MANIFEST_PATH.is_file()
        gate_exists = GATE_RESULT_PATH.is_file()
        if not manifest_exists and not gate_exists:
            self.skipTest("Round-2 economics evidence is not materialized yet")
        self.assertTrue(
            manifest_exists,
            "Round-2 economics gate exists but manifest is missing",
        )
        self.assertTrue(
            gate_exists,
            "Round-2 economics manifest exists but gate result is missing",
        )
        self.manifest = materializer._read_json(
            materializer.MANIFEST_REL
        )
        self.gate_result = materializer._read_json(
            materializer.GATE_RESULT_REL
        )

    def test_economics_reports_and_comparisons_recompute_from_frozen_results(self):
        payloads = materializer.build_round2_economics_payloads()

        for candidate_id in materializer.CANDIDATES:
            self.assertEqual(
                materializer._read_json(
                    materializer.CANDIDATE_REPORT_FILES[candidate_id]
                ),
                payloads["candidates"][candidate_id],
            )

        self.assertEqual(
            materializer._read_json(materializer.COMPARISONS_REL),
            payloads["comparisons"],
        )

    def test_manifest_binds_round2_inputs_and_outputs(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema_version"], "0.1.0")
        self.assertEqual(
            manifest["package_id"],
            "procureharness-round2-economics-v0.1",
        )
        self.assertEqual(manifest["round"], 2)
        self.assertEqual(
            manifest["candidate_ids"],
            list(materializer.CANDIDATES),
        )
        self.assertEqual(
            manifest["execution"],
            {
                "mode": "offline_deterministic_economics",
                "provider_calls": 0,
            },
        )
        self.assertEqual(
            manifest["baseline_freeze_commit"],
            "7b101f08eb2ad2ca33df628e30fd3c3173befc32",
        )
        self.assertEqual(
            self.gate_result["round2_economics_manifest_sha256"],
            materializer._sha256_path(materializer.MANIFEST_REL),
        )

        bindings = [
            manifest["comparisons"],
            manifest["base_validation_selection"],
            manifest["source_confirmation_manifest"],
            manifest["baseline_economics_manifest"],
            manifest["baseline_reference_cohort"],
            *manifest["candidate_reports"].values(),
        ]
        for row in bindings:
            path = Path(row["path"])
            self.assertTrue((ROOT / path).is_file())
            self.assertEqual(
                materializer._sha256_path(path),
                row["sha256"],
            )
            self.assertEqual(
                len((ROOT / path).read_bytes()),
                row["bytes"],
            )

        for candidate_id in materializer.CANDIDATES:
            row = manifest["candidate_reports"][candidate_id]
            self.assertEqual(
                row["policy_id"],
                f"procureharness--{candidate_id}--"
                "openai/gpt-5.6-sol",
            )

    def test_gate_result_recomputes_exact_efficiency_decisions(self):
        gate = self.gate_result
        self.assertEqual(gate["round"], 2)
        self.assertEqual(gate["provider_calls"], 0)

        base_selection = materializer._read_json(
            materializer.BASE_SELECTION_REL
        )
        validate_frozen_validation_selection(base_selection)
        self.assertEqual(
            gate["base_validation_selection_sha256"],
            materializer._sha256_path(
                materializer.BASE_SELECTION_REL
            ),
        )

        comparisons = materializer._read_json(
            materializer.COMPARISONS_REL
        )

        approved = []
        rejected = []
        for candidate_id in materializer.CANDIDATES:
            outcome = gate["outcomes"][candidate_id]
            candidate_path = (
                materializer.CANDIDATE_REPORT_FILES[candidate_id]
            )
            try:
                promotion = evaluate_efficiency_promotion(
                    base_selection=base_selection,
                    candidate_id=candidate_id,
                    candidate_reports_path=candidate_path.as_posix(),
                    expected_candidate_sha256=(
                        materializer._sha256_path(candidate_path)
                    ),
                )
            except ValueError as exc:
                reason = str(exc)
                self.assertTrue(
                    materializer._is_expected_rejection(reason),
                    f"unexpected recomputed rejection: {reason}",
                )
                self.assertFalse(outcome["approved"])
                self.assertEqual(outcome["status"], "not_promoted")
                self.assertEqual(outcome["reason"], reason)
                self.assertEqual(
                    outcome["comparison"],
                    comparisons["candidates"][candidate_id],
                )
                rejected.append(candidate_id)
                continue

            self.assertTrue(outcome["approved"])
            self.assertEqual(outcome["status"], "authorized")
            self.assertEqual(outcome["promotion"], promotion)
            self.assertEqual(
                outcome["comparison"],
                comparisons["candidates"][candidate_id],
            )

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
            approved.append(candidate_id)

        self.assertEqual(gate["authorized_candidate_ids"], approved)
        self.assertEqual(gate["not_promoted_candidate_ids"], rejected)
        self.assertEqual(
            sorted(approved + rejected),
            sorted(materializer.CANDIDATES),
        )

    def test_base_validation_selection_remains_immutable(self):
        selection = materializer._read_json(
            materializer.BASE_SELECTION_REL
        )
        self.assertEqual(selection["round"], 2)
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
