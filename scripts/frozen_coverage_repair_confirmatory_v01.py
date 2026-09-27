"""Load and verify frozen Coverage + Repair confirmatory evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 4949
EXPECTED_COMPRESSED_SHA256 = (
    "6b0cbb6602b3654e7c3301831b841b219b16846da767e209733ad0cf7868b9c8"
)
EXPECTED_COMPACT_ROWS_BYTES = 39183
EXPECTED_COMPACT_ROWS_SHA256 = (
    "ab5054761af6af31f91fa88526d2a393e278b657c5f7a2618552241cd1477607"
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

POLICY_METRIC_FIELDS = [
    "model_calls_attempted",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "latency_ms",
    "cost_usd",
    "usage_incomplete",
    "temperature",
    "reasoning_effort",
    "context_strategy",
    "agent_pattern",
    "coverage_repair_interventions",
    "coverage_forced_rfqs",
    "coverage_forced_followups",
    "coverage_forced_answers",
    "model_calls_failed",
]


def evidence_dir(repo_root: Path) -> Path:
    return (
        Path(repo_root)
        / "evidence"
        / "coverage-repair-confirmatory-v0.1"
    )


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


def _compact_row_from_record(
    record: dict[str, Any],
    repeat: int,
) -> list[Any]:
    episode_id = record["episode_id"]
    episode_index = EPISODES.index(episode_id) + 1
    decisions = [
        [
            row["action"]["type"],
            row["action"].get("supplier_id"),
            row["action"].get("arguments") or {},
        ]
        for row in record["trajectory"]
    ]
    metrics = record["policy_metrics"]
    compact_metrics = [metrics.get(key) for key in POLICY_METRIC_FIELDS]
    return [
        episode_index,
        repeat,
        record["status"],
        decisions,
        compact_metrics,
    ]


def load_frozen_coverage_repair_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    root = evidence_dir(repo_root)
    parts = sorted(root.glob("replay-source.b64.part*"))
    if len(parts) != 3:
        raise ValueError(
            f"Expected 3 frozen replay chunks; found {len(parts)}"
        )
    encoded = "".join(
        path.read_text(encoding="utf-8").strip()
        for path in parts
    )

    try:
        compressed = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError(
            "Frozen Coverage + Repair replay base64 is invalid"
        ) from exc

    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("Frozen Coverage + Repair replay size mismatch")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Frozen Coverage + Repair replay digest mismatch")

    try:
        payload_bytes = gzip.decompress(compressed)
        payload = payload_bytes.decode("utf-8")
    except Exception as exc:
        raise ValueError(
            "Frozen Coverage + Repair replay gzip is invalid"
        ) from exc

    if len(payload_bytes) != EXPECTED_COMPACT_ROWS_BYTES:
        raise ValueError(
            "Frozen Coverage + Repair compact-row byte count mismatch"
        )
    if sha256(payload_bytes).hexdigest() != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError(
            "Frozen Coverage + Repair compact-row digest mismatch"
        )

    rows = [
        json.loads(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} frozen runs; found {len(rows)}"
        )

    records: list[dict[str, Any]] = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 5:
            raise ValueError(
                "Compact Coverage + Repair record must have five fields"
            )
        episode_index, repeat, status, decisions, metrics = row
        if (
            not isinstance(episode_index, int)
            or not 1 <= episode_index <= len(EPISODES)
        ):
            raise ValueError("Invalid Coverage + Repair episode index")
        if (
            not isinstance(repeat, int)
            or not 1 <= repeat <= EXPECTED_REPEATS
        ):
            raise ValueError("Invalid Coverage + Repair repeat")
        if status != "completed":
            raise ValueError(
                f"Unexpected Coverage + Repair status: {status!r}"
            )
        if not isinstance(decisions, list):
            raise ValueError("Coverage + Repair decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != len(
            POLICY_METRIC_FIELDS
        ):
            raise ValueError(
                "Coverage + Repair metrics have unexpected field count"
            )

        decoded = []
        for decision in decisions:
            if not isinstance(decision, list) or len(decision) != 3:
                raise ValueError("Semantic decision must have three fields")
            action_type, supplier_id, arguments = decision
            if not isinstance(action_type, str) or not action_type:
                raise ValueError("Invalid Coverage + Repair action type")
            if supplier_id is not None and not isinstance(supplier_id, str):
                raise ValueError("supplier_id must be string/null")
            if not isinstance(arguments, dict):
                raise ValueError("Action arguments must be object")
            decoded.append({
                "type": action_type,
                "supplier_id": supplier_id,
                "arguments": arguments,
            })

        values = dict(zip(POLICY_METRIC_FIELDS, metrics))
        calls = values["model_calls_attempted"]
        interventions = values["coverage_repair_interventions"]
        if not isinstance(calls, int) or calls < 0:
            raise ValueError("Invalid model call count")
        if not isinstance(interventions, int) or interventions < 0:
            raise ValueError("Invalid intervention count")
        if len(decoded) != calls + interventions:
            raise ValueError(
                "Accepted actions must equal model calls + interventions"
            )
        forced_total = sum(
            int(values[key])
            for key in (
                "coverage_forced_rfqs",
                "coverage_forced_followups",
                "coverage_forced_answers",
            )
        )
        if forced_total != interventions:
            raise ValueError("Coverage + Repair intervention count mismatch")
        if values["model_calls_failed"] != 0:
            raise ValueError("Frozen source contains failed model calls")
        if values["usage_incomplete"] is not False:
            raise ValueError("Frozen source has incomplete provider usage")
        if values["total_tokens"] != (
            values["prompt_tokens"] + values["completion_tokens"]
        ):
            raise ValueError("Coverage + Repair total_tokens mismatch")
        if values["cost_usd"] is None:
            raise ValueError("Frozen source must have known cost")
        if (
            values["temperature"] is not None
            or values["reasoning_effort"] != "medium"
        ):
            raise ValueError("Unexpected sampling configuration")
        if values["context_strategy"] != "factual_compiled_v0.1":
            raise ValueError("Unexpected context strategy")
        if values["agent_pattern"] != "coverage_repair_v0.1":
            raise ValueError("Unexpected agent pattern")

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
                key: values[key] for key in POLICY_METRIC_FIELDS
            },
        })

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    if keys != expected:
        raise ValueError("Frozen Coverage + Repair source grid mismatch")
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
