"""Tests for the frozen State Validity Frontier development v0.2 runner."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from run_state_validity_frontier_development_v02 import (
    PREREQUISITE_SEQUENCE_REQUIREMENTS,
    TARGET_EPISODES,
    TARGET_MAX_ACTIONS,
    TARGET_MODEL,
    TARGET_REASONING_EFFORT,
    TARGET_REPEATS,
    TARGET_RUNS,
    TARGET_TEMPERATURE,
    validate_exact_grid,
    validate_execution_statuses,
    validate_prerequisite_sequences,
)


EPISODE_013 = "electrical-dla-transformer-013"


def _trajectory(*, rfq_step: int, clarification_step: int):
    rows = []
    last_step = max(rfq_step, clarification_step)
    for step in range(1, last_step + 1):
        action_type = "identify_suppliers"
        supplier_id = None
        observations = []
        if step == rfq_step:
            action_type = "send_rfq"
            supplier_id = "syn-test"
        if step == clarification_step:
            observations.append({
                "event_id": "e-clarification",
                "type": "buyer_clarification",
            })
        rows.append({
            "step": step,
            "action": {
                "type": action_type,
                "supplier_id": supplier_id,
                "arguments": {},
            },
            "observations": observations,
        })
    return rows


def _write_013_runs(root: Path, *, bad_repeat: int | None = None):
    for repeat in (1, 2, 3):
        path = root / EPISODE_013 / f"run-{repeat:03d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if repeat == bad_repeat:
            trajectory = _trajectory(rfq_step=1, clarification_step=2)
        else:
            trajectory = _trajectory(rfq_step=3, clarification_step=2)
        path.write_text(
            json.dumps({
                "run_id": f"test-013-r{repeat:03d}",
                "episode_id": EPISODE_013,
                "trajectory": trajectory,
            }),
            encoding="utf-8",
        )


class StateValidityFrontierDevelopmentV02RunnerTests(unittest.TestCase):
    def test_runner_constants_are_exactly_frozen(self):
        self.assertEqual(len(TARGET_EPISODES), 20)
        self.assertEqual(TARGET_REPEATS, 3)
        self.assertEqual(TARGET_RUNS, 60)
        self.assertEqual(TARGET_MODEL, "openai/gpt-5.6-sol")
        self.assertEqual(TARGET_REASONING_EFFORT, "medium")
        self.assertIsNone(TARGET_TEMPERATURE)
        self.assertEqual(TARGET_MAX_ACTIONS, 50)
        self.assertEqual(
            PREREQUISITE_SEQUENCE_REQUIREMENTS,
            {
                EPISODE_013: {
                    "response_event_type": "buyer_clarification",
                    "blocked_action_type": "send_rfq",
                    "rule": (
                        "first send_rfq must occur strictly after the visible "
                        "buyer_clarification response"
                    ),
                }
            },
        )

    def test_exact_grid_validator_rejects_missing_repeat(self):
        rows = [
            {
                "episode_id": episode_id,
                "repeat": repeat,
                "model": TARGET_MODEL,
            }
            for episode_id in TARGET_EPISODES
            for repeat in (1, 2, 3)
        ]
        validate_exact_grid(rows)
        with self.assertRaises(ValueError):
            validate_exact_grid(rows[:-1])

    def test_execution_status_gate_rejects_protocol_error(self):
        rows = [
            {
                "episode_id": "electrical-bongabon-generator-001",
                "repeat": 1,
                "status": "completed",
                "error_type": None,
            }
        ]
        validate_execution_statuses(rows)

        bad = [
            {
                "episode_id": "electrical-bongabon-generator-001",
                "repeat": 1,
                "status": "policy_error",
                "error_type": "StateValidityFrontierError",
            }
        ]
        with self.assertRaisesRegex(
            ValueError,
            "execution-status gate failed",
        ):
            validate_execution_statuses(bad)

    def test_sequence_gate_accepts_rfq_after_clarification(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_013_runs(root)
            result = validate_prerequisite_sequences(root)
            self.assertTrue(result["pass"])
            self.assertEqual(result["checks"], 3)
            self.assertEqual(result["failures"], 0)

    def test_sequence_gate_rejects_early_rfq(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_013_runs(root, bad_repeat=2)
            with self.assertRaisesRegex(
                ValueError,
                "prerequisite sequence gate failed",
            ):
                validate_prerequisite_sequences(root)
            payload = json.loads(
                (root / "prerequisite-sequence-gate.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(payload["pass"])
            self.assertEqual(payload["failures"], 1)


if __name__ == "__main__":
    unittest.main()
