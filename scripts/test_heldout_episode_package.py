"""Regression tests for the frozen held-out episode package."""
import json
import unittest

from validate_heldout_episode_package_v01 import (
    EXPECTED,
    SPLIT_PATH,
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
