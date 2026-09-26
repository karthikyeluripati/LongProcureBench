"""Regression tests for frozen cross-family reactive evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
import audit_cross_family_reactive_v01 as audit_module
from audit_cross_family_reactive_v01 import (
    build_summary,
    check_manifest,
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

    def test_frozen_action_counts_support_efficiency_diagnostic(self):
        summary = load_frozen_summary()
        expected = {
            "openai/gpt-5.6-sol": {
                "send_rfq": 165,
                "send_follow_up": 2,
                "mean_send_rfq": 2.75,
            },
            "anthropic/claude-opus-5-5": {
                "send_rfq": 181,
                "send_follow_up": 8,
                "mean_send_rfq": 181 / 60,
            },
            "gemini/gemini-3.8-flash": {
                "send_rfq": 183,
                "send_follow_up": 0,
                "mean_send_rfq": 3.05,
            },
        }
        for model, values in expected.items():
            with self.subTest(model=model):
                item = summary["by_model"][model]
                self.assertEqual(
                    item["action_type_counts"].get("send_rfq", 0),
                    values["send_rfq"],
                )
                self.assertEqual(
                    item["action_type_counts"].get("send_follow_up", 0),
                    values["send_follow_up"],
                )
                self.assertAlmostEqual(
                    item["mean_action_type_counts_per_run"]["send_rfq"],
                    values["mean_send_rfq"],
                )

    def test_manifest_provenance_drift_is_rejected(self):
        manifest = json.loads(
            (
                ROOT
                / "evidence"
                / "cross-family-reactive-v0.1"
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        mutations = [
            ("workflow_run", lambda value: value.__setitem__(
                "source_workflow_run_id", 1
            )),
            ("artifact_id", lambda value: value["source_artifacts"][0].__setitem__(
                "artifact_id", 1
            )),
            ("artifact_digest", lambda value: value["source_artifacts"][0].__setitem__(
                "digest", "sha256:" + "0" * 64
            )),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                changed = json.loads(json.dumps(manifest))
                mutate(changed)
                path = Path(tmp) / "manifest.json"
                path.write_text(
                    json.dumps(changed),
                    encoding="utf-8",
                )
                with patch.object(audit_module, "MANIFEST_PATH", path):
                    with self.assertRaisesRegex(
                        ValueError,
                        "manifest provenance mismatch",
                    ):
                        check_manifest()

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
