"""Audit frozen State Validity Frontier development v0.2 evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEnv, LongProcureBenchEvaluator
from frozen_state_validity_frontier_development_v02 import (
    EPISODES,
    EXPECTED_ROWS_SHA256,
    canonical_line,
    load_frozen_state_validity_frontier_development_v02,
    reconstruct_actions,
)


EVIDENCE_DIR = (
    ROOT / "evidence" / "state-validity-frontier-development-v0.2"
)
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
RESULTS_PATH = EVIDENCE_DIR / "results.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"
SOURCE_VERIFICATION_PATH = EVIDENCE_DIR / "source-verification.json"
COVERAGE_RESULTS_PATH = (
    ROOT / "evidence" / "coverage-repair-confirmatory-v0.1" / "results.json"
)

WITHDRAWAL_DEAD_END = (
    "Withdrawal recovery has no unattempted active-supplier quote evidence "
    "left; replacement evidence was not obtained"
)


def _close(actual: Any, expected: Any, path: str) -> None:
    if isinstance(expected, float):
        if not math.isclose(
            float(actual), expected, rel_tol=1e-12, abs_tol=1e-9
        ):
            raise ValueError(
                f"Numeric drift at {path}: expected={expected}, actual={actual}"
            )
        return
    if actual != expected:
        raise ValueError(
            f"Evidence drift at {path}: expected={expected!r}, actual={actual!r}"
        )


def _check_provenance(
    records: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    payload = PROVENANCE_PATH.read_bytes()
    _close(len(payload), manifest["provenance"]["bytes"], "provenance.bytes")
    _close(
        sha256(payload).hexdigest(),
        manifest["provenance"]["sha256"],
        "provenance.sha256",
    )

    entries = {}
    for line in payload.decode("utf-8").splitlines():
        fields = line.split("|")
        if len(fields) != 6:
            raise ValueError("Malformed SVF development provenance row")
        episode_id, repeat, member, raw_bytes, raw_sha, compact_sha = fields
        key = (episode_id, int(repeat))
        if key in entries:
            raise ValueError("Duplicate SVF development provenance key")
        entries[key] = {
            "member": member,
            "raw_bytes": int(raw_bytes),
            "raw_sha": raw_sha,
            "compact_sha": compact_sha,
        }

    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in (1, 2, 3)
    }
    if set(entries) != expected:
        raise ValueError("SVF development provenance grid drift")

    for record in records:
        key = (record["episode_id"], record["repeat"])
        digest = sha256(canonical_line(record)).hexdigest()
        _close(
            digest,
            entries[key]["compact_sha"],
            f"provenance.{key}.compact_sha",
        )


def _check_source_verification_receipt(
    manifest: dict[str, Any],
) -> None:
    meta = manifest.get("source_verification") or {}
    payload = SOURCE_VERIFICATION_PATH.read_bytes()
    _close(len(payload), meta.get("bytes"), "source_verification.bytes")
    _close(
        sha256(payload).hexdigest(),
        meta.get("sha256"),
        "source_verification.sha256",
    )
    receipt = json.loads(payload)
    _close(receipt.get("result"), "verified", "source_verification.result")
    _close(
        receipt.get("source_workflow_run_id"),
        manifest["source_workflow_run_id"],
        "source_verification.workflow_run",
    )
    _close(
        receipt.get("source_artifact_id"),
        manifest["source_artifact_id"],
        "source_verification.artifact_id",
    )
    _close(
        receipt.get("source_artifact_name"),
        manifest["source_artifact_name"],
        "source_verification.artifact_name",
    )
    _close(
        receipt.get("source_artifact_bytes"),
        manifest["source_artifact_bytes"],
        "source_verification.artifact_bytes",
    )
    _close(
        receipt.get("source_artifact_sha256"),
        manifest["source_artifact_digest"].removeprefix("sha256:"),
        "source_verification.artifact_sha256",
    )
    _close(
        receipt.get("source_artifact_expires_at"),
        manifest["source_artifact_expires_at"],
        "source_verification.artifact_expiry",
    )

    source_members_payload = (
        json.dumps(
            manifest["source_members"],
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    _close(
        receipt.get("source_members_count"),
        len(manifest["source_members"]),
        "source_verification.source_members_count",
    )
    _close(
        receipt.get("source_members_sha256"),
        sha256(source_members_payload).hexdigest(),
        "source_verification.source_members_sha256",
    )
    _close(
        receipt.get("provenance_sha256"),
        sha256(PROVENANCE_PATH.read_bytes()).hexdigest(),
        "source_verification.provenance_sha256",
    )
    _close(
        receipt.get("committed_compact_rows_sha256"),
        EXPECTED_ROWS_SHA256,
        "source_verification.compact_rows_sha256",
    )
    _close(
        receipt.get("verifier"),
        manifest.get("source_verifier"),
        "source_verification.verifier",
    )


def _replay_and_evaluate(
    record: dict[str, Any],
    evaluator: LongProcureBenchEvaluator,
) -> dict[str, Any]:
    episode_id = record["episode_id"]
    env = LongProcureBenchEnv(repo_root=ROOT)
    env.reset(episode_id)
    for frozen in record["trajectory"]:
        state = env.step(deepcopy(frozen["action"]))
        _close(
            state["step"],
            frozen["step"],
            f"{record['run_id']}.trajectory.step",
        )
        _close(
            state["observations"],
            frozen["observations"],
            f"{record['run_id']}.step_{frozen['step']}.observations",
        )
    return evaluator.evaluate_actions(
        episode_id,
        reconstruct_actions(record),
    )


def _first_observation_step(record: dict[str, Any], event_type: str):
    for row in record["trajectory"]:
        if any(
            obs.get("type") == event_type
            for obs in row.get("observations") or []
        ):
            return int(row["step"])
    return None


def _first_action_step(record: dict[str, Any], action_type: str):
    for row in record["trajectory"]:
        if row["action"]["type"] == action_type:
            return int(row["step"])
    return None


def _comparison(
    treatment: dict[str, Any],
    base: dict[str, Any],
) -> dict[str, float]:
    return {
        "terminal_pp": 100 * (
            treatment["terminal"] - base["terminal"]
        ) / 60,
        "feasible_obligation_pp": 100 * (
            treatment["feasible"] - base["feasible"]
        ) / 60,
        "strict_pp": 100 * (
            treatment["strict"] - base["strict"]
        ) / 60,
        "economic_pp": 100 * (
            treatment["economic"] - base["economic"]
        ) / 60,
        "accepted_actions_pct": 100 * (
            treatment["actions"] / base["actions"] - 1
        ),
        "model_calls_pct": 100 * (
            treatment["calls"] / base["calls"] - 1
        ),
        "tokens_pct": 100 * (
            treatment["tokens"] / base["tokens"] - 1
        ),
        "latency_pct": 100 * (
            treatment["latency"] / base["latency"] - 1
        ),
        "cost_pct": 100 * (
            treatment["cost"] / base["cost"] - 1
        ),
    }


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    frozen = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    records = load_frozen_state_validity_frontier_development_v02(ROOT)
    _check_provenance(records, manifest)
    _check_source_verification_receipt(manifest)

    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    evaluated = {}
    for record in records:
        key = (record["episode_id"], record["repeat"])
        evaluated[key] = _replay_and_evaluate(record, evaluator)

    terminal = feasible = strict = economic = 0
    actionable = resolved = unresolved = 0
    actions = calls = tokens = deterministic = llm = interventions = 0
    invalidations = req_invalid = quote_invalid = withdrawal_invalid = 0
    latency = cost = 0.0
    completed = policy_errors = 0
    frontier_sizes = Counter()
    errors = Counter()
    by_episode = defaultdict(list)

    for record in records:
        key = (record["episode_id"], record["repeat"])
        evaluation = evaluated[key]
        metrics = record["policy_metrics"]
        by_episode[record["episode_id"]].append((record, evaluation))

        terminal += int(evaluation["terminal_outcome"]["correct"])
        feasible += int(evaluation["feasible_obligation_success"])
        strict += int(evaluation["episode_success_v02"])
        economic += int(evaluation["economic_objective"]["satisfied"])
        actionable += int(evaluation["obligations"]["actionable"])
        resolved += int(evaluation["obligations"]["resolved"])
        unresolved += int(evaluation["obligations"]["unresolved"])
        actions += len(record["trajectory"])
        calls += int(metrics["model_calls_attempted"])
        tokens += int(metrics["total_tokens"])
        latency += float(metrics["latency_ms"])
        cost += float(metrics["cost_usd"])
        deterministic += int(metrics["deterministic_frontier_actions"])
        llm += int(metrics["llm_frontier_calls"])
        interventions += int(metrics["validity_frontier_interventions"])
        invalidations += int(metrics["validity_invalidations"])
        req_invalid += int(metrics["requirement_invalidations"])
        quote_invalid += int(metrics["quote_invalidations"])
        withdrawal_invalid += int(metrics["withdrawal_invalidations"])
        for trace in metrics.get("frontier_trace") or []:
            frontier_sizes[len(trace.get("frontier") or [])] += 1

        if record["status"] == "completed":
            completed += 1
        elif record["status"] == "policy_error":
            policy_errors += 1
            error = record["error"]
            errors[(error["type"], error["message"])] += 1

    aggregate = {
        "runs": 60,
        "completed": completed,
        "policy_error": policy_errors,
        "terminal_feasible": [terminal, 60],
        "feasible_obligation_success": [feasible, 60],
        "strict_v02": [strict, 60],
        "economic_objective": [economic, 60],
        "actionable_obligations": actionable,
        "resolved_obligations": resolved,
        "unresolved_obligations": unresolved,
        "accepted_actions": actions,
        "model_calls": calls,
        "total_tokens": tokens,
        "latency_ms": latency,
        "known_cost_usd": cost,
        "deterministic_frontier_actions": deterministic,
        "llm_frontier_calls": llm,
        "validity_frontier_interventions": interventions,
        "validity_invalidations": invalidations,
        "requirement_invalidations": req_invalid,
        "quote_invalidations": quote_invalid,
        "withdrawal_invalidations": withdrawal_invalid,
        "frontier_size_counts": {
            str(key): frontier_sizes[key]
            for key in sorted(frontier_sizes)
        },
    }
    for key, value in aggregate.items():
        _close(value, frozen["aggregate"][key], f"aggregate.{key}")

    per_episode = {}
    for episode_id in EPISODES:
        rows = by_episode[episode_id]
        per_episode[episode_id] = {
            "completed": sum(r["status"] == "completed" for r, _ in rows),
            "policy_error": sum(r["status"] == "policy_error" for r, _ in rows),
            "terminal_feasible": [
                sum(e["terminal_outcome"]["correct"] for _, e in rows), 3
            ],
            "feasible_obligation_success": [
                sum(e["feasible_obligation_success"] for _, e in rows), 3
            ],
            "strict_v02": [
                sum(e["episode_success_v02"] for _, e in rows), 3
            ],
            "economic_objective": [
                sum(e["economic_objective"]["satisfied"] for _, e in rows), 3
            ],
            "unresolved_obligations": sum(
                int(e["obligations"]["unresolved"]) for _, e in rows
            ),
            "accepted_actions": sum(len(r["trajectory"]) for r, _ in rows),
            "model_calls": sum(
                int(r["policy_metrics"]["model_calls_attempted"])
                for r, _ in rows
            ),
            "total_tokens": sum(
                int(r["policy_metrics"]["total_tokens"]) for r, _ in rows
            ),
            "known_cost_usd": sum(
                float(r["policy_metrics"]["cost_usd"]) for r, _ in rows
            ),
        }
    _close(per_episode, frozen["per_episode"], "per_episode")

    sequence_checks = []
    for repeat in (1, 2, 3):
        record = next(
            row for row in records
            if row["episode_id"] == "electrical-dla-transformer-013"
            and row["repeat"] == repeat
        )
        response = _first_observation_step(record, "buyer_clarification")
        first_rfq = _first_action_step(record, "send_rfq")
        sequence_checks.append({
            "repeat": repeat,
            "response_step": response,
            "first_rfq_step": first_rfq,
            "pass": (
                response is not None
                and first_rfq is not None
                and first_rfq > response
            ),
        })
    sequence = {
        "episode_id": "electrical-dla-transformer-013",
        "checks": sequence_checks,
        "pass": all(row["pass"] for row in sequence_checks),
    }
    _close(
        sequence,
        frozen["prerequisite_sequence_gate"],
        "prerequisite_sequence_gate",
    )

    expected_errors = {
        ("StateValidityFrontierError", WITHDRAWAL_DEAD_END): 9,
    }
    _close(errors, expected_errors, "execution_failures.error_fingerprints")
    episodes_with_policy_error = Counter(
        record["episode_id"]
        for record in records
        if record["status"] == "policy_error"
    )
    _close(
        dict(sorted(episodes_with_policy_error.items())),
        frozen["execution_failures"]["policy_errors_by_episode"],
        "execution_failures.policy_errors_by_episode",
    )

    baseline_results = json.loads(
        COVERAGE_RESULTS_PATH.read_text(encoding="utf-8")
    )["rows"]
    anchors = {}
    for output_name, source_name in (
        ("context", "factual_context"),
        ("react", "react"),
        ("coverage_repair", "coverage_repair"),
    ):
        row = baseline_results[source_name]
        anchors[output_name] = {
            "terminal": row["terminal_feasible"][0],
            "feasible": row["feasible_obligation_success"][0],
            "strict": row["strict_v02"][0],
            "economic": row["economic_objective"][0],
            "actions": row["accepted_actions"],
            "calls": row["model_calls"],
            "tokens": row["total_tokens"],
            "latency": row["latency_ms"],
            "cost": row["known_cost_usd"],
        }

    treatment = {
        "terminal": terminal,
        "feasible": feasible,
        "strict": strict,
        "economic": economic,
        "actions": actions,
        "calls": calls,
        "tokens": tokens,
        "latency": latency,
        "cost": cost,
    }
    comparisons = {
        name: _comparison(treatment, baseline)
        for name, baseline in anchors.items()
    }
    for name, value in comparisons.items():
        _close(
            value,
            frozen["comparisons"][name],
            f"comparisons.{name}",
        )

    quality = {
        "feasible_ge_47": feasible >= 47,
        "strict_ge_30": strict >= 30,
        "economic_ge_30": economic >= 30,
    }
    coverage = anchors["coverage_repair"]
    react = anchors["react"]
    quality_branch = (
        (strict - coverage["strict"] >= 3)
        or (economic - coverage["economic"] >= 3)
    ) and cost <= react["cost"]
    efficiency_branch = (
        feasible >= coverage["feasible"] - 3
        and strict >= coverage["strict"] - 3
        and economic >= coverage["economic"] - 3
        and cost <= coverage["cost"] * 0.8
    )
    gates = {
        "execution_clean": policy_errors == 0,
        "prerequisite_sequence_pass": sequence["pass"],
        "quality_requirements": quality,
        "quality_branch": quality_branch,
        "efficiency_branch": efficiency_branch,
        "overall_development_gate": (
            policy_errors == 0
            and sequence["pass"]
            and all(quality.values())
            and (quality_branch or efficiency_branch)
        ),
    }
    _close(gates, frozen["gates"], "gates")

    if gates["overall_development_gate"]:
        raise ValueError(
            "Frozen SVF development verdict drift: gate must remain false"
        )

    print("SVF development v0.2 evidence audit passed.")
    print(
        "negative result: terminal=39/60 feasible=38/60 strict=23/60 "
        "economic=24/60 policy_error=9 cost=$2.7651588"
    )
    print(
        "No ablation or new held-out evaluation is authorized by v0.2."
    )


if __name__ == "__main__":
    main()
