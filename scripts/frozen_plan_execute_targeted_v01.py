"""Load frozen Plan-and-Execute targeted diagnostic replay evidence."""
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
        3020,
        "1bc969059b483ecea31747f27eed296a5adf6bc01f3f927b17b65d67109f1f0d",
    ),
    (
        "replay-source.b64.part01",
        3020,
        "f88b4456b7ea4c3bbac2451705b0a56ce93035131152998b7142a348f50f1a4a",
    ),
    (
        "replay-source.b64.part02",
        3020,
        "5b8ec7d7bedbce9c582e0849bc4ac1af8f09dcaa676c2aebae5c42b0cbddbccd",
    ),
]
EXPECTED_ENCODED_BYTES = 9060
EXPECTED_ENCODED_SHA256 = (
    "92794c31b8880908b4859ce769468a11a445761b72e2639f4e5fe9870332c297"
)
EXPECTED_COMPRESSED_BYTES = 6794
EXPECTED_COMPRESSED_SHA256 = (
    "840c9dabccfcc8cc26b11789f08fee8ad4e14abdc466ebd25a93b82d00b720cb"
)
EXPECTED_COMPACT_ROWS_BYTES = 77050
EXPECTED_COMPACT_ROWS_SHA256 = (
    "bde30bb86265b76e0717ce6d467eb3b7f92a6d0a5f963b497ac29ac940601872"
)

POLICY_METRIC_FIELDS = [
    "model",
    "reasoning_effort",
    "temperature",
    "planner_calls",
    "executor_calls",
    "model_calls",
    "model_calls_attempted",
    "model_calls_failed",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "latency_ms",
    "cost_usd",
    "unplanned_exceptions",
    "plan_steps",
    "plan_step_usage",
    "fixed_plan",
    "execution_trace",
]


def _canonical_line(record: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def compact_record_from_raw(record: dict[str, Any]) -> dict[str, Any]:
    metrics = record.get("policy_metrics") or {}
    return {
        "run_id": record["run_id"],
        "episode_id": record["episode_id"],
        "repeat": 1,
        "status": record["status"],
        "max_actions": record["max_actions"],
        "trajectory": record["trajectory"],
        "policy_metrics": {
            key: metrics.get(key)
            for key in POLICY_METRIC_FIELDS
        },
    }


def reconstruct_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(step["action"])
        for step in record["trajectory"]
    ]


def _validate_record(record: dict[str, Any]) -> None:
    episode_id = record.get("episode_id")
    if episode_id not in EPISODES:
        raise ValueError(f"Unexpected Plan-and-Execute episode: {episode_id}")
    if record.get("repeat") != 1:
        raise ValueError("Targeted Plan-and-Execute replay must use repeat 1")
    if record.get("max_actions") != 50:
        raise ValueError("Targeted Plan-and-Execute replay max_actions drift")

    trajectory = record.get("trajectory")
    if not isinstance(trajectory, list):
        raise ValueError("Replay trajectory must be a list")
    expected_steps = list(range(1, len(trajectory) + 1))
    actual_steps = [row.get("step") for row in trajectory]
    if actual_steps != expected_steps:
        raise ValueError(
            f"Non-sequential trajectory steps for {episode_id}"
        )
    for row in trajectory:
        if not isinstance(row.get("action"), dict):
            raise ValueError("Trajectory row is missing action")
        if not isinstance(row.get("observations"), list):
            raise ValueError("Trajectory row is missing observations")

    metrics = record.get("policy_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Replay is missing policy_metrics")
    if set(metrics) != set(POLICY_METRIC_FIELDS):
        raise ValueError("Frozen policy metric field set drift")
    if metrics.get("model") != "openai/gpt-5.6-sol":
        raise ValueError("Frozen Plan-and-Execute model drift")
    if metrics.get("reasoning_effort") != "medium":
        raise ValueError("Frozen reasoning effort drift")
    if metrics.get("temperature") is not None:
        raise ValueError("Frozen temperature must remain omitted")
    if metrics.get("planner_calls") != 1:
        raise ValueError("Each targeted replay must have one planner call")
    if metrics.get("executor_calls") != len(trajectory):
        raise ValueError("Executor-call count does not match trajectory")
    if metrics.get("model_calls_attempted") != (
        metrics.get("planner_calls") + metrics.get("executor_calls")
    ):
        raise ValueError("Model-call accounting drift")
    if metrics.get("model_calls_failed") != 0:
        raise ValueError("Frozen targeted replay contains a failed model call")
    trace = metrics.get("execution_trace")
    if not isinstance(trace, list) or len(trace) != len(trajectory):
        raise ValueError("Execution-trace length does not match trajectory")


def load_frozen_plan_execute_targeted_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    evidence = (
        repo_root
        / "evidence"
        / "plan-execute-targeted-v0.1"
    )

    encoded_parts = []
    for name, expected_bytes, expected_sha in EXPECTED_CHUNKS:
        path = evidence / name
        if not path.is_file():
            raise ValueError(f"Missing replay chunk: {path}")
        payload = path.read_bytes()
        if len(payload) != expected_bytes:
            raise ValueError(f"Replay chunk byte drift: {name}")
        if sha256(payload).hexdigest() != expected_sha:
            raise ValueError(f"Replay chunk digest drift: {name}")
        encoded_parts.append(payload)

    encoded = b"".join(encoded_parts)
    if len(encoded) != EXPECTED_ENCODED_BYTES:
        raise ValueError("Frozen replay encoded-byte drift")
    if sha256(encoded).hexdigest() != EXPECTED_ENCODED_SHA256:
        raise ValueError("Frozen replay encoded digest drift")

    compressed = base64.b64decode(encoded, validate=True)
    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("Frozen replay compressed-byte drift")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Frozen replay compressed digest drift")

    compact_rows = gzip.decompress(compressed)
    if len(compact_rows) != EXPECTED_COMPACT_ROWS_BYTES:
        raise ValueError("Frozen replay row-byte drift")
    if sha256(compact_rows).hexdigest() != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError("Frozen replay row digest drift")

    records = [
        json.loads(line)
        for line in compact_rows.splitlines()
        if line
    ]
    if len(records) != 3:
        raise ValueError("Targeted replay must contain exactly three records")
    if len({record.get("episode_id") for record in records}) != 3:
        raise ValueError("Duplicate targeted replay episode")

    for record in records:
        _validate_record(record)

    by_episode = {
        record["episode_id"]: record
        for record in records
    }
    if set(by_episode) != set(EPISODES):
        raise ValueError("Targeted replay episode set drift")
    return [by_episode[episode_id] for episode_id in EPISODES]
