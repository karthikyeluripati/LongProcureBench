"""Load and verify the frozen 60-run context-compiled evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 5141
EXPECTED_COMPRESSED_SHA256 = (
    "aacc3d6e60ea87d7ccd5718689b480f6e0f71b2c0df606b306963be65f5b3939"
)
EXPECTED_RUNS = 60
EXPECTED_EPISODES = 20
EXPECTED_REPEATS = 3
MODEL = "openai/gpt-5.6-sol"

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
    "electrical-vre-generator-020",
]


def evidence_dir(repo_root: Path) -> Path:
    return (
        Path(repo_root)
        / "evidence"
        / "context-compiled-reactive-v0.1"
    )


def load_frozen_context_compiled_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    path = evidence_dir(repo_root) / "replay-source.b64"
    if not path.is_file():
        raise ValueError(f"Missing frozen replay source: {path}")

    try:
        compressed = base64.b64decode(
            path.read_text(encoding="utf-8").strip(),
            validate=True,
        )
    except Exception as exc:
        raise ValueError("Frozen replay source base64 is invalid") from exc

    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError(
            "Frozen replay source size mismatch: "
            f"expected={EXPECTED_COMPRESSED_BYTES}, actual={len(compressed)}"
        )
    digest = sha256(compressed).hexdigest()
    if digest != EXPECTED_COMPRESSED_SHA256:
        raise ValueError(
            "Frozen replay source digest mismatch: "
            f"expected={EXPECTED_COMPRESSED_SHA256}, actual={digest}"
        )

    try:
        payload = gzip.decompress(compressed).decode("utf-8")
    except Exception as exc:
        raise ValueError("Frozen replay source gzip is invalid") from exc

    rows = [
        json.loads(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} frozen runs; found {len(rows)}"
        )

    records = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError("Compact context record must have four fields")
        episode_index, repeat, decisions, metrics = row
        if (
            not isinstance(episode_index, int)
            or not 1 <= episode_index <= len(EPISODES)
        ):
            raise ValueError(f"Invalid episode index: {episode_index!r}")
        if (
            not isinstance(repeat, int)
            or not 1 <= repeat <= EXPECTED_REPEATS
        ):
            raise ValueError(f"Invalid repeat: {repeat!r}")
        if not isinstance(decisions, list):
            raise ValueError("Compact decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != 10:
            raise ValueError("Compact metrics must contain ten fields")

        decoded_decisions = []
        for decision in decisions:
            if not isinstance(decision, list) or len(decision) != 3:
                raise ValueError("Semantic decision must have three fields")
            action_type, supplier_id, arguments = decision
            if not isinstance(action_type, str) or not action_type:
                raise ValueError("Invalid semantic action type")
            if supplier_id is not None and not isinstance(supplier_id, str):
                raise ValueError("supplier_id must be string/null")
            if not isinstance(arguments, dict):
                raise ValueError("Semantic action arguments must be object")
            decoded_decisions.append({
                "type": action_type,
                "supplier_id": supplier_id,
                "arguments": arguments,
            })

        (
            calls,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            latency_ms,
            cost_usd,
            usage_incomplete,
            temperature,
            reasoning_effort,
            context_strategy,
        ) = metrics
        if calls != len(decoded_decisions):
            raise ValueError(
                "Completed source run must have one model call per action"
            )
        if usage_incomplete is not False:
            raise ValueError("Frozen source must have complete usage")
        if total_tokens != prompt_tokens + completion_tokens:
            raise ValueError("total_tokens must equal prompt + completion")
        if context_strategy != "factual_compiled_v0.1":
            raise ValueError("Unexpected frozen context strategy")

        episode_id = EPISODES[episode_index - 1]
        key = (episode_id, repeat)
        if key in keys:
            raise ValueError(f"Duplicate frozen run key: {key}")
        keys.add(key)

        records.append({
            "model": MODEL,
            "episode_id": episode_id,
            "repeat": repeat,
            "decisions": decoded_decisions,
            "policy_metrics": {
                "model_calls_attempted": calls,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "latency_ms": float(latency_ms),
                "cost_usd": float(cost_usd),
                "usage_incomplete": usage_incomplete,
                "temperature": temperature,
                "reasoning_effort": reasoning_effort,
                "context_strategy": context_strategy,
            },
        })

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    if keys != expected:
        raise ValueError("Frozen context source grid mismatch")
    return records


def reconstruct_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    episode_id = record["episode_id"]
    return [
        {
            "action_id": f"a{index}",
            "episode_id": episode_id,
            "type": decision["type"],
            "supplier_id": decision["supplier_id"],
            "arguments": dict(decision["arguments"]),
        }
        for index, decision in enumerate(record["decisions"], start=1)
    ]
