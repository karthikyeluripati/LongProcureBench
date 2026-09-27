"""Audit frozen Coverage + Repair confirmatory evidence."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
from frozen_coverage_repair_v01 import (
    EPISODES,
    EXPECTED_COMPACT_ROWS_BYTES,
    EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256,
    EXPECTED_RUNS,
    MODEL,
    load_frozen_coverage_repair_source,
    reconstruct_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "coverage-repair-confirmatory-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
RESULTS_PATH = EVIDENCE_DIR / "results.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"

EXPECTED_PROVENANCE_BYTES = 12606
EXPECTED_PROVENANCE_SHA256 = (
    "016fd2f237854356d34f85fae65096b28273c27301c52909f51d8470abd7d122"
)


def _close(actual: Any, expected: Any, path: str) -> None:
    if isinstance(expected, float):
        if not math.isclose(
            float(actual),
            expected,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Coverage+Repair numeric drift at {path}: "
                f"expected={expected}, actual={actual}"
            )
        return
    if actual != expected:
        raise ValueError(
            f"Coverage+Repair drift at {path}: "
            f"expected={expected!r}, actual={actual!r}"
        )


def check_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        "source_workflow_run_id": 36345529581,
        "source_artifact_id": 10941001111,
        "source_artifact_name": "coverage-repair-20x3-36345529581-1",
        "source_artifact_digest": (
            "sha256:c8a0c85e6ec00af8199d0085a9bcbc64ea46826d92d0a20a0df00aad485474a5"
        ),
        "protocol_commit": "005c526416eb18789a2431d347c1cc3f635f035d",
        "execution_commit": "e2bdf265bd284cfbebab5eddf16629acd1a0a885",
        "model": MODEL,
        "records": EXPECTED_RUNS,
        "episodes": 20,
        "repeats_per_episode": 3,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(
                f"Coverage+Repair manifest mismatch for {key}"
            )

    expected_episode_index = {
        str(index): episode_id
        for index, episode_id in enumerate(EPISODES, start=1)
    }
    if manifest.get("episode_index") != expected_episode_index:
        raise ValueError("Coverage+Repair manifest episode index mismatch")

    storage = manifest.get("storage") or {}
    expected_storage = {
        "path": "replay-source.b64",
        "compressed_bytes": EXPECTED_COMPRESSED_BYTES,
        "compressed_sha256": EXPECTED_COMPRESSED_SHA256,
        "compact_rows_bytes": EXPECTED_COMPACT_ROWS_BYTES,
    }
    for key, value in expected_storage.items():
        if storage.get(key) != value:
            raise ValueError(
                f"Coverage+Repair replay storage mismatch for {key}"
            )

    provenance = PROVENANCE_PATH.read_bytes()
    if len(provenance) != EXPECTED_PROVENANCE_BYTES:
        raise ValueError("Coverage+Repair provenance size mismatch")
    if sha256(provenance).hexdigest() != EXPECTED_PROVENANCE_SHA256:
        raise ValueError("Coverage+Repair provenance digest mismatch")

    source_verification = manifest.get("source_verification") or {}
    if source_verification.get("record_provenance_path") != "source-provenance.txt":
        raise ValueError("Coverage+Repair provenance path mismatch")
    if source_verification.get("record_provenance_bytes") != EXPECTED_PROVENANCE_BYTES:
        raise ValueError("Coverae+Repair manifest provenance size mismatch")
    if (
        source_verification.get("record_provenance_sha256")
        != EXPECTED_PROVENANCE_SHA256
    ):
        raise ValueError("Coverage+Repair manifest provenance digest mismatch")


def build_summary() -> dict[str, Any]:
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    records = load_frozen_coverage_repair_source(ROOT)

    actions = Counter()
    unresolved = Counter()
    status_counts = Counter()
    terminal = obligation_success = strict = economic = 0
    actionable = resolved = unresolved_total = 0
    accepted = calls = prompt = completion = total_tokens = 0
    latency = cost = 0.0
    interventions = forced_rfqs = forced_followups = forced_answers = 0

    for record in records:
        evaluation = evaluator.evaluate_actions(
            record["episode_id"],
            reconstruct_actions(record),
        )
        obligations = evaluation["obligations"]
        metrics = record["policy_metrics"]

        status_counts[record["status"]] += 1
        terminal += int(evaluation["terminal_outcome"]["correct"])
        obligation_success += int(evaluation["feasible_obligation_success"])
        strict += int(evaluation["episode_success_v02"])
        economic += int(evaluation["economic_objective"]["satisfied"])
        actionable += int(obligations["actionable"])
        resolved += int(obligations["resolved"])
        unresolved_total += int(obligations["unresolved"])

        accepted += len(record["decisions"])
        for decision in record["decisions"]:
            actions[decision["type"]] += 1

        for row in obligations.get("results") or []:
            if row.get("status") == "unresolved" and row.get("checkpoint"):
                unresolved[row["checkpoint"]] += 1

        calls += int(metrics["model_calls_attempted"])
        prompt += int(metrics["prompt_tokens"])
        completion += int(metrics["completion_tokens"])
        total_tokens += int(metrics["total_tokens"])
        latency += float(metrics["latency_ms"])
        cost += float(metrics["cost_usd"])
        interventions += int(metrics["coverage_repair_interventions"])
        forced_rfqs += int(metrics["coverage_forced_rfqs"])
        forced_followups += int(metrics["coverage_forced_followups"])
        forced_answers += int(metrics["coverage_forced_answers"])

    return {
        "runs": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "terminal_feasible": terminal,
        "feasible_obligation_success": obligation_success,
        "episode_success_v02": strict,
        "economic_objective_satisfied": economic,
        "actionable_obligations": actionable,
        "resolved_obligations": resolved,
        "unresolved_obligations": unresolved_total,
        "unresolved_obligation_counts": dict(sorted(unresolved.items())),
        "accepted_actions": accepted,
        "action_type_counts": dict(sorted(actions.items())),
        "model_calls": calls,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total_tokens,
        "latency_ms": latency,
        "cost_usd": cost,
        "coverage_repair_interventions": interventions,
        "coverage_forced_rfqs": forced_rfqs,
        "coverage_forced_followups": forced_followups,
        "coverage_forced_answers": forced_answers,
    }


def check_results(summary: dict[str, Any]) -> None:
    frozen = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    row = frozen["rows"]["coverage_repair"]
    diagnostics = frozen["coverage_repair_diagnostics"]
    obligations = frozen["unresolved_obligations"]["coverage_repair"]

    expected_pairs = {
        "terminal_feasible": row["terminal_feasible"][0],
        "feasible_obligation_success": row["feasible_obligation_success"][0],
        "episode_success_v02": row["strict_v02"][0],
        "economic_objective_satisfied": row["economic_objective"][0],
        "accepted_actions": row["accepted_actions"],
        "model_calls": row["model_calls"],
        "total_tokens": row["total_tokens"],
        "latency_ms": row["latency_ms"],
        "cost_usd": row["known_cost_usd"],
        "coverage_repair_interventions": diagnostics["interventions"],
        "coverage_forced_rfqs": diagnostics["forced_rfqs"],
        "coverage_forced_followups": diagnostics["forced_followups"],
        "coverage_forced_answers": diagnostics["forced_answers"],
        "actionable_obligations": obligations["actionable"],
        "resolved_obligations": obligations["resolved"],
        "unresolved_obligations": obligations["unresolved"],
        "unresolved_obligation_counts": obligations["by_class"],
    }
    for key, expected in expected_pairs.items():
        _close(summary[key], expected, key)

    if summary["runs"] != 60 or summary["status_counts"] != {"completed": 60}:
        raise ValueError("Coverage+Repair frozen source completion grid mismatch")


def main() -> None:
    check_manifest()
    summary = build_summary()
    check_results(summary)
    print("Coverage+Repair confirmatory audit passed.")
    print(
        "terminal={}/60 obligation_success={}/60 strict={}/60 "
        "economic={}/60 calls={} tokens={} cost=${:.6f}".format(
            summary["terminal_feasible"],
            summary["feasible_obligation_success"],
            summary["episode_success_v02"],
            summary["economic_objective_satisfied"],
            summary["model_calls"],
            summary["total_tokens"],
            summary["cost_usd"],
        )
    )


if __name__ == "__main__":
    main()
