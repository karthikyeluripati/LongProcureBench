"""Regression tests for the frozen context-compiled experiment."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import audit_context_compiled_v01 as audit_module
from audit_context_compiled_v01 import (
    BOOTSTRAP_SAMPLER,
    _bootstrap_index,
    build_comparison,
    check_frozen_comparison,
    check_manifest,
)
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

    def test_bootstrap_sample_plan_is_version_independent(self):
        self.assertEqual(BOOTSTRAP_SAMPLER, "sha256-index-v1")
        self.assertEqual(
            [_bootstrap_index(0, draw) for draw in range(20)],
            [15, 14, 18, 4, 14, 19, 0, 13, 6, 1,
             18, 6, 1, 17, 16, 5, 17, 18, 4, 2],
        )
        self.assertEqual(
            [_bootstrap_index(1, draw) for draw in range(20)],
            [15, 3, 9, 5, 11, 16, 12, 8, 16, 12,
             4, 17, 0, 1, 10, 15, 11, 12, 5, 19],
        )

    def test_frozen_comparison_replays_with_recorded_sampler(self):
        check_manifest()
        comparison = check_frozen_comparison()
        self.assertEqual(
            comparison["cluster_bootstrap"]["sampler"],
            "sha256-index-v1",
        )

    def test_manifest_replay_and_bootstrap_drift_is_rejected(self):
        manifest_path = (
            ROOT
            / "evidence"
            / "context-compiled-reactive-v0.1"
            / "manifest.json"
        )
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        mutations = [
            (
                "replay_digest",
                lambda value: value["storage"].__setitem__(
                    "compressed_sha256", "0" * 64
                ),
            ),
            (
                "episode_count",
                lambda value: value.__setitem__("episodes", 19),
            ),
            (
                "bootstrap_seed",
                lambda value: value["comparison"].__setitem__(
                    "bootstrap_seed", 1
                ),
            ),
            (
                "bootstrap_sampler",
                lambda value: value["comparison"].__setitem__(
                    "bootstrap_sampler", "other"
                ),
            ),
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
                    with self.assertRaises(ValueError):
                        check_manifest()

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
