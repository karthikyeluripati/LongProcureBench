"""Regression tests for frozen cross-family reactive evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
from audit_cross_family_reactive_v01 import (
    build_summary,
    load_frozen_summary,
    rescore_records,
)
from frozen_cross_family_reactive_v01 import (
    EPISODES,
    MODELS,
    load_frozen_cross_family_source,
    reconstruct_actions,
)


class CrossFamilyReactiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_frozen_cross_family_source(ROOT)

    def test_frozen_source_has_exact_three_by_twenty_by_three_grid(self):
        self.assertEqual(len(self.source), 180)
        self.assertEqual({r["model"] for r in self.source}, set(MODELS))
        self.assertEqual(
            {r["episode_id"] for r in self.source},
            set(EPISODES),
        )
        self.assertEqual(
            len({
                (r["model"], r["episode_id"], r["repeat"])
                for r in self.source
            }),
            180,
        )

    def test_compact_actions_reconstruct_runner_owned_ids(self):
        record = self.source[0]
        actions = reconstruct_actions(record)
        self.assertEqual(len(actions), len(record["decisions"]))
        self.assertEqual(
            [a["action_id"] for a in actions],
            [f"a{i}" for i in range(1, len(actions) + 1)],
        )
        self.assertTrue(
            all(a["episode_id"] == record["episode_id"] for a in actions)
        )

    def test_one_frozen_trajectory_replays_under_current_evaluator(self):
        record = next(
            item
            for item in self.source
            if item["model"] == "openai/gpt-5.6-sol"
            and item["episode_id"] == "electrical-bongabon-generator-001"
            and item["repeat"] == 1
        )
        evaluation = LongProcureBenchEvaluator(
            repo_root=ROOT
        ).evaluate_actions(
            record["episode_id"],
            reconstruct_actions(record),
        )
        self.assertEqual(evaluation["evaluation_version"], "0.2.0")
        self.assertIn("obligations", evaluation)

    def test_frozen_summary_contains_core_cross_family_signal(self):
        summary = load_frozen_summary()
        combined = summary["combined"]
        self.assertEqual(summary["runs"], 180)
        self.assertEqual(combined["terminal_feasible"], 113)
        self.assertEqual(combined["feasible_obligation_success"], 57)
        self.assertEqual(combined["episode_success_v02"], 26)
        self.assertEqual(combined["actionable_obligations"], 241)
        self.assertEqual(combined["resolved_obligations"], 134)
        self.assertEqual(combined["unresolved_obligations"], 107)
        self.assertAlmostEqual(
            combined["known_cost_usd"],
            17.643001375,
            places=9,
        )

    def test_episode_016_preserves_terminal_obligation_gap(self):
        summary = load_frozen_summary()
        episode = summary["by_episode"][
            "electrical-dla-power-supply-016"
        ]
        self.assertEqual(episode["runs"], 9)
        self.assertEqual(episode["terminal_feasible"], 9)
        self.assertEqual(episode["feasible_obligation_success"], 0)
        self.assertEqual(episode["unresolved_obligations"], 9)


if __name__ == "__main__":
    unittest.main()
