"""Regression tests for the frozen maintained-working-plan experiment."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import working_plan_audit_v01_lib as audit_module
from frozen_working_plan_v01 import (
    EPISODES,
    EXPECTED_PARTS,
    load_frozen_working_plan_source,
)
from working_plan_audit_v01_lib import (
    BOOTSTRAP_SAMPLER,
    _bootstrap_index,
    _check_declared_replay_files,
    check_frozen_comparison,
    check_manifest,
    check_source_provenance,
    evaluate_predeclared_gate,
)


class WorkingPlanFrozenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_frozen_working_plan_source(ROOT)
        check_manifest()
        check_source_provenance()
        cls.comparison = check_frozen_comparison()

    def test_frozen_source_is_exact_twenty_by_three_completed_grid(self):
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
            {record["status"] for record in self.source},
            {"completed"},
        )

    def test_matched_comparison_preserves_primary_result(self):
        context = self.comparison["context_compiled"]
        plan = self.comparison["working_plan"]
        delta = self.comparison["delta"]

        self.assertEqual(context["terminal_feasible"], 46)
        self.assertEqual(plan["terminal_feasible"], 41)
        self.assertEqual(context["feasible_obligation_success"], 40)
        self.assertEqual(plan["feasible_obligation_success"], 27)
        self.assertEqual(context["episode_success_v02"], 14)
        self.assertEqual(plan["episode_success_v02"], 17)
        self.assertEqual(plan["actionable_obligations"], 86)
        self.assertEqual(plan["resolved_obligations"], 63)
        self.assertEqual(plan["total_tokens"], 1316025)
        self.assertAlmostEqual(plan["cost_usd"], 7.8465334)
        self.assertAlmostEqual(delta["terminal_feasible_pp"], -8.3333333333)
        self.assertAlmostEqual(
            delta["feasible_obligation_success_pp"],
            -21.6666666667,
        )
        self.assertAlmostEqual(delta["episode_success_v02_pp"], 5.0)
        self.assertFalse(self.comparison["predeclared_gate"]["passed"])

    def test_plan_diagnostics_show_plan_was_active_not_ignored(self):
        diagnostics = self.comparison["plan_diagnostics"]
        self.assertEqual(diagnostics["total_plan_updates"], 473)
        self.assertEqual(diagnostics["total_plan_rejections"], 8)
        self.assertEqual(diagnostics["runs_with_plan_rejections"], 7)
        self.assertAlmostEqual(
            diagnostics["accepted_plan_first_step_action_type_match_rate"],
            0.8530927835051546,
        )
        self.assertAlmostEqual(
            diagnostics[
                "accepted_plan_first_step_action_and_supplier_match_rate"
            ],
            0.7809278350515464,
        )
        self.assertAlmostEqual(
            diagnostics["objective_change_rate"],
            0.7796610169491526,
        )
        self.assertAlmostEqual(
            diagnostics["stop_condition_change_rate"],
            0.7990314769975787,
        )

    def test_observed_result_fails_both_predeclared_gate_branches(self):
        verdict = evaluate_predeclared_gate({
            "terminal_feasible_pp": -8.3333333333,
            "feasible_obligation_success_pp": -21.6666666667,
            "episode_success_v02_pp": 5.0,
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

    def test_bootstrap_sample_plan_matches_prior_frozen_audits(self):
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
            / "working-plan-reactive-v0.1"
            / "manifest.json"
        ).read_text(encoding="utf-8"))
        verification = manifest["source_verification"]
        self.assertEqual(
            verification["selected_compaction_sha256"],
            "392060d51c9e8b430156428f53dd20c7c4caae4da062d23b51bc7a6eb6b92923",
        )
        self.assertEqual(
            verification["selected_raw_provenance_sha256"],
            "8395185f72bf3b52e624385e2f524d87113582065075852be08223b23584d8a3",
        )

    def test_declared_replay_parts_are_exact_and_no_orphans_exist(self):
        evidence = (
            ROOT / "evidence" / "working-plan-reactive-v0.1"
        )
        _check_declared_replay_files(evidence, EXPECTED_PARTS)
        self.assertEqual(
            {path.name for path in evidence.glob("replay-source*.b64")},
            set(EXPECTED_PARTS),
        )

    def test_undeclared_replay_fragment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "replay-source.part-01.b64").write_text(
                "x", encoding="utf-8"
            )
            (directory / "replay-source.orphan.b64").write_text(
                "x", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ValueError,
                "replay file set mismatch",
            ):
                _check_declared_replay_files(
                    directory,
                    ("replay-source.part-01.b64",),
                )

    def test_record_provenance_drift_is_rejected(self):
        provenance_path = (
            ROOT
            / "evidence"
            / "working-plan-reactive-v0.1"
            / "source-provenance.txt"
        )
        lines = provenance_path.read_text(
            encoding="utf-8"
        ).splitlines()
        fields = lines[0].split("|")
        fields[-1] = "0" * 64
        lines[0] = "|".join(fields)

        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "source-provenance.txt"
            changed.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )
            with patch.object(
                audit_module,
                "PROVENANCE_PATH",
                changed,
            ):
                with self.assertRaises(ValueError):
                    check_source_provenance()

    def test_manifest_artifact_replay_and_bootstrap_drift_is_rejected(self):
        manifest_path = (
            ROOT
            / "evidence"
            / "working-plan-reactive-v0.1"
            / "manifest.json"
        )
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        mutations = [
            (
                "artifact_digest",
                lambda value: value.__setitem__(
                    "source_artifact_digest", "sha256:" + "0" * 64
                ),
            ),
            (
                "replay_digest",
                lambda value: value["storage"].__setitem__(
                    "compressed_sha256", "0" * 64
                ),
            ),
            (
                "compaction_root",
                lambda value: value["source_verification"].__setitem__(
                    "selected_compaction_sha256", "0" * 64
                ),
            ),
            (
                "raw_provenance_root",
                lambda value: value["source_verification"].__setitem__(
                    "selected_raw_provenance_sha256", "0" * 64
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
                path.write_text(json.dumps(changed), encoding="utf-8")
                with patch.object(
                    audit_module,
                    "MANIFEST_PATH",
                    path,
                ):
                    with self.assertRaises(ValueError):
                        check_manifest()


if __name__ == "__main__":
    unittest.main()
