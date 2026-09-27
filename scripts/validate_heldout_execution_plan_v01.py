"""Validate the pre-run held-out paper evaluation execution plan."""
from __future__ import annotations

import json
from pathlib import Path
import re

from run_heldout_paper_row import (
    EXPECTED_HELDOUT_EPISODES,
    EXPECTED_ROW_IDS,
    load_execution_plan,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    ROOT
    / "evidence"
    / "heldout-paper-evaluation-v0.1"
    / "plan.json"
)
WORKFLOW_PATH = (
    ROOT
    / ".github"
    / "workflows"
    / "heldout-paper-evaluation-v0.1.yml"
)

HELDOUT_PACKAGE_MERGE_SHA = (
    "4d58ddc8021c6298cf9f345cbbb3adb059067219"
)
DEVELOPMENT_FREEZE_MERGE_SHA = (
    "0a9378f005d9c66a5d991b1af77d865a4fe2f75b"
)


def validate_execution_plan() -> dict:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if plan.get("schema_version") != "0.1.0":
        raise ValueError("Held-out execution plan schema drift")
    if plan.get("experiment") != "heldout-paper-evaluation-v0.1":
        raise ValueError("Held-out execution experiment identity drift")
    if plan.get("status") != "execution_protocol_frozen_pre_run":
        raise ValueError("Held-out execution protocol is not pre-run frozen")
    if plan.get("heldout_package_merge_sha") != HELDOUT_PACKAGE_MERGE_SHA:
        raise ValueError("Held-out package merge provenance drift")
    if plan.get("development_comparator_freeze_merge_sha") != (
        DEVELOPMENT_FREEZE_MERGE_SHA
    ):
        raise ValueError("Development freeze merge provenance drift")
    if plan.get("model_evaluations_run") is not False:
        raise ValueError("Pre-run execution plan must have zero model runs")
    if tuple(plan.get("episodes") or []) != EXPECTED_HELDOUT_EPISODES:
        raise ValueError("Execution-plan held-out episode order drift")

    runtime_plan = load_execution_plan()
    rows = plan.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Execution plan rows must be a list")
    by_id = {}
    for row in rows:
        row_id = row.get("id")
        if row_id in by_id:
            raise ValueError(f"Duplicate execution-plan row: {row_id}")
        by_id[row_id] = row

    if set(by_id) != EXPECTED_ROW_IDS:
        raise ValueError("Execution-plan row set changed")

    keys = (
        "model",
        "repeats",
        "expected_runs",
        "policy_kind",
        "temperature_mode",
        "temperature",
        "reasoning_effort",
        "max_actions",
        "context_strategy",
        "agent_pattern",
    )
    for row_id, spec in runtime_plan.items():
        planned = by_id[row_id]
        for key in keys:
            if planned.get(key) != spec.get(key):
                raise ValueError(
                    f"Execution plan drift for {row_id}.{key}: "
                    f"expected={spec.get(key)!r}, "
                    f"actual={planned.get(key)!r}"
                )

    if plan.get("expected_model_backed_runs") != 150:
        raise ValueError("Execution plan model-backed total changed")
    if plan.get("expected_reference_control_runs") != 10:
        raise ValueError("Execution plan reference total changed")
    if plan.get("expected_total_runs") != 160:
        raise ValueError("Execution plan total run count changed")
    if plan.get("workflow") != (
        ".github/workflows/heldout-paper-evaluation-v0.1.yml"
    ):
        raise ValueError("Execution workflow path changed")
    if plan.get("workflow_trigger") != "manual_only":
        raise ValueError("Held-out execution workflow must be manual-only")

    if not WORKFLOW_PATH.is_file():
        raise ValueError("Held-out execution workflow is missing")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    if not re.search(
        r"(?m)^on:\s*\n\s{2}workflow_dispatch:\s*$",
        workflow,
    ):
        raise ValueError(
            "Held-out execution workflow must expose workflow_dispatch only"
        )
    if re.search(
        r"(?m)^\s{2}(push|pull_request|schedule):\s*$",
        workflow,
    ):
        raise ValueError(
            "Held-out execution workflow has an automatic trigger"
        )
    if re.search(r"(?m)^\s{4}inputs:\s*$", workflow):
        raise ValueError(
            "Held-out execution workflow must not expose run-setting inputs"
        )

    for forbidden in (
        "--model",
        "--episode",
        "--repeats",
        "--max-actions",
        "--temperature",
        "--omit-temperature",
        "--reasoning-effort",
    ):
        if forbidden in workflow:
            raise ValueError(
                f"Held-out workflow exposes forbidden override: {forbidden}"
            )

    for row_id in sorted(EXPECTED_ROW_IDS):
        if f"--row {row_id}" not in workflow:
            raise ValueError(
                f"Held-out workflow does not execute frozen row: {row_id}"
            )

    return plan


def main() -> None:
    plan = validate_execution_plan()
    print(
        "Held-out execution plan validated: "
        f"{plan['expected_model_backed_runs']} model-backed + "
        f"{plan['expected_reference_control_runs']} reference runs; "
        "manual-only, no research-setting overrides."
    )


if __name__ == "__main__":
    main()
