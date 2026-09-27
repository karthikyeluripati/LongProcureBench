"""Regression tests for the frozen held-out episode package."""
from copy import deepcopy
import json
import unittest

from validate_heldout_episode_package_v01 import (
    EXPECTED,
    EXPECTED_FROZEN_BLOB_PATHS,
    MANIFEST_PATH,
    ROOT,
    SPLIT_PATH,
    validate_frozen_blob_map,
    validate_heldout_package,
)


class HeldoutEpisodePackageTests(unittest.TestCase):
    def test_frozen_heldout_package_passes_reference_controls(self):
        summary = validate_heldout_package()
        self.assertEqual(summary["episodes"], 10)
        self.assertEqual(summary["initial_states"], 10)
        self.assertEqual(len(summary["reference_controls"]), 10)
        self.assertTrue(
            all(
                row["resolved_obligations"]
                == row["actionable_obligations"]
                for row in summary["reference_controls"].values()
            )
        )
        self.assertEqual(
            set(summary["event_types"]),
            {
                "buyer_clarification",
                "quote_received",
                "quote_revision",
                "supplier_non_response",
                "supplier_question",
                "supplier_withdrawal",
                "requirement_change",
            },
        )

    def test_port_angeles_public_estimate_is_not_hard_cap(self):
        episode = json.loads(
            (
                ROOT
                / "data/episodes/electrical/"
                "electrical-port-angeles-transformers-025.json"
            ).read_text(encoding="utf-8")
        )
        config = json.loads(
            (
                ROOT
                / "data/evaluation/electrical/"
                "electrical-port-angeles-transformers-025.json"
            ).read_text(encoding="utf-8")
        )
        initial = json.loads(
            (
                ROOT
                / "data/initial_states/electrical/"
                "us-port-angeles-mec-2025-18.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            initial["total_estimated_budget"]["amount"],
            800000,
        )
        self.assertIn(
            "Government estimate",
            initial["total_estimated_budget"]["basis"],
        )

        constraint = next(
            row
            for row in episode["oracle"]["hard_constraints"]
            if row["constraint_id"] == "c2"
        )
        self.assertEqual(constraint["basis"], "synthetic_scenario")
        self.assertIn("synthetic USD 790,000", constraint["description"])
        self.assertIn(
            "nonbinding",
            episode["realism"]["notes"],
        )

        clarification = next(
            event
            for event in episode["events"]
            if event["event_id"] == "e1"
        )
        self.assertEqual(
            clarification["details"]["max_total_price_usd"],
            790000,
        )

        rule = next(
            row
            for row in config["constraint_rules"]
            if row["constraint_id"] == "c2"
        )
        self.assertEqual(rule["checks"][0]["value"], 790000)

    def test_frozen_blob_paths_are_exact_not_count_only(self):
        manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )
        frozen = deepcopy(manifest["frozen_git_blobs"])
        removed = (
            "data/initial_states/electrical/"
            "us-port-angeles-mec-2025-18.json"
        )
        frozen.pop(removed)
        frozen["README.md"] = "0" * 40

        self.assertEqual(len(frozen), 33)
        with self.assertRaisesRegex(
            ValueError,
            "Held-out frozen file path set changed",
        ):
            validate_frozen_blob_map(frozen)

    def test_frozen_blob_path_set_contains_exact_expected_files(self):
        manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(manifest["frozen_git_blobs"]),
            EXPECTED_FROZEN_BLOB_PATHS,
        )

    def test_split_is_exact_021_to_030_mapping(self):
        split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            split["held_out_test"]["episode_ids"],
            list(EXPECTED),
        )
        self.assertEqual(
            split["held_out_test"]["initial_state_package_ids"],
            list(EXPECTED.values()),
        )
        self.assertFalse(
            split["held_out_test"]["model_evaluations_run"]
        )


if __name__ == "__main__":
    unittest.main()
