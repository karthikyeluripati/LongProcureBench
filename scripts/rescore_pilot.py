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
from run_reactive_pilot import flatten_result, summarize, write_csv


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
    rescored["evaluation"] = evaluator.evaluate_actions(
        episode_id,
        accepted_actions(result),
    )
    rescored["evaluation_error"] = None
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


def failure_taxonomy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint_counts: dict[str, int] = {}
    constraint_counts: dict[str, int] = {}

    for row in rows:
        for checkpoint in row["incomplete_checkpoints"]:
            checkpoint_counts[checkpoint] = checkpoint_counts.get(checkpoint, 0) + 1
        for constraint in row["constraint_violations"]:
            constraint_counts[constraint] = constraint_counts.get(constraint, 0) + 1

    return {
        "schema_version": "0.1.0",
        "runs": len(rows),
        "terminal_infeasible_runs": sum(
            not row["terminal_feasible"] for row in rows
        ),
        "feasible_but_process_incomplete_runs": sum(
            row["terminal_feasible"]
            and not row["feasible_process_success"]
            for row in rows
        ),
        "feasible_process_but_economically_suboptimal_runs": sum(
            row["feasible_process_success"]
            and not row["economic_objective_satisfied"]
            for row in rows
        ),
        "strict_success_runs": sum(row["episode_success"] for row in rows),
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
            flatten_result(
                rescored,
                model=model,
                repeat=_repeat_from_path(source_path),
            )
        )

    summary = summarize(rows)
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
    write_csv(rows, output_dir / "runs.csv")
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
