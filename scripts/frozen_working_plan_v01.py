"""Load and verify the frozen maintained-working-plan evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 43174
EXPECTED_COMPRESSED_SHA256 = "b22c8b72afbc5fcf2fbdcdb0cdefe390002472723d1381516c75fab961c05296"
EXPECTED_PROVENANCE_BYTES = 8073
EXPECTED_PROVENANCE_SHA256 = "1deaedab45a6107168cf3e0cac64667916737de90520401aa97975d89965b694"
EXPECTED_COMPACTION_SHA256 = "c5403ecb08ec634e794a3afb8ffb24a95fb3bf8eec53e49335c34d9b087a3f2c"
EXPECTED_RAW_PROVENANCE_SHA256 = "f70087fb162b626843563a51f728bac4d7fad01fbff477e74f2e9114c8b8dca3"
EXPECTED_RUNS = 60
EXPECTED_EPISODES = 20
EXPECTED_REPEATS = 3
EXPECTED_PARTS = (
    "replay-source.part-01.b64",
    "replay-source.part-02.b64",
    "replay-source.part-03.b64",
    "replay-source.part-04.b64",
    "replay-source.part-05.b64",
    "replay-source.part-06.b64",
    "replay-source.part-07.b64",
    "replay-source.part-08.b64",
)
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


def compact_rows_sha256(rows: list[Any]) -> str:
    payload = b"".join(
        json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
        for row in rows
    )
    return sha256(payload).hexdigest()


def load_frozen_working_plan_source(repo_root: Path) -> list[dict[str, Any]]:
    directory = evidence_dir(repo_root)
    paths = [directory / name for name in EXPECTED_PARTS]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("Missing frozen working-plan replay source part(s): " + ", ".join(missing))
    try:
        compressed = base64.b64decode("".join(path.read_text(encoding="utf-8").strip() for path in paths), validate=True)
    except Exception as exc:
        raise ValueError("Frozen working-plan replay source is invalid base64") from exc
    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("Frozen working-plan replay source size mismatch")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Frozen working-plan replay source digest mismatch")
    try:
        payload = gzip.decompress(compressed).decode("utf-8")
    except Exception as exc:
        raise ValueError("Frozen working-plan replay source gzip is invalid") from exc
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(f"Expected {EXPECTED_RUNS} frozen runs; found {len(rows)}")
    if compact_rows_sha256(rows) != EXPECTED_COMPACTION_SHA256:
        raise ValueError("Frozen working-plan artifact-derived compaction mismatch")

    records = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 8:
            raise ValueError("Compact working-plan record must have eight fields")
        episode_index, repeat, status, decisions, metrics, final_plan, plan_trace, rejection_trace = row
        if not isinstance(episode_index, int) or not 1 <= episode_index <= len(EPISODES):
            raise ValueError(f"Invalid episode index: {episode_index!r}")
        if not isinstance(repeat, int) or not 1 <= repeat <= EXPECTED_REPEATS:
            raise ValueError(f"Invalid repeat: {repeat!r}")
        if status != "completed":
            raise ValueError(f"Unexpected frozen working-plan status: {status!r}")
        if not isinstance(decisions, list):
            raise ValueError("Compact decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != 15:
            raise ValueError("Compact working-plan metrics must contain fifteen fields")
        if not isinstance(final_plan, dict):
            raise ValueError("Frozen final plan must be an object")
        if not isinstance(plan_trace, list) or not isinstance(rejection_trace, list):
            raise ValueError("Frozen working-plan traces must be lists")

        decoded = []
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
            decoded.append({"type": action_type, "supplier_id": supplier_id, "arguments": arguments})

        (
            calls, prompt_tokens, completion_tokens, total_tokens, latency_ms,
            cost_usd, usage_incomplete, temperature, reasoning_effort,
            context_strategy, state_strategy, plan_updates, plan_rejections,
            mean_plan_steps, max_plan_steps,
        ) = metrics
        if calls != len(decoded):
            raise ValueError("Frozen working-plan run must have one call per accepted action")
        if usage_incomplete is not False:
            raise ValueError("Frozen working-plan source must have complete usage")
        if total_tokens != prompt_tokens + completion_tokens:
            raise ValueError("total_tokens must equal prompt + completion")
        if cost_usd is None:
            raise ValueError("Frozen working-plan source must have known API cost")
        if context_strategy != "factual_compiled_v0.1":
            raise ValueError("Unexpected frozen context strategy")
        if state_strategy != "maintained_working_plan_v0.1":
            raise ValueError("Unexpected frozen working-plan state strategy")
        if plan_updates != len(plan_trace):
            raise ValueError("Frozen working-plan update count mismatch")
        if plan_rejections != len(rejection_trace):
            raise ValueError("Frozen working-plan rejection count mismatch")
        if plan_updates + plan_rejections != calls:
            raise ValueError("Every working-plan proposal must be accepted or rejected")

        lengths = []
        for trace in plan_trace:
            if not isinstance(trace, dict) or not isinstance(trace.get("next_plan"), dict):
                raise ValueError("Malformed working-plan trace")
            steps = trace["next_plan"].get("next_steps")
            if not isinstance(steps, list) or len(steps) > 4:
                raise ValueError("Working-plan trace violates step bound")
            lengths.append(len(steps))
        observed_mean = (sum(lengths) / len(lengths)) if lengths else None
        observed_max = max(lengths, default=0)
        if mean_plan_steps is None:
            if observed_mean is not None:
                raise ValueError("Working-plan mean-step diagnostic mismatch")
        elif abs(float(mean_plan_steps) - float(observed_mean)) > 1e-12:
            raise ValueError("Working-plan mean-step diagnostic mismatch")
        if int(max_plan_steps or 0) != observed_max:
            raise ValueError("Working-plan max-step diagnostic mismatch")
        if plan_trace and final_plan != plan_trace[-1]["next_plan"]:
            raise ValueError("Frozen final plan does not match final accepted plan update")

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
                "plan_updates": plan_updates,
                "plan_rejections": plan_rejections,
                "mean_plan_steps": mean_plan_steps,
                "max_plan_steps": max_plan_steps,
            },
            "final_plan": final_plan,
            "plan_trace": plan_trace,
            "plan_rejection_trace": rejection_trace,
        })
    expected = {(episode_id, repeat) for episode_id in EPISODES for repeat in range(1, EXPECTED_REPEATS + 1)}
    if keys != expected:
        raise ValueError("Frozen working-plan source grid mismatch")
    return records


def reconstruct_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    episode_id = record["episode_id"]
    return [
        {"action_id": f"a{index}", "episode_id": episode_id, "type": decision["type"], "supplier_id": decision["supplier_id"], "arguments": dict(decision["arguments"])}
        for index, decision in enumerate(record["decisions"], start=1)
    ]
