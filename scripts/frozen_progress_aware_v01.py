"""Load and verify frozen progress-aware reactive evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 4361
EXPECTED_COMPRESSED_SHA256 = (
    "1bd89a732721e513cb64591752693f3a02977f42ebee5c30ce37acb816bb9f6e"
)
EXPECTED_COMPACT_ROWS_SHA256 = (
    "3317c8d61477a7d22d077b1f9f829ede74f49431b8ae16c2274ff08af71ebee5"
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
    return Path(repo_root) / "evidence" / "progress-aware-reactive-v0.1"


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


def load_frozen_progress_aware_source(
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
        raise ValueError("Frozen replay source size mismatch")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Frozen replay source digest mismatch")

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
            f"Expected {EXPECTED_RUNS} runs; found {len(rows)}"
        )
    if (
        sha256(b"".join(_canonical_line(row) for row in rows)).hexdigest()
        != EXPECTED_COMPACT_ROWS_SHA256
    ):
        raise ValueError("Frozen compact-row digest mismatch")

    records: list[dict[str, Any]] = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 5:
            raise ValueError("Compact progress record must have five fields")
        episode_index, repeat, status, decisions, metrics = row
        if (
            not isinstance(episode_index, int)
            or not 1 <= episode_index <= len(EPISODES)
        ):
            raise ValueError("Invalid episode index")
        if (
            not isinstance(repeat, int)
            or not 1 <= repeat <= EXPECTED_REPEATS
        ):
            raise ValueError("Invalid repeat")
        if status != "completed":
            raise ValueError(f"Unexpected progress status: {status!r}")
        if not isinstance(decisions, list):
            raise ValueError("Decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != 18:
            raise ValueError("Progress metrics must contain eighteen fields")

        decoded = []
        for decision in decisions:
            if not isinstance(decision, list) or len(decision) != 3:
                raise ValueError("Semantic decision must have three fields")
            action_type, supplier_id, arguments = decision
            if not isinstance(action_type, str) or not action_type:
                raise ValueError("Invalid action type")
            if supplier_id is not None and not isinstance(supplier_id, str):
                raise ValueError("supplier_id must be string/null")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be object")
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
            state_strategy,
            no_progress_marks,
            progress_events,
            evidence_epoch,
            guard_interventions,
            guard_retry_calls,
            guard_retry_noncompliance,
            model_calls_failed,
        ) = metrics

        if usage_incomplete is not False:
            raise ValueError("Frozen progress source must have complete usage")
        if total_tokens != prompt_tokens + completion_tokens:
            raise ValueError("total_tokens must equal prompt + completion")
        if cost_usd is None:
            raise ValueError("Frozen progress source must have known API cost")
        if temperature is not None or reasoning_effort != "medium":
            raise ValueError("Unexpected progress sampling configuration")
        if context_strategy != "factual_compiled_v0.1":
            raise ValueError("Unexpected context strategy")
        if state_strategy != "progress_aware_no_progress_guard_v0.1":
            raise ValueError("Unexpected progress state strategy")
        if model_calls_failed != 0:
            raise ValueError("Frozen progress run contains failed model calls")
        if guard_retry_calls != guard_interventions:
            raise ValueError("Every guard intervention must have one retry")
        if guard_retry_noncompliance > guard_retry_calls:
            raise ValueError("Guard noncompliance exceeds retry count")
        if calls != len(decoded) + guard_retry_calls:
            raise ValueError("Progress model-call decomposition mismatch")
        for value, label in (
            (no_progress_marks, "no_progress_marks"),
            (progress_events, "progress_events"),
            (evidence_epoch, "evidence_epoch"),
            (guard_interventions, "guard_interventions"),
            (guard_retry_calls, "guard_retry_calls"),
            (guard_retry_noncompliance, "guard_retry_noncompliance"),
        ):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"Invalid {label}")

        episode_id = EPISODES[episode_index - 1]
        key = (episode_id, repeat)
        if key in keys:
            raise ValueError(f"Duplicate frozen run key: {key}")
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
                "state_strategy": state_strategy,
                "no_progress_marks": no_progress_marks,
                "progress_events": progress_events,
                "evidence_epoch": evidence_epoch,
                "guard_interventions": guard_interventions,
                "guard_retry_calls": guard_retry_calls,
                "guard_retry_noncompliance": guard_retry_noncompliance,
                "model_calls_failed": model_calls_failed,
            },
        })

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    if keys != expected:
        raise ValueError("Frozen progress source grid mismatch")
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
