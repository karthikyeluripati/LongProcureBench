"""End-to-end offline tests for ProcureHarness search selectors."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    PROTOCOL_ID,
    round_candidate_ids,
    validate_phase_authorization,
)
from select_procureharness_screening_v01 import (
    freeze_selection,
    validate_frozen_screening_selection,
)
from select_procureharness_validation_v01 import (
    freeze_validation_selection,
    validate_frozen_validation_selection,
)


def _screening_summary(candidate_id: str, feasible: int) -> dict:
    rows = []
    for index, episode_id in enumerate(DEVELOPMENT_EPISODES):
        rows.append({
            "episode_id": episode_id,
            "repeat": 1,
            "status": "completed",
            "terminal_feasible": index < feasible,
            "feasible_obligation_success": index < feasible,
            "strict_v02": index < max(0, feasible - 2),
            "economic_objective": index < max(0, feasible - 3),
            "obligation_resolved": 1,
            "obligation_actionable": 1,
            "obligation_resolution_rate": 1.0,
            "accepted_actions": 8,
            "model_calls": 2,
            "total_tokens": 100,
            "latency_ms": 10.0,
            "known_cost_usd": 0.01,
            "deterministic_action_fraction": 0.75,
        })
    return {
        "protocol_id": PROTOCOL_ID,
        "candidate_id": candidate_id,
        "round": 1,
        "phase": "screening",
        "planned_runs": 20,
        "completed_runs": 20,
        "execution_failures": 0,
        "rows": rows,
    }


def _confirmation_summary(
    candidate_id: str,
    *,
    feasible: int,
    strict: int,
    economic: int,
) -> dict:
    rows = []
    index = 0
    for repeat in range(1, 4):
        for episode_id in DEVELOPMENT_EPISODES:
            rows.append({
                "episode_id": episode_id,
                "repeat": repeat,
                "status": "completed",
                "terminal_feasible": index < feasible,
                "feasible_obligation_success": index < feasible,
                "strict_v02": index < strict,
                "economic_objective": index < economic,
                "obligation_resolved": 1,
                "obligation_actionable": 1,
                "obligation_resolution_rate": 1.0,
                "accepted_actions": 8,
                "model_calls": 2,
                "total_tokens": 100,
                "latency_ms": 10.0,
                "known_cost_usd": 0.05,
                "deterministic_action_fraction": 0.75,
            })
            index += 1
    return {
        "protocol_id": PROTOCOL_ID,
        "candidate_id": candidate_id,
        "round": 1,
        "phase": "development_confirmation",
        "planned_runs": 60,
        "completed_runs": 60,
        "execution_failures": 0,
        "rows": rows,
    }


class ProcureHarnessSelectorTests(unittest.TestCase):
    def _write_screening_summaries(self, root: Path) -> None:
        scores = [20, 19, 15, 14, 13, 12]
        for candidate_id, feasible in zip(round_candidate_ids(1), scores):
            path = root / candidate_id / "screening" / "summary.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    _screening_summary(candidate_id, feasible),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

    def _freeze_screening(self, root: Path, gates: Path):
        self._write_screening_summaries(root)
        selection_path, auth_paths = freeze_selection(
            round_id=1,
            results_root=root,
            output_dir=gates,
        )
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        validate_frozen_screening_selection(selection)
        self.assertEqual(
            selection["selected_candidate_ids"],
            ["ph-r1-c01", "ph-r1-c02"],
        )
        self.assertEqual(len(auth_paths), 2)
        return selection_path, auth_paths

    def test_screening_gate_preflights_all_outputs_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            gates = Path(tmp) / "gates"
            self._write_screening_summaries(root)
            gates.mkdir(parents=True, exist_ok=True)

            preexisting = (
                gates / "ph-r1-c01--development-confirmation-auth.json"
            )
            preexisting.write_text("{}\n", encoding="utf-8")

            selection_path = gates / "screening-selection-round-1.json"
            with self.assertRaisesRegex(
                ValueError,
                "refusing to overwrite frozen screening gate artifact",
            ):
                freeze_selection(
                    round_id=1,
                    results_root=root,
                    output_dir=gates,
                )

            self.assertFalse(selection_path.exists())
            self.assertEqual(
                preexisting.read_text(encoding="utf-8"),
                "{}\n",
            )

    def test_screening_gate_rejects_concurrent_freeze_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            gates = Path(tmp) / "gates"
            self._write_screening_summaries(root)
            gates.mkdir(parents=True, exist_ok=True)
            lock = gates / ".screening-selection-round-1.lock"
            lock.write_text("pid=other\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "already in progress"):
                freeze_selection(
                    round_id=1,
                    results_root=root,
                    output_dir=gates,
                )

            self.assertFalse(
                (gates / "screening-selection-round-1.json").exists()
            )
            self.assertEqual(
                lock.read_text(encoding="utf-8"),
                "pid=other\n",
            )

    def test_quality_candidate_advances_while_peer_waits_for_efficiency_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            gates = Path(tmp) / "gates"
            screening_selection_path, _ = self._freeze_screening(
                root,
                gates,
            )

            specs = {
                "ph-r1-c01": (53, 30, 30),
                "ph-r1-c02": (47, 27, 27),
            }
            for candidate_id, (feasible, strict, economic) in specs.items():
                path = (
                    root
                    / candidate_id
                    / "development_confirmation"
                    / "summary.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        _confirmation_summary(
                            candidate_id,
                            feasible=feasible,
                            strict=strict,
                            economic=economic,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            validation_path, auth_paths = freeze_validation_selection(
                round_id=1,
                results_root=root,
                screening_selection_path=screening_selection_path,
                output_dir=gates,
            )
            selection = json.loads(
                validation_path.read_text(encoding="utf-8")
            )
            validate_frozen_validation_selection(selection)

            self.assertEqual(
                selection["validation_selected_candidate_ids"],
                ["ph-r1-c01"],
            )
            self.assertEqual(
                selection["pending_efficiency_candidate_ids"],
                ["ph-r1-c02"],
            )
            self.assertEqual(len(auth_paths), 1)

            authorization = json.loads(
                auth_paths[0].read_text(encoding="utf-8")
            )
            self.assertEqual(
                authorization["candidate_id"],
                "ph-r1-c01",
            )
            validate_phase_authorization(
                candidate_id="ph-r1-c01",
                phase="validation",
                authorization=authorization,
            )

    def test_validation_gate_rejects_concurrent_freeze_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            gates = Path(tmp) / "gates"
            screening_selection_path, _ = self._freeze_screening(
                root,
                gates,
            )

            for candidate_id in ("ph-r1-c01", "ph-r1-c02"):
                path = (
                    root
                    / candidate_id
                    / "development_confirmation"
                    / "summary.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        _confirmation_summary(
                            candidate_id,
                            feasible=53,
                            strict=30,
                            economic=30,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            lock = gates / ".validation-selection-round-1.lock"
            lock.write_text("pid=other\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already in progress"):
                freeze_validation_selection(
                    round_id=1,
                    results_root=root,
                    screening_selection_path=screening_selection_path,
                    output_dir=gates,
                )

            self.assertFalse(
                (gates / "validation-selection-round-1.json").exists()
            )
            self.assertEqual(
                lock.read_text(encoding="utf-8"),
                "pid=other\n",
            )

    def test_validation_authorization_is_recomputed_from_confirmation_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            gates = Path(tmp) / "gates"
            screening_selection_path, _ = self._freeze_screening(
                root,
                gates,
            )

            confirmation_specs = {
                "ph-r1-c01": (53, 30, 30),
                "ph-r1-c02": (50, 33, 30),
            }
            for candidate_id, (feasible, strict, economic) in (
                confirmation_specs.items()
            ):
                path = (
                    root
                    / candidate_id
                    / "development_confirmation"
                    / "summary.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        _confirmation_summary(
                            candidate_id,
                            feasible=feasible,
                            strict=strict,
                            economic=economic,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            validation_path, auth_paths = freeze_validation_selection(
                round_id=1,
                results_root=root,
                screening_selection_path=screening_selection_path,
                output_dir=gates,
            )
            selection = json.loads(
                validation_path.read_text(encoding="utf-8")
            )
            validate_frozen_validation_selection(selection)
            self.assertEqual(
                selection["validation_selected_candidate_ids"],
                ["ph-r1-c01", "ph-r1-c02"],
            )

            auth_by_candidate = {}
            for path in auth_paths:
                payload = json.loads(path.read_text(encoding="utf-8"))
                auth_by_candidate[payload["candidate_id"]] = payload
                validate_phase_authorization(
                    candidate_id=payload["candidate_id"],
                    phase="validation",
                    authorization=payload,
                )

            self.assertEqual(
                set(auth_by_candidate),
                {"ph-r1-c01", "ph-r1-c02"},
            )
            self.assertTrue(
                all(
                    payload["promotion_branch"] == "quality"
                    for payload in auth_by_candidate.values()
                )
            )

            confirmation_path = (
                root
                / "ph-r1-c01"
                / "development_confirmation"
                / "summary.json"
            )
            payload = json.loads(
                confirmation_path.read_text(encoding="utf-8")
            )
            payload["rows"][0]["strict_v02"] = False
            confirmation_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                validate_phase_authorization(
                    candidate_id="ph-r1-c01",
                    phase="validation",
                    authorization=auth_by_candidate["ph-r1-c01"],
                )


if __name__ == "__main__":
    unittest.main()
