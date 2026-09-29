"""Audit the frozen ProcureHarness Phase-1 search summary package."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import materialize_procureharness_phase1_search_summary_v01 as materializer
from run_procureharness_search_v01 import round_candidate_ids


class ProcureHarnessPhase1SearchSummaryTests(unittest.TestCase):
    def setUp(self):
        paths = [
            ROOT / materializer.SUMMARY_REL,
            ROOT / materializer.README_REL,
            ROOT / materializer.MANIFEST_REL,
        ]
        existing = [path.is_file() for path in paths]
        if not any(existing):
            self.skipTest("Phase-1 search summary has not been materialized")
        self.assertTrue(
            all(existing),
            "Phase-1 search summary package is partially materialized",
        )
        self.summary = materializer._read_json(materializer.SUMMARY_REL)
        self.manifest = materializer._read_json(materializer.MANIFEST_REL)

    def test_summary_recomputes_exactly_from_frozen_evidence(self):
        self.assertEqual(
            self.summary,
            materializer.build_summary(),
        )

    def test_readme_recomputes_exactly_from_summary(self):
        expected = materializer.build_readme(self.summary)
        observed = (
            ROOT / materializer.README_REL
        ).read_text(encoding="utf-8")
        self.assertEqual(observed, expected)

    def test_manifest_binds_generated_files_and_all_sources(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema_version"], "0.1.0")
        self.assertEqual(
            manifest["protocol_id"],
            materializer.PROTOCOL_ID,
        )
        self.assertEqual(
            manifest["package_id"],
            "procureharness-phase1-search-summary-v0.1",
        )
        self.assertEqual(
            manifest["execution"],
            {
                "mode": "offline_evidence_summary",
                "provider_calls": 0,
            },
        )

        self.assertEqual(
            set(manifest["source_evidence"]),
            set(materializer.SOURCE_PATHS),
        )
        for name, path in materializer.SOURCE_PATHS.items():
            self.assertEqual(
                manifest["source_evidence"][name],
                materializer._binding(path),
            )

        self.assertEqual(
            manifest["generated_files"]["summary"],
            materializer._binding(materializer.SUMMARY_REL),
        )
        self.assertEqual(
            manifest["generated_files"]["readme"],
            materializer._binding(materializer.README_REL),
        )

    def test_search_accounting_and_stop_boundary_are_frozen(self):
        accounting = self.summary["execution_accounting"]
        self.assertEqual(accounting["preregistered_rounds"], 3)
        self.assertEqual(accounting["completed_rounds"], 2)
        self.assertEqual(accounting["preregistered_candidates"], 18)
        self.assertEqual(accounting["screened_candidates"], 12)
        self.assertEqual(accounting["development_confirmed_candidates"], 4)
        self.assertEqual(accounting["development_runs"], 480)
        self.assertEqual(
            accounting["total_tokens_across_executed_search_rows"],
            1789236,
        )
        self.assertAlmostEqual(
            accounting["known_cost_usd_across_executed_search_rows"],
            7.7604622,
            places=10,
        )
        self.assertEqual(accounting["search_validation_031_040_runs"], 0)
        self.assertEqual(accounting["final_test_041_050_runs"], 0)
        self.assertFalse(accounting["round3_executed"])
        self.assertEqual(accounting["summary_provider_calls"], 0)

        termination = self.summary["termination"]
        self.assertEqual(termination["completed_round"], 2)
        self.assertEqual(termination["decision"], "stop")
        self.assertEqual(
            termination["stop_reason"],
            "two_consecutive_no_new_frontier_rounds",
        )
        self.assertEqual(termination["plateau_stop_threshold"], 2)
        self.assertEqual(
            termination["consecutive_no_new_frontier_rounds"],
            2,
        )

    def test_no_validation_or_round3_authorization_is_claimed(self):
        self.assertEqual(
            self.summary["development_gate_result"][
                "validation_authorized_candidate_ids"
            ],
            [],
        )
        for round_id in ("1", "2"):
            self.assertEqual(
                self.summary["rounds"][round_id][
                    "final_validation_candidate_ids"
                ],
                [],
            )

        unexecuted = {
            row["candidate_id"]
            for row in self.summary["candidate_designs"][
                "not_executed_due_plateau_stop"
            ]
        }
        self.assertEqual(unexecuted, set(round_candidate_ids(3)))

        gate = (
            ROOT
            / "evidence"
            / "procureharness-search-gates-v0.1"
        )
        for candidate_id in round_candidate_ids(3):
            self.assertFalse(
                (gate / f"{candidate_id}--screening-auth.json").exists()
            )

    def test_repeated_efficiency_failure_is_exactly_bound(self):
        failure = self.summary["development_gate_result"][
            "repeated_efficiency_failure_pattern"
        ]
        self.assertEqual(
            failure["affected_candidate_ids"],
            [
                "ph-r1-c02",
                "ph-r1-c05",
                "ph-r2-c12",
                "ph-r2-c09",
            ],
        )
        self.assertEqual(failure["regret_eligible_count"], 42)
        self.assertEqual(failure["reference_cohort_count"], 48)
        self.assertEqual(failure["regret_eligibility_rate"], 0.875)
        self.assertEqual(
            failure["reason"],
            (
                "candidate lacks full frozen regret "
                "reference-cohort comparability"
            ),
        )


if __name__ == "__main__":
    unittest.main()
