"""Audit frozen State Validity Frontier Stage-1 evidence."""
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
from frozen_state_validity_frontier_stage1_v01 import (
    EPISODES,
    EXPECTED_ROWS_SHA256,
    canonical_line,
    load_frozen_state_validity_frontier_stage1,
    reconstruct_actions,
)


EVIDENCE_DIR = ROOT / "evidence" / "state-validity-frontier-stage1-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
RESULTS_PATH = EVIDENCE_DIR / "results.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"
SOURCE_VERIFICATION_PATH = EVIDENCE_DIR / "source-verification.json"


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
            f"{episode_id}.trajectory.step",
        )
        _close(
            state["observations"],
            frozen["observations"],
            f"{episode_id}.trajectory.step_{frozen['step']}.observations",
        )

    return evaluator.evaluate_actions(
        episode_id,
        reconstruct_actions(record),
    )


def _action_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    return record["trajectory"]


def _first_step(
    record: dict[str, Any],
    *,
    action_type: str | None = None,
    observation_type: str | None = None,
    observation_id: str | None = None,
) -> int | None:
    for row in _action_rows(record):
        if action_type is not None and row["action"]["type"] == action_type:
            return int(row["step"])
        if observation_type is not None and any(
            obs.get("type") == observation_type
            for obs in row.get("observations") or []
        ):
            return int(row["step"])
        if observation_id is not None and any(
            obs.get("event_id") == observation_id
            for obs in row.get("observations") or []
        ):
            return int(row["step"])
    return None


def _terminal_step(record: dict[str, Any]) -> int | None:
    for row in _action_rows(record):
        if row["action"]["type"] in {"award_supplier", "no_award"}:
            return int(row["step"])
    return None


def _frontier_after_state_step(
    record: dict[str, Any],
    state_step: int,
) -> list[dict[str, Any]]:
    trace = (record["policy_metrics"].get("frontier_trace") or [])
    rows = [
        row
        for row in trace
        if row.get("proposed_state_step") is not None
        and int(row["proposed_state_step"]) >= state_step
    ]
    return rows


def _assertions_008(record: dict[str, Any]) -> dict[str, Any]:
    metrics = record["policy_metrics"]
    graph = metrics["validity_graph"]
    trajectory = _action_rows(record)

    withdrawal_step = _first_step(record, observation_id="e4")
    if withdrawal_step is None:
        raise ValueError("008 never revealed supplier withdrawal")

    post = [
        row for row in trajectory
        if int(row["step"]) > withdrawal_step
    ]
    replacement_step = next(
        (
            int(row["step"])
            for row in post
            if any(
                obs.get("type") in {"quote_received", "quote_revision"}
                and obs.get("supplier_id") != "syn-burauen-a"
                for obs in row.get("observations") or []
            )
        ),
        None,
    )
    reeval_step = next(
        (
            int(row["step"])
            for row in post
            if row["action"]["type"] == "evaluate_quotes"
            and replacement_step is not None
            and int(row["step"]) > replacement_step
        ),
        None,
    )
    terminal_step = _terminal_step(record)

    invalidation_trace = next(
        (
            row
            for row in metrics.get("frontier_trace") or []
            if "e4" in (row.get("observation_event_ids") or [])
        ),
        None,
    )

    return {
        "supplier_withdrawal_marks_supplier_inactive": (
            "syn-burauen-a" in graph["withdrawn_supplier_ids"]
            and "syn-burauen-a" not in graph["active_supplier_ids"]
        ),
        "pre_withdrawal_evaluation_becomes_invalid": (
            invalidation_trace is not None
            and invalidation_trace.get("evaluation_current_after") is False
        ),
        "withdrawn_supplier_excluded_from_later_terminal_actions": all(
            not (
                row["action"]["type"] == "award_supplier"
                and row["action"].get("supplier_id") == "syn-burauen-a"
            )
            for row in post
        ),
        "replacement_quote_then_reevaluation_before_terminal": (
            replacement_step is not None
            and reeval_step is not None
            and terminal_step is not None
            and replacement_step < reeval_step < terminal_step
        ),
        "no_post_withdrawal_clarification_without_new_requirement_epoch": all(
            row["action"]["type"] != "request_buyer_clarification"
            for row in post
        ),
    }


def _assertions_013(record: dict[str, Any]) -> dict[str, Any]:
    trajectory = _action_rows(record)
    metrics = record["policy_metrics"]

    clarification_steps = [
        int(row["step"])
        for row in trajectory
        if row["action"]["type"] == "request_buyer_clarification"
    ]
    response_step = _first_step(
        record,
        observation_type="buyer_clarification",
    )
    identify_step = _first_step(record, action_type="identify_suppliers")
    first_rfq_step = _first_step(record, action_type="send_rfq")
    evaluation_step = _first_step(record, action_type="evaluate_quotes")
    terminal_step = _terminal_step(record)

    post_response_frontiers = (
        _frontier_after_state_step(record, response_step)
        if response_step is not None
        else []
    )
    clarification_absent = (
        response_step is not None
        and all(
            "request_buyer_clarification"
            not in {item["type"] for item in row.get("frontier") or []}
            for row in post_response_frontiers
        )
    )

    sourcing_begin_step = min(
        step
        for step in (identify_step, first_rfq_step)
        if step is not None
    )

    terminal_trace = next(
        (
            row
            for row in metrics.get("frontier_trace") or []
            if row.get("chosen_action", {}).get("type")
            in {"award_supplier", "no_award"}
        ),
        None,
    )

    return {
        "at_most_one_clarification_in_requirement_epoch_0": (
            len(clarification_steps) <= 1
        ),
        "clarification_absent_from_frontier_after_buyer_response": (
            clarification_absent
        ),
        "supplier_discovery_rfq_begins_after_clarification_response": (
            response_step is not None
            and sourcing_begin_step > response_step
        ),
        "first_rfq_occurs_after_clarification_response": (
            response_step is not None
            and first_rfq_step is not None
            and first_rfq_step > response_step
        ),
        "terminal_action_only_after_current_evaluation": (
            evaluation_step is not None
            and terminal_step is not None
            and terminal_step > evaluation_step
            and terminal_trace is not None
            and terminal_trace.get("evaluation_current_before") is True
        ),
        "observed_order": {
            "identify_suppliers_step": identify_step,
            "buyer_clarification_step": response_step,
            "first_rfq_step": first_rfq_step,
        },
    }


def _assertions_016(record: dict[str, Any]) -> dict[str, Any]:
    trajectory = _action_rows(record)
    metrics = record["policy_metrics"]

    change_step = _first_step(record, observation_id="e4")
    amendment_step = _first_step(record, action_type="issue_amendment")
    terminal_step = _terminal_step(record)
    repair_steps = [
        int(row["step"])
        for row in trajectory
        if row["action"]["type"]
        in {"send_follow_up", "request_quote_revision"}
    ]
    clarification_count = sum(
        row["action"]["type"] == "request_buyer_clarification"
        for row in trajectory
    )

    # Derive the stale set from what the agent actually observed before the
    # requirement change. This prevents two revisions of one supplier from
    # masquerading as repair of two distinct stale offers.
    pre_change_offers: dict[str, dict[str, Any]] = {}
    if change_step is not None:
        for row in trajectory:
            if int(row["step"]) > change_step:
                break
            for obs in row.get("observations") or []:
                supplier_id = obs.get("supplier_id")
                if (
                    obs.get("type") in {"quote_received", "quote_revision"}
                    and isinstance(supplier_id, str)
                    and supplier_id
                ):
                    pre_change_offers[supplier_id] = {
                        "event_id": obs.get("event_id"),
                        "observed_step": int(row["step"]),
                    }

    stale_offer_repairs: dict[str, dict[str, Any]] = {}
    if amendment_step is not None:
        for supplier_id in sorted(pre_change_offers):
            request_row = next(
                (
                    row
                    for row in trajectory
                    if int(row["step"]) > amendment_step
                    and row["action"]["type"] == "request_quote_revision"
                    and row["action"].get("supplier_id") == supplier_id
                ),
                None,
            )
            replacement = None
            if request_row is not None:
                replacement = next(
                    (
                        obs
                        for obs in request_row.get("observations") or []
                        if obs.get("type")
                        in {"quote_received", "quote_revision"}
                        and obs.get("supplier_id") == supplier_id
                    ),
                    None,
                )

            stale_offer_repairs[supplier_id] = {
                "pre_change_quote_event_id": (
                    pre_change_offers[supplier_id]["event_id"]
                ),
                "revision_request_step": (
                    int(request_row["step"])
                    if request_row is not None
                    else None
                ),
                "replacement_event_id": (
                    replacement.get("event_id")
                    if replacement is not None
                    else None
                ),
                "replacement_step": (
                    int(request_row["step"])
                    if replacement is not None
                    else None
                ),
            }

    every_stale_offer_repaired = bool(pre_change_offers) and all(
        row["revision_request_step"] is not None
        and row["replacement_event_id"] is not None
        and row["replacement_step"] is not None
        for row in stale_offer_repairs.values()
    )

    return {
        "requirement_change_increments_epoch": (
            metrics["validity_graph"]["requirement_epoch"] == 1
        ),
        "amendment_required_after_change": (
            change_step is not None
            and amendment_step is not None
            and amendment_step > change_step
            and 1 in (metrics.get("amendment_required_epochs") or [])
            and 1 in (metrics.get("amended_epochs") or [])
        ),
        "pre_change_offer_suppliers": sorted(pre_change_offers),
        "stale_offer_repairs": stale_offer_repairs,
        "pre_change_offers_repaired_as_stale": every_stale_offer_repaired,
        "post_amendment_repair_before_terminal": (
            amendment_step is not None
            and terminal_step is not None
            and repair_steps
            and min(repair_steps) > amendment_step
            and max(repair_steps) < terminal_step
        ),
        "no_clarification_loop": clarification_count <= 1,
    }


def _check_provenance(
    records: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    payload = PROVENANCE_PATH.read_bytes()
    _close(
        len(payload),
        manifest["provenance"]["bytes"],
        "provenance.bytes",
    )
    _close(
        sha256(payload).hexdigest(),
        manifest["provenance"]["sha256"],
        "provenance.sha256",
    )

    entries = {}
    for line in payload.decode("utf-8").splitlines():
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError("Malformed Stage-1 provenance row")
        episode_id, member, raw_bytes, raw_sha, compact_sha = fields
        if episode_id in entries:
            raise ValueError("Duplicate Stage-1 provenance episode")
        entries[episode_id] = {
            "member": member,
            "raw_bytes": int(raw_bytes),
            "raw_sha": raw_sha,
            "compact_sha": compact_sha,
        }

    if set(entries) != set(EPISODES):
        raise ValueError("Stage-1 provenance episode set drift")

    for record in records:
        episode_id = record["episode_id"]
        digest = sha256(canonical_line(record)).hexdigest()
        _close(
            digest,
            entries[episode_id]["compact_sha"],
            f"provenance.{episode_id}.compact_sha",
        )


def _check_source_verification_receipt(
    manifest: dict[str, Any],
) -> None:
    meta = manifest.get("source_verification") or {}
    payload = SOURCE_VERIFICATION_PATH.read_bytes()
    _close(
        len(payload),
        meta.get("bytes"),
        "source_verification.bytes",
    )
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
        "source_verification.source_workflow_run_id",
    )
    _close(
        receipt.get("source_artifact_id"),
        manifest["source_artifact_id"],
        "source_verification.source_artifact_id",
    )
    _close(
        receipt.get("source_artifact_name"),
        manifest["source_artifact_name"],
        "source_verification.source_artifact_name",
    )
    _close(
        receipt.get("source_artifact_bytes"),
        manifest["source_artifact_bytes"],
        "source_verification.source_artifact_bytes",
    )
    _close(
        receipt.get("source_artifact_sha256"),
        manifest["source_artifact_digest"].removeprefix("sha256:"),
        "source_verification.source_artifact_sha256",
    )
    _close(
        receipt.get("source_artifact_expires_at"),
        manifest["source_artifact_expires_at"],
        "source_verification.source_artifact_expires_at",
    )
    _close(
        receipt.get("archive_members"),
        manifest.get("source_members"),
        "source_verification.archive_members",
    )
    _close(
        receipt.get("committed_compact_rows_sha256"),
        EXPECTED_ROWS_SHA256,
        "source_verification.committed_compact_rows_sha256",
    )
    _close(
        receipt.get("verifier"),
        manifest.get("source_verifier"),
        "source_verification.verifier",
    )

    provenance_entries = {}
    for line in PROVENANCE_PATH.read_text(encoding="utf-8").splitlines():
        episode_id, member, raw_bytes, raw_sha, compact_sha = line.split("|")
        provenance_entries[episode_id] = {
            "artifact_member": member,
            "raw_bytes": int(raw_bytes),
            "raw_sha256": raw_sha,
            "compact_record_sha256": compact_sha,
        }

    verified = {
        row["episode_id"]: {
            "artifact_member": row["artifact_member"],
            "raw_bytes": int(row["raw_bytes"]),
            "raw_sha256": row["raw_sha256"],
            "compact_record_sha256": row["compact_record_sha256"],
        }
        for row in receipt.get("verified_run_members") or []
    }
    _close(
        verified,
        provenance_entries,
        "source_verification.verified_run_members",
    )


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    frozen = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    records = load_frozen_state_validity_frontier_stage1(ROOT)
    _check_provenance(records, manifest)
    _check_source_verification_receipt(manifest)

    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    evaluations = {
        record["episode_id"]: _replay_and_evaluate(record, evaluator)
        for record in records
    }
    by_episode = {record["episode_id"]: record for record in records}

    terminal = feasible = strict = economic = 0
    actionable = resolved = unresolved = 0
    actions = calls = tokens = deterministic = llm = invalidations = 0
    req_invalid = quote_invalid = withdrawal_invalid = 0
    latency = cost = 0.0

    for episode_id in EPISODES:
        record = by_episode[episode_id]
        evaluation = evaluations[episode_id]
        metrics = record["policy_metrics"]
        expected = frozen["runs"][episode_id]

        actual = {
            "status": record["status"],
            "terminal_feasible": bool(
                evaluation["terminal_outcome"]["correct"]
            ),
            "feasible_obligation_success": bool(
                evaluation["feasible_obligation_success"]
            ),
            "strict_v02": bool(evaluation["episode_success_v02"]),
            "economic_objective": bool(
                evaluation["economic_objective"]["satisfied"]
            ),
            "actionable_obligations": int(
                evaluation["obligations"]["actionable"]
            ),
            "resolved_obligations": int(
                evaluation["obligations"]["resolved"]
            ),
            "unresolved_obligations": int(
                evaluation["obligations"]["unresolved"]
            ),
            "accepted_actions": len(record["trajectory"]),
            "model_calls": int(metrics["model_calls_attempted"]),
            "total_tokens": int(metrics["total_tokens"]),
            "latency_ms": float(metrics["latency_ms"]),
            "cost_usd": float(metrics["cost_usd"]),
            "deterministic_frontier_actions": int(
                metrics["deterministic_frontier_actions"]
            ),
            "llm_frontier_calls": int(metrics["llm_frontier_calls"]),
            "validity_invalidations": int(
                metrics["validity_invalidations"]
            ),
        }
        for key, value in actual.items():
            _close(value, expected[key], f"{episode_id}.{key}")

        terminal += int(actual["terminal_feasible"])
        feasible += int(actual["feasible_obligation_success"])
        strict += int(actual["strict_v02"])
        economic += int(actual["economic_objective"])
        actionable += actual["actionable_obligations"]
        resolved += actual["resolved_obligations"]
        unresolved += actual["unresolved_obligations"]
        actions += actual["accepted_actions"]
        calls += actual["model_calls"]
        tokens += actual["total_tokens"]
        latency += actual["latency_ms"]
        cost += actual["cost_usd"]
        deterministic += actual["deterministic_frontier_actions"]
        llm += actual["llm_frontier_calls"]
        invalidations += actual["validity_invalidations"]
        req_invalid += int(metrics["requirement_invalidations"])
        quote_invalid += int(metrics["quote_invalidations"])
        withdrawal_invalid += int(metrics["withdrawal_invalidations"])

    aggregate = {
        "runs": 3,
        "completed": 3,
        "terminal_feasible": [terminal, 3],
        "feasible_obligation_success": [feasible, 3],
        "strict_v02": [strict, 3],
        "economic_objective": [economic, 3],
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
        "validity_invalidations": invalidations,
        "requirement_invalidations": req_invalid,
        "quote_invalidations": quote_invalid,
        "withdrawal_invalidations": withdrawal_invalid,
    }
    for key, value in aggregate.items():
        _close(value, frozen["aggregate"][key], f"aggregate.{key}")

    assertions_008 = _assertions_008(
        by_episode["electrical-burauen-generator-008"]
    )
    assertions_013 = _assertions_013(
        by_episode["electrical-dla-transformer-013"]
    )
    assertions_016 = _assertions_016(
        by_episode["electrical-dla-power-supply-016"]
    )

    observed = {
        "electrical-burauen-generator-008": {
            **assertions_008,
            "pass": all(assertions_008.values()),
        },
        "electrical-dla-transformer-013": {
            **assertions_013,
            "pass": all(
                value
                for key, value in assertions_013.items()
                if key not in {
                    "first_rfq_occurs_after_clarification_response",
                    "observed_order",
                }
            ),
        },
        "electrical-dla-power-supply-016": {
            **assertions_016,
            "pass": all(
                assertions_016[key]
                for key in (
                    "requirement_change_increments_epoch",
                    "amendment_required_after_change",
                    "pre_change_offers_repaired_as_stale",
                    "post_amendment_repair_before_terminal",
                    "no_clarification_loop",
                )
            ),
        },
    }
    _close(
        observed,
        frozen["mechanism_assertions"],
        "mechanism_assertions",
    )

    quality_gate = terminal >= 2 and feasible >= 2
    mechanism_gate = all(
        row["pass"] for row in observed.values()
    )
    gates = {
        "execution_clean": all(
            record["status"] == "completed" for record in records
        ),
        "no_max_actions": all(
            record["status"] != "max_actions" for record in records
        ),
        "mechanism_activated_all_runs": all(
            int(record["policy_metrics"]["validity_frontier_interventions"]) > 0
            for record in records
        ),
        "quality_gate_pass": quality_gate,
        "strict_mechanism_gate_pass": mechanism_gate,
        "overall_preregistered_go_gate": quality_gate and mechanism_gate,
    }
    _close(gates, frozen["gates"], "gates")

    if gates["overall_preregistered_go_gate"]:
        raise ValueError(
            "Frozen Stage-1 verdict drift: the preregistered overall gate "
            "must remain false because 013 begins supplier discovery before "
            "the buyer clarification response."
        )

    print("State Validity Frontier Stage-1 evidence audit passed.")
    print(
        "quality: terminal=3/3 feasible_obligation=3/3 strict=3/3 "
        "economic=3/3 unresolved=0"
    )
    print(
        "strict mechanism gate: FAIL only on 013 discovery/RFQ ordering; "
        "no broad development run is authorized"
    )


if __name__ == "__main__":
    main()
