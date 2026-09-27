"""Validate one frozen held-out paper-evaluation row artifact."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from run_heldout_paper_row import (
    EXPECTED_HELDOUT_EPISODES,
    load_execution_plan,
)
from run_reactive_pilot import (
    flatten_result,
    model_slug,
    summarize,
)
from validate_live_pilot_statuses import invalid_rows

INFRA_STATUS = {
    "environment_error",
    "setup_error",
    "evaluation_error",
    "metadata_error",
}

CSV_FIELDS = [
    "model",
    "episode_id",
    "repeat",
    "run_id",
    "status",
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
    "plan_updates",
    "plan_rejections",
    "mean_plan_steps",
    "max_plan_steps",
    "evidence_epoch",
    "no_progress_marks",
    "progress_events",
    "guard_interventions",
    "guard_retry_calls",
    "guard_retry_noncompliance",
    "agent_pattern",
    "react_steps_proposed",
    "react_steps_accepted",
    "react_thought_chars_total",
    "react_thought_chars_mean",
    "react_thought_chars_max",
    "error_type",
    "evaluation_error_type",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        if fields != CSV_FIELDS:
            raise ValueError(
                "Held-out runs.csv schema drift: "
                f"expected={CSV_FIELDS}, actual={fields}"
            )
        return list(reader)


def _assert_json_equivalent(
    actual: Any,
    expected: Any,
    *,
    path: str = "root",
) -> None:
    if isinstance(actual, bool) or isinstance(expected, bool):
        if actual != expected:
            raise ValueError(
                f"JSON value drift at {path}: "
                f"expected={expected!r}, actual={actual!r}"
            )
        return

    if isinstance(actual, (int, float)) and isinstance(
        expected,
        (int, float),
    ):
        if isinstance(actual, float) or isinstance(expected, float):
            if not math.isclose(
                float(actual),
                float(expected),
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"JSON numeric drift at {path}: "
                    f"expected={expected!r}, actual={actual!r}"
                )
        elif actual != expected:
            raise ValueError(
                f"JSON integer drift at {path}: "
                f"expected={expected!r}, actual={actual!r}"
            )
        return

    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(
                f"JSON key drift at {path}: "
                f"missing={sorted(set(expected) - set(actual))}, "
                f"extra={sorted(set(actual) - set(expected))}"
            )
        for key in sorted(actual):
            _assert_json_equivalent(
                actual[key],
                expected[key],
                path=f"{path}.{key}",
            )
        return

    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(
                f"JSON list-length drift at {path}: "
                f"expected={len(expected)}, actual={len(actual)}"
            )
        for index, (actual_item, expected_item) in enumerate(
            zip(actual, expected)
        ):
            _assert_json_equivalent(
                actual_item,
                expected_item,
                path=f"{path}[{index}]",
            )
        return

    if actual != expected:
        raise ValueError(
            f"JSON value drift at {path}: "
            f"expected={expected!r}, actual={actual!r}"
        )


def _csv_projection(row: dict[str, Any]) -> dict[str, str]:
    projected = dict(row)
    projected["constraint_violations"] = ";".join(
        row.get("constraint_violations") or []
    )
    projected["incomplete_checkpoints"] = ";".join(
        row.get("incomplete_checkpoints") or []
    )
    projected["unresolved_obligations"] = ";".join(
        row.get("unresolved_obligations") or []
    )
    return {
        field: (
            ""
            if projected.get(field) is None
            else str(projected.get(field))
        )
        for field in CSV_FIELDS
    }


def _expected_keys(spec: dict[str, Any]) -> set[tuple[str, int]]:
    return {
        (episode_id, repeat)
        for episode_id in EXPECTED_HELDOUT_EPISODES
        for repeat in range(1, spec["repeats"] + 1)
    }


def _result_path(
    output_dir: Path,
    spec: dict[str, Any],
    episode_id: str,
    repeat: int,
) -> Path:
    if spec["row_id"] == "reference-control":
        root = output_dir / "reference-control"
    else:
        root = output_dir / model_slug(spec["model"])
    return root / episode_id / f"run-{repeat:03d}.json"


def validate_row_results(
    row_id: str,
    output_dir: Path,
    *,
    write_manifest: bool = True,
) -> dict[str, Any]:
    plan = load_execution_plan()
    if row_id not in plan:
        raise ValueError(f"Held-out row {row_id!r} is not frozen")
    spec = plan[row_id]
    output_dir = Path(output_dir)

    csv_path = output_dir / "runs.csv"
    summary_path = output_dir / "summary.json"
    if not csv_path.is_file() or not summary_path.is_file():
        raise ValueError(
            f"Held-out row output is incomplete: {output_dir}"
        )

    rows = _read_csv(csv_path)
    if len(rows) != spec["expected_runs"]:
        raise ValueError(
            f"{row_id} expected {spec['expected_runs']} runs; "
            f"found {len(rows)}"
        )

    actual_keys = set()
    expected_model = (
        "reference-control"
        if row_id == "reference-control"
        else spec["model"]
    )
    for row in rows:
        if row.get("model") != expected_model:
            raise ValueError(
                f"{row_id} emitted unexpected model: {row.get('model')!r}"
            )
        episode_id = row.get("episode_id")
        try:
            repeat = int(row.get("repeat") or "")
        except ValueError as exc:
            raise ValueError(
                f"{row_id} emitted invalid repeat: {row.get('repeat')!r}"
            ) from exc
        key = (episode_id, repeat)
        if key in actual_keys:
            raise ValueError(f"{row_id} duplicate run key: {key}")
        actual_keys.add(key)

    expected_keys = _expected_keys(spec)
    if actual_keys != expected_keys:
        raise ValueError(
            f"{row_id} held-out grid mismatch: "
            f"missing={sorted(expected_keys - actual_keys)}, "
            f"extra={sorted(actual_keys - expected_keys)}"
        )

    rows_by_key = {}
    for row in rows:
        key = (row["episode_id"], int(row["repeat"]))
        rows_by_key[key] = row

    raw_results = []
    raw_flat_rows = []
    for episode_id, repeat in sorted(actual_keys):
        path = _result_path(
            output_dir,
            spec,
            episode_id,
            repeat,
        )
        if not path.is_file():
            raise ValueError(
                f"{row_id} missing raw result: {path.relative_to(output_dir)}"
            )
        result = _load_json(path)
        if result.get("episode_id") != episode_id:
            raise ValueError(
                f"{row_id} raw result episode mismatch: {path}"
            )
        if result.get("status") in INFRA_STATUS:
            raise ValueError(
                f"{row_id} raw result has infrastructure status: "
                f"{result.get('status')}"
            )
        if result.get("evaluation_error") is not None:
            raise ValueError(
                f"{row_id} raw result has evaluation error: {path}"
            )

        policy = result.get("policy") or {}
        if policy.get("policy_kind") != spec["policy_kind"]:
            raise ValueError(
                f"{row_id} policy kind drift: "
                f"expected={spec['policy_kind']!r}, "
                f"actual={policy.get('policy_kind')!r}"
            )

        evaluation = result.get("evaluation")
        if not isinstance(evaluation, dict):
            raise ValueError(f"{row_id} raw result lacks evaluation: {path}")
        if evaluation.get("evaluation_version") != "0.2.0":
            raise ValueError(
                f"{row_id} evaluator version drift: "
                f"{evaluation.get('evaluation_version')!r}"
            )

        metrics = result.get("policy_metrics") or {}
        if row_id == "reference-control":
            if metrics.get("model_calls_attempted") not in (None, 0):
                raise ValueError(
                    "Reference control unexpectedly used model calls"
                )
            if not evaluation.get("episode_success_v02"):
                raise ValueError(
                    f"Reference control strict failure: {episode_id}"
                )
            if not evaluation.get("feasible_obligation_success"):
                raise ValueError(
                    f"Reference control obligation failure: {episode_id}"
                )
            obligations = evaluation.get("obligations") or {}
            if obligations.get("unresolved") != 0:
                raise ValueError(
                    f"Reference control unresolved obligations: {episode_id}"
                )
        else:
            if metrics.get("model") != spec["model"]:
                raise ValueError(
                    f"{row_id} model metadata drift: "
                    f"{metrics.get('model')!r}"
                )
            if metrics.get("temperature") != spec["temperature"]:
                raise ValueError(
                    f"{row_id} temperature drift: "
                    f"{metrics.get('temperature')!r}"
                )
            if (
                metrics.get("reasoning_effort")
                != spec["reasoning_effort"]
            ):
                raise ValueError(
                    f"{row_id} reasoning-effort drift: "
                    f"{metrics.get('reasoning_effort')!r}"
                )
            if (
                metrics.get("context_strategy")
                != spec["context_strategy"]
            ):
                raise ValueError(
                    f"{row_id} context-strategy drift: "
                    f"{metrics.get('context_strategy')!r}"
                )
            if metrics.get("agent_pattern") != spec["agent_pattern"]:
                raise ValueError(
                    f"{row_id} agent-pattern drift: "
                    f"{metrics.get('agent_pattern')!r}"
                )
            if metrics.get("usage_incomplete") is not False:
                raise ValueError(
                    f"{row_id} has incomplete provider usage: {path}"
                )
            if metrics.get("cost_usd") is None:
                raise ValueError(
                    f"{row_id} has unknown API cost: {path}"
                )
            if metrics.get("model_calls_failed") not in (None, 0):
                raise ValueError(
                    f"{row_id} has failed model calls: {path}"
                )

        raw_results.append(result)
        expected_flat = flatten_result(
            result,
            expected_model,
            repeat,
        )
        raw_flat_rows.append(expected_flat)
        expected_csv = _csv_projection(expected_flat)
        actual_csv = rows_by_key[(episode_id, repeat)]
        if actual_csv != expected_csv:
            changed = sorted(
                field
                for field in CSV_FIELDS
                if actual_csv.get(field) != expected_csv.get(field)
            )
            raise ValueError(
                f"{row_id} runs.csv disagrees with raw result for "
                f"{episode_id} r{repeat}: changed_fields={changed}"
            )

    bad = invalid_rows(raw_flat_rows)
    if bad:
        raise ValueError(
            f"{row_id} contains {len(bad)} infrastructure/model failure rows"
        )

    expected_baseline = (
        "heldout-reference-control-v0.1"
        if row_id == "reference-control"
        else f"heldout-paper-v0.1--{row_id}"
    )
    expected_summary = summarize(
        raw_flat_rows,
        baseline_name=expected_baseline,
    )
    summary = _load_json(summary_path)
    try:
        _assert_json_equivalent(
            summary,
            expected_summary,
            path=f"{row_id}.summary",
        )
    except ValueError as exc:
        raise ValueError(
            f"{row_id} summary.json disagrees with raw result evidence: "
            f"{exc}"
        ) from exc

    validation = {
        "schema_version": "0.1.0",
        "row_id": row_id,
        "model": spec["model"],
        "episodes": list(EXPECTED_HELDOUT_EPISODES),
        "repeats": spec["repeats"],
        "expected_runs": spec["expected_runs"],
        "validated_runs": len(raw_results),
        "policy_kind": spec["policy_kind"],
        "temperature": spec["temperature"],
        "temperature_mode": spec["temperature_mode"],
        "reasoning_effort": spec["reasoning_effort"],
        "max_actions": spec["max_actions"],
        "context_strategy": spec["context_strategy"],
        "agent_pattern": spec["agent_pattern"],
        "evaluation_version": "0.2.0",
        "infrastructure_failures": 0,
    }
    if write_manifest:
        (output_dir / "validated-row.json").write_text(
            json.dumps(validation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    validation = validate_row_results(
        args.row,
        Path(args.output_dir),
    )
    print(
        f"Validated held-out row {validation['row_id']}: "
        f"{validation['validated_runs']} exact frozen runs."
    )


if __name__ == "__main__":
    main()
