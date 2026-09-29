"""Tests for guarded ProcureHarness architecture-search execution."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MODEL,
    PHASES,
    REASONING_EFFORT,
    TEMPERATURE,
    VALIDATION_EPISODES,
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
            "screening_selected",
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
                    "screening_selected": False,
                },
            )

    def test_validation_requires_floor_and_promotion_branch(self):
        base = {
            "protocol_id": "procureharness-architecture-search-v0.1",
            "candidate_id": "ph-r1-c01",
            "round": 1,
            "phase": "validation",
            "approved": True,
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
        }
        validate_phase_authorization(
            candidate_id="ph-r1-c01",
            phase="validation",
            authorization=authorized,
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
