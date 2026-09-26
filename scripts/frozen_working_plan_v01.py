"""Load and verify the frozen 60-run maintained-working-plan evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 43177
EXPECTED_COMPRESSED_SHA256 = (
    "d889aac2249d7b8dce9e89c489bef32f356fefde3b4b907236192f8a23e2a057"
)
EXPECTED_PROVENANCE_BYTES = 12606
EXPECTED_PROVENANCE_SHA256 = (
    "25f55c2ecfd5b7f7e46a85b4b89039a621275f385aec232eec8f1f068bacd759"
)
EXPECTED_SELECTED_COMPACTION_SHA256 = (
    "392060d51c9e8b430156428f53dd20c7c4caae4da062d23b51bc7a6eb6b92923"
)
EXPECTED_SELECTED_RAW_PROVENANCE_SHA256 = (
    "8395185f72bf3b52e624385e2f524d87113582065075852be08223b23584d8a3"
)
EXPECTED_RUNS = 60
EXPECTED_EPISODES = 20
EXPECTED_REPEATS = 3
EXPECTED_PARTS = ("replay-source.b64",)
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
    return Path(repo_root) / "evidence" / "working-plan-reactive-v0.1"


def _canonical_compact_line(row: Any) -> bytes:
    return (
        json.dumps(
            row,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def compact_rows_sha256(rows: list[Any]) -> str:
    return sha256(b"".join(_canonical_compact_line(row) for row in rows)).hexdigest()


def load_frozen_working_plan_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    directory = evidence_dir(repo_root)
    paths = [directory / name for name in EXPECTED_PARTS]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError(
            "Missing frozen working-plan replay source part(s): "
            + ", ".join(missing)
        )

    encoded = "".join(
        path.read_text(encoding="utf-8").strip()
        for path in paths
    )
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Frozen working-plan replay source base64 is invalid") from exc

    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError(
            "Frozen working-plan replay source size mismatch: "
            f"expected={EXPECTED_COMPRESSED_BYTES}, actual={len(compressed)}"
        )
    digest = sha256(compressed).hexdigest()
    if digest != EXPECTED_COMPRESSED_SHA256:
        raise ValueError(
            "Frozen working-plan replay source digest mismatch: "
            f"expected={EXPECTED_COMPRESSED_SHA256}, actual={digest}"
        )

    try:
        payload = gzip.decompress(compressed).decode("utf-8")
    except Exception as exc:
        raise ValueError("Frozen working-plan replay source gzip is invalid") from exc

    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} frozen working-plan runs; found {len(rows)}"
        )
    if compact_rows_sha256(rows) != EXPECTED_SELECTED_COMPACTION_SHA256:
        raise ValueError("Frozen working-plan artifact-derived compaction mismatch")

    records = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 8:
            raise ValueError("Compact working-plan record must have eight fields")
        (
            episode_index,
            repeat,
            status,
            decisions,
            metrics,
            final_plan,
            plan_trace,
            plan_rejection_trace,
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
        if status != "completed":
            raise ValueError(f"Unexpected frozen working-plan status: {status!r}")
        if not isinstance(decisions, list):
            raise ValueError("Compact decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != 16:
            raise ValueError("Compact working-plan metrics must contain sixteen fields")
        if not isinstance(final_plan, dict):
            raise ValueError("final_plan must be an object")
        if not isinstance(plan_trace, list):
            raise ValueError("plan_trace must be a list")
        if not isinstance(plan_rejection_trace, list):
            raise ValueError("plan_rejection_trace must be a list")

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
            plan_updates,
            plan_rejections,
            mean_plan_steps,
            max_plan_steps,
            model_calls_failed,
        ) = metrics

        if calls != len(decoded_decisions):
            raise ValueError(
                "Frozen working-plan run must have one model call per accepted action"
            )
        if usage_incomplete is not False:
            raise ValueError("Frozen working-plan source must have complete usage")
        if total_tokens != prompt_tokens + completion_tokens:
            raise ValueError("total_tokens must equal prompt + completion")
        if cost_usd is None:
            raise ValueError("Frozen working-plan source must have known API cost")
        if temperature is not None:
            raise ValueError("Frozen working-plan temperature must be omitted")
        if reasoning_effort != "medium":
            raise ValueError("Unexpected frozen working-plan reasoning effort")
        if context_strategy != "factual_compiled_v0.1":
            raise ValueError("Unexpected frozen context strategy")
        if state_strategy != "maintained_working_plan_v0.1":
            raise ValueError("Unexpected frozen state strategy")
        if model_calls_failed != 0:
            raise ValueError("Frozen working-plan run contains failed model calls")
        if plan_updates != len(plan_trace):
            raise ValueError("Frozen working-plan update/trace count mismatch")
        if plan_rejections != len(plan_rejection_trace):
            raise ValueError("Frozen working-plan rejection/trace count mismatch")
        if plan_updates + plan_rejections != calls:
            raise ValueError("Every model call must yield an accepted or rejected plan update")

        plan_lengths = []
        for trace in plan_trace:
            if not isinstance(trace, dict):
                raise ValueError("Working-plan trace row must be an object")
            plan = trace.get("next_plan")
            if not isinstance(plan, dict):
                raise ValueError("Working-plan trace next_plan must be an object")
            steps = plan.get("next_steps")
            if not isinstance(steps, list) or len(steps) > 4:
                raise ValueError("Working-plan trace exceeds the four-step bound")
            plan_lengths.append(len(steps))

        observed_max = max(plan_lengths, default=0)
        if observed_max != max_plan_steps:
            raise ValueError("Frozen working-plan max-plan-step mismatch")
        if plan_lengths:
            observed_mean = sum(plan_lengths) / len(plan_lengths)
            if not math.isclose(
                float(mean_plan_steps), observed_mean, rel_tol=1e-12, abs_tol=1e-12
            ):
                raise ValueError("Frozen working-plan mean-plan-step mismatch")
        elif mean_plan_steps is not None:
            raise ValueError("Zero-update run must not report a mean plan length")

        if plan_trace and final_plan != plan_trace[-1].get("next_plan"):
            raise ValueError("Frozen final plan must equal the last accepted replacement")

        episode_id = EPISODES[episode_index - 1]
        key = (episode_id, repeat)
        if key in keys:
            raise ValueError(f"Duplicate frozen working-plan run key: {key}")
        keys.add(key)

        records.append({
            "model": MODEL,
            "episode_id": episode_id,
            "repeat": repeat,
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
                "plan_updates": plan_updates,
                "plan_rejections": plan_rejections,
                "mean_plan_steps": mean_plan_steps,
                "max_plan_steps": max_plan_steps,
                "model_calls_failed": model_calls_failed,
            },
            "final_plan": final_plan,
            "plan_trace": plan_trace,
            "plan_rejection_trace": plan_rejection_trace,
        })

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    if keys != expected:
        raise ValueError("Frozen working-plan source grid mismatch")
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
