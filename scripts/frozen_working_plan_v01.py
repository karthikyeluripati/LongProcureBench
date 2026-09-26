"""Load and verify the frozen 60-run maintained-working-plan evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 8182
EXPECTED_COMPRESSED_SHA256 = "27a024a55a06cc5361f54d1d0c08f1988d413bfe5b4121dcee008aaa9a45e52f"
EXPECTED_PROVENANCE_BYTES = 8073
EXPECTED_PROVENANCE_SHA256 = "329328958c1cc6abcb31ce1a906570f659ce3859b38dc4fe426735eac3af7e3d"
EXPECTED_SELECTED_COMPACTION_SHA256 = "da1150dd04d46ccc22c8c434006e0a49e4c926b62ce5fe68982c3dbdc06c58b0"
EXPECTED_SELECTED_RAW_PROVENANCE_SHA256 = "f70087fb162b626843563a51f728bac4d7fad01fbff477e74f2e9114c8b8dca3"
EXPECTED_RUNS = 60
EXPECTED_EPISODES = 20
EXPECTED_REPEATS = 3
EXPECTED_PARTS = ("replay-source.b64",)
MODEL = "openai/gpt-5.6-sol"
ARTIFACT_SHA256 = "924443c9bde20b687a2a3b9fe0c8058f8a224604d8532d6c325c6a9c89fd6c9b"
ARTIFACT_BYTES = 280188

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


def _canonical_line(row: Any) -> bytes:
    return json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def compact_rows_sha256(rows: list[Any]) -> str:
    return sha256(b"".join(_canonical_line(row) for row in rows)).hexdigest()


def compact_record_from_raw(raw: dict[str, Any], *, episode_index: int, repeat: int) -> list[Any]:
    decisions = []
    for trajectory_row in raw.get("trajectory") or []:
        action = trajectory_row["action"]
        decisions.append([action["type"], action.get("supplier_id"), action.get("arguments") or {}])
    metrics = raw.get("policy_metrics") or {}
    plan_trace = []
    for trace in metrics.get("plan_trace") or []:
        next_plan = trace.get("next_plan") or {}
        plan_trace.append([
            trace.get("model_call"), trace.get("proposed_state_step"),
            trace.get("accepted_state_step"), len(next_plan.get("next_steps") or []),
        ])
    rejection_trace = []
    for trace in metrics.get("plan_rejection_trace") or []:
        rejected = trace.get("rejected_plan") or {}
        rejection_trace.append([
            trace.get("model_call"), trace.get("state_step"), trace.get("message"),
            len(rejected.get("next_steps") or []),
        ])
    return [
        episode_index, repeat, raw.get("status"), decisions,
        [
            metrics.get("model_calls_attempted"), metrics.get("prompt_tokens"),
            metrics.get("completion_tokens"), metrics.get("total_tokens"),
            metrics.get("latency_ms"), metrics.get("cost_usd"),
            metrics.get("usage_incomplete"), metrics.get("temperature"),
            metrics.get("reasoning_effort"), metrics.get("context_strategy"),
            metrics.get("state_strategy"), metrics.get("plan_updates"),
            metrics.get("plan_rejections"), metrics.get("mean_plan_steps"),
            metrics.get("max_plan_steps"),
        ],
        plan_trace, rejection_trace,
    ]


def compact_record_from_record(record: dict[str, Any]) -> list[Any]:
    m = record["policy_metrics"]
    decisions = [[d["type"], d.get("supplier_id"), d.get("arguments") or {}] for d in record["decisions"]]
    return [
        EPISODES.index(record["episode_id"]) + 1, record["repeat"], record["status"], decisions,
        [m["model_calls_attempted"], m["prompt_tokens"], m["completion_tokens"], m["total_tokens"],
         m["latency_ms"], m["cost_usd"], m["usage_incomplete"], m["temperature"],
         m["reasoning_effort"], m["context_strategy"], m["state_strategy"], m["plan_updates"],
         m["plan_rejections"], m["mean_plan_steps"], m["max_plan_steps"]],
        record["plan_trace"], record["plan_rejection_trace"],
    ]


def load_frozen_working_plan_source(repo_root: Path) -> list[dict[str, Any]]:
    directory = evidence_dir(repo_root)
    actual = {p.name for p in directory.glob("replay-source*.b64") if p.is_file()}
    if actual != set(EXPECTED_PARTS):
        raise ValueError(f"Frozen working-plan replay file set mismatch: expected={list(EXPECTED_PARTS)}, actual={sorted(actual)}")
    encoded = "".join((directory / name).read_text(encoding="utf-8").strip() for name in EXPECTED_PARTS)
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Frozen working-plan replay source base64 is invalid") from exc
    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("Frozen working-plan replay source size mismatch")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Frozen working-plan replay source digest mismatch")
    try:
        rows = [json.loads(line) for line in gzip.decompress(compressed).decode("utf-8").splitlines() if line.strip()]
    except Exception as exc:
        raise ValueError("Frozen working-plan replay source gzip is invalid") from exc
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(f"Expected {EXPECTED_RUNS} frozen working-plan runs; found {len(rows)}")
    if compact_rows_sha256(rows) != EXPECTED_SELECTED_COMPACTION_SHA256:
        raise ValueError("Frozen working-plan artifact-derived compaction mismatch")

    records = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 7:
            raise ValueError("Compact working-plan record must have seven fields")
        episode_index, repeat, status, decisions, metrics, plan_trace, rejection_trace = row
        if not isinstance(episode_index, int) or not 1 <= episode_index <= EXPECTED_EPISODES:
            raise ValueError("Invalid episode index")
        if not isinstance(repeat, int) or not 1 <= repeat <= EXPECTED_REPEATS:
            raise ValueError("Invalid repeat")
        if status != "completed":
            raise ValueError(f"Unexpected working-plan run status: {status!r}")
        if not isinstance(decisions, list) or not isinstance(metrics, list) or len(metrics) != 15:
            raise ValueError("Malformed compact working-plan record")
        if not isinstance(plan_trace, list) or not isinstance(rejection_trace, list):
            raise ValueError("Working-plan diagnostics must be lists")
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
        (calls,prompt,completion,total,latency,cost,usage_incomplete,temperature,reasoning_effort,
         context_strategy,state_strategy,plan_updates,plan_rejections,mean_plan_steps,max_plan_steps) = metrics
        if calls != len(decoded):
            raise ValueError("Working-plan run must have one model call per accepted action")
        if usage_incomplete is not False or cost is None:
            raise ValueError("Frozen working-plan source must have complete usage and known cost")
        if total != prompt + completion:
            raise ValueError("total_tokens must equal prompt + completion")
        if context_strategy != "factual_compiled_v0.1" or state_strategy != "maintained_working_plan_v0.1":
            raise ValueError("Unexpected frozen working-plan strategies")
        if plan_updates != len(plan_trace) or plan_rejections != len(rejection_trace):
            raise ValueError("Working-plan diagnostic count mismatch")
        if plan_updates + plan_rejections != calls:
            raise ValueError("Every model call must yield one accepted or rejected plan update")
        accepted_calls = []
        lengths = []
        for trace in plan_trace:
            if not isinstance(trace, list) or len(trace) != 4:
                raise ValueError("Malformed accepted plan trace")
            model_call, proposed_step, accepted_step, steps = trace
            if not all(isinstance(v, int) for v in (model_call, proposed_step, accepted_step, steps)):
                raise ValueError("Plan trace integer field mismatch")
            if not 0 <= steps <= 4:
                raise ValueError("Accepted plan exceeds four-step bound")
            accepted_calls.append(model_call); lengths.append(steps)
        rejected_calls = []
        for trace in rejection_trace:
            if not isinstance(trace, list) or len(trace) != 4:
                raise ValueError("Malformed rejected plan trace")
            model_call, state_step, message, steps = trace
            if not isinstance(model_call, int) or not isinstance(state_step, int) or not isinstance(message, str) or not isinstance(steps, int):
                raise ValueError("Rejected plan trace field mismatch")
            rejected_calls.append(model_call)
        if sorted(accepted_calls + rejected_calls) != list(range(1, calls + 1)):
            raise ValueError("Working-plan call/diagnostic coverage mismatch")
        observed_max = max(lengths, default=0)
        if observed_max != max_plan_steps:
            raise ValueError("Working-plan max step diagnostic mismatch")
        observed_mean = sum(lengths) / len(lengths) if lengths else 0.0
        if not math.isclose(float(mean_plan_steps), observed_mean, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Working-plan mean step diagnostic mismatch")
        episode_id = EPISODES[episode_index - 1]
        key = (episode_id, repeat)
        if key in keys:
            raise ValueError(f"Duplicate frozen working-plan key: {key}")
        keys.add(key)
        records.append({
            "model": MODEL, "episode_id": episode_id, "repeat": repeat, "status": status,
            "decisions": decoded,
            "policy_metrics": {
                "model_calls_attempted": calls, "prompt_tokens": prompt, "completion_tokens": completion,
                "total_tokens": total, "latency_ms": float(latency), "cost_usd": float(cost),
                "usage_incomplete": usage_incomplete, "temperature": temperature,
                "reasoning_effort": reasoning_effort, "context_strategy": context_strategy,
                "state_strategy": state_strategy, "plan_updates": plan_updates,
                "plan_rejections": plan_rejections, "mean_plan_steps": float(mean_plan_steps),
                "max_plan_steps": max_plan_steps,
            },
            "plan_trace": plan_trace, "plan_rejection_trace": rejection_trace,
        })
    expected={(e,r) for e in EPISODES for r in range(1,EXPECTED_REPEATS+1)}
    if keys != expected:
        raise ValueError("Frozen working-plan source grid mismatch")
    return records


def reconstruct_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    episode_id = record["episode_id"]
    return [{"action_id": f"a{index}", "episode_id": episode_id, "type": d["type"],
             "supplier_id": d["supplier_id"], "arguments": dict(d["arguments"])}
            for index,d in enumerate(record["decisions"], start=1)]
