"""Aggregate and revalidate the complete frozen held-out matrix."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from run_heldout_paper_row import (
    EXPECTED_ROW_IDS,
    load_execution_plan,
)
from validate_heldout_row_results_v01 import validate_row_results


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def aggregate_matrix(
    root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    root = Path(root)
    output_dir = Path(output_dir)
    plan = load_execution_plan()

    validations = {}
    combined_rows = []
    csv_fields = None

    for row_id in sorted(EXPECTED_ROW_IDS):
        row_dir = root / row_id
        if not row_dir.is_dir():
            raise ValueError(
                f"Missing held-out row artifact directory: {row_id}"
            )

        validation = validate_row_results(
            row_id,
            row_dir,
            write_manifest=False,
        )
        validations[row_id] = validation

        fields, rows = _read_csv(row_dir / "runs.csv")
        if csv_fields is None:
            csv_fields = fields
        elif fields != csv_fields:
            raise ValueError(
                f"runs.csv schema drift for held-out row {row_id}"
            )
        for row in rows:
            combined_rows.append({"row_id": row_id, **row})

    expected_total = sum(
        spec["expected_runs"] for spec in plan.values()
    )
    expected_model = sum(
        spec["expected_runs"]
        for row_id, spec in plan.items()
        if row_id != "reference-control"
    )
    expected_reference = plan["reference-control"]["expected_runs"]

    if expected_total != 160:
        raise ValueError(
            f"Frozen plan total must be 160; found {expected_total}"
        )
    if expected_model != 150 or expected_reference != 10:
        raise ValueError(
            "Frozen held-out split must be 150 model-backed + 10 reference"
        )
    if len(combined_rows) != expected_total:
        raise ValueError(
            f"Combined held-out evidence expected {expected_total} rows; "
            f"found {len(combined_rows)}"
        )

    row_counts = {
        row_id: sum(row["row_id"] == row_id for row in combined_rows)
        for row_id in sorted(EXPECTED_ROW_IDS)
    }
    expected_counts = {
        row_id: spec["expected_runs"]
        for row_id, spec in sorted(plan.items())
    }
    if row_counts != expected_counts:
        raise ValueError(
            f"Held-out row count drift: expected={expected_counts}, "
            f"actual={row_counts}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    combined_path = output_dir / "heldout-runs.csv"
    fieldnames = ["row_id", *(csv_fields or [])]
    with combined_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(combined_rows)

    row_summaries = {}
    for row_id in sorted(EXPECTED_ROW_IDS):
        row_summaries[row_id] = json.loads(
            (root / row_id / "summary.json").read_text(
                encoding="utf-8"
            )
        )

    manifest = {
        "schema_version": "0.1.0",
        "experiment": "heldout-paper-evaluation-v0.1",
        "rows": sorted(EXPECTED_ROW_IDS),
        "total_runs": expected_total,
        "model_backed_runs": expected_model,
        "reference_control_runs": expected_reference,
        "row_counts": row_counts,
        "validations": validations,
        "row_summaries": row_summaries,
        "interpretation_rule": (
            "Report the frozen matrix as measured; do not tune methods, "
            "episodes, evaluator semantics, or model settings from these "
            "held-out outcomes."
        ),
    }
    (output_dir / "heldout-matrix-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    manifest = aggregate_matrix(
        Path(args.root),
        Path(args.output_dir),
    )
    print(
        "Validated complete held-out matrix: "
        f"{manifest['model_backed_runs']} model-backed + "
        f"{manifest['reference_control_runs']} reference = "
        f"{manifest['total_runs']} runs."
    )


if __name__ == "__main__":
    main()
