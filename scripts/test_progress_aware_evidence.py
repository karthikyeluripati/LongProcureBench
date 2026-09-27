"""Regression checks for frozen progress-aware evidence."""
from pathlib import Path
import tempfile
import unittest

from audit_progress_aware_v01 import (
    _gate,
    build_comparison,
    check_provenance_entries,
)
from frozen_progress_aware_v01 import (
    EXPECTED_EPISODES,
    EXPECTED_REPEATS,
    EXPECTED_RUNS,
    load_frozen_progress_aware_source,
)


ROOT = Path(__file__).resolve().parents[1]


class FrozenProgressAwareEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comparison = build_comparison()

    def test_frozen_grid_and_usage_contract(self):
        records = load_frozen_progress_aware_source(ROOT)
        self.assertEqual(len(records), EXPECTED_RUNS)
        self.assertEqual(
            len({record["episode_id"] for record in records}),
            EXPECTED_EPISODES,
        )
        self.assertEqual(
            {record["repeat"] for record in records},
            set(range(1, EXPECTED_REPEATS + 1)),
        )
        self.assertTrue(
            all(
                not record["policy_metrics"]["usage_incomplete"]
                for record in records
            )
        )
        self.assertTrue(
            all(
                record["policy_metrics"]["model_calls_failed"] == 0
                for record in records
            )
        )

    def test_predeclared_gate_rejects_frozen_result(self):
        comparison = self.comparison
        gate = comparison["predeclared_gate"]
        self.assertFalse(gate["passed"])
        self.assertLess(
            comparison["delta"]["feasible_obligation_success_pp"],
            -2.0,
        )

    def test_gate_branches_are_frozen(self):
        self.assertTrue(_gate({
            "feasible_obligation_success_pp": 5.0,
            "terminal_feasible_pp": -5.0,
            "episode_success_v02_pp": 0.0,
            "total_tokens_pct": 15.0,
        })["branch1"]["passed"])
        self.assertTrue(_gate({
            "feasible_obligation_success_pp": -2.0,
            "terminal_feasible_pp": -5.0,
            "episode_success_v02_pp": 5.0,
            "total_tokens_pct": 15.0,
        })["branch2"]["passed"])

    def test_mechanism_diagnostic_records_zero_interventions(self):
        comparison = self.comparison
        diagnostic = comparison["mechanism_diagnostic"]
        self.assertEqual(diagnostic["no_progress_marks"], 15)
        self.assertEqual(diagnostic["runs_with_no_progress_marks"], 13)
        self.assertEqual(diagnostic["guard_interventions"], 0)
        self.assertEqual(diagnostic["guard_retry_calls"], 0)
        self.assertEqual(
            diagnostic["guard_retry_noncompliance"],
            0,
        )
        self.assertEqual(
            diagnostic["episode_obligation_success_effect_counts"],
            {"improved": 1, "worsened": 7, "tied": 12},
        )

    def test_frozen_matched_result_is_preserved(self):
        comparison = self.comparison
        self.assertEqual(
            comparison["context_compiled"]["feasible_obligation_success"],
            40,
        )
        self.assertEqual(
            comparison["progress_aware"]["feasible_obligation_success"],
            30,
        )
        self.assertEqual(
            comparison["context_compiled"]["terminal_feasible"],
            46,
        )
        self.assertEqual(
            comparison["progress_aware"]["terminal_feasible"],
            47,
        )
        self.assertEqual(
            comparison["progress_aware"]["episode_success_v02"],
            15,
        )

    def test_provenance_entries_are_linked_to_compact_replay(self):
        records = load_frozen_progress_aware_source(ROOT)
        check_provenance_entries(records)

        source = (
            ROOT
            / "evidence"
            / "progress-aware-reactive-v0.1"
            / "source-provenance.txt"
        ).read_text(encoding="utf-8")
        lines = source.splitlines()
        fields = lines[0].split("|")
        fields[4] = "0" * 64
        lines[0] = "|".join(fields)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source-provenance.txt"
            path.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "does not match frozen replay",
            ):
                check_provenance_entries(records, path)


if __name__ == "__main__":
    unittest.main()
