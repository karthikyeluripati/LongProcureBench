"""Regression tests for fresh ProcureHarness observability."""
from copy import deepcopy
import unittest

from validate_procureharness_observability_v01 import (
    load_matrix,
    validate_fresh_observability,
)


class ProcureHarnessObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.rows = load_matrix()

    def test_fresh_observability_passes(self):
        summary = validate_fresh_observability(deepcopy(self.rows))
        self.assertEqual(summary["rows"], 20)

    def test_final_episode_cannot_be_relabeled_validation(self):
        rows = deepcopy(self.rows)
        rows[-1]["paper_split"] = "architecture_validation"
        with self.assertRaisesRegex(ValueError, "paper split drift"):
            validate_fresh_observability(rows)

    def test_future_events_cannot_be_visible_at_reset(self):
        rows = deepcopy(self.rows)
        rows[0]["future_event_visibility"] = "visible_at_reset"
        with self.assertRaisesRegex(ValueError, "observability drift"):
            validate_fresh_observability(rows)

    def test_failure_tags_must_match_episode(self):
        rows = deepcopy(self.rows)
        rows[0]["primary_failure_mechanisms"] = "quote_received"
        with self.assertRaisesRegex(ValueError, "failure-mechanism"):
            validate_fresh_observability(rows)


if __name__ == "__main__":
    unittest.main()
