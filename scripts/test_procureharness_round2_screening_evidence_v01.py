"""Audit frozen ProcureHarness Round-2 screening evidence."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import unittest

from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MODEL,
    PROTOCOL_ID,
    REASONING_EFFORT,
    TEMPERATURE,
    _authorization_sha256,
    round_candidate_ids,
    validate_phase_authorization,
)
from select_procureharness_screening_v01 import (
    validate_frozen_screening_selection,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = (
    ROOT / "evidence" / "procureharness-round2-screening-v0.1"
)
MANIFEST_PATH = EVIDENCE_ROOT / "manifest.json"
GATE_ROOT = ROOT / "evidence" / "procureharness-search-gates-v0.1"
SELECTION_PATH = GATE_ROOT / "screening-selection-round-2.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_summary_row(
    *,
    raw_result: dict,
    episode_id: str,
) -> dict:
    evaluation = raw_result.get("evaluation") or {}
    metrics = raw_result.get("policy_metrics") or {}
    obligations = evaluation.get("obligations") or {}
    return {
        "episode_id": episode_id,
        "repeat": 1,
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


@unittest.skipUnless(
    MANIFEST_PATH.is_file(),
    "Round-2 screening evidence has not been materialized yet",
)
class ProcureHarnessRound2ScreeningEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _load(MANIFEST_PATH)
        self.candidates = round_candidate_ids(2)

    def test_manifest_identity_and_exact_source_grid(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema_version"], "0.1.0")
        self.assertEqual(manifest["protocol_id"], PROTOCOL_ID)
        self.assertEqual(
            manifest["package_id"],
            "procureharness-round2-screening-v0.1",
        )
        self.assertEqual(manifest["round"], 2)
        self.assertEqual(manifest["phase"], "screening")
        self.assertEqual(manifest["candidate_ids"], self.candidates)
        self.assertEqual(manifest["episode_suffixes"], list(range(1, 21)))
        self.assertEqual(manifest["repeats"], 1)
        self.assertEqual(manifest["total_runs"], 120)
        self.assertEqual(manifest["model"], MODEL)
        self.assertEqual(manifest["reasoning_effort"], REASONING_EFFORT)
        self.assertEqual(manifest["temperature"], TEMPERATURE)

        expected_paths = set()
        for candidate_id in self.candidates:
            root = EVIDENCE_ROOT / "results" / candidate_id / "screening"
            expected_paths.add(str(root.relative_to(ROOT) / "summary.json"))
            for episode_id in DEVELOPMENT_EPISODES:
                expected_paths.add(
                    str(
                        root.relative_to(ROOT)
                        / "r1"
                        / f"{episode_id}.json"
                    )
                )

        rows = manifest["source_files"]
        observed = {row["path"] for row in rows}
        self.assertEqual(len(rows), 126)
        self.assertEqual(observed, expected_paths)

        for row in rows:
            path = ROOT / row["path"]
            raw = path.read_bytes()
            self.assertEqual(len(raw), row["bytes"])
            self.assertEqual(sha256(raw).hexdigest(), row["sha256"])

    def test_summary_rows_match_raw_results_and_screening_authorizations(self):
        expected_names = {
            f"{episode_id}.json"
            for episode_id in DEVELOPMENT_EPISODES
        }

        for candidate_id in self.candidates:
            root = (
                EVIDENCE_ROOT
                / "results"
                / candidate_id
                / "screening"
            )
            summary = _load(root / "summary.json")
            self.assertEqual(summary["protocol_id"], PROTOCOL_ID)
            self.assertEqual(summary["candidate_id"], candidate_id)
            self.assertEqual(summary["round"], 2)
            self.assertEqual(summary["phase"], "screening")
            self.assertEqual(summary["model"], MODEL)
            self.assertEqual(
                summary["reasoning_effort"],
                REASONING_EFFORT,
            )
            self.assertEqual(summary["temperature"], TEMPERATURE)
            self.assertEqual(summary["planned_runs"], 20)
            self.assertEqual(summary["completed_runs"], 20)
            self.assertEqual(summary["execution_failures"], 0)

            auth_path = (
                GATE_ROOT / f"{candidate_id}--screening-auth.json"
            )
            authorization = _load(auth_path)
            validate_phase_authorization(
                candidate_id=candidate_id,
                phase="screening",
                authorization=authorization,
            )
            self.assertEqual(summary["authorization"], authorization)
            self.assertEqual(
                summary["authorization_sha256"],
                _authorization_sha256(authorization),
            )

            run_dir = root / "r1"
            self.assertEqual(
                {
                    path.name
                    for path in run_dir.iterdir()
                    if path.is_file() and path.suffix == ".json"
                },
                expected_names,
            )

            expected_rows = []
            for episode_id in DEVELOPMENT_EPISODES:
                raw_result = _load(run_dir / f"{episode_id}.json")
                self.assertEqual(raw_result["episode_id"], episode_id)
                self.assertEqual(
                    (raw_result.get("policy") or {}).get("policy_id"),
                    f"procureharness--{candidate_id}--{MODEL}",
                )
                expected_rows.append(
                    _expected_summary_row(
                        raw_result=raw_result,
                        episode_id=episode_id,
                    )
                )
            self.assertEqual(summary["rows"], expected_rows)

    def test_frozen_selection_and_gate_files_are_exact(self):
        selection = _load(SELECTION_PATH)
        validate_frozen_screening_selection(selection)
        self.assertEqual(selection["round"], 2)
        self.assertEqual(selection["candidate_ids"], self.candidates)

        selected = selection["selected_candidate_ids"]
        self.assertEqual(len(selected), 2)

        expected_gate_paths = {
            str(SELECTION_PATH.relative_to(ROOT)),
            *{
                str(
                    (
                        GATE_ROOT
                        / (
                            f"{candidate_id}"
                            "--development-confirmation-auth.json"
                        )
                    ).relative_to(ROOT)
                )
                for candidate_id in selected
            },
        }
        gate_rows = self.manifest["gate_files"]
        self.assertEqual(
            {row["path"] for row in gate_rows},
            expected_gate_paths,
        )
        self.assertEqual(len(gate_rows), 3)

        for row in gate_rows:
            path = ROOT / row["path"]
            raw = path.read_bytes()
            self.assertEqual(len(raw), row["bytes"])
            self.assertEqual(sha256(raw).hexdigest(), row["sha256"])

        for candidate_id in selected:
            authorization = _load(
                GATE_ROOT
                / f"{candidate_id}--development-confirmation-auth.json"
            )
            validate_phase_authorization(
                candidate_id=candidate_id,
                phase="development_confirmation",
                authorization=authorization,
            )


if __name__ == "__main__":
    unittest.main()
