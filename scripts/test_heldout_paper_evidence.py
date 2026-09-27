"""Regression checks for frozen held-out paper evidence."""
from pathlib import Path
import unittest

from audit_heldout_paper_v01 import (
    EVIDENCE_DIR,
    SOURCE_ARTIFACTS,
    audit_committed_outputs,
)


class HeldoutPaperEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = audit_committed_outputs()

    def test_complete_frozen_grid(self):
        self.assertEqual(self.results["total_runs"], 160)
        self.assertEqual(self.results["model_backed_runs"], 150)
        self.assertEqual(self.results["reference_control_runs"], 10)
        self.assertEqual(
            self.results["model_backed_totals"]["runs"],
            150,
        )

    def test_reference_control_is_clean(self):
        reference = self.results["reference_control"]
        self.assertEqual(reference["terminal_feasible"], [10, 10])
        self.assertEqual(
            reference["feasible_obligation_success"],
            [10, 10],
        )
        self.assertEqual(reference["episode_success_v02"], [10, 10])
        self.assertEqual(reference["obligation_resolution"], [20, 20])
        self.assertEqual(
            reference["economic_objective_satisfied"],
            [10, 10],
        )

    def test_provider_diverse_raw_reliability_gap_is_preserved(self):
        raw = self.results["provider_diverse_raw_reactive"]
        self.assertEqual(
            raw["raw-reactive-openai"]["terminal_feasible"],
            [26, 30],
        )
        self.assertEqual(
            raw["raw-reactive-openai"][
                "feasible_obligation_success"
            ],
            [12, 30],
        )
        self.assertEqual(
            raw["raw-reactive-anthropic"]["terminal_feasible"],
            [22, 30],
        )
        self.assertEqual(
            raw["raw-reactive-anthropic"][
                "feasible_obligation_success"
            ],
            [4, 30],
        )
        self.assertEqual(
            raw["raw-reactive-gemini"]["terminal_feasible"],
            [23, 30],
        )
        self.assertEqual(
            raw["raw-reactive-gemini"][
                "feasible_obligation_success"
            ],
            [6, 30],
        )

    def test_context_and_react_tie_primary_metric(self):
        matched = self.results["matched_openai"]
        self.assertEqual(
            matched["context-compiled-openai"][
                "feasible_obligation_success"
            ],
            [20, 30],
        )
        self.assertEqual(
            matched["react-openai"]["feasible_obligation_success"],
            [20, 30],
        )
        self.assertEqual(
            self.results["matched_deltas_vs_context"][
                "react-openai"
            ]["feasible_obligation_success_pp"],
            0,
        )

    def test_react_strict_gain_and_efficiency_cost_are_frozen(self):
        matched = self.results["matched_openai"]
        self.assertEqual(
            matched["context-compiled-openai"]["episode_success_v02"],
            [6, 30],
        )
        self.assertEqual(
            matched["react-openai"]["episode_success_v02"],
            [15, 30],
        )

        delta = self.results["matched_deltas_vs_context"][
            "react-openai"
        ]
        self.assertEqual(delta["episode_success_v02_pp"], 30)
        self.assertGreater(delta["total_tokens_pct"], 73)
        self.assertGreater(delta["cost_pct"], 98)
        self.assertGreater(delta["latency_pct"], 57)

        interval = self.results[
            "paired_episode_cluster_bootstrap_vs_context"
        ]["react-openai"]
        self.assertGreater(
            interval["episode_success_v02_pp"][0],
            0,
        )
        self.assertLessEqual(
            interval["feasible_obligation_success_pp"][0],
            0,
        )
        self.assertGreaterEqual(
            interval["feasible_obligation_success_pp"][1],
            0,
        )
        self.assertGreater(interval["total_tokens_pct"][0], 0)
        self.assertGreater(interval["cost_pct"][0], 0)

    def test_context_reduces_raw_openai_obligation_failures(self):
        interval = self.results[
            "paired_episode_cluster_bootstrap_vs_context"
        ]["raw-reactive-openai"]
        self.assertLess(
            interval["obligation_resolution_pp"][1],
            0,
        )
        taxonomy = self.results["failure_taxonomy"]
        gaps = {
            row["method"]: row["unresolved_count"]
            for row in taxonomy
            if row["unresolved_obligation_class"]
            == "resolve_requirement_gap"
        }
        self.assertEqual(gaps["raw-reactive-openai"], 14)
        self.assertEqual(gaps["context-compiled-openai"], 6)
        self.assertEqual(gaps["react-openai"], 6)

    def test_exact_source_artifacts_are_committed(self):
        self.assertEqual(len(SOURCE_ARTIFACTS), 7)
        for spec in SOURCE_ARTIFACTS.values():
            path = EVIDENCE_DIR / spec["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.stat().st_size, spec["bytes"])


if __name__ == "__main__":
    unittest.main()
