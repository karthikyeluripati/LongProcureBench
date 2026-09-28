"""Run the frozen State Validity Frontier development v0.2 grid.

This runner is intentionally hard-limited to the preregistered development
comparison: episodes 001-020 x 3 repeats with GPT-5.6 Sol, medium reasoning,
temperature omitted, and max_actions=50. It does not expose CLI overrides for
the grid, model, repeats, or sampling settings.
"""
from __future__ import annotations

import argparse
from hashlib import sha1
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import StateValidityFrontierPolicy
from run_reactive_pilot import run_pilot


TARGET_MODEL = "openai/gpt-5.6-sol"
TARGET_REASONING_EFFORT = "medium"
TARGET_TEMPERATURE = None
TARGET_REPEATS = 3
TARGET_MAX_ACTIONS = 50
TARGET_EPISODES = [
    "electrical-bongabon-generator-001",
    "electrical-national-museum-lighting-002",
    "electrical-neust-cable-003",
    "electrical-dla-breaker-004",
    "electrical-barrie-transformer-005",
    "electrical-bfar-generator-006",
    "electrical-negros-wire-007",
    "electrical-burauen-generator-008",
    "electrical-highpoint-transformer-009",
    "electrical-painesville-switchgear-010",
    "electrical-sagada-generator-011",
    "electrical-dla-relay-012",
    "electrical-dla-transformer-013",
    "electrical-dla-battery-supply-014",
    "electrical-dla-battery-charger-015",
    "electrical-dla-power-supply-016",
    "electrical-dla-qpl-breaker-017",
    "electrical-highpoint-cable-018",
    "electrical-usaf-ups-019",
    "electrical-vre-generator-020",
]
TARGET_RUNS = 60

PROTOCOL_PATH = (
    ROOT / "docs" / "state-validity-frontier-development-v0.2-protocol.json"
)
CONTROLLER_PATH = ROOT / "longprocurebench" / "state_validity_frontier.py"
RUNNER_PATH = Path(__file__).resolve()

PREREQUISITE_SEQUENCE_REQUIREMENTS = {
    "electrical-dla-transformer-013": {
        "response_event_type": "buyer_clarification",
        "blocked_action_type": "send_rfq",
        "rule": (
            "first send_rfq must occur strictly after the visible "
            "buyer_clarification response"
        ),
    },
}


def _git_blob_sha(path: Path) -> str:
    """Return the Git blob SHA-1 for the exact file bytes."""
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return sha1(header + payload).hexdigest()


def validate_frozen_implementation(
    *,
    protocol_path: Path = PROTOCOL_PATH,
    repo_root: Path = ROOT,
    runner_path: Path = RUNNER_PATH,
) -> dict[str, str]:
    """Verify actual executable bytes/settings against the preregistration."""
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    implementation = protocol["implementation"]
    grid = protocol["development_grid"]

    controller_path = repo_root / implementation["controller_path"]
    expected_runner_path = repo_root / implementation["runner_path"]
    if runner_path.resolve() != expected_runner_path.resolve():
        raise ValueError(
            "development v0.2 runner path drift: "
            f"expected={expected_runner_path}, actual={runner_path}"
        )

    actual = {
        "controller_blob_sha": _git_blob_sha(controller_path),
        "runner_blob_sha": _git_blob_sha(runner_path),
    }
    for key, value in actual.items():
        expected = implementation[key]
        if value != expected:
            raise ValueError(
                f"development v0.2 implementation hash drift for {key}: "
                f"expected={expected}, actual={value}"
            )

    expected_settings = {
        "episodes": TARGET_EPISODES,
        "repeats_per_episode": TARGET_REPEATS,
        "total_runs": TARGET_RUNS,
        "model": TARGET_MODEL,
        "reasoning_effort": TARGET_REASONING_EFFORT,
        "temperature": TARGET_TEMPERATURE,
        "max_actions": TARGET_MAX_ACTIONS,
    }
    for key, expected in expected_settings.items():
        if grid.get(key) != expected:
            raise ValueError(
                f"development v0.2 protocol/settings drift at {key}: "
                f"expected={expected!r}, protocol={grid.get(key)!r}"
            )

    return actual


def _result_paths(output_dir: Path) -> list[Path]:
    return sorted(output_dir.rglob("run-*.json"))


def validate_exact_grid(rows: list[dict[str, Any]]) -> None:
    expected = {
        (episode_id, repeat)
        for episode_id in TARGET_EPISODES
        for repeat in range(1, TARGET_REPEATS + 1)
    }
    actual = [(row["episode_id"], int(row["repeat"])) for row in rows]

    if len(actual) != TARGET_RUNS:
        raise ValueError(
            f"development v0.2 requires exactly {TARGET_RUNS} runs; "
            f"got {len(actual)}"
        )
    if len(set(actual)) != TARGET_RUNS or set(actual) != expected:
        missing = sorted(expected - set(actual))
        extra = sorted(set(actual) - expected)
        raise ValueError(
            "development v0.2 grid drift; "
            f"missing={missing}, extra={extra}"
        )
    if any(row.get("model") != TARGET_MODEL for row in rows):
        raise ValueError("development v0.2 model drift")


def validate_execution_statuses(rows: list[dict[str, Any]]) -> None:
    """Reject infrastructure/protocol/evaluation failures.

    EnvironmentError and jsonschema ValidationError remain measured accepted
    benchmark-action rejections. RunnerError is a runner decision-contract
    failure and is never accepted as clean development evidence.
    """
    infrastructure_statuses = {
        "setup_error",
        "environment_error",
        "evaluation_error",
        "metadata_error",
    }
    measured_policy_errors = {
        "EnvironmentError",
        "ValidationError",
    }

    failures = []
    for row in rows:
        status = row.get("status")
        error_type = row.get("error_type")
        evaluation_error_type = row.get("evaluation_error_type")

        if evaluation_error_type:
            failures.append(
                f"{row.get('episode_id')} r{row.get('repeat')}: "
                f"evaluation_error={evaluation_error_type}"
            )

        if status in infrastructure_statuses:
            failures.append(
                f"{row.get('episode_id')} r{row.get('repeat')}: "
                f"status={status} error={error_type}"
            )
        elif status == "policy_error":
            if (
                error_type == "StateValidityFrontierError"
                or error_type not in measured_policy_errors
            ):
                failures.append(
                    f"{row.get('episode_id')} r{row.get('repeat')}: "
                    f"status=policy_error error={error_type}"
                )

    if failures:
        raise ValueError(
            "development v0.2 execution-status gate failed: "
            + "; ".join(failures)
        )


def _first_observation_step(
    trajectory: list[dict[str, Any]],
    event_type: str,
) -> int | None:
    for row in trajectory:
        if any(
            isinstance(obs, dict) and obs.get("type") == event_type
            for obs in row.get("observations") or []
        ):
            return int(row["step"])
    return None


def _first_action_step(
    trajectory: list[dict[str, Any]],
    action_type: str,
) -> int | None:
    for row in trajectory:
        action = row.get("action") or {}
        if action.get("type") == action_type:
            return int(row["step"])
    return None


def validate_prerequisite_sequences(output_dir: Path) -> dict[str, Any]:
    """Enforce preregistered action ordering from raw accepted trajectories."""
    records = []
    failures = []

    for path in _result_paths(output_dir):
        result = json.loads(path.read_text(encoding="utf-8"))
        episode_id = result.get("episode_id")
        requirement = PREREQUISITE_SEQUENCE_REQUIREMENTS.get(episode_id)
        if requirement is None:
            continue

        trajectory = result.get("trajectory") or []
        response_step = _first_observation_step(
            trajectory,
            requirement["response_event_type"],
        )
        blocked_action_step = _first_action_step(
            trajectory,
            requirement["blocked_action_type"],
        )
        passed = (
            response_step is not None
            and blocked_action_step is not None
            and blocked_action_step > response_step
        )
        row = {
            "run_id": result.get("run_id"),
            "episode_id": episode_id,
            "response_event_type": requirement["response_event_type"],
            "response_step": response_step,
            "blocked_action_type": requirement["blocked_action_type"],
            "first_blocked_action_step": blocked_action_step,
            "rule": requirement["rule"],
            "pass": passed,
        }
        records.append(row)
        if not passed:
            failures.append(row)

    expected_checks = TARGET_REPEATS * len(
        PREREQUISITE_SEQUENCE_REQUIREMENTS
    )
    if len(records) != expected_checks:
        raise ValueError(
            "development v0.2 prerequisite-sequence coverage drift: "
            f"expected {expected_checks} checks, got {len(records)}"
        )

    payload = {
        "schema_version": "0.2.0",
        "protocol": "state-validity-frontier-development-v0.2",
        "checks": len(records),
        "failures": len(failures),
        "pass": not failures,
        "records": records,
    }
    (output_dir / "prerequisite-sequence-gate.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if failures:
        detail = "; ".join(
            (
                f"{row['run_id']}: "
                f"{row['blocked_action_type']}@"
                f"{row['first_blocked_action_step']} not after "
                f"{row['response_event_type']}@{row['response_step']}"
            )
            for row in failures
        )
        raise ValueError(
            "development v0.2 prerequisite sequence gate failed: " + detail
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="results/state-validity-frontier-development-v0.2",
    )
    args = parser.parse_args()

    validate_frozen_implementation()

    output_dir = Path(args.output_dir)
    rows, _ = run_pilot(
        [TARGET_MODEL],
        TARGET_EPISODES,
        TARGET_REPEATS,
        output_dir,
        TARGET_MAX_ACTIONS,
        policy_factory=StateValidityFrontierPolicy,
        policy_kwargs={
            "temperature": TARGET_TEMPERATURE,
            "reasoning_effort": TARGET_REASONING_EFFORT,
        },
        run_prefix="state-validity-frontier-development-v0.2",
        baseline_name="state-validity-frontier-development-v0.2",
    )
    validate_exact_grid(rows)
    validate_execution_statuses(rows)
    sequence = validate_prerequisite_sequences(output_dir)
    print(json.dumps({
        "runs": len(rows),
        "sequence_gate_pass": sequence["pass"],
        "sequence_checks": sequence["checks"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
