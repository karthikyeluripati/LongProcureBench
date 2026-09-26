"""Regression tests for the frozen operational-ledger experiment."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import audit_operational_ledger_v01 as audit_module
from audit_operational_ledger_v01 import (
    BOOTSTRAP_SAMPLER,
    _bootstrap_index,
    _check_declared_replay_files,
    check_frozen_comparison,
    check_manifest,
    evaluate_predeclared_gate,
)
from frozen_operational_ledger_v01 import (
    EPISODES,
    load_frozen_operational_ledger_source,
)


class OperationalLedgerFrozenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_frozen_operational_ledger_source(ROOT)
        check_manifest()
        cls.comparison = check_frozen_comparison()

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
        self.assertEqual(
            sum(record["source_code"] == 0 for record in self.source),
            43,
        )
        self.assertEqual(
            sum(record["source_code"] == 1 for record in self.source),
            17,
        )

    def test_recovery_selection_is_key_frozen(self):
        by_key = {
            (record["episode_id"], record["repeat"]): record["source_code"]
            for record in self.source
        }
        self.assertEqual(
            by_key[("electrical-dla-battery-charger-015", 1)],
            0,
        )
        self.assertEqual(
            by_key[("electrical-dla-battery-charger-015", 2)],
            1,
        )
        self.assertEqual(
            by_key[("electrical-dla-battery-charger-015", 3)],
            1,
        )
        for episode_id in EPISODES[15:]:
            for repeat in (1, 2, 3):
                self.assertEqual(by_key[(episode_id, repeat)], 1)

    def test_matched_comparison_preserves_primary_result(self):
        context = self.comparison["context_compiled"]
        ledger = self.comparison["operational_ledger"]
        delta = self.comparison["delta"]

        self.assertEqual(context["terminal_feasible"], 46)
        self.assertEqual(ledger["terminal_feasible"], 31)
        self.assertEqual(context["feasible_obligation_success"], 40)
        self.assertEqual(ledger["feasible_obligation_success"], 28)
        self.assertEqual(context["episode_success_v02"], 14)
        self.assertEqual(ledger["episode_success_v02"], 19)
        self.assertEqual(
            ledger["status_counts"],
            {"completed": 49, "max_actions": 11},
        )
        self.assertAlmostEqual(delta["terminal_feasible_pp"], -25.0)
        self.assertAlmostEqual(
            delta["feasible_obligation_success_pp"],
            -20.0,
        )
        self.assertAlmostEqual(
            delta["episode_success_v02_pp"],
            8.3333333333,
        )
        self.assertFalse(self.comparison["predeclared_gate"]["passed"])

    def test_mechanism_signal_records_clarification_loops(self):
        context = self.comparison["context_compiled"]["action_type_counts"]
        ledger = self.comparison["operational_ledger"]["action_type_counts"]
        self.assertEqual(context["request_buyer_clarification"], 47)
        self.assertEqual(ledger["request_buyer_clarification"], 652)
        self.assertEqual(
            self.comparison["operational_ledger"]["model_calls"],
            1077,
        )

    def test_predeclared_gate_rejects_observed_guardrail_failures(self):
        verdict = evaluate_predeclared_gate({
            "terminal_feasible_pp": -25.0,
            "feasible_obligation_success_pp": -20.0,
            "episode_success_v02_pp": 8.3,
        })
        self.assertFalse(verdict["passed"])
        self.assertIsNone(verdict["matched_condition"])
        self.assertFalse(verdict["feasible_obligation_gain"]["passed"])
        self.assertFalse(verdict["strict_gain_guardrailed"]["passed"])

    def test_predeclared_gate_supports_each_frozen_branch(self):
        obligation = evaluate_predeclared_gate({
            "terminal_feasible_pp": -5.0,
            "feasible_obligation_success_pp": 5.0,
            "episode_success_v02_pp": 0.0,
        })
        self.assertTrue(obligation["passed"])
        self.assertEqual(
            obligation["matched_condition"],
            "feasible_obligation_gain",
        )

        strict = evaluate_predeclared_gate({
            "terminal_feasible_pp": -4.0,
            "feasible_obligation_success_pp": -2.0,
            "episode_success_v02_pp": 5.0,
        })
        self.assertTrue(strict["passed"])
        self.assertEqual(
            strict["matched_condition"],
            "strict_gain_guardrailed",
        )

    def test_bootstrap_sample_plan_matches_prior_context_audit(self):
        self.assertEqual(BOOTSTRAP_SAMPLER, "sha256-index-v1")
        self.assertEqual(
            [_bootstrap_index(0, draw) for draw in range(20)],
            [15, 14, 18, 4, 14, 19, 0, 13, 6, 1,
             18, 6, 1, 17, 16, 5, 17, 18, 4, 2],
        )

    def test_artifact_derived_source_roots_are_frozen(self):
        manifest = json.loads((
            ROOT
            / "evidence"
            / "operational-ledger-reactive-v0.1"
            / "manifest.json"
        ).read_text(encoding="utf-8"))
        verification = manifest["source_verification"]
        self.assertEqual(
            verification["selected_compaction_sha256"],
            "9c1651f0ecb07877259dc56e2f75a8d0d1a7506ab527aaceb9ed8c650ed89c68",
        )
        self.assertEqual(
            verification["selected_raw_provenance_sha256"],
            "5a960571e1f3bed0613d77881062982844987243db462f4ca62399e7d95af4e8",
        )

    def test_undeclared_replay_fragment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in (
                "replay-source.part-01.b64",
                "replay-source.part-02.b64",
            ):
                (directory / name).write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "replay file set mismatch",
            ):
                _check_declared_replay_files(
                    directory,
                    ("replay-source.part-01.b64",),
                )

    def test_manifest_provenance_and_selection_drift_is_rejected(self):
        manifest_path = (
            ROOT
            / "evidence"
            / "operational-ledger-reactive-v0.1"
            / "manifest.json"
        )
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        mutations = [
            (
                "original_artifact_digest",
                lambda value: value["source_artifacts"]["original"].__setitem__(
                    "artifact_digest", "sha256:" + "0" * 64
                ),
            ),
            (
                "recovery_artifact_digest",
                lambda value: value["source_artifacts"]["recovery"].__setitem__(
                    "artifact_digest", "sha256:" + "0" * 64
                ),
            ),
            (
                "replay_digest",
                lambda value: value["storage"].__setitem__(
                    "compressed_sha256", "0" * 64
                ),
            ),
            (
                "artifact_compaction_root",
                lambda value: value["source_verification"].__setitem__(
                    "selected_compaction_sha256", "0" * 64
                ),
            ),
            (
                "artifact_raw_provenance_root",
                lambda value: value["source_verification"].__setitem__(
                    "selected_raw_provenance_sha256", "0" * 64
                ),
            ),
            (
                "discard_key",
                lambda value: value["recovery_selection"].__setitem__(
                    "discarded_recovery_key", "other"
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


if __name__ == "__main__":
    unittest.main()
