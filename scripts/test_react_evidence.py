"""Regression checks for frozen ReAct comparator evidence."""
from pathlib import Path
import tempfile
import unittest

from audit_react_comparator_v01 import (
    build_comparison,
    check_provenance_entries,
)
from frozen_react_comparator_v01 import (
    EXPECTED_EPISODES,
    EXPECTED_REPEATS,
    EXPECTED_RUNS,
    load_frozen_react_source,
)


ROOT = Path(__file__).resolve().parents[1]


class FrozenReActEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comparison = build_comparison()

    def test_frozen_grid_and_react_contract(self):
        records = load_frozen_react_source(ROOT)
        self.assertEqual(len(records), EXPECTED_RUNS)
        self.assertEqual(
            len({record["episode_id"] for record in records}),
            EXPECTED_EPISODES,
        )
        self.assertEqual(
            {record["repeat"] for record in records},
            set(range(1, EXPECTED_REPEATS + 1)),
        )
        for record in records:
            metrics = record["policy_metrics"]
            self.assertEqual(
                metrics["model_calls_attempted"],
                len(record["decisions"]),
            )
            self.assertEqual(
                metrics["react_steps_proposed"],
                len(record["decisions"]),
            )
            self.assertEqual(
                metrics["react_steps_accepted"],
                len(record["decisions"]),
            )
            self.assertEqual(metrics["model_calls_failed"], 0)
            self.assertFalse(metrics["usage_incomplete"])

    def test_matched_result_is_frozen(self):
        comparison = self.comparison
        self.assertEqual(
            comparison["context_compiled"]["terminal_feasible"],
            46,
        )
        self.assertEqual(comparison["react"]["terminal_feasible"], 52)
        self.assertEqual(
            comparison["context_compiled"]["feasible_obligation_success"],
            40,
        )
        self.assertEqual(
            comparison["react"]["feasible_obligation_success"],
            41,
        )
        self.assertEqual(
            comparison["context_compiled"]["episode_success_v02"],
            14,
        )
        self.assertEqual(
            comparison["react"]["episode_success_v02"],
            27,
        )

    def test_react_is_external_comparator_without_inclusion_gate(self):
        comparison = self.comparison
        self.assertEqual(comparison["role"], "external_comparator")
        self.assertIsNone(comparison["decision"]["inclusion_gate"])
        self.assertEqual(
            comparison["decision"]["next_step"],
            "Freeze the development comparator set before any held-out "
            "evaluation.",
        )

    def test_strict_gain_and_resource_increase_are_preserved(self):
        comparison = self.comparison
        delta = comparison["delta"]
        self.assertGreater(delta["episode_success_v02_pp"], 20.0)
        self.assertGreater(delta["terminal_feasible_pp"], 9.0)
        self.assertGreater(delta["total_tokens_pct"], 49.0)
        self.assertGreater(delta["cost_pct"], 73.0)

        intervals = comparison["cluster_bootstrap"]["95pct_ci"]
        self.assertGreater(
            intervals["episode_success_v02_pp"][0],
            0.0,
        )
        self.assertGreater(
            intervals["total_tokens_pct"][0],
            0.0,
        )
        self.assertGreater(intervals["cost_pct"][0], 0.0)

    def test_react_diagnostic_shows_complete_thought_action_steps(self):
        diagnostic = self.comparison["react_diagnostic"]
        self.assertEqual(diagnostic["react_steps_proposed"], 488)
        self.assertEqual(diagnostic["react_steps_accepted"], 488)
        self.assertEqual(
            diagnostic["runs_with_complete_react_steps"],
            60,
        )
        self.assertEqual(diagnostic["thought_chars_total"], 81495)
        self.assertEqual(diagnostic["thought_chars_max"], 252)
        self.assertEqual(
            diagnostic["episode_effect_counts"]["episode_success_v02"],
            {"improved": 8, "tied": 12, "worsened": 0},
        )

    def test_provenance_entries_are_linked_to_compact_replay(self):
        records = load_frozen_react_source(ROOT)
        check_provenance_entries(records)

        source = (
            ROOT
            / "evidence"
            / "react-comparator-v0.1"
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
