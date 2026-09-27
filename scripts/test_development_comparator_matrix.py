"""Regression checks for the frozen development comparator matrix."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from validate_development_comparator_matrix_v01 import (
    MATRIX_PATH,
    validate_matrix,
)


class DevelopmentComparatorMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    def test_frozen_matrix_matches_committed_evidence(self):
        validate_matrix(deepcopy(self.matrix))

    def test_dropped_mechanism_cannot_become_heldout_eligible(self):
        matrix = deepcopy(self.matrix)
        for method in matrix["development_methods"]:
            if method["id"] == "working-plan-reactive-v0.1":
                method["heldout_eligible"] = True
                break
        with self.assertRaisesRegex(
            ValueError,
            "became held-out eligible",
        ):
            validate_matrix(matrix)

    def test_heldout_method_cannot_be_added_after_freeze(self):
        matrix = deepcopy(self.matrix)
        matrix["heldout_protocol"]["eligible_rows"].append({
            "id": "new-method-after-freeze",
            "model": "openai/gpt-5.6-sol",
            "runs_if_10_episodes": 30,
            "competitive": True,
        })
        matrix["heldout_protocol"]["expected_model_backed_runs"] = 180
        with self.assertRaisesRegex(
            ValueError,
            "Held-out eligible row set changed",
        ):
            validate_matrix(matrix)

    def test_primary_metric_is_frozen(self):
        matrix = deepcopy(self.matrix)
        matrix["reporting_contract"]["primary_quality_metric"] = (
            "episode_success_v02"
        )
        with self.assertRaisesRegex(
            ValueError,
            "Primary paper metric changed",
        ):
            validate_matrix(matrix)

    def test_exact_model_set_is_frozen(self):
        matrix = deepcopy(self.matrix)
        cross = next(
            method
            for method in matrix["development_methods"]
            if method["id"] == "raw-reactive-cross-family-v0.1"
        )
        cross["models"][2] = "gemini/a-different-model"
        with self.assertRaisesRegex(
            ValueError,
            "model identifiers changed",
        ):
            validate_matrix(matrix)

    def test_heldout_episode_count_is_frozen(self):
        matrix = deepcopy(self.matrix)
        matrix["heldout_protocol"]["heldout_episode_count"] = 9
        with self.assertRaisesRegex(
            ValueError,
            "episode count must remain 10",
        ):
            validate_matrix(matrix)


if __name__ == "__main__":
    unittest.main()
