"""Tests for guarded ProcureHarness architecture-search execution."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MODEL,
    PHASES,
    REASONING_EFFORT,
    TEMPERATURE,
    VALIDATION_EPISODES,
    _assert_output_tree_fresh,
    _assert_phase_exposure,
    phase_plan,
    validate_phase_authorization,
)
from validate_procureharness_harness_v01 import (
    IMPLEMENTATION_MANIFEST_PATH,
    validate_harness,
    validate_implementation_freeze,
)


class ProcureHarnessHarnessProtocolTests(unittest.TestCase):
    def test_harness_matches_frozen_protocol(self):
        summary = validate_harness()
        self.assertEqual(summary["candidates"], 18)
        self.assertEqual(summary["final_episodes_exposed"], 0)

    def test_implementation_freeze_is_bound_to_snapshot(self):
        validate_implementation_freeze()

    def test_manifest_blob_map_cannot_be_rewritten(self):
        manifest = json.loads(
            IMPLEMENTATION_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        mutated = deepcopy(manifest)
        mutated["frozen_files"][0]["git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(
            ValueError,
            "implementation manifest blob map changed",
        ):
            validate_implementation_freeze(mutated)

    def test_implementation_freeze_commit_cannot_change(self):
        manifest = json.loads(
            IMPLEMENTATION_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        mutated = deepcopy(manifest)
        mutated["freeze_commit"] = "0" * 40
        with self.assertRaisesRegex(
            ValueError,
            "implementation freeze commit changed",
        ):
            validate_implementation_freeze(mutated)

    def test_frozen_phase_run_counts(self):
        self.assertEqual(
            phase_plan("ph-r1-c01", "screening")["run_count"],
            20,
        )
        self.assertEqual(
            phase_plan(
                "ph-r1-c01",
                "development_confirmation",
            )["run_count"],
            60,
        )
        self.assertEqual(
            phase_plan("ph-r1-c01", "validation")["run_count"],
            30,
        )

    def test_search_runner_never_exposes_final_041_050(self):
        self.assertEqual(
            [int(x.rsplit("-", 1)[1]) for x in DEVELOPMENT_EPISODES],
            list(range(1, 21)),
        )
        self.assertEqual(
            [int(x.rsplit("-", 1)[1]) for x in VALIDATION_EPISODES],
            list(range(31, 41)),
        )
        for phase in PHASES:
            _assert_phase_exposure(phase)
            suffixes = {
                int(x.rsplit("-", 1)[1])
                for x in PHASES[phase]["episodes"]
            }
            self.assertTrue(
                all(not (41 <= suffix <= 50) for suffix in suffixes)
            )

    def test_execution_defaults_are_exact(self):
        self.assertEqual(MODEL, "openai/gpt-5.6-sol")
        self.assertEqual(REASONING_EFFORT, "medium")
        self.assertIsNone(TEMPERATURE)

    def test_screening_rejects_authorization_file(self):
        with self.assertRaisesRegex(
            ValueError,
            "screening does not accept",
        ):
            validate_phase_authorization(
                candidate_id="ph-r1-c01",
                phase="screening",
                authorization={"approved": True},
            )

    def test_confirmation_requires_screening_selection(self):
        with self.assertRaisesRegex(
            ValueError,
            "screening_selected_candidate_ids",
        ):
            validate_phase_authorization(
                candidate_id="ph-r1-c01",
                phase="development_confirmation",
                authorization={
                    "protocol_id": "procureharness-architecture-search-v0.1",
                    "candidate_id": "ph-r1-c01",
                    "round": 1,
                    "phase": "development_confirmation",
                    "approved": True,
                    "screening_complete": True,
                    "screening_selected_candidate_ids": [],
                    "selection_rule": "frozen_screening_selection_v0.1",
                },
            )

    def test_confirmation_rejects_more_than_two_round_candidates(self):
        with self.assertRaisesRegex(ValueError, "exceeds max 2"):
            validate_phase_authorization(
                candidate_id="ph-r2-c07",
                phase="development_confirmation",
                authorization={
                    "protocol_id": "procureharness-architecture-search-v0.1",
                    "candidate_id": "ph-r2-c07",
                    "round": 2,
                    "phase": "development_confirmation",
                    "approved": True,
                    "screening_complete": True,
                    "screening_selected_candidate_ids": [
                        "ph-r2-c07",
                        "ph-r2-c08",
                        "ph-r2-c09",
                    ],
                    "selection_rule": "frozen_screening_selection_v0.1",
                },
            )

    def test_validation_requires_floor_and_promotion_branch(self):
        base = {
            "protocol_id": "procureharness-architecture-search-v0.1",
            "candidate_id": "ph-r1-c01",
            "round": 1,
            "phase": "validation",
            "approved": True,
            "development_confirmation_complete": True,
        }
        with self.assertRaisesRegex(
            ValueError,
            "development_confirmation_floor_passed",
        ):
            validate_phase_authorization(
                candidate_id="ph-r1-c01",
                phase="validation",
                authorization=base,
            )

        authorized = {
            **base,
            "development_confirmation_floor_passed": True,
            "promotion_branch": "quality",
            "validation_selected_candidate_ids": ["ph-r1-c01"],
            "selection_rule": "frozen_validation_entry_lexicographic_v0.1",
        }
        validate_phase_authorization(
            candidate_id="ph-r1-c01",
            phase="validation",
            authorization=authorized,
        )

    def test_validation_rejects_more_than_two_selected_candidates(self):
        with self.assertRaisesRegex(ValueError, "exceeds max 2"):
            validate_phase_authorization(
                candidate_id="ph-r2-c07",
                phase="validation",
                authorization={
                    "protocol_id": "procureharness-architecture-search-v0.1",
                    "candidate_id": "ph-r2-c07",
                    "round": 2,
                    "phase": "validation",
                    "approved": True,
                    "development_confirmation_complete": True,
                    "development_confirmation_floor_passed": True,
                    "promotion_branch": "quality",
                    "validation_selected_candidate_ids": [
                        "ph-r2-c07",
                        "ph-r2-c08",
                        "ph-r2-c09",
                    ],
                    "selection_rule":
                        "frozen_validation_entry_lexicographic_v0.1",
                },
            )

    def test_later_round_screening_requires_prior_round_gate(self):
        with self.assertRaisesRegex(ValueError, "requires --authorization-json"):
            validate_phase_authorization(
                candidate_id="ph-r2-c07",
                phase="screening",
                authorization=None,
            )

        validate_phase_authorization(
            candidate_id="ph-r2-c07",
            phase="screening",
            authorization={
                "protocol_id": "procureharness-architecture-search-v0.1",
                "candidate_id": "ph-r2-c07",
                "round": 2,
                "phase": "screening",
                "approved": True,
                "round_candidate_ids": [
                    "ph-r2-c07",
                    "ph-r2-c08",
                    "ph-r2-c09",
                    "ph-r2-c10",
                    "ph-r2-c11",
                    "ph-r2-c12",
                ],
                "prior_round": 1,
                "prior_round_validation_complete": True,
                "plateau_stop_fired": False,
                "search_budget_exhausted": False,
            },
        )

    def test_later_round_screening_stops_when_plateau_fires(self):
        with self.assertRaisesRegex(ValueError, "plateau_stop_fired=false"):
            validate_phase_authorization(
                candidate_id="ph-r2-c07",
                phase="screening",
                authorization={
                    "protocol_id": "procureharness-architecture-search-v0.1",
                    "candidate_id": "ph-r2-c07",
                    "round": 2,
                    "phase": "screening",
                    "approved": True,
                    "round_candidate_ids": [
                        "ph-r2-c07",
                        "ph-r2-c08",
                        "ph-r2-c09",
                        "ph-r2-c10",
                        "ph-r2-c11",
                        "ph-r2-c12",
                    ],
                    "prior_round": 1,
                    "prior_round_validation_complete": True,
                    "plateau_stop_fired": True,
                    "search_budget_exhausted": False,
                },
            )

    def test_candidate_phase_cannot_be_rerun_into_nonempty_output_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase_root = _assert_output_tree_fresh(
                output_dir=root,
                candidate_id="ph-r1-c01",
                phase="screening",
            )
            phase_root.mkdir(parents=True)
            (phase_root / "partial.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to rerun"):
                _assert_output_tree_fresh(
                    output_dir=root,
                    candidate_id="ph-r1-c01",
                    phase="screening",
                )

    def test_validation_rejects_wrong_candidate_authorization(self):
        with self.assertRaisesRegex(
            ValueError,
            "candidate_id mismatch",
        ):
            validate_phase_authorization(
                candidate_id="ph-r1-c01",
                phase="validation",
                authorization={
                    "protocol_id": "procureharness-architecture-search-v0.1",
                    "candidate_id": "ph-r1-c02",
                    "round": 1,
                    "phase": "validation",
                    "approved": True,
                    "development_confirmation_floor_passed": True,
                    "promotion_branch": "quality",
                },
            )


if __name__ == "__main__":
    unittest.main()
