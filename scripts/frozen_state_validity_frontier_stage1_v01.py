"""Load frozen State Validity Frontier Stage-1 replay evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


EPISODES = [
    "electrical-burauen-generator-008",
    "electrical-dla-transformer-013",
    "electrical-dla-power-supply-016",
]

EXPECTED_CHUNKS = [
    (
        "replay-source.b64.part00",
        3000,
        "b726606e8d2faa586de57b3447a789d194676ed1a77d88e7c4de9dc452f192e7",
    ),
    (
        "replay-source.b64.part01",
        2880,
        "921845c867fc8cfd6962924da5d4e915b87b6e3f61e692d0e065105d02350858",
    ),
]
EXPECTED_ENCODED_BYTES = 5880
EXPECTED_ENCODED_SHA256 = (
    "561847af414cdd83e6d8481cf1a702a3f35fb5155125b82734dbc059cb2de53e"
)
EXPECTED_COMPRESSED_BYTES = 4408
EXPECTED_COMPRESSED_SHA256 = (
    "bdfd1f17cfdaced641abb30da904a28cbc0ebd5c20f39e4a45fc74702a31aa05"
)
EXPECTED_ROWS_BYTES = 45266
EXPECTED_ROWS_SHA256 = (
    "5601b4ca76630815fcae97d48e21a50603920185c6f9e9c9a69e08238f07bf48"
)


COMPACT_POLICY_METRIC_FIELDS = (
    "agent_pattern",
    "amended_epochs",
    "amendment_required_epochs",
    "clarification_epochs_used",
    "clarification_lease_blocks",
    "completion_tokens",
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
    "withdrawal_invalidations",
)


def compact_record_from_raw(
    record: dict[str, Any],
) -> dict[str, Any]:
    metrics = record.get("policy_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Raw Stage-1 run is missing policy_metrics")

    return {
        "run_id": record["run_id"],
        "episode_id": record["episode_id"],
        "repeat": 1,
        "status": record["status"],
        "max_actions": record["max_actions"],
        "trajectory": record["trajectory"],
        "policy_metrics": {
            key: metrics.get(key)
            for key in COMPACT_POLICY_METRIC_FIELDS
        },
    }


def canonical_line(record: dict[str, Any]) -> bytes:
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def reconstruct_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row["action"])
        for row in record["trajectory"]
    ]


def load_frozen_state_validity_frontier_stage1(
    repo_root: Path,
) -> list[dict[str, Any]]:
    evidence = (
        repo_root
        / "evidence"
        / "state-validity-frontier-stage1-v0.1"
    )

    encoded_parts = []
    for name, expected_bytes, expected_sha in EXPECTED_CHUNKS:
        payload = (evidence / name).read_bytes()
        if len(payload) != expected_bytes:
            raise ValueError(f"Replay chunk byte drift: {name}")
        if sha256(payload).hexdigest() != expected_sha:
            raise ValueError(f"Replay chunk digest drift: {name}")
        encoded_parts.append(payload)

    encoded = b"".join(encoded_parts)
    if len(encoded) != EXPECTED_ENCODED_BYTES:
        raise ValueError("Replay encoded-byte drift")
    if sha256(encoded).hexdigest() != EXPECTED_ENCODED_SHA256:
        raise ValueError("Replay encoded digest drift")

    compressed = base64.b64decode(encoded, validate=True)
    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("Replay compressed-byte drift")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Replay compressed digest drift")

    rows = gzip.decompress(compressed)
    if len(rows) != EXPECTED_ROWS_BYTES:
        raise ValueError("Replay row-byte drift")
    if sha256(rows).hexdigest() != EXPECTED_ROWS_SHA256:
        raise ValueError("Replay row digest drift")

    records = [
        json.loads(line)
        for line in rows.splitlines()
        if line
    ]
    if len(records) != 3:
        raise ValueError("Stage-1 replay must contain exactly three records")

    by_episode = {}
    for record in records:
        episode_id = record.get("episode_id")
        if episode_id not in EPISODES or episode_id in by_episode:
            raise ValueError("Unexpected or duplicate Stage-1 episode")
        if record.get("repeat") != 1:
            raise ValueError("Stage-1 repeat drift")
        if record.get("status") != "completed":
            raise ValueError("Frozen Stage-1 source must contain completed runs")
        if record.get("max_actions") != 50:
            raise ValueError("Stage-1 max-actions drift")

        metrics = record.get("policy_metrics") or {}
        if metrics.get("model") != "openai/gpt-5.6-sol":
            raise ValueError("Stage-1 model drift")
        if metrics.get("reasoning_effort") != "medium":
            raise ValueError("Stage-1 reasoning-effort drift")
        if metrics.get("temperature") is not None:
            raise ValueError("Stage-1 temperature must remain omitted")

        trajectory = record.get("trajectory")
        if not isinstance(trajectory, list):
            raise ValueError("Stage-1 trajectory must be a list")
        if [row.get("step") for row in trajectory] != list(
            range(1, len(trajectory) + 1)
        ):
            raise ValueError("Stage-1 trajectory step drift")

        by_episode[episode_id] = record

    if set(by_episode) != set(EPISODES):
        raise ValueError("Stage-1 episode set drift")
    return [by_episode[episode_id] for episode_id in EPISODES]
