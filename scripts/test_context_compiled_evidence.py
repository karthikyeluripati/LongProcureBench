"""Regression tests for the frozen context-compiled experiment."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_context_compiled_v01 import build_comparison
from frozen_context_compiled_v01 import (
    EPISODES,
    load_frozen_context_compiled_source,
)


class ContextCompiledFrozenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_frozen_context_compiled_source(ROOT)

    def test_frozen_source_is_exact_twenty_by_three_grid(self):
        self.assertEqual(len(self.source), 60)
        self.assertEqual(
            {record["episode_id"] for record in self.source},
            set(EPISODES),
        )
        self.assertEqual(
            len({
                (record["episode_id"], record["repeat"])
                for record in self.source
            }),
            60,
        )

    def test_matched_comparison_preserves_key_result(self):
        comparison = build_comparison()
        raw = comparison["raw_history"]
        compiled = comparison["context_compiled"]
        delta = comparison["delta"]

        self.assertEqual(raw["terminal_feasible"], 49)
        self.assertEqual(compiled["terminal_feasible"], 46)
        self.assertEqual(raw["feasible_obligation_success"], 41)
        self.assertEqual(compiled["feasible_obligation_success"], 40)
        self.assertEqual(raw["resolved_obligations"], 73)
        self.assertEqual(raw["actionable_obligations"], 94)
        self.assertEqual(compiled["resolved_obligations"], 72)
        self.assertEqual(compiled["actionable_obligations"], 86)
        self.assertEqual(raw["total_tokens"], 1640350)
        self.assertEqual(compiled["total_tokens"], 974208)
        self.assertAlmostEqual(
            delta["obligation_resolution_pp"],
            6.061355764473042,
        )
        self.assertAlmostEqual(
            delta["total_tokens_pct"],
            -40.6097479196513,
        )
        self.assertTrue(comparison["predeclared_gate"]["passed"])

    def test_key_long_horizon_failure_is_not_claimed_solved(self):
        comparison = build_comparison()
        self.assertLess(
            comparison["context_compiled"][
                "feasible_obligation_success"
            ],
            comparison["raw_history"]["feasible_obligation_success"] + 1,
        )


if __name__ == "__main__":
    unittest.main()
