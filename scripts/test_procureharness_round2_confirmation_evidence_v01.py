"""Audit frozen ProcureHarness Round-2 confirmation evidence."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MODEL,
    PROTOCOL_ID,
    REASONING_EFFORT,
    TEMPERATURE,
    _authorization_sha256,
    validate_phase_authorization,
)
from select_procureharness_validation_v01 import (
    validate_frozen_validation_selection,
)

EVIDENCE_ROOT = (
    ROOT / "evidence" / "procureharness-round2-confirmation-v0.1"
)
MANIFEST_PATH = EVIDENCE_ROOT / "manifest.json"
GATE_ROOT = ROOT / "evidence" / "procureharness-search-gates-v0.1"
SCREENING_SELECTION_PATH = GATE_ROOT / "screening-selection-round-2.json"
VALIDATION_SELECTION_PATH = GATE_ROOT / "validation-selection-round-2.json"
CANDIDATES = ("ph-r2-c12", "ph-r2-c09")
REPEATS = (1, 2, 3)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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


class ProcureHarnessRound2ConfirmationEvidenceTests(unittest.TestCase):
    def setUp(self):
        manifest_exists = MANIFEST_PATH.is_file()
        selection_exists = VALIDATION_SELECTION_PATH.is_file()
        if not manifest_exists and not selection_exists:
            self.skipTest(
                "Round-2 confirmation evidence has not been materialized yet"
            )
        self.assertTrue(
            manifest_exists,
            "Round-2 validation selection exists but confirmation manifest is missing",
        )
        self.assertTrue(
            selection_exists,
            "Round-2 confirmation manifest exists but validation selection is missing",
        )
        self.manifest = _load(MANIFEST_PATH)

    def test_manifest_identity_and_exact_source_grid(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema_version"], "0.1.0")
        self.assertEqual(manifest["protocol_id"], PROTOCOL_ID)
        self.assertEqual(
            manifest["package_id"],
            "procureharness-round2-confirmation-v0.1",
        )
        self.assertEqual(manifest["round"], 2)
        self.assertEqual(manifest["phase"], "development_confirmation")
        self.assertEqual(manifest["candidate_ids"], list(CANDIDATES))
        self.assertEqual(manifest["episode_suffixes"], list(range(1, 21)))
        self.assertEqual(manifest["repeats"], 3)
        self.assertEqual(manifest["total_runs"], 120)
        self.assertEqual(manifest["model"], MODEL)
        self.assertEqual(manifest["reasoning_effort"], REASONING_EFFORT)
        self.assertEqual(manifest["temperature"], TEMPERATURE)

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

        rows = manifest["source_files"]
        self.assertEqual(len(rows), 122)
        self.assertEqual({row["path"] for row in rows}, expected_paths)
        for row in rows:
            path = ROOT / row["path"]
            raw = path.read_bytes()
            self.assertEqual(len(raw), row["bytes"])
            self.assertEqual(sha256(raw).hexdigest(), row["sha256"])

    def test_manifest_binds_input_confirmation_authorizations(self):
        expected_paths = {
            str(
                (
                    GATE_ROOT
                    / f"{candidate_id}--development-confirmation-auth.json"
                ).relative_to(ROOT)
            )
            for candidate_id in CANDIDATES
        }
        rows = self.manifest["input_authorization_files"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["path"] for row in rows}, expected_paths)
        for row in rows:
            path = ROOT / row["path"]
            raw = path.read_bytes()
            self.assertEqual(len(raw), row["bytes"])
            self.assertEqual(sha256(raw).hexdigest(), row["sha256"])

    def test_summary_rows_match_raw_results_and_authorizations(self):
        expected_names = {
            f"{episode_id}.json"
            for episode_id in DEVELOPMENT_EPISODES
        }
        expected_keys = [
            (episode_id, repeat)
            for repeat in REPEATS
            for episode_id in DEVELOPMENT_EPISODES
        ]

        for candidate_id in CANDIDATES:
            base = (
                EVIDENCE_ROOT
                / "results"
                / candidate_id
                / "development_confirmation"
            )
            summary = _load(base / "summary.json")
            self.assertEqual(summary["protocol_id"], PROTOCOL_ID)
            self.assertEqual(summary["candidate_id"], candidate_id)
            self.assertEqual(summary["round"], 2)
            self.assertEqual(summary["phase"], "development_confirmation")
            self.assertEqual(summary["model"], MODEL)
            self.assertEqual(summary["reasoning_effort"], REASONING_EFFORT)
            self.assertEqual(summary["temperature"], TEMPERATURE)
            self.assertEqual(summary["planned_runs"], 60)
            self.assertEqual(summary["completed_runs"], 60)
            self.assertEqual(summary["execution_failures"], 0)

            auth_path = (
                GATE_ROOT
                / f"{candidate_id}--development-confirmation-auth.json"
            )
            authorization = _load(auth_path)
            validate_phase_authorization(
                candidate_id=candidate_id,
                phase="development_confirmation",
                authorization=authorization,
            )
            self.assertEqual(summary["authorization"], authorization)
            self.assertEqual(
                summary["authorization_sha256"],
                _authorization_sha256(authorization),
            )

            observed_keys = [
                (row.get("episode_id"), row.get("repeat"))
                for row in summary["rows"]
            ]
            self.assertEqual(observed_keys, expected_keys)

            expected_rows = []
            for repeat in REPEATS:
                repeat_dir = base / f"r{repeat}"
                self.assertEqual(
                    {
                        path.name
                        for path in repeat_dir.iterdir()
                        if path.is_file() and path.suffix == ".json"
                    },
                    expected_names,
                )
                for episode_id in DEVELOPMENT_EPISODES:
                    raw_result = _load(
                        repeat_dir / f"{episode_id}.json"
                    )
                    self.assertEqual(raw_result["episode_id"], episode_id)
                    self.assertEqual(
                        (raw_result.get("policy") or {}).get("policy_id"),
                        f"procureharness--{candidate_id}--{MODEL}",
                    )
                    expected_rows.append(
                        _expected_summary_row(
                            raw_result=raw_result,
                            episode_id=episode_id,
                            repeat=repeat,
                        )
                    )
            self.assertEqual(summary["rows"], expected_rows)

    def test_frozen_validation_selection_and_gate_files_are_exact(self):
        selection = _load(VALIDATION_SELECTION_PATH)
        validate_frozen_validation_selection(selection)
        self.assertEqual(selection["round"], 2)
        self.assertEqual(
            selection["screening_selected_candidate_ids"],
            list(CANDIDATES),
        )

        expected_gate_paths = {
            str(VALIDATION_SELECTION_PATH.relative_to(ROOT)),
            *{
                str(
                    (
                        GATE_ROOT / f"{candidate_id}--validation-auth.json"
                    ).relative_to(ROOT)
                )
                for candidate_id in selection[
                    "validation_selected_candidate_ids"
                ]
            },
        }
        rows = self.manifest["gate_files"]
        self.assertEqual(
            {row["path"] for row in rows},
            expected_gate_paths,
        )
        for row in rows:
            path = ROOT / row["path"]
            raw = path.read_bytes()
            self.assertEqual(len(raw), row["bytes"])
            self.assertEqual(sha256(raw).hexdigest(), row["sha256"])

        for candidate_id in selection[
            "validation_selected_candidate_ids"
        ]:
            authorization = _load(
                GATE_ROOT / f"{candidate_id}--validation-auth.json"
            )
            validate_phase_authorization(
                candidate_id=candidate_id,
                phase="validation",
                authorization=authorization,
            )


if __name__ == "__main__":
    unittest.main()
