"""Load frozen State Validity Frontier development v0.2 replay evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


EPISODES = [
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
    "electrical-vre-generator-020"
]
EXPECTED_REPEATS = 3
EXPECTED_RUNS = 60
MODEL = "openai/gpt-5.6-sol"
EXPECTED_CHUNKS = [
    [
        "replay-source.b64.part00",
        14000,
        "e55508bd3fd057e5f7e4ee2a31f0d566f3cbcaef526869f08485e44d3d32cfa5"
    ],
    [
        "replay-source.b64.part01",
        14000,
        "f002a2e955b3239396758056aa19647c3f0f2ab9cef66c4b0d3ac80c9c8885e4"
    ],
    [
        "replay-source.b64.part02",
        12688,
        "e7f64daf563cbc4d0b42898c21118709d4e77aa454b120b56835cc9697193691"
    ]
]
EXPECTED_ENCODED_BYTES = 40688
EXPECTED_ENCODED_SHA256 = "d5e3a58b8817f1f32c2c40eb8a6ddd384e59efa05fd189392f1c6d52de1c6e89"
EXPECTED_COMPRESSED_BYTES = 30516
EXPECTED_COMPRESSED_SHA256 = "e823c4b212f52fc758d536333cfa8687b07e91e314b54b6dfed2e07bb439cc20"
EXPECTED_ROWS_BYTES = 822948
EXPECTED_ROWS_SHA256 = "18426844fd7886da35a770b1a4000f243db197c76b48a3dcf1d84329d312e806"

COMPACT_POLICY_METRIC_FIELDS = [
    "agent_pattern",
    "amended_epochs",
    "amendment_required_epochs",
    "clarification_epochs_used",
    "clarification_lease_blocks",
    "completion_tokens",
    "context_strategy",
    "cost_usd",
    "coverage_forced_answers",
    "coverage_forced_followups",
    "coverage_forced_rfqs",
    "deterministic_frontier_actions",
    "evaluation_current",
    "evaluation_generation",
    "frontier_decisions",
    "frontier_trace",
    "handled_repair_event_ids",
    "latency_ms",
    "llm_frontier_calls",
    "max_frontier_size",
    "model",
    "model_calls",
    "model_calls_attempted",
    "model_calls_failed",
    "model_calls_succeeded",
    "prompt_tokens",
    "quote_invalidations",
    "reasoning_effort",
    "requirement_epoch",
    "requirement_invalidations",
    "revision_attempt_offer_ids",
    "state_strategy",
    "temperature",
    "total_tokens",
    "usage_incomplete",
    "validity_frontier_interventions",
    "validity_generation",
    "validity_graph",
    "validity_invalidations",
    "withdrawal_invalidations"
]


def evidence_dir(repo_root: Path) -> Path:
    return (
        Path(repo_root)
        / "evidence"
        / "state-validity-frontier-development-v0.2"
    )


def canonical_line(record: dict[str, Any]) -> bytes:
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def compact_record_from_raw(
    record: dict[str, Any],
    repeat: int,
) -> dict[str, Any]:
    metrics = record.get("policy_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Raw SVF development run is missing policy_metrics")
    return {
        "run_id": record["run_id"],
        "episode_id": record["episode_id"],
        "repeat": repeat,
        "status": record["status"],
        "max_actions": record["max_actions"],
        "trajectory": record["trajectory"],
        "error": record.get("error"),
        "evaluation_error": record.get("evaluation_error"),
        "policy_metrics": {
            key: metrics.get(key)
            for key in COMPACT_POLICY_METRIC_FIELDS
        },
    }


def reconstruct_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row["action"]) for row in record["trajectory"]]


def load_frozen_state_validity_frontier_development_v02(
    repo_root: Path,
) -> list[dict[str, Any]]:
    root = evidence_dir(repo_root)
    encoded_parts = []
    for name, expected_bytes, expected_sha in EXPECTED_CHUNKS:
        payload = (root / name).read_bytes()
        if len(payload) != expected_bytes:
            raise ValueError(f"SVF development replay chunk byte drift: {name}")
        if sha256(payload).hexdigest() != expected_sha:
            raise ValueError(f"SVF development replay chunk digest drift: {name}")
        encoded_parts.append(payload)

    encoded = b"".join(encoded_parts)
    if len(encoded) != EXPECTED_ENCODED_BYTES:
        raise ValueError("SVF development encoded-byte drift")
    if sha256(encoded).hexdigest() != EXPECTED_ENCODED_SHA256:
        raise ValueError("SVF development encoded digest drift")

    compressed = base64.b64decode(encoded, validate=True)
    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("SVF development compressed-byte drift")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("SVF development compressed digest drift")

    rows = gzip.decompress(compressed)
    if len(rows) != EXPECTED_ROWS_BYTES:
        raise ValueError("SVF development row-byte drift")
    if sha256(rows).hexdigest() != EXPECTED_ROWS_SHA256:
        raise ValueError("SVF development row digest drift")

    records = [
        json.loads(line)
        for line in rows.splitlines()
        if line
    ]
    if len(records) != EXPECTED_RUNS:
        raise ValueError(
            f"SVF development replay must contain {EXPECTED_RUNS} records"
        )

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    seen = set()
    for record in records:
        key = (record.get("episode_id"), record.get("repeat"))
        if key not in expected or key in seen:
            raise ValueError(f"Unexpected/duplicate SVF development key: {key}")
        seen.add(key)

        if record.get("max_actions") != 50:
            raise ValueError("SVF development max-actions drift")
        if record.get("status") not in {"completed", "policy_error"}:
            raise ValueError("Unexpected SVF development status")

        metrics = record.get("policy_metrics") or {}
        if metrics.get("model") != MODEL:
            raise ValueError("SVF development model drift")
        if metrics.get("reasoning_effort") != "medium":
            raise ValueError("SVF development reasoning-effort drift")
        if metrics.get("temperature") is not None:
            raise ValueError("SVF development temperature must remain omitted")
        if metrics.get("state_strategy") != (
            "recomputed_versioned_validity_frontier_v0.1"
        ):
            raise ValueError("SVF development state-strategy drift")
        if metrics.get("agent_pattern") != "state_validity_frontier_v0.1":
            raise ValueError("SVF development agent-pattern drift")
        if metrics.get("usage_incomplete") is not False:
            raise ValueError("SVF development provider usage is incomplete")
        if metrics.get("model_calls_failed") != 0:
            raise ValueError("SVF development contains failed provider calls")
        if metrics.get("total_tokens") != (
            metrics.get("prompt_tokens", 0)
            + metrics.get("completion_tokens", 0)
        ):
            raise ValueError("SVF development token accounting drift")

        error = record.get("error")
        if record["status"] == "policy_error":
            if not isinstance(error, dict):
                raise ValueError("Policy-error run is missing error metadata")
            if error.get("type") != "StateValidityFrontierError":
                raise ValueError("Unexpected frozen policy-error type")
        elif error is not None:
            raise ValueError("Completed SVF development run has an error")

        if record.get("evaluation_error") is not None:
            raise ValueError("Frozen SVF development run has evaluation error")

        trajectory = record.get("trajectory")
        if not isinstance(trajectory, list):
            raise ValueError("SVF development trajectory must be a list")
        if [row.get("step") for row in trajectory] != list(
            range(1, len(trajectory) + 1)
        ):
            raise ValueError("SVF development trajectory step drift")

    if seen != expected:
        raise ValueError("SVF development episode/repeat grid mismatch")
    return sorted(
        records,
        key=lambda row: (EPISODES.index(row["episode_id"]), row["repeat"]),
    )
