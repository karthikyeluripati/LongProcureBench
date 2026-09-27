"""Load and verify frozen always-replan + pre-terminal-verifier evidence."""
from __future__ import annotations

import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_BYTES = 51107
EXPECTED_COMPRESSED_SHA256 = "494a9cf48d868589b39e75a034f3e314c0c1f52be3636959a81981cd6085a4ab"
EXPECTED_COMPACT_ROWS_SHA256 = "e8e854bf0ba45176641a1d888fc8a4733f3b122c1fb031eb135d29f09054d380"
EXPECTED_RUNS = 60
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
    return Path(repo_root) / "evidence" / "always-replan-verifier-v0.1"


def _canonical_line(row: Any) -> bytes:
    return (
        json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def load_frozen_always_replan_verifier_source(repo_root: Path) -> list[dict[str, Any]]:
    directory = evidence_dir(repo_root)
    paths = [directory / name for name in EXPECTED_PARTS]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("Missing frozen replay source part(s): " + ", ".join(missing))
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in paths)
    try:
        compressed = base64.b64decode(encoded, validate=True)
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
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    if len(rows) != EXPECTED_RUNS:
        raise ValueError(f"Expected {EXPECTED_RUNS} runs; found {len(rows)}")
    if sha256(b"".join(_canonical_line(row) for row in rows)).hexdigest() != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError("Frozen compact-row digest mismatch")

    records = []
    keys = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError("Compact treatment record must have six fields")
        episode_index, repeat, status, decisions, metrics, diagnostics = row
        if not isinstance(episode_index, int) or not 1 <= episode_index <= len(EPISODES):
            raise ValueError("Invalid episode index")
        if not isinstance(repeat, int) or not 1 <= repeat <= EXPECTED_REPEATS:
            raise ValueError("Invalid repeat")
        if status not in {"completed", "max_actions"}:
            raise ValueError(f"Unexpected treatment status: {status!r}")
        if not isinstance(decisions, list):
            raise ValueError("Decisions must be a list")
        if not isinstance(metrics, list) or len(metrics) != 17:
            raise ValueError("Treatment metrics must contain seventeen fields")
        if not isinstance(diagnostics, list) or len(diagnostics) != 4:
            raise ValueError("Treatment diagnostics must contain four fields")

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
            decoded.append({"type": action_type, "supplier_id": supplier_id, "arguments": arguments})

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
            planner_calls,
            action_calls,
            verifier_calls,
            verifier_rejections,
            repair_calls,
            model_calls_failed,
        ) = metrics
        if usage_incomplete is not False:
            raise ValueError("Frozen treatment source must have complete usage")
        if total_tokens != prompt_tokens + completion_tokens:
            raise ValueError("total_tokens must equal prompt + completion")
        if cost_usd is None:
            raise ValueError("Frozen treatment source must have known API cost")
        if temperature is not None or reasoning_effort != "medium":
            raise ValueError("Unexpected treatment sampling configuration")
        if context_strategy != "factual_compiled_v0.1":
            raise ValueError("Unexpected context strategy")
        if state_strategy != "always_replan_preterminal_verifier_v0.1":
            raise ValueError("Unexpected state strategy")
        if model_calls_failed != 0:
            raise ValueError("Frozen treatment run contains failed model calls")
        if planner_calls != len(decoded) or action_calls != len(decoded):
            raise ValueError("Every accepted action must have one planner and one selector call")
        if verifier_rejections != repair_calls:
            raise ValueError("Each verifier rejection must have one repair call")
        if calls != planner_calls + action_calls + verifier_calls + repair_calls:
            raise ValueError("Treatment model-call decomposition mismatch")
        if status == "max_actions" and len(decoded) != 50:
            raise ValueError("max_actions treatment run must contain 50 accepted actions")

        proposals, rejected_recs, approved_recs, bounded_issue_traces = diagnostics
        for mapping in (proposals, rejected_recs, approved_recs):
            if not isinstance(mapping, dict):
                raise ValueError("Diagnostic action counts must be objects")
        if sum(int(v) for v in proposals.values()) != verifier_calls:
            raise ValueError("Verifier proposal diagnostic mismatch")
        if sum(int(v) for v in rejected_recs.values()) != verifier_rejections:
            raise ValueError("Verifier rejection diagnostic mismatch")
        if sum(int(v) for v in approved_recs.values()) + verifier_rejections != verifier_calls:
            raise ValueError("Verifier approval diagnostic mismatch")
        if not isinstance(bounded_issue_traces, int) or bounded_issue_traces < 0:
            raise ValueError("Invalid bounded-issue diagnostic")

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
                "planner_calls": planner_calls,
                "action_calls": action_calls,
                "verifier_calls": verifier_calls,
                "verifier_rejections": verifier_rejections,
                "repair_calls": repair_calls,
                "model_calls_failed": model_calls_failed,
            },
            "diagnostics": {
                "terminal_proposal_type_counts": proposals,
                "rejected_verifier_recommendation_counts": rejected_recs,
                "approved_verifier_recommendation_counts": approved_recs,
                "verification_traces_with_bounded_issues": bounded_issue_traces,
            },
        })

    expected = {(episode_id, repeat) for episode_id in EPISODES for repeat in range(1, 4)}
    if keys != expected:
        raise ValueError("Frozen treatment source grid mismatch")
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
