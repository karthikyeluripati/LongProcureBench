"""Load and verify frozen ReAct comparator evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 12554
EXPECTED_COMPRESSED_SHA256 = (
    "8f725cbc46b933d466dab481dde03ce2313acac7fce14193481a6af9e58c19e2"
)
EXPECTED_COMPACT_ROWS_BYTES = 90934
EXPECTED_COMPACT_ROWS_SHA256 = (
    "b93c810ce585807a7a822953bb890ee1d6161291c523d0d2de4a96b60f0a1c1c"
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
    return Path(repo_root) / "evidence" / "react-comparator-v0.1"


def _canonical_line(row: Any) -> bytes:
    return (
        json.dumps(
            row,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def _compact_row_from_record(record: dict[str, Any]) -> list[Any]:
    episode_index = EPISODES.index(record["episode_id"]) + 1
    decisions = [
        [
            decision["type"],
            decision.get("supplier_id"),
            decision.get("arguments") or {},
        ]
        for decision in record["decisions"]
    ]
    metrics = record["policy_metrics"]
    compact_metrics = [
        metrics.get("model_calls_attempted"),
        metrics.get("prompt_tokens"),
        metrics.get("completion_tokens"),
        metrics.get("total_tokens"),
        metrics.get("latency_ms"),
        metrics.get("cost_usd"),
        metrics.get("usage_incomplete"),
        metrics.get("temperature"),
        metrics.get("reasoning_effort"),
        metrics.get("context_strategy"),
        metrics.get("agent_pattern"),
        metrics.get("react_steps_proposed"),
        metrics.get("react_steps_accepted"),
        metrics.get("react_thought_chars_total"),
        metrics.get("react_thought_chars_mean"),
        metrics.get("react_thought_chars_max"),
        metrics.get("model_calls_failed"),
    ]
    return [
        episode_index,
        record["repeat"],
        record["status"],
        decisions,
        compact_metrics,
    ]


def load_frozen_react_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    path = evidence_dir(repo_root) / "replay-source.b64"
    if not path.is_file():
        raise ValueError(f"Missing frozen ReAct replay source: {path}")

    try:
        compressed = base64.b64decode(
            path.read_text(encoding="utf-8").strip(),
            validate=True,
        )
    except Exception as exc:
        raise ValueError("Frozen ReAct replay base64 is invalid") from exc

    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("Frozen ReAct replay size mismatch")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Frozen ReAct replay digest mismatch")

    try:
        payload_bytes = gzip.decompress(compressed)
        payload = payload_bytes.decode("utf-8")
    except Exception as exc:
        raise ValueError("Frozen ReAct replay gzip is invalid") from exc

    if len(payload_bytes) != EXPECTED_COMPACT_ROWS_BYTES:
        raise ValueError("Frozen ReAct compact-row byte count mismatch")
    if sha256(payload_bytes).hexdigest() != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError("Frozen ReAct compact-row digest mismatch")

    rows = [
        json.loads(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} ReAct runs; found {len(rows)}"
        )

    records: list[dict[str, Any]] = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 5:
            raise ValueError("Compact ReAct record must have five fields")
        episode_index, repeat, status, decisions, metrics = row
        if (
            not isinstance(episode_index, int)
            or not 1 <= episode_index <= len(EPISODES)
        ):
            raise ValueError("Invalid ReAct episode index")
        if (
            not isinstance(repeat, int)
            or not 1 <= repeat <= EXPECTED_REPEATS
        ):
            raise ValueError("Invalid ReAct repeat")
        if status != "completed":
            raise ValueError(f"Unexpected ReAct status: {status!r}")
        if not isinstance(decisions, list):
            raise ValueError("ReAct decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != 17:
            raise ValueError("ReAct metrics must contain seventeen fields")

        decoded = []
        for decision in decisions:
            if not isinstance(decision, list) or len(decision) != 3:
                raise ValueError("Semantic decision must have three fields")
            action_type, supplier_id, arguments = decision
            if not isinstance(action_type, str) or not action_type:
                raise ValueError("Invalid ReAct action type")
            if supplier_id is not None and not isinstance(supplier_id, str):
                raise ValueError("supplier_id must be string/null")
            if not isinstance(arguments, dict):
                raise ValueError("ReAct action arguments must be object")
            decoded.append({
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
            agent_pattern,
            react_steps_proposed,
            react_steps_accepted,
            thought_chars_total,
            thought_chars_mean,
            thought_chars_max,
            model_calls_failed,
        ) = metrics

        if calls != len(decoded):
            raise ValueError("ReAct must use one model call per action")
        if react_steps_proposed != len(decoded):
            raise ValueError("ReAct proposed-step count mismatch")
        if react_steps_accepted != len(decoded):
            raise ValueError("ReAct accepted-step count mismatch")
        if model_calls_failed != 0:
            raise ValueError("Frozen ReAct source contains failed calls")
        if usage_incomplete is not False:
            raise ValueError("Frozen ReAct source has incomplete usage")
        if total_tokens != prompt_tokens + completion_tokens:
            raise ValueError("ReAct total_tokens mismatch")
        if cost_usd is None:
            raise ValueError("Frozen ReAct source must have known cost")
        if temperature is not None or reasoning_effort != "medium":
            raise ValueError("Unexpected ReAct sampling configuration")
        if context_strategy != "factual_compiled_v0.1":
            raise ValueError("Unexpected ReAct context strategy")
        if agent_pattern != "react_v0.1":
            raise ValueError("Unexpected ReAct agent pattern")
        if not isinstance(thought_chars_total, int) or thought_chars_total <= 0:
            raise ValueError("Invalid ReAct thought character total")
        if not isinstance(thought_chars_max, int) or thought_chars_max <= 0:
            raise ValueError("Invalid ReAct thought character max")
        if not math.isclose(
            float(thought_chars_mean),
            thought_chars_total / len(decoded),
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("ReAct thought character mean mismatch")

        episode_id = EPISODES[episode_index - 1]
        key = (episode_id, repeat)
        if key in keys:
            raise ValueError(f"Duplicate frozen ReAct run key: {key}")
        keys.add(key)
        records.append({
            "model": MODEL,
            "episode_id": episode_id,
            "repeat": repeat,
            "status": status,
            "decisions": decoded,
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
                "agent_pattern": agent_pattern,
                "react_steps_proposed": react_steps_proposed,
                "react_steps_accepted": react_steps_accepted,
                "react_thought_chars_total": thought_chars_total,
                "react_thought_chars_mean": float(thought_chars_mean),
                "react_thought_chars_max": thought_chars_max,
                "model_calls_failed": model_calls_failed,
            },
        })

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    if keys != expected:
        raise ValueError("Frozen ReAct source grid mismatch")
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
