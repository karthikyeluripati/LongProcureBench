"""Regression tests for frozen ProcureHarness Round-1 -> Round-2 progression."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_procureharness_search_v01 import (
    round_candidate_ids,
    validate_phase_authorization,
)
import select_procureharness_round_progression_v01 as progression_selector
from select_procureharness_round_progression_v01 import (
    RULE_ID,
    _expected_candidate_source_paths,
    _recompute_efficiency_gate,
    _validate_manifest_entries,
    compute_round1_progression,
    compute_round2_progression,
    freeze_round1_progression,
    freeze_round2_progression,
    validate_frozen_round2_progression,
    validate_frozen_round_progression,
)


class ProcureHarnessRoundProgressionTests(unittest.TestCase):
    def test_round1_progression_recomputes_to_round2(self):
        progression = compute_round1_progression()
        self.assertEqual(progression["rule_id"], RULE_ID)
        self.assertEqual(progression["completed_round"], 1)
        self.assertEqual(
            progression["round_completion_status"],
            "complete_no_validation_candidate",
        )
        self.assertFalse(progression["round_added_new_frontier_point"])
        self.assertEqual(
            progression["consecutive_no_new_frontier_rounds"],
            1,
        )
        self.assertEqual(progression["plateau_stop_threshold"], 2)
        self.assertFalse(progression["plateau_stop_fired"])
        self.assertFalse(progression["max_rounds_stop_fired"])
        self.assertFalse(progression["unique_candidate_budget_stop_fired"])
        self.assertFalse(progression["stop_search"])
        self.assertEqual(progression["decision"], "advance")
        self.assertEqual(progression["next_round"], 2)
        self.assertEqual(
            progression["screening_authorized_candidate_ids"],
            round_candidate_ids(2),
        )
        self.assertEqual(
            progression["round1_final_validation_candidate_ids"],
            [],
        )

    def test_round1_progression_validator_rejects_mutation(self):
        progression = compute_round1_progression()
        validate_frozen_round_progression(progression)

        mutated = deepcopy(progression)
        mutated["plateau_stop_fired"] = True
        with self.assertRaisesRegex(
            ValueError,
            "does not match recomputed frozen Round-1 evidence",
        ):
            validate_frozen_round_progression(mutated)

    def test_efficiency_result_is_recomputed_from_frozen_economics(self):
        validation_selection = progression_selector._load_json(
            progression_selector.VALIDATION_SELECTION_PATH
        )
        economics_manifest = progression_selector._load_json(
            progression_selector.ECONOMICS_MANIFEST_PATH
        )
        recorded = progression_selector._load_json(
            progression_selector.EFFICIENCY_GATE_RESULT_PATH
        )

        approved, rejected = _recompute_efficiency_gate(
            validation_selection=validation_selection,
            economics_manifest=economics_manifest,
            recorded_result=recorded,
        )
        self.assertEqual(approved, [])
        self.assertEqual(rejected, ["ph-r1-c02", "ph-r1-c05"])

        tampered = deepcopy(recorded)
        tampered["outcomes"]["ph-r1-c02"]["reason"] = (
            "candidate regret is worse than Coverage+Repair on frozen cohort"
        )
        with self.assertRaisesRegex(
            ValueError,
            "recorded rejection reason disagrees",
        ):
            _recompute_efficiency_gate(
                validation_selection=validation_selection,
                economics_manifest=economics_manifest,
                recorded_result=tampered,
            )

    def test_screening_manifest_rejects_missing_declared_source_file(self):
        manifest = progression_selector._load_json(
            progression_selector.SCREENING_MANIFEST_PATH
        )
        expected = _expected_candidate_source_paths(
            evidence_root=(
                progression_selector.SCREENING_MANIFEST_PATH.parent
            ),
            candidate_ids=round_candidate_ids(1),
            phase="screening",
            repeats=(1,),
        )

        _validate_manifest_entries(
            manifest=manifest,
            field="source_files",
            expected_paths=expected,
            label="Round-1 screening",
        )

        mutated = deepcopy(manifest)
        mutated["source_files"] = mutated["source_files"][1:]
        with self.assertRaisesRegex(
            ValueError,
            "manifest source_files path set changed",
        ):
            _validate_manifest_entries(
                manifest=mutated,
                field="source_files",
                expected_paths=expected,
                label="Round-1 screening",
            )

    def test_interrupted_progression_freeze_is_retry_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            progression_path, auth_paths = freeze_round1_progression(
                output_dir=output_dir,
            )
            all_paths = [progression_path, *auth_paths]
            self.assertEqual(len(all_paths), 7)

            # Simulate process death after only part of the artifact set
            # reached final names.
            for path in all_paths[3:]:
                path.unlink()

            recovered_progression, recovered_auths = (
                freeze_round1_progression(output_dir=output_dir)
            )
            self.assertEqual(recovered_progression, progression_path)
            self.assertEqual(recovered_auths, auth_paths)
            self.assertTrue(all(path.is_file() for path in all_paths))

            # Exact survivors are reusable, but a mismatched survivor must
            # still fail closed rather than being overwritten.
            auth_paths[0].write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "does not match recomputed frozen content",
            ):
                freeze_round1_progression(output_dir=output_dir)

    def test_freeze_writes_bound_round2_screening_authorizations(self):
        with tempfile.TemporaryDirectory() as tmp:
            progression_path, auth_paths = freeze_round1_progression(
                output_dir=Path(tmp),
            )
            self.assertTrue(progression_path.is_file())
            self.assertEqual(len(auth_paths), 6)

            progression = json.loads(
                progression_path.read_text(encoding="utf-8")
            )
            validate_frozen_round_progression(progression)

            expected = round_candidate_ids(2)
            observed = []
            for auth_path in auth_paths:
                authorization = json.loads(
                    auth_path.read_text(encoding="utf-8")
                )
                candidate_id = authorization["candidate_id"]
                observed.append(candidate_id)
                self.assertEqual(
                    authorization["screening_authorized_candidate_ids"],
                    expected,
                )
                validate_phase_authorization(
                    candidate_id=candidate_id,
                    phase="screening",
                    authorization=authorization,
                )
            self.assertEqual(observed, expected)

    def test_round2_economics_baseline_provenance_is_bound(self):
        economics_manifest = progression_selector._load_json(
            progression_selector.ROUND2_ECONOMICS_MANIFEST_PATH
        )
        progression_selector._validate_round2_economics_baseline_provenance(
            economics_manifest
        )

        cases = [
            (
                "baseline_economics_manifest",
                "sha256",
                "0" * 64,
                "baseline manifest binding drift",
            ),
            (
                "baseline_reference_cohort",
                "sha256",
                "0" * 64,
                "reference-cohort binding drift",
            ),
        ]
        for field, key, value, pattern in cases:
            mutated = deepcopy(economics_manifest)
            mutated[field][key] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError,
                pattern,
            ):
                progression_selector._validate_round2_economics_baseline_provenance(
                    mutated
                )

        mutated = deepcopy(economics_manifest)
        mutated["baseline_freeze_commit"] = "0" * 40
        with self.assertRaisesRegex(
            ValueError,
            "baseline freeze commit drift",
        ):
            progression_selector._validate_round2_economics_baseline_provenance(
                mutated
            )

    def test_round2_progression_fires_two_round_plateau_stop(self):
        progression = compute_round2_progression()
        self.assertEqual(progression["completed_round"], 2)
        self.assertFalse(progression["round_added_new_frontier_point"])
        self.assertEqual(
            progression["prior_consecutive_no_new_frontier_rounds"],
            1,
        )
        self.assertEqual(
            progression["consecutive_no_new_frontier_rounds"],
            2,
        )
        self.assertEqual(progression["plateau_stop_threshold"], 2)
        self.assertTrue(progression["plateau_stop_fired"])
        self.assertFalse(progression["max_rounds_stop_fired"])
        self.assertFalse(
            progression["unique_candidate_budget_stop_fired"]
        )
        self.assertTrue(progression["stop_search"])
        self.assertEqual(progression["decision"], "stop")
        self.assertEqual(
            progression["stop_reason"],
            "two_consecutive_no_new_frontier_rounds",
        )
        self.assertIsNone(progression["next_round"])
        self.assertEqual(
            progression["screening_authorized_candidate_ids"],
            [],
        )
        self.assertEqual(
            progression["round2_final_validation_candidate_ids"],
            [],
        )
        self.assertEqual(
            progression["screened_unique_candidate_count"],
            12,
        )

    def test_round2_progression_validator_rejects_mutation(self):
        progression = compute_round2_progression()
        validate_frozen_round2_progression(progression)

        mutated = deepcopy(progression)
        mutated["plateau_stop_fired"] = False
        with self.assertRaisesRegex(
            ValueError,
            "does not match recomputed frozen Round-2 evidence",
        ):
            validate_frozen_round2_progression(mutated)

    def test_round2_stop_freeze_is_retry_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = freeze_round2_progression(
                output_dir=output_dir,
            )
            first = path.read_bytes()

            recovered = freeze_round2_progression(
                output_dir=output_dir,
            )
            self.assertEqual(recovered, path)
            self.assertEqual(path.read_bytes(), first)

            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "does not match recomputed frozen content",
            ):
                freeze_round2_progression(
                    output_dir=output_dir,
                )

    def test_round2_stop_emits_no_round3_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = freeze_round2_progression(
                output_dir=output_dir,
            )
            progression = json.loads(
                path.read_text(encoding="utf-8")
            )
            validate_frozen_round2_progression(progression)
            self.assertEqual(
                list(output_dir.glob("ph-r3-*-screening-auth.json")),
                [],
            )

    def test_committed_progression_artifact_recomputes_if_present(self):
        gate = (
            Path(__file__).resolve().parents[1]
            / "evidence"
            / "procureharness-search-gates-v0.1"
        )
        path = gate / "round-progression-after-round-1.json"
        if not path.is_file():
            self.skipTest("Round-2 progression artifact not materialized yet")
        progression = json.loads(path.read_text(encoding="utf-8"))
        validate_frozen_round_progression(progression)

        expected = round_candidate_ids(2)
        self.assertEqual(
            progression["screening_authorized_candidate_ids"],
            expected,
        )
        for candidate_id in expected:
            auth_path = gate / f"{candidate_id}--screening-auth.json"
            self.assertTrue(
                auth_path.is_file(),
                f"missing committed Round-2 screening auth: {auth_path}",
            )
            authorization = json.loads(
                auth_path.read_text(encoding="utf-8")
            )
            validate_phase_authorization(
                candidate_id=candidate_id,
                phase="screening",
                authorization=authorization,
            )

        round2_path = gate / "round-progression-after-round-2.json"
        if round2_path.is_file():
            round2 = json.loads(
                round2_path.read_text(encoding="utf-8")
            )
            validate_frozen_round2_progression(round2)
            self.assertTrue(round2["plateau_stop_fired"])
            self.assertEqual(round2["decision"], "stop")
            self.assertEqual(
                round2["screening_authorized_candidate_ids"],
                [],
            )
            self.assertEqual(
                set(round2["evidence_bindings"]),
                {
                    "prior_round_progression",
                    "screening_manifest",
                    "screening_selection",
                    "confirmation_manifest",
                    "validation_selection",
                    "round2_economics_manifest",
                    "efficiency_gate_result",
                },
            )
            for candidate_id in round_candidate_ids(3):
                self.assertFalse(
                    (
                        gate
                        / f"{candidate_id}--screening-auth.json"
                    ).exists(),
                    f"Round-3 auth must not exist after plateau stop: "
                    f"{candidate_id}",
                )


if __name__ == "__main__":
    unittest.main()
