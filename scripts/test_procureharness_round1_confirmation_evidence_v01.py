"""Regression checks for frozen ProcureHarness Round 1 confirmation evidence."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_procureharness_search_v01 import DEVELOPMENT_EPISODES
from select_procureharness_validation_v01 import (
    validate_frozen_validation_selection,
)

EVIDENCE_ROOT = ROOT / "evidence" / "procureharness-round1-confirmation-v0.1"
GATE_ROOT = ROOT / "evidence" / "procureharness-search-gates-v0.1"
CANDIDATES = ("ph-r1-c02", "ph-r1-c05")
REPEATS = (1, 2, 3)


class ProcureHarnessRound1ConfirmationEvidenceTests(unittest.TestCase):
    def _manifest(self) -> dict:
        return json.loads(
            (EVIDENCE_ROOT / "manifest.json").read_text(encoding="utf-8")
        )

    @staticmethod
    def _expected_summary_row(
        *,
        raw_result: dict,
        episode_id: str,
        repeat: int,
    ) -> dict:
        evaluation = raw_result.get("evaluation") or {}
        metrics = raw_result.get("policy_metrics") or {}
        obligations = evaluation.get("obligations") or {}

        return {
            "episode_id": episode_id,
            "repeat": repeat,
            "status": raw_result["status"],
            "terminal_feasible": bool(evaluation.get("episode_success")),
            "feasible_obligation_success": bool(
                evaluation.get("feasible_obligation_success")
            ),
            "strict_v02": bool(evaluation.get("episode_success_v02")),
            "economic_objective": bool(
                (evaluation.get("economic_objective") or {}).get("satisfied")
            ),
            "obligation_resolved": obligations.get("resolved"),
            "obligation_actionable": obligations.get("actionable"),
            "obligation_resolution_rate": obligations.get("resolution_rate"),
            "accepted_actions": (
                (evaluation.get("efficiency") or {}).get("accepted_actions")
            ),
            "model_calls": metrics.get("model_calls"),
            "total_tokens": metrics.get("total_tokens"),
            "latency_ms": metrics.get("latency_ms"),
            "known_cost_usd": metrics.get("cost_usd"),
            "deterministic_action_fraction": metrics.get(
                "deterministic_action_fraction"
            ),
        }

    def test_raw_result_filenames_match_exact_frozen_grid(self):
        expected_names = {
            f"{episode_id}.json"
            for episode_id in DEVELOPMENT_EPISODES
        }

        for candidate_id in CANDIDATES:
            root = (
                EVIDENCE_ROOT
                / "results"
                / candidate_id
                / "development_confirmation"
            )
            for repeat in REPEATS:
                repeat_dir = root / f"r{repeat}"
                self.assertTrue(
                    repeat_dir.is_dir(),
                    f"missing repeat directory: {repeat_dir}",
                )
                actual_names = {
                    path.name
                    for path in repeat_dir.iterdir()
                    if path.is_file()
                }
                self.assertEqual(
                    actual_names,
                    expected_names,
                    (
                        f"{candidate_id} repeat {repeat} raw filenames "
                        "do not match the frozen 001-020 grid"
                    ),
                )

    def test_manifest_source_set_is_exact_grid_plus_two_summaries(self):
        manifest = self._manifest()
        self.assertEqual(manifest["candidate_ids"], list(CANDIDATES))
        self.assertEqual(manifest["repeats"], 3)
        self.assertEqual(manifest["total_runs"], 120)

        expected_paths = set()
        for candidate_id in CANDIDATES:
            base = (
                EVIDENCE_ROOT
                / "results"
                / candidate_id
                / "development_confirmation"
            )
            expected_paths.add(str((base / "summary.json").relative_to(ROOT)))
            for repeat in REPEATS:
                for episode_id in DEVELOPMENT_EPISODES:
                    expected_paths.add(
                        str(
                            (
                                base
                                / f"r{repeat}"
                                / f"{episode_id}.json"
                            ).relative_to(ROOT)
                        )
                    )

        source_files = manifest.get("source_files")
        self.assertIsInstance(source_files, list)
        self.assertEqual(len(source_files), 122)
        manifested_paths = {item["path"] for item in source_files}
        self.assertEqual(manifested_paths, expected_paths)

        for item in source_files:
            path = ROOT / item["path"]
            self.assertTrue(path.is_file(), f"missing manifested file: {path}")
            raw = path.read_bytes()
            self.assertEqual(
                sha256(raw).hexdigest(),
                item["sha256"],
                f"manifest SHA-256 mismatch: {path}",
            )
            self.assertEqual(
                len(raw),
                item["bytes"],
                f"manifest byte-count mismatch: {path}",
            )

        gate_files = manifest.get("gate_files")
        self.assertIsInstance(gate_files, list)
        expected_gate_paths = {
            str(
                (
                    GATE_ROOT / "validation-selection-round-1.json"
                ).relative_to(ROOT)
            ),
        }
        self.assertEqual(
            {item["path"] for item in gate_files},
            expected_gate_paths,
        )
        for item in gate_files:
            path = ROOT / item["path"]
            self.assertTrue(path.is_file(), f"missing manifested gate: {path}")
            raw = path.read_bytes()
            self.assertEqual(
                sha256(raw).hexdigest(),
                item["sha256"],
                f"manifest gate SHA-256 mismatch: {path}",
            )
            self.assertEqual(
                len(raw),
                item["bytes"],
                f"manifest gate byte-count mismatch: {path}",
            )

    def test_summary_rows_match_raw_results_and_exact_frozen_run_keys(self):
        expected_keys = [
            (episode_id, repeat)
            for repeat in REPEATS
            for episode_id in DEVELOPMENT_EPISODES
        ]

        for candidate_id in CANDIDATES:
            root = (
                EVIDENCE_ROOT
                / "results"
                / candidate_id
                / "development_confirmation"
            )
            summary_path = root / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["candidate_id"], candidate_id)
            self.assertEqual(summary["phase"], "development_confirmation")
            self.assertEqual(summary["planned_runs"], 60)
            self.assertEqual(summary["completed_runs"], 60)
            self.assertEqual(summary["execution_failures"], 0)

            rows = summary["rows"]
            observed_keys = [
                (row.get("episode_id"), row.get("repeat"))
                for row in rows
            ]
            self.assertEqual(observed_keys, expected_keys)

            for row in rows:
                episode_id = row["episode_id"]
                repeat = row["repeat"]
                raw_path = (
                    root
                    / f"r{repeat}"
                    / f"{episode_id}.json"
                )
                raw_result = json.loads(
                    raw_path.read_text(encoding="utf-8")
                )
                expected_row = self._expected_summary_row(
                    raw_result=raw_result,
                    episode_id=episode_id,
                    repeat=repeat,
                )
                self.assertEqual(
                    row,
                    expected_row,
                    (
                        f"{candidate_id} summary row does not match raw "
                        f"result for {episode_id} repeat {repeat}"
                    ),
                )


    def test_frozen_validation_selection_recomputes_from_bound_summaries(self):
        selection_path = GATE_ROOT / "validation-selection-round-1.json"
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        validate_frozen_validation_selection(selection)
        self.assertEqual(
            selection["pending_efficiency_candidate_ids"],
            list(CANDIDATES),
        )
        self.assertEqual(
            selection["validation_slot_candidate_ids"],
            list(CANDIDATES),
        )
        self.assertEqual(selection["validation_selected_candidate_ids"], [])


if __name__ == "__main__":
    unittest.main()
