"""Re-evaluate saved LongProcureBench pilot trajectories without model calls."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
from run_reactive_pilot import flatten_result



def _error_record(exc: Exception) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _execution_status(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status == "evaluation_error":
        # Runner v0.1 promotes only an otherwise completed execution to this
        # status when deterministic evaluation fails.
        return "completed"
    return status if isinstance(status, str) else "unknown"


def accepted_actions(result: dict[str, Any]) -> list[dict[str, Any]]:
    trajectory = result.get("trajectory")
    if not isinstance(trajectory, list):
        raise ValueError("Saved result is missing trajectory")
    actions = []
    for row in trajectory:
        if not isinstance(row, dict) or not isinstance(row.get("action"), dict):
            raise ValueError("Saved trajectory row is missing action")
        actions.append(deepcopy(row["action"]))
    return actions


def rescore_result(
    result: dict[str, Any],
    evaluator: LongProcureBenchEvaluator,
) -> dict[str, Any]:
    episode_id = result.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("Saved result is missing episode_id")

    rescored = deepcopy(result)
    rescored["source_status"] = result.get("status")
    rescored["source_error"] = deepcopy(result.get("error"))
    rescored["source_evaluation_error"] = deepcopy(
        result.get("evaluation_error")
    )
    rescored["status"] = _execution_status(result)
    if rescored["source_status"] == "evaluation_error":
        rescored["error"] = None

    try:
        evaluation = evaluator.evaluate_actions(
            episode_id,
            accepted_actions(result),
        )
    except Exception as exc:
        audit_error = _error_record(exc)
        rescored["evaluation"] = None
        rescored["evaluation_error"] = deepcopy(audit_error)
        rescored["audit_status"] = "evaluation_error"
        rescored["audit_error"] = audit_error
    else:
        rescored["evaluation"] = evaluation
        rescored["evaluation_error"] = None
        rescored["audit_status"] = "success"
        rescored["audit_error"] = None

    return rescored


def _repeat_from_path(path: Path) -> int:
    stem = path.stem
    if not stem.startswith("run-"):
        raise ValueError(f"Unexpected raw run filename: {path.name}")
    return int(stem[len("run-"):])


def discover_runs(input_dir: Path) -> list[Path]:
    runs = sorted(input_dir.glob("**/run-*.json"))
    if not runs:
        raise ValueError(f"No raw run JSON found under {input_dir}")
    return runs


def flatten_audited_result(
    result: dict[str, Any],
    *,
    model: str,
    repeat: int,
) -> dict[str, Any]:
    if result.get("audit_status") == "success":
        row = flatten_result(result, model=model, repeat=repeat)
        row.pop("status", None)
    else:
        metrics = result.get("policy_metrics") or {}
        row = {
            "model": model,
            "episode_id": result.get("episode_id"),
            "repeat": repeat,
            "run_id": result.get("run_id"),
            "episode_success": None,
            "episode_success_v02": None,
            "feasible_process_success": None,
            "feasible_obligation_success": None,
            "terminal_feasible": None,
            "economic_objective_satisfied": None,
            "hard_constraints_passed": None,
            "hard_constraints_total": None,
            "checkpoints_completed": None,
            "checkpoints_total": None,
            "constraint_violations": [],
            "incomplete_checkpoints": [],
            "obligations_actionable": None,
            "obligations_resolved": None,
            "obligations_unresolved": None,
            "obligations_no_opportunity": None,
            "obligations_not_applicable": None,
            "obligation_resolution_rate": None,
            "unresolved_obligations": [],
            "accepted_actions": len(result.get("trajectory") or []),
            "model_calls": metrics.get(
                "model_calls_attempted", metrics.get("model_calls")
            ),
            "total_tokens": metrics.get("total_tokens"),
            "latency_ms": metrics.get("latency_ms"),
            "cost_usd": metrics.get("cost_usd"),
            "usage_incomplete": metrics.get("usage_incomplete"),
            "state_strategy": metrics.get("state_strategy"),
            "ledger_open_items": metrics.get("ledger_open_items"),
            "ledger_resolved_items": metrics.get("ledger_resolved_items"),
            "ledger_items_created": metrics.get("ledger_items_created"),
            "ledger_max_open_items": metrics.get("ledger_max_open_items"),
            "error_type": (result.get("error") or {}).get("type"),
            "evaluation_error_type": (
                result.get("evaluation_error") or {}
            ).get("type"),
        }

    row["source_status"] = result.get("source_status")
    row["execution_status"] = result.get("status")
    row["audit_status"] = result.get("audit_status")
    row["audit_error_type"] = (
        (result.get("audit_error") or {}).get("type")
    )
    return row


def _mean(values):
    known = [float(value) for value in values if value is not None]
    return sum(known) / len(known) if known else None


def summarize_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, Any] = {}
    for model in sorted({row["model"] for row in rows}):
        subset = [row for row in rows if row["model"] == model]
        audited = [
            row for row in subset if row["audit_status"] == "success"
        ]

        def rate(key):
            if not audited:
                return None
            return sum(bool(row[key]) for row in audited) / len(audited)

        by_model[model] = {
            "runs": len(subset),
            "audited_runs": len(audited),
            "audit_failed_runs": len(subset) - len(audited),
            "episode_success_rate": rate("episode_success"),
            "episode_success_rate_v02": rate("episode_success_v02"),
            "terminal_feasible_rate": rate("terminal_feasible"),
            "feasible_process_success_rate": rate(
                "feasible_process_success"
            ),
            "feasible_obligation_success_rate": rate(
                "feasible_obligation_success"
            ),
            "economic_objective_rate": rate(
                "economic_objective_satisfied"
            ),
            "execution_status_counts": dict(sorted(
                __import__("collections").Counter(
                    row["execution_status"] for row in subset
                ).items()
            )),
            "audit_status_counts": dict(sorted(
                __import__("collections").Counter(
                    row["audit_status"] for row in subset
                ).items()
            )),
            "mean_accepted_actions": _mean(
                [row["accepted_actions"] for row in subset]
            ),
            "mean_total_tokens": _mean(
                [row["total_tokens"] for row in subset]
            ),
            "mean_latency_ms": _mean(
                [row["latency_ms"] for row in subset]
            ),
            "total_known_cost_usd": sum(
                float(row["cost_usd"])
                for row in subset
                if row["cost_usd"] is not None
            ),
            "runs_with_unknown_cost_usd": sum(
                row["cost_usd"] is None for row in subset
            ),
            "runs_with_incomplete_usage": sum(
                bool(row["usage_incomplete"]) for row in subset
            ),
        }

    return {
        "schema_version": "0.1.0",
        "benchmark": "LongProcureBench",
        "baseline": "reactive-llm-v0.1",
        "runs": len(rows),
        "audited_runs": sum(
            row["audit_status"] == "success" for row in rows
        ),
        "audit_failed_runs": sum(
            row["audit_status"] != "success" for row in rows
        ),
        "by_model": by_model,
    }


def write_audit_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "model",
        "episode_id",
        "repeat",
        "run_id",
        "source_status",
        "execution_status",
        "audit_status",
        "audit_error_type",
        "episode_success",
        "episode_success_v02",
        "feasible_process_success",
        "feasible_obligation_success",
        "terminal_feasible",
        "economic_objective_satisfied",
        "hard_constraints_passed",
        "hard_constraints_total",
        "checkpoints_completed",
        "checkpoints_total",
        "constraint_violations",
        "incomplete_checkpoints",
        "obligations_actionable",
        "obligations_resolved",
        "obligations_unresolved",
        "obligations_no_opportunity",
        "obligations_not_applicable",
        "obligation_resolution_rate",
        "unresolved_obligations",
        "accepted_actions",
        "model_calls",
        "total_tokens",
        "latency_ms",
        "cost_usd",
        "usage_incomplete",
        "state_strategy",
        "ledger_open_items",
        "ledger_resolved_items",
        "ledger_items_created",
        "ledger_max_open_items",
        "error_type",
        "evaluation_error_type",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record["constraint_violations"] = ";".join(
                row["constraint_violations"]
            )
            record["incomplete_checkpoints"] = ";".join(
                row["incomplete_checkpoints"]
            )
            record["unresolved_obligations"] = ";".join(
                row.get("unresolved_obligations") or []
            )
            writer.writerow(record)


def failure_taxonomy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint_counts: dict[str, int] = {}
    constraint_counts: dict[str, int] = {}

    audited_rows = [
        row
        for row in rows
        if row.get("audit_status", "success") == "success"
    ]

    for row in audited_rows:
        for checkpoint in row["incomplete_checkpoints"]:
            checkpoint_counts[checkpoint] = checkpoint_counts.get(checkpoint, 0) + 1
        for constraint in row["constraint_violations"]:
            constraint_counts[constraint] = constraint_counts.get(constraint, 0) + 1

    return {
        "schema_version": "0.1.0",
        "runs": len(rows),
        "audited_runs": len(audited_rows),
        "audit_failed_runs": len(rows) - len(audited_rows),
        "terminal_infeasible_runs": sum(
            not row["terminal_feasible"] for row in audited_rows
        ),
        "feasible_but_process_incomplete_runs": sum(
            row["terminal_feasible"]
            and not row["feasible_process_success"]
            for row in audited_rows
        ),
        "feasible_process_but_economically_suboptimal_runs": sum(
            row["feasible_process_success"]
            and not row["economic_objective_satisfied"]
            for row in audited_rows
        ),
        "strict_success_runs": sum(
            bool(row["episode_success"]) for row in audited_rows
        ),
        "checkpoint_failure_counts": dict(
            sorted(checkpoint_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "constraint_failure_counts": dict(
            sorted(constraint_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
    }


def rescore_directory(
    input_dir: Path,
    output_dir: Path,
    *,
    evaluator: LongProcureBenchEvaluator | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Audit output directory is not empty: {output_dir}"
        )

    evaluator = evaluator or LongProcureBenchEvaluator()
    rows: list[dict[str, Any]] = []

    for source_path in discover_runs(input_dir):
        original = json.loads(source_path.read_text(encoding="utf-8"))
        rescored = rescore_result(original, evaluator)

        relative = source_path.relative_to(input_dir)
        destination = output_dir / "rescored" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(rescored, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        model = (
            (original.get("policy_metrics") or {}).get("model")
            or (original.get("policy") or {}).get("policy_id")
            or "unknown"
        )
        rows.append(
            flatten_audited_result(
                rescored,
                model=model,
                repeat=_repeat_from_path(source_path),
            )
        )

    summary = summarize_audit(rows)
    taxonomy = failure_taxonomy(rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "failure-taxonomy.json").write_text(
        json.dumps(taxonomy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_audit_csv(rows, output_dir / "runs.csv")
    return rows, summary, taxonomy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    rows, summary, taxonomy = rescore_directory(
        Path(args.input_dir),
        Path(args.output_dir),
    )
    print(
        f"Rescored {len(rows)} runs; strict_success="
        f"{taxonomy['strict_success_runs']}/{len(rows)}"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
