"""Audit frozen Plan-and-Execute targeted development evidence."""
from __future__ import annotations

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
from frozen_plan_execute_targeted_v01 import (
    EPISODES,
    _canonical_line,
    load_frozen_plan_execute_targeted_source,
    reconstruct_actions,
)


EVIDENCE_DIR = ROOT / "evidence" / "plan-execute-targeted-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
RESULTS_PATH = EVIDENCE_DIR / "results.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"


def _close(actual: Any, expected: Any, path: str) -> None:
    if isinstance(expected, float):
        if not math.isclose(
            float(actual),
            expected,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Numeric drift at {path}: expected={expected}, actual={actual}"
            )
        return
    if actual != expected:
        raise ValueError(
            f"Evidence drift at {path}: "
            f"expected={expected!r}, actual={actual!r}"
        )


def _trajectory_rle(record: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for row in record["trajectory"]:
        action_type = row["action"]["type"]
        step = int(row["step"])
        if groups and groups[-1]["type"] == action_type:
            groups[-1]["end"] = step
            groups[-1]["count"] += 1
        else:
            groups.append({
                "start": step,
                "end": step,
                "type": action_type,
                "count": 1,
            })
    return [
        {
            "steps": (
                str(group["start"])
                if group["start"] == group["end"]
                else f"{group['start']}-{group['end']}"
            ),
            "type": group["type"],
            "count": group["count"],
        }
        for group in groups
    ]


def _observation_labels(
    record: dict[str, Any],
    step: int,
) -> set[str]:
    row = record["trajectory"][step - 1]
    return {
        f"{obs.get('type')}:{obs.get('event_id')}"
        for obs in row.get("observations") or []
        if isinstance(obs, dict)
    }


def _obligation_resolved(
    evaluation: dict[str, Any],
    checkpoint: str,
) -> bool:
    return any(
        row.get("checkpoint") == checkpoint
        and row.get("status") == "resolved"
        for row in evaluation["obligations"]["results"]
    )


def _replay_and_check_trajectory(
    record: dict[str, Any],
) -> None:
    """Require the current runtime to reproduce the frozen trace exactly."""
    episode_id = record["episode_id"]
    env = LongProcureBenchEnv(repo_root=ROOT)
    state = env.reset(episode_id)

    for frozen_row in record["trajectory"]:
        action = deepcopy(frozen_row["action"])
        state = env.step(action)

        _close(
            state["step"],
            frozen_row["step"],
            f"{episode_id}.trajectory.step",
        )
        _close(
            state["observations"],
            frozen_row["observations"],
            f"{episode_id}.trajectory.step_{frozen_row['step']}.observations",
        )

    if len(state["action_history"]) != len(record["trajectory"]):
        raise ValueError(
            f"Replay action-history length drift for {episode_id}"
        )


def _check_manifest(manifest: dict[str, Any]) -> None:
    expected = {
        "schema_version": "0.1.0",
        "experiment": "plan-execute-targeted-v0.1",
        "source_workflow_run_id": 36396684099,
        "source_workflow_run_attempt": 1,
        "source_artifact_id": 10957769763,
        "source_artifact_bytes": 18258,
        "source_artifact_digest": (
            "sha256:"
            "b5588478661f9ccc30ceeac563cdef2dc4b6fd48eb6515603b0117c7d935925f"
        ),
        "benchmark_code_sha": "5257769482b79ff3c8c717715b96d2e116552ac1",
        "execution_commit": "135ff49e61c557da6efc7dc5b36e57fbbc8e64a6",
        "model": "openai/gpt-5.6-sol",
        "reasoning_effort": "medium",
        "temperature": None,
        "records": 3,
        "episodes": EPISODES,
        "repeats_per_episode": 1,
        "max_actions": 50,
    }
    for key, value in expected.items():
        _close(manifest.get(key), value, f"manifest.{key}")

    provenance = manifest.get("provenance") or {}
    payload = PROVENANCE_PATH.read_bytes()
    _close(len(payload), provenance.get("bytes"), "provenance.bytes")
    _close(
        sha256(payload).hexdigest(),
        provenance.get("sha256"),
        "provenance.sha256",
    )


def _check_provenance(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
) -> None:
    lines = PROVENANCE_PATH.read_text(encoding="utf-8").splitlines()
    if len(lines) != 3:
        raise ValueError("Plan-and-Execute provenance must contain 3 rows")

    entries: dict[str, dict[str, Any]] = {}
    raw_lines = []
    for line in lines:
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError("Malformed Plan-and-Execute provenance row")
        episode_id, member, raw_bytes, raw_sha, compact_sha = fields
        if episode_id not in EPISODES or episode_id in entries:
            raise ValueError("Invalid or duplicate provenance episode")
        if len(raw_sha) != 64 or len(compact_sha) != 64:
            raise ValueError("Invalid provenance digest length")
        int(raw_sha, 16)
        int(compact_sha, 16)
        entries[episode_id] = {
            "member": member,
            "raw_bytes": int(raw_bytes),
            "raw_sha256": raw_sha,
            "compact_sha256": compact_sha,
        }
        raw_lines.append(
            f"{episode_id}|{member}|{raw_bytes}|{raw_sha}\n"
        )

    if set(entries) != set(EPISODES):
        raise ValueError("Plan-and-Execute provenance episode set drift")

    manifest_members = {
        row["path"]: row
        for row in manifest.get("source_members") or []
    }
    for record in records:
        episode_id = record["episode_id"]
        entry = entries[episode_id]
        member_meta = manifest_members.get(entry["member"])
        if member_meta is None:
            raise ValueError("Run provenance member missing from manifest")
        _close(
            member_meta["bytes"],
            entry["raw_bytes"],
            f"manifest.source_members.{episode_id}.bytes",
        )
        _close(
            member_meta["sha256"],
            entry["raw_sha256"],
            f"manifest.source_members.{episode_id}.sha256",
        )
        compact_sha = sha256(_canonical_line(record)).hexdigest()
        _close(
            compact_sha,
            entry["compact_sha256"],
            f"compact_record.{episode_id}.sha256",
        )

    raw_root = sha256("".join(raw_lines).encode("utf-8")).hexdigest()
    _close(
        raw_root,
        manifest["provenance"]["raw_provenance_sha256"],
        "manifest.provenance.raw_provenance_sha256",
    )


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    records = load_frozen_plan_execute_targeted_source(ROOT)

    _check_manifest(manifest)
    _check_provenance(manifest, records)

    source = results["source"]
    source_mapping = {
        "workflow_run_id": manifest["source_workflow_run_id"],
        "artifact_id": manifest["source_artifact_id"],
        "artifact_name": manifest["source_artifact_name"],
        "artifact_digest": manifest["source_artifact_digest"],
        "artifact_expires_at": manifest["source_artifact_expires_at"],
        "benchmark_code_sha": manifest["benchmark_code_sha"],
        "execution_commit": manifest["execution_commit"],
        "model": manifest["model"],
        "reasoning_effort": manifest["reasoning_effort"],
        "temperature": manifest["temperature"],
        "repeats": 1,
        "max_actions": manifest["max_actions"],
        "episodes": EPISODES,
    }
    for key, value in source_mapping.items():
        _close(source.get(key), value, f"results.source.{key}")

    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    evaluations: dict[str, dict[str, Any]] = {}
    by_episode = {record["episode_id"]: record for record in records}
    for episode_id in EPISODES:
        record = by_episode[episode_id]
        _replay_and_check_trajectory(record)
        evaluations[episode_id] = evaluator.evaluate_actions(
            episode_id,
            reconstruct_actions(record),
        )

    expected_runs = {
        row["episode_id"]: row
        for row in results["runs"]
    }
    if set(expected_runs) != set(EPISODES):
        raise ValueError("results.runs episode set drift")

    aggregate = {
        "runs": 0,
        "completed": 0,
        "max_actions": 0,
        "terminal_feasible": 0,
        "feasible_obligation_success": 0,
        "strict_v02": 0,
        "economic_objective": 0,
        "accepted_actions": 0,
        "planner_calls": 0,
        "executor_calls": 0,
        "model_calls": 0,
        "total_tokens": 0,
        "latency_ms": 0.0,
        "known_cost_usd": 0.0,
        "unplanned_exceptions": 0,
    }

    for episode_id in EPISODES:
        record = by_episode[episode_id]
        evaluation = evaluations[episode_id]
        expected = expected_runs[episode_id]
        metrics = record["policy_metrics"]

        terminal = bool(evaluation["terminal_outcome"]["correct"])
        obligation = bool(evaluation["feasible_obligation_success"])
        strict = bool(evaluation["episode_success_v02"])
        economic = bool(evaluation["economic_objective"]["satisfied"])

        _close(record["status"], expected["status"], f"{episode_id}.status")
        actual_outcomes = {
            "terminal_feasible": terminal,
            "feasible_obligation_success": obligation,
            "strict_v02": strict,
            "economic_objective": economic,
        }
        _close(
            actual_outcomes,
            expected["outcomes"],
            f"{episode_id}.outcomes",
        )

        actual_efficiency = {
            "accepted_actions": len(record["trajectory"]),
            "planner_calls": metrics["planner_calls"],
            "executor_calls": metrics["executor_calls"],
            "model_calls": metrics["model_calls_attempted"],
            "total_tokens": metrics["total_tokens"],
            "latency_ms": metrics["latency_ms"],
            "cost_usd": metrics["cost_usd"],
            "unplanned_exceptions": metrics["unplanned_exceptions"],
        }
        for key, value in actual_efficiency.items():
            _close(
                value,
                expected["efficiency"][key],
                f"{episode_id}.efficiency.{key}",
            )

        actual_rle = _trajectory_rle(record)
        expected_rle = [
            {
                "steps": row["steps"],
                "type": row["type"],
                "count": row["count"],
            }
            for row in expected["trajectory_rle"]
        ]
        _close(actual_rle, expected_rle, f"{episode_id}.trajectory_rle")
        for row in expected["trajectory_rle"]:
            for key, value in row.items():
                if not key.startswith("observed_at_step_"):
                    continue
                step = int(key.rsplit("_", 1)[1])
                if value not in _observation_labels(record, step):
                    raise ValueError(
                        f"Missing frozen observation annotation "
                        f"{episode_id} step {step}: {value}"
                    )

        if "target_event" in expected:
            reached = any(
                obs.get("type") == expected["target_event"]
                for step in record["trajectory"]
                for obs in step.get("observations") or []
                if isinstance(obs, dict)
            )
            _close(
                reached,
                expected["reached_target_event"],
                f"{episode_id}.reached_target_event",
            )

        if "prerequisite_obligation_resolved" in expected:
            _close(
                _obligation_resolved(
                    evaluation,
                    "resolve_requirement_gap",
                ),
                expected["prerequisite_obligation_resolved"],
                f"{episode_id}.prerequisite_obligation_resolved",
            )
        if "amendment_obligation_resolved" in expected:
            _close(
                _obligation_resolved(
                    evaluation,
                    "handle_amendment",
                ),
                expected["amendment_obligation_resolved"],
                f"{episode_id}.amendment_obligation_resolved",
            )

        aggregate["runs"] += 1
        aggregate["completed"] += int(record["status"] == "completed")
        aggregate["max_actions"] += int(record["status"] == "max_actions")
        aggregate["terminal_feasible"] += int(terminal)
        aggregate["feasible_obligation_success"] += int(obligation)
        aggregate["strict_v02"] += int(strict)
        aggregate["economic_objective"] += int(economic)
        aggregate["accepted_actions"] += len(record["trajectory"])
        aggregate["planner_calls"] += int(metrics["planner_calls"])
        aggregate["executor_calls"] += int(metrics["executor_calls"])
        aggregate["model_calls"] += int(metrics["model_calls_attempted"])
        aggregate["total_tokens"] += int(metrics["total_tokens"])
        aggregate["latency_ms"] += float(metrics["latency_ms"])
        aggregate["known_cost_usd"] += float(metrics["cost_usd"])
        aggregate["unplanned_exceptions"] += int(
            metrics["unplanned_exceptions"]
        )

    frozen_aggregate = results["aggregate"]
    derived = {
        **aggregate,
        "terminal_feasible": [
            aggregate["terminal_feasible"],
            aggregate["runs"],
        ],
        "feasible_obligation_success": [
            aggregate["feasible_obligation_success"],
            aggregate["runs"],
        ],
        "strict_v02": [
            aggregate["strict_v02"],
            aggregate["runs"],
        ],
        "economic_objective": [
            aggregate["economic_objective"],
            aggregate["runs"],
        ],
    }
    for key, value in derived.items():
        _close(
            value,
            frozen_aggregate[key],
            f"results.aggregate.{key}",
        )

    print("Plan-and-Execute targeted evidence audit passed.")
    print(
        "runs={runs} terminal={terminal_feasible[0]}/{terminal_feasible[1]} "
        "strict={strict_v02[0]}/{strict_v02[1]} "
        "economic={economic_objective[0]}/{economic_objective[1]} "
        "tokens={total_tokens} cost={known_cost_usd:.6f}".format(
            **derived
        )
    )


if __name__ == "__main__":
    main()
