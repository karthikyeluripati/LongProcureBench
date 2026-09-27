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
            "Held-out eligible row count changed",
        ):
            validate_matrix(matrix)

    def test_extra_development_method_is_rejected(self):
        matrix = deepcopy(self.matrix)
        matrix["development_methods"].append({
            "id": "new-development-method-v0.1",
            "role": "development_only",
            "status": "dropped",
            "heldout_eligible": False,
            "models": ["openai/gpt-5.6-sol"],
            "evidence": "evidence/new/",
            "development_runs": 60,
            "gate_passed": False,
        })
        with self.assertRaisesRegex(
            ValueError,
            "Frozen development method set changed",
        ):
            validate_matrix(matrix)

    def test_heldout_model_mapping_is_frozen_per_row(self):
        matrix = deepcopy(self.matrix)
        rows = {
            row["id"]: row
            for row in matrix["heldout_protocol"]["eligible_rows"]
        }
        rows["raw-reactive-openai"]["model"] = (
            "gemini/gemini-3.8-flash"
        )
        rows["raw-reactive-openai"]["execution_settings"]["model"] = (
            "gemini/gemini-3.8-flash"
        )
        rows["raw-reactive-openai"]["execution_settings"]["provider"] = (
            "gemini"
        )
        with self.assertRaisesRegex(
            ValueError,
            "Held-out row contract changed for raw-reactive-openai",
        ):
            validate_matrix(matrix)

    def test_per_row_run_counts_cannot_shift_while_total_stays_same(self):
        matrix = deepcopy(self.matrix)
        rows = {
            row["id"]: row
            for row in matrix["heldout_protocol"]["eligible_rows"]
        }
        rows["raw-reactive-openai"]["runs_if_10_episodes"] = 60
        rows["raw-reactive-gemini"]["runs_if_10_episodes"] = 0
        with self.assertRaisesRegex(
            ValueError,
            "Held-out row contract changed",
        ):
            validate_matrix(matrix)

    def test_reference_control_count_is_frozen(self):
        matrix = deepcopy(self.matrix)
        rows = {
            row["id"]: row
            for row in matrix["heldout_protocol"]["eligible_rows"]
        }
        rows["reference-control"]["runs_if_10_episodes"] = 9
        with self.assertRaisesRegex(
            ValueError,
            "Held-out row contract changed for reference-control",
        ):
            validate_matrix(matrix)

    def test_sampling_settings_are_frozen_per_row(self):
        matrix = deepcopy(self.matrix)
        rows = {
            row["id"]: row
            for row in matrix["heldout_protocol"]["eligible_rows"]
        }
        rows["raw-reactive-openai"]["execution_settings"][
            "reasoning_effort"
        ] = None
        with self.assertRaisesRegex(
            ValueError,
            "Held-out row contract changed for raw-reactive-openai",
        ):
            validate_matrix(matrix)

    def test_temperature_override_is_rejected(self):
        matrix = deepcopy(self.matrix)
        rows = {
            row["id"]: row
            for row in matrix["heldout_protocol"]["eligible_rows"]
        }
        settings = rows["raw-reactive-gemini"]["execution_settings"]
        settings["temperature"] = 0.0
        settings["temperature_mode"] = "explicit"
        with self.assertRaisesRegex(
            ValueError,
            "Held-out row contract changed for raw-reactive-gemini",
        ):
            validate_matrix(matrix)

    def test_table_rows_are_frozen(self):
        matrix = deepcopy(self.matrix)
        table = next(
            table
            for table in matrix["paper_tables"]
            if table["id"] == "table-openai-matched-methods"
        )
        table["rows"].remove("react-openai")
        with self.assertRaisesRegex(
            ValueError,
            "Frozen paper table changed for table-openai-matched-methods",
        ):
            validate_matrix(matrix)

    def test_table_columns_are_frozen(self):
        matrix = deepcopy(self.matrix)
        table = next(
            table
            for table in matrix["paper_tables"]
            if table["id"] == "table-openai-matched-methods"
        )
        table["columns"].remove("feasible_obligation_success")
        with self.assertRaisesRegex(
            ValueError,
            "Frozen paper table changed for table-openai-matched-methods",
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
