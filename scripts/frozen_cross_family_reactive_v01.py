"""Load and verify the durable 180-run cross-family reactive evidence."""
from __future__ import annotations

import base64
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_SHA256 = (
    "a5ebf60142d2278463357e5081d7edef64757de58b5eba0f751a5f4f850ef4d1"
)
EXPECTED_COMPRESSED_BYTES = 12196
EXPECTED_RUNS = 180
EXPECTED_MODELS = 3
EXPECTED_EPISODES = 20
EXPECTED_REPEATS = 3

MODELS = [
    "anthropic/claude-opus-5-5",
    "gemini/gemini-3.8-flash",
    "openai/gpt-5.6-sol",
]

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


def source_dir(repo_root: Path) -> Path:
    return (
        Path(repo_root)
        / "evidence"
        / "cross-family-reactive-v0.1"
    )


def _decode_record(row: Any) -> dict[str, Any]:
    if not isinstance(row, list) or len(row) != 5:
        raise ValueError("Compact replay record must contain five fields")

    model_index, episode_index, repeat, decisions, metrics = row
    if (
        not isinstance(model_index, int)
        or not 0 <= model_index < len(MODELS)
    ):
        raise ValueError(f"Invalid model index: {model_index!r}")
    if (
        not isinstance(episode_index, int)
        or not 1 <= episode_index <= len(EPISODES)
    ):
        raise ValueError(f"Invalid episode index: {episode_index!r}")
    if not isinstance(repeat, int) or not 1 <= repeat <= EXPECTED_REPEATS:
        raise ValueError(f"Invalid repeat: {repeat!r}")
    if not isinstance(decisions, list):
        raise ValueError("Compact replay decisions must be a list")
    if not isinstance(metrics, list) or len(metrics) != 9:
        raise ValueError("Compact replay metrics must contain nine fields")

    decoded_decisions = []
    for decision in decisions:
        if not isinstance(decision, list) or len(decision) != 3:
            raise ValueError("Semantic decision must contain three fields")
        action_type, supplier_id, arguments = decision
        if not isinstance(action_type, str) or not action_type:
            raise ValueError("Semantic decision has invalid action type")
        if supplier_id is not None and not isinstance(supplier_id, str):
            raise ValueError("Semantic decision supplier_id must be string/null")
        if not isinstance(arguments, dict):
            raise ValueError("Semantic decision arguments must be an object")
        decoded_decisions.append({
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": arguments,
        })

    (
        model_calls_attempted,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        latency_ms,
        cost_usd,
        usage_incomplete,
        temperature,
        reasoning_effort,
    ) = metrics

    if model_calls_attempted != len(decoded_decisions):
        raise ValueError(
            "Completed source run must have one model call per accepted action"
        )
    if usage_incomplete is not False:
        raise ValueError("Frozen source must have complete provider usage")
    if not all(
        isinstance(value, int) and value >= 0
        for value in (prompt_tokens, completion_tokens, total_tokens)
    ):
        raise ValueError("Token metrics must be non-negative integers")
    if total_tokens != prompt_tokens + completion_tokens:
        raise ValueError("total_tokens must equal prompt + completion")
    if not isinstance(cost_usd, (int, float)) or isinstance(cost_usd, bool):
        raise ValueError("Frozen source cost_usd must be numeric")
    if not isinstance(latency_ms, (int, float)) or isinstance(latency_ms, bool):
        raise ValueError("Frozen source latency_ms must be numeric")

    return {
        "model": MODELS[model_index],
        "episode_id": EPISODES[episode_index - 1],
        "repeat": repeat,
        "decisions": decoded_decisions,
        "policy_metrics": {
            "model_calls_attempted": model_calls_attempted,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms": float(latency_ms),
            "cost_usd": float(cost_usd),
            "usage_incomplete": usage_incomplete,
            "temperature": temperature,
            "reasoning_effort": reasoning_effort,
        },
    }


def load_frozen_cross_family_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    root = source_dir(repo_root)
    parts = sorted(root.glob("replay-source.b64.part*"))
    if len(parts) != 6:
        raise ValueError(
            f"Expected 6 frozen source chunks; found {len(parts)}"
        )

    encoded = "".join(
        path.read_text(encoding="utf-8").strip()
        for path in parts
    )
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Frozen source base64 is invalid") from exc

    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError(
            "Frozen source compressed size mismatch: "
            f"expected={EXPECTED_COMPRESSED_BYTES}, "
            f"actual={len(compressed)}"
        )
    digest = sha256(compressed).hexdigest()
    if digest != EXPECTED_COMPRESSED_SHA256:
        raise ValueError(
            "Frozen source digest mismatch: "
            f"expected={EXPECTED_COMPRESSED_SHA256}, actual={digest}"
        )

    try:
        payload = gzip.decompress(compressed).decode("utf-8")
    except Exception as exc:
        raise ValueError(
            "Frozen source gzip could not be decompressed"
        ) from exc

    rows = [
        json.loads(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} frozen runs; found {len(rows)}"
        )

    records = [_decode_record(row) for row in rows]
    keys = [
        (record["model"], record["episode_id"], record["repeat"])
        for record in records
    ]
    if len(set(keys)) != len(keys):
        raise ValueError("Frozen source contains duplicate model/episode/repeat")

    expected = {
        (model, episode, repeat)
        for model in MODELS
        for episode in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    actual = set(keys)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            "Frozen source grid mismatch: "
            f"missing={missing}, extra={extra}"
        )

    model_counts = Counter(record["model"] for record in records)
    if len(model_counts) != EXPECTED_MODELS or any(
        count != 60 for count in model_counts.values()
    ):
        raise ValueError(
            f"Expected three models x 60 runs; found {dict(model_counts)}"
        )

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
