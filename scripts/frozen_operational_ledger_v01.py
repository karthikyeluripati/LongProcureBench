"""Load and verify the frozen selected operational-ledger evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 28669
EXPECTED_COMPRESSED_SHA256 = (
    "966c926f9396d157826f845488dde701575b72d8b2993bdc6e74749f0978dbe7"
)
EXPECTED_RUNS = 60
EXPECTED_EPISODES = 20
EXPECTED_REPEATS = 3
EXPECTED_ORIGINAL_RUNS = 43
EXPECTED_RECOVERY_RUNS = 17
EXPECTED_PARTS = 6
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
        / "operational-ledger-reactive-v0.1"
    )


def _expected_source_code(episode_index: int, repeat: int) -> int:
    if episode_index <= 14:
        return 0
    if episode_index == 15 and repeat == 1:
        return 0
    return 1


def load_frozen_operational_ledger_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    directory = evidence_dir(repo_root)
    paths = [
        directory / f"replay-source.part-{index:02d}.b64"
        for index in range(1, EXPECTED_PARTS + 1)
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError(
            "Missing frozen ledger replay source part(s): "
            + ", ".join(missing)
        )

    encoded = "".join(
        path.read_text(encoding="utf-8").strip()
        for path in paths
    )
    try:
        compressed = base64.b64decode(
            encoded,
            validate=True,
        )
    except Exception as exc:
        raise ValueError("Frozen ledger replay source base64 is invalid") from exc

    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError(
            "Frozen ledger replay source size mismatch: "
            f"expected={EXPECTED_COMPRESSED_BYTES}, actual={len(compressed)}"
        )
    digest = sha256(compressed).hexdigest()
    if digest != EXPECTED_COMPRESSED_SHA256:
        raise ValueError(
            "Frozen ledger replay source digest mismatch: "
            f"expected={EXPECTED_COMPRESSED_SHA256}, actual={digest}"
        )

    try:
        payload = gzip.decompress(compressed).decode("utf-8")
    except Exception as exc:
        raise ValueError("Frozen ledger replay source gzip is invalid") from exc

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
    source_counts = {0: 0, 1: 0}
    for row in rows:
        if not isinstance(row, list) or len(row) != 8:
            raise ValueError("Compact ledger record must have eight fields")

        (
            episode_index,
            repeat,
            source_code,
            status,
            decisions,
            metrics,
            final_ledger,
            ledger_trace,
        ) = row

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
        if source_code not in {0, 1}:
            raise ValueError(f"Invalid source code: {source_code!r}")
        if source_code != _expected_source_code(episode_index, repeat):
            raise ValueError(
                "Frozen recovery selection mismatch for "
                f"episode_index={episode_index}, repeat={repeat}"
            )
        if status not in {"completed", "max_actions"}:
            raise ValueError(f"Unexpected retained run status: {status!r}")
        if not isinstance(decisions, list):
            raise ValueError("Compact decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != 15:
            raise ValueError("Compact ledger metrics must contain fifteen fields")
        if not isinstance(final_ledger, dict):
            raise ValueError("final_ledger must be an object")
        if not isinstance(ledger_trace, list):
            raise ValueError("ledger_trace must be a list")

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
            state_strategy,
            ledger_open_items,
            ledger_resolved_items,
            ledger_items_created,
            ledger_max_open_items,
        ) = metrics

        if calls != len(decoded_decisions):
            raise ValueError(
                "Retained ledger run must have one model call per accepted action"
            )
        if usage_incomplete is not False:
            raise ValueError("Frozen ledger source must have complete usage")
        if total_tokens != prompt_tokens + completion_tokens:
            raise ValueError("total_tokens must equal prompt + completion")
        if cost_usd is None:
            raise ValueError("Frozen ledger source must have known API cost")
        if context_strategy != "factual_compiled_v0.1":
            raise ValueError("Unexpected frozen context strategy")
        if state_strategy != "operational_ledger_v0.1":
            raise ValueError("Unexpected frozen state strategy")

        open_items = final_ledger.get("open_items")
        resolved_items = final_ledger.get("resolved_items")
        if not isinstance(open_items, list) or not isinstance(
            resolved_items, list
        ):
            raise ValueError("Frozen final ledger must contain item lists")
        if len(open_items) != ledger_open_items:
            raise ValueError("Frozen ledger open-item count mismatch")
        if len(resolved_items) != ledger_resolved_items:
            raise ValueError("Frozen ledger resolved-item count mismatch")
        if ledger_items_created != ledger_open_items + ledger_resolved_items:
            raise ValueError("Frozen ledger created-item count mismatch")
        if len(ledger_trace) != len(decoded_decisions):
            raise ValueError("Frozen ledger trace/action count mismatch")

        observed_max_open = max(
            (
                len(trace.get("open_item_ids_after") or [])
                for trace in ledger_trace
                if isinstance(trace, dict)
            ),
            default=0,
        )
        if observed_max_open != ledger_max_open_items:
            raise ValueError("Frozen ledger max-open count mismatch")

        episode_id = EPISODES[episode_index - 1]
        key = (episode_id, repeat)
        if key in keys:
            raise ValueError(f"Duplicate frozen run key: {key}")
        keys.add(key)
        source_counts[source_code] += 1

        records.append({
            "model": MODEL,
            "episode_id": episode_id,
            "repeat": repeat,
            "source_code": source_code,
            "status": status,
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
                "state_strategy": state_strategy,
                "ledger_open_items": ledger_open_items,
                "ledger_resolved_items": ledger_resolved_items,
                "ledger_items_created": ledger_items_created,
                "ledger_max_open_items": ledger_max_open_items,
            },
            "final_ledger": final_ledger,
            "ledger_trace": ledger_trace,
        })

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    if keys != expected:
        raise ValueError("Frozen operational-ledger source grid mismatch")
    if source_counts != {
        0: EXPECTED_ORIGINAL_RUNS,
        1: EXPECTED_RECOVERY_RUNS,
    }:
        raise ValueError(
            f"Frozen operational-ledger source counts mismatch: {source_counts}"
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
