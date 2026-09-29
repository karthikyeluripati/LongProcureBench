"""Freeze development-confirmation -> validation selection for one round.

This is an offline, no-provider gate. It revalidates the frozen screening
selection, reads the complete 001-020 x3 confirmation summaries, recomputes the
development floor and quality promotion branch, ranks eligible candidates, and
emits at most two validation authorizations.

Efficiency-only promotion intentionally fails closed until a separately frozen
economic-comparison gate is supplied. No boolean in an authorization can create
eligibility by itself.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha1, sha256
import json
import math
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX local environments
    fcntl = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench.economics import (
    EconomicsError,
    compare_candidate_on_reference_cohort,
)
from longprocurebench.procureharness import get_candidate
from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    PROTOCOL_ID,
    round_candidate_ids,
)
from select_procureharness_screening_v01 import (
    SCREENING_RANKING_PRIORITY,
    validate_frozen_screening_selection,
)

REGISTRY_PATH = ROOT / "docs" / "procureharness-candidate-registry-v0.1.json"
PROTOCOL_PATH = (
    ROOT / "docs" / "procureharness-architecture-search-v0.1-protocol.json"
)
RULE_ID = "frozen_validation_entry_lexicographic_v0.1"
EFFICIENCY_RULE_ID = "frozen_development_efficiency_promotion_v0.1"
DEVELOPMENT_ECONOMICS_BINDING_PATH = (
    ROOT
    / "evidence"
    / "procureharness-development-economics-v0.1"
    / "manifest.json"
)

VALIDATION_RANKING_PRIORITY = [
    {"metric": "feasible_obligation_success", "direction": "desc"},
    {"metric": "strict_v02", "direction": "desc"},
    {"metric": "economic_objective", "direction": "desc"},
    {"metric": "obligation_resolution_rate", "direction": "desc"},
    {"metric": "known_cost_usd", "direction": "asc"},
    {"metric": "total_tokens", "direction": "asc"},
    {"metric": "candidate_id", "direction": "asc"},
]

COVERAGE_REPAIR_BASELINE = {
    "feasible_obligation_success": 50,
    "strict_v02": 30,
    "economic_objective": 30,
}
DEVELOPMENT_FLOOR = {
    "feasible_obligation_success": 47,
    "strict_v02": 27,
    "economic_objective": 27,
}
QUALITY_IMPROVEMENT_RUNS = 3
QUALITY_MAX_DEFICIT_RUNS = 3
QUALITY_MAX_KNOWN_COST_USD = 7.9842032


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _exclusive_gate_lock(
    output_dir: Path,
    *,
    gate_name: str,
    round_id: int,
):
    """Serialize one gate freeze with an OS lock released on process death."""
    if fcntl is None:
        raise RuntimeError(
            "ProcureHarness gate freezing requires POSIX advisory file locks"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / f".{gate_name}-round-{round_id}.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise ValueError(
                f"{gate_name} round {round_id} freeze is already in progress: "
                f"{lock_path}"
            ) from exc

        # The lock file may outlive a killed process. Once the OS advisory lock
        # is acquired, stale contents are harmless and can be replaced.
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "gate_name": gate_name,
                    "round": round_id,
                },
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
        yield lock_path
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return sha1(header + data).hexdigest()


def _blob_at_commit(commit: str, path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{commit}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"frozen economics path missing at commit: {path}"
        ) from exc
    blob = result.stdout.strip()
    if len(blob) != 40:
        raise ValueError(f"invalid frozen economics blob for {path}: {blob!r}")
    return blob


def _load_development_economics_binding() -> dict[str, Any]:
    if not DEVELOPMENT_ECONOMICS_BINDING_PATH.is_file():
        raise ValueError(
            "efficiency append is unavailable until the frozen development "
            "economics binding manifest exists"
        )

    raw = DEVELOPMENT_ECONOMICS_BINDING_PATH.read_bytes()
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("schema_version") != "0.1.0":
        raise ValueError("development economics binding schema changed")
    if manifest.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("development economics binding protocol mismatch")
    if manifest.get("package") != (
        "procureharness-development-economics-v0.1"
    ):
        raise ValueError("development economics binding package changed")

    freeze_commit = manifest.get("freeze_commit")
    if (
        not isinstance(freeze_commit, str)
        or len(freeze_commit) != 40
        or any(ch not in "0123456789abcdef" for ch in freeze_commit)
    ):
        raise ValueError("development economics binding freeze_commit invalid")

    rel_manifest = str(
        DEVELOPMENT_ECONOMICS_BINDING_PATH.relative_to(ROOT)
    )
    immutable_manifest_blob = _blob_at_commit(
        freeze_commit,
        rel_manifest,
    )
    if immutable_manifest_blob != _git_blob_sha1(raw):
        raise ValueError(
            "development economics binding manifest drifted from freeze commit"
        )

    reports = manifest.get("reports")
    if not isinstance(reports, dict):
        raise ValueError("development economics binding reports missing")
    for key in ("coverage_repair", "react"):
        row = reports.get(key)
        if not isinstance(row, dict):
            raise ValueError(f"development economics binding lacks {key}")
        path_value = row.get("path")
        expected_blob = row.get("git_blob_sha1")
        expected_sha = row.get("sha256")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError(f"{key} economics binding path missing")
        if not isinstance(expected_blob, str) or len(expected_blob) != 40:
            raise ValueError(f"{key} economics binding blob invalid")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise ValueError(f"{key} economics binding SHA-256 invalid")

        immutable_blob = _blob_at_commit(freeze_commit, path_value)
        if immutable_blob != expected_blob:
            raise ValueError(
                f"{key} economics binding disagrees with freeze commit"
            )
        path = ROOT / path_value
        if not path.is_file():
            raise ValueError(f"{key} frozen economics reports missing")
        report_raw = path.read_bytes()
        if _git_blob_sha1(report_raw) != expected_blob:
            raise ValueError(f"{key} frozen economics report drift")
        if _sha256_bytes(report_raw) != expected_sha:
            raise ValueError(f"{key} frozen economics SHA-256 mismatch")

    return {
        **manifest,
        "manifest_sha256": _sha256_bytes(raw),
    }


def _validate_economics_report_grid(
    reports: list[dict[str, Any]],
    *,
    label: str,
) -> None:
    keys = []
    for row in reports:
        run_key = row.get("run_key")
        if not isinstance(run_key, dict):
            raise ValueError(f"{label} economics report lacks run_key")
        episode_id = run_key.get("episode_id")
        repeat = run_key.get("repeat")
        if not isinstance(episode_id, str) or not isinstance(repeat, int):
            raise ValueError(f"{label} economics report has invalid run_key")
        keys.append((episode_id, repeat))
    expected = _expected_run_keys()
    if (
        len(keys) != len(expected)
        or len(keys) != len(set(keys))
        or set(keys) != set(expected)
    ):
        raise ValueError(
            f"{label} economics reports must cover exact 001-020 x3 grid"
        )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _expected_run_keys() -> list[tuple[str, int]]:
    return [
        (episode_id, repeat)
        for repeat in range(1, 4)
        for episode_id in DEVELOPMENT_EPISODES
    ]


def _aggregate_confirmation(
    *,
    candidate_id: str,
    round_id: int,
    summary_path: Path,
) -> dict[str, Any]:
    raw = summary_path.read_bytes()
    summary = json.loads(raw.decode("utf-8"))

    if summary.get("protocol_id") != PROTOCOL_ID:
        raise ValueError(f"confirmation protocol mismatch: {candidate_id}")
    if summary.get("candidate_id") != candidate_id:
        raise ValueError(f"confirmation candidate mismatch: {candidate_id}")
    if summary.get("round") != round_id:
        raise ValueError(f"confirmation round mismatch: {candidate_id}")
    if summary.get("phase") != "development_confirmation":
        raise ValueError(
            f"candidate is not a development confirmation summary: "
            f"{candidate_id}"
        )
    if summary.get("planned_runs") != 60:
        raise ValueError(f"confirmation planned_runs must equal 60: {candidate_id}")
    if summary.get("completed_runs") != 60:
        raise ValueError(f"confirmation must complete 60 runs: {candidate_id}")
    if summary.get("execution_failures") != 0:
        raise ValueError(f"confirmation execution is not clean: {candidate_id}")

    rows = summary.get("rows")
    if not isinstance(rows, list) or len(rows) != 60:
        raise ValueError(f"confirmation summary requires 60 rows: {candidate_id}")
    observed_keys = [
        (row.get("episode_id"), row.get("repeat"))
        for row in rows
        if isinstance(row, dict)
    ]
    if observed_keys != _expected_run_keys():
        raise ValueError(f"confirmation run grid changed: {candidate_id}")

    feasible = sum(
        row.get("feasible_obligation_success") is True
        for row in rows
    )
    strict = sum(row.get("strict_v02") is True for row in rows)
    economic = sum(
        row.get("economic_objective") is True
        for row in rows
    )

    resolved = 0
    actionable = 0
    for row in rows:
        row_resolved = row.get("obligation_resolved")
        row_actionable = row.get("obligation_actionable")
        if not isinstance(row_resolved, int) or isinstance(row_resolved, bool):
            raise ValueError(
                f"confirmation row missing obligation_resolved: {candidate_id}"
            )
        if not isinstance(row_actionable, int) or isinstance(row_actionable, bool):
            raise ValueError(
                f"confirmation row missing obligation_actionable: {candidate_id}"
            )
        if row_resolved < 0 or row_actionable < 0 or row_resolved > row_actionable:
            raise ValueError(
                f"invalid obligation counts in confirmation: {candidate_id}"
            )
        resolved += row_resolved
        actionable += row_actionable
    if actionable <= 0:
        raise ValueError(
            f"confirmation has no actionable obligations: {candidate_id}"
        )

    costs = [row.get("known_cost_usd") for row in rows]
    cost_complete = all(_finite_number(value) for value in costs)
    known_cost_usd = (
        math.fsum(float(value) for value in costs)
        if cost_complete
        else None
    )
    if known_cost_usd is not None and not math.isfinite(known_cost_usd):
        raise ValueError(f"confirmation cost total is non-finite: {candidate_id}")

    tokens = [row.get("total_tokens") for row in rows]
    tokens_complete = all(
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        for value in tokens
    )
    total_tokens = sum(tokens) if tokens_complete else None

    floor_passed = (
        feasible >= DEVELOPMENT_FLOOR["feasible_obligation_success"]
        and strict >= DEVELOPMENT_FLOOR["strict_v02"]
        and economic >= DEVELOPMENT_FLOOR["economic_objective"]
    )

    metrics = {
        "feasible_obligation_success": feasible,
        "strict_v02": strict,
        "economic_objective": economic,
    }
    improved = [
        metric
        for metric, baseline in COVERAGE_REPAIR_BASELINE.items()
        if metrics[metric] >= baseline + QUALITY_IMPROVEMENT_RUNS
    ]
    deficits_ok = all(
        metrics[metric] >= baseline - QUALITY_MAX_DEFICIT_RUNS
        for metric, baseline in COVERAGE_REPAIR_BASELINE.items()
    )
    quality_cost_ok = (
        known_cost_usd is not None
        and known_cost_usd <= QUALITY_MAX_KNOWN_COST_USD
    )
    quality_passed = bool(
        floor_passed
        and improved
        and deficits_ok
        and quality_cost_ok
    )

    return {
        "candidate_id": candidate_id,
        "round": round_id,
        "feasible_obligation_success": feasible,
        "strict_v02": strict,
        "economic_objective": economic,
        "obligation_resolved": resolved,
        "obligation_actionable": actionable,
        "obligation_resolution_rate": resolved / actionable,
        "known_cost_usd": known_cost_usd,
        "known_cost_complete": cost_complete,
        "total_tokens": total_tokens,
        "total_tokens_complete": tokens_complete,
        "development_confirmation_floor_passed": floor_passed,
        "quality_promotion_passed": quality_passed,
        "quality_improved_metrics": improved,
        "efficiency_promotion_status": (
            "requires_frozen_economic_comparison_gate"
            if floor_passed and not quality_passed
            else "not_needed_for_selection"
        ),
        "confirmation_summary_path": str(summary_path),
        "confirmation_summary_sha256": _sha256_bytes(raw),
    }


def _ranking_value(
    row: dict[str, Any],
    *,
    metric: str,
    direction: str,
):
    if metric == "known_cost_usd":
        value = (
            float(row["known_cost_usd"])
            if row["known_cost_complete"]
            else math.inf
        )
    elif metric == "total_tokens":
        value = (
            int(row["total_tokens"])
            if row["total_tokens_complete"]
            else math.inf
        )
    else:
        value = row[metric]
    if metric == "candidate_id":
        if direction != "asc":
            raise ValueError("candidate_id ranking must remain ascending")
        return str(value)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"non-numeric validation ranking metric: {metric}")
    return -value if direction == "desc" else value


def _ranking_key(row: dict[str, Any]):
    return tuple(
        _ranking_value(
            row,
            metric=entry["metric"],
            direction=entry["direction"],
        )
        for entry in VALIDATION_RANKING_PRIORITY
    )


def _load_screening_selection(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    selection = json.loads(raw.decode("utf-8"))
    validate_frozen_screening_selection(selection)
    return selection, _sha256_bytes(raw)


def select_validation_round(
    *,
    round_id: int,
    results_root: Path,
    screening_selection_path: Path,
) -> dict[str, Any]:
    if round_id not in (1, 2, 3):
        raise ValueError("round must be 1, 2, or 3")

    registry = _load_json(REGISTRY_PATH)
    rule = registry.get("validation_selection_rule")
    if not isinstance(rule, dict) or rule.get("rule_id") != RULE_ID:
        raise ValueError("validation selection rule is not frozen")
    if rule.get("max_selected_candidates") != 2:
        raise ValueError("validation selection max must remain two")
    if rule.get("method") != "lexicographic":
        raise ValueError("validation selection method changed")
    if rule.get("priority") != VALIDATION_RANKING_PRIORITY:
        raise ValueError("validation ranking priority changed")
    if rule.get("missing_resource_values") != "rank_last":
        raise ValueError("validation missing-resource policy changed")

    screening, screening_sha = _load_screening_selection(
        screening_selection_path
    )
    if screening.get("round") != round_id:
        raise ValueError("screening/confirmation round mismatch")
    selected_screening = screening.get("selected_candidate_ids")
    if not isinstance(selected_screening, list) or not selected_screening:
        raise ValueError("screening selection has no candidates")
    if len(selected_screening) > 2:
        raise ValueError("screening selection exceeds two candidates")

    rows = []
    pending_efficiency = []
    for candidate_id in selected_screening:
        config = get_candidate(candidate_id)
        if config.round != round_id:
            raise ValueError("candidate registry round mismatch")
        summary_path = (
            results_root
            / candidate_id
            / "development_confirmation"
            / "summary.json"
        )
        if not summary_path.is_file():
            raise ValueError(
                f"missing confirmation summary for {candidate_id}: "
                f"{summary_path}"
            )
        aggregate = _aggregate_confirmation(
            candidate_id=candidate_id,
            round_id=round_id,
            summary_path=summary_path,
        )
        rows.append(aggregate)
        if (
            aggregate["development_confirmation_floor_passed"]
            and not aggregate["quality_promotion_passed"]
        ):
            pending_efficiency.append(candidate_id)

    eligible = [
        row for row in rows
        if row["development_confirmation_floor_passed"]
        and row["quality_promotion_passed"]
    ]
    eligible.sort(key=_ranking_key)
    selected = [row["candidate_id"] for row in eligible[:2]]

    reserved_slots = list(selected)
    for candidate_id in pending_efficiency:
        if (
            candidate_id not in reserved_slots
            and len(reserved_slots) < 2
        ):
            reserved_slots.append(candidate_id)

    return {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "rule_id": RULE_ID,
        "round": round_id,
        "round_candidate_ids": round_candidate_ids(round_id),
        "screening_selection_path": str(screening_selection_path),
        "screening_selection_sha256": screening_sha,
        "screening_selected_candidate_ids": selected_screening,
        "validation_selected_candidate_ids": selected,
        "validation_slot_candidate_ids": reserved_slots,
        "pending_efficiency_candidate_ids": pending_efficiency,
        "selection_status": (
            "partial_pending_efficiency"
            if pending_efficiency
            else "complete"
        ),
        "efficiency_append_policy": (
            "append_only_authorization_bound_to_immutable_base_selection"
        ),
        "ranking": eligible,
        "confirmation_rows": rows,
        "promotion_branch_by_candidate": {
            candidate_id: "quality"
            for candidate_id in selected
        },
    }


def validate_frozen_validation_selection(
    selection: dict[str, Any],
) -> None:
    if selection.get("schema_version") != "0.1.0":
        raise ValueError("validation selection schema version changed")
    if selection.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("validation selection protocol mismatch")
    if selection.get("rule_id") != RULE_ID:
        raise ValueError("validation selection rule mismatch")

    round_id = selection.get("round")
    if round_id not in (1, 2, 3):
        raise ValueError("validation selection round is invalid")
    if selection.get("round_candidate_ids") != round_candidate_ids(round_id):
        raise ValueError("validation selection candidate grid changed")

    screening_path_value = selection.get("screening_selection_path")
    screening_sha = selection.get("screening_selection_sha256")
    if not isinstance(screening_path_value, str) or not screening_path_value:
        raise ValueError("validation selection lacks screening path")
    screening_path = Path(screening_path_value)
    if not screening_path.is_absolute():
        screening_path = ROOT / screening_path
    if not screening_path.is_file():
        raise ValueError("bound screening selection is missing")
    raw = screening_path.read_bytes()
    if _sha256_bytes(raw) != screening_sha:
        raise ValueError("bound screening selection hash mismatch")
    screening = json.loads(raw.decode("utf-8"))
    validate_frozen_screening_selection(screening)
    if screening.get("round") != round_id:
        raise ValueError("validation selection screening round mismatch")
    if selection.get("screening_selected_candidate_ids") != (
        screening.get("selected_candidate_ids")
    ):
        raise ValueError("validation selection screening candidates changed")

    rows = selection.get("confirmation_rows")
    if not isinstance(rows, list):
        raise ValueError("validation selection lacks confirmation rows")
    expected_candidates = screening.get("selected_candidate_ids")
    if [row.get("candidate_id") for row in rows] != expected_candidates:
        raise ValueError("validation confirmation candidate order changed")

    recomputed = []
    for row in rows:
        candidate_id = row["candidate_id"]
        path_value = row.get("confirmation_summary_path")
        expected_sha = row.get("confirmation_summary_sha256")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError("confirmation row lacks summary path")
        summary_path = Path(path_value)
        if not summary_path.is_absolute():
            summary_path = ROOT / summary_path
        if not summary_path.is_file():
            raise ValueError(
                f"bound confirmation summary missing: {summary_path}"
            )
        raw = summary_path.read_bytes()
        if _sha256_bytes(raw) != expected_sha:
            raise ValueError(
                f"bound confirmation summary hash mismatch: {summary_path}"
            )
        aggregate = _aggregate_confirmation(
            candidate_id=candidate_id,
            round_id=round_id,
            summary_path=Path(path_value),
        )
        if aggregate != row:
            raise ValueError(
                f"confirmation row does not match bound summary: {candidate_id}"
            )
        recomputed.append(aggregate)

    pending_efficiency = [
        row["candidate_id"]
        for row in recomputed
        if (
            row["development_confirmation_floor_passed"]
            and not row["quality_promotion_passed"]
        )
    ]
    if selection.get("pending_efficiency_candidate_ids") != pending_efficiency:
        raise ValueError(
            "validation pending-efficiency candidate set changed"
        )

    selected_now = selection.get("validation_selected_candidate_ids")
    reserved_slots = selection.get("validation_slot_candidate_ids")
    if not isinstance(selected_now, list) or not isinstance(reserved_slots, list):
        raise ValueError("validation selection lacks slot reservation metadata")
    if len(reserved_slots) != len(set(reserved_slots)) or len(reserved_slots) > 2:
        raise ValueError("validation slot reservation is invalid")
    expected_reserved = list(selected_now)
    for candidate_id in pending_efficiency:
        if (
            candidate_id not in expected_reserved
            and len(expected_reserved) < 2
        ):
            expected_reserved.append(candidate_id)
    if reserved_slots != expected_reserved:
        raise ValueError("validation slot reservation changed")
    expected_status = (
        "partial_pending_efficiency"
        if pending_efficiency
        else "complete"
    )
    if selection.get("selection_status") != expected_status:
        raise ValueError("validation selection status changed")
    if selection.get("efficiency_append_policy") != (
        "append_only_authorization_bound_to_immutable_base_selection"
    ):
        raise ValueError("validation efficiency append policy changed")

    eligible = [
        row for row in recomputed
        if row["development_confirmation_floor_passed"]
        and row["quality_promotion_passed"]
    ]
    eligible.sort(key=_ranking_key)
    if selection.get("ranking") != eligible:
        raise ValueError("validation ranking order changed")

    selected = [row["candidate_id"] for row in eligible[:2]]
    if selection.get("validation_selected_candidate_ids") != selected:
        raise ValueError("validation selected candidates changed")
    expected_branches = {
        candidate_id: "quality"
        for candidate_id in selected
    }
    if selection.get("promotion_branch_by_candidate") != expected_branches:
        raise ValueError("validation promotion branches changed")


def _read_bound_report_list(
    *,
    path_value: str,
    expected_sha256: str | None,
    label: str,
) -> tuple[list[dict[str, Any]], str]:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise ValueError(f"{label} economics report file is missing: {path}")
    raw = path.read_bytes()
    observed_sha = _sha256_bytes(raw)
    if expected_sha256 is not None and observed_sha != expected_sha256:
        raise ValueError(f"{label} economics report hash mismatch: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{label} economics reports are not valid JSON: {path}"
        ) from exc
    if not isinstance(payload, list) or not all(
        isinstance(row, dict) for row in payload
    ):
        raise ValueError(
            f"{label} economics report file must contain a JSON list"
        )
    _validate_economics_report_grid(payload, label=label)
    return payload, observed_sha


def _confirmation_row_for_candidate(
    selection: dict[str, Any],
    candidate_id: str,
) -> dict[str, Any]:
    for row in selection.get("confirmation_rows") or []:
        if (
            isinstance(row, dict)
            and row.get("candidate_id") == candidate_id
        ):
            return row
    raise ValueError(
        f"validation selection lacks confirmation row for {candidate_id}"
    )


def evaluate_efficiency_promotion(
    *,
    base_selection: dict[str, Any],
    candidate_id: str,
    candidate_reports_path: str,
    expected_candidate_sha256: str | None = None,
) -> dict[str, Any]:
    """Recompute the frozen development efficiency branch from bound evidence."""
    validate_frozen_validation_selection(base_selection)

    if candidate_id not in (
        base_selection.get("pending_efficiency_candidate_ids") or []
    ):
        raise ValueError(
            "efficiency promotion candidate is not pending in base selection"
        )
    if candidate_id not in (
        base_selection.get("validation_slot_candidate_ids") or []
    ):
        raise ValueError(
            "efficiency promotion candidate has no reserved validation slot"
        )
    if candidate_id in (
        base_selection.get("validation_selected_candidate_ids") or []
    ):
        raise ValueError(
            "quality-selected candidate does not need efficiency append"
        )

    confirmation = _confirmation_row_for_candidate(
        base_selection,
        candidate_id,
    )
    protocol = _load_json(PROTOCOL_PATH)
    efficiency = (
        protocol["admissibility_and_frontier"]
        ["development_promotion_branches"]["efficiency"]
    )
    baseline = protocol["frozen_development_comparators"]["coverage_repair"]

    for metric, max_deficit in efficiency["max_deficit_runs"].items():
        candidate_value = confirmation.get(metric)
        baseline_value = baseline.get(metric)
        if (
            not isinstance(candidate_value, int)
            or isinstance(candidate_value, bool)
            or not isinstance(baseline_value, list)
            or len(baseline_value) != 2
            or candidate_value < int(baseline_value[0]) - int(max_deficit)
        ):
            raise ValueError(
                f"candidate fails efficiency quality deficit on {metric}"
            )

    candidate_cost = confirmation.get("known_cost_usd")
    baseline_cost = baseline.get("known_cost_usd")
    if not _finite_number(candidate_cost) or not _finite_number(baseline_cost):
        raise ValueError("efficiency promotion requires finite known costs")
    reduction = (float(baseline_cost) - float(candidate_cost)) / float(
        baseline_cost
    )
    if reduction + 1e-15 < float(
        efficiency["min_known_cost_reduction_fraction"]
    ):
        raise ValueError(
            "candidate fails efficiency known-cost reduction requirement"
        )

    economics_binding = _load_development_economics_binding()
    coverage_binding = economics_binding["reports"]["coverage_repair"]
    react_binding = economics_binding["reports"]["react"]

    candidate_reports, candidate_sha = _read_bound_report_list(
        path_value=candidate_reports_path,
        expected_sha256=expected_candidate_sha256,
        label="candidate",
    )
    coverage_reports, coverage_sha = _read_bound_report_list(
        path_value=coverage_binding["path"],
        expected_sha256=coverage_binding["sha256"],
        label="Coverage+Repair",
    )
    react_reports, react_sha = _read_bound_report_list(
        path_value=react_binding["path"],
        expected_sha256=react_binding["sha256"],
        label="ReAct",
    )

    try:
        candidate_comparison = compare_candidate_on_reference_cohort(
            candidate_reports,
            coverage_repair_reports=coverage_reports,
            react_reports=react_reports,
        )
        coverage_comparison = compare_candidate_on_reference_cohort(
            coverage_reports,
            coverage_repair_reports=coverage_reports,
            react_reports=react_reports,
        )
    except EconomicsError as exc:
        raise ValueError(
            f"efficiency economic comparison failed: {exc}"
        ) from exc

    if (
        candidate_comparison.get("status") != "comparable"
        or candidate_comparison.get("regret_comparable") is not True
    ):
        raise ValueError(
            "candidate lacks full frozen regret reference-cohort comparability"
        )
    if (
        coverage_comparison.get("status") != "comparable"
        or coverage_comparison.get("regret_comparable") is not True
    ):
        raise ValueError(
            "Coverage+Repair regret reference cohort is unavailable"
        )

    candidate_regret = candidate_comparison.get(
        "mean_feasible_price_regret_pct_on_reference_cohort"
    )
    coverage_regret = coverage_comparison.get(
        "mean_feasible_price_regret_pct_on_reference_cohort"
    )
    if not _finite_number(candidate_regret) or not _finite_number(
        coverage_regret
    ):
        raise ValueError(
            "efficiency promotion requires finite comparable regret means"
        )
    if float(candidate_regret) > float(coverage_regret) + 1e-12:
        raise ValueError(
            "candidate regret is worse than Coverage+Repair on frozen cohort"
        )

    return {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "rule_id": EFFICIENCY_RULE_ID,
        "candidate_id": candidate_id,
        "round": base_selection["round"],
        "promotion_branch": "efficiency",
        "known_cost_usd": float(candidate_cost),
        "coverage_repair_known_cost_usd": float(baseline_cost),
        "known_cost_reduction_fraction": reduction,
        "candidate_regret_mean_pct": float(candidate_regret),
        "coverage_repair_regret_mean_pct": float(coverage_regret),
        "reference_cohort_count": candidate_comparison.get(
            "reference_cohort_count"
        ),
        "development_economics_binding_path": str(
            DEVELOPMENT_ECONOMICS_BINDING_PATH
        ),
        "development_economics_binding_sha256": economics_binding[
            "manifest_sha256"
        ],
        "development_economics_binding_freeze_commit": economics_binding[
            "freeze_commit"
        ],
        "candidate_economics_reports_path": candidate_reports_path,
        "candidate_economics_reports_sha256": candidate_sha,
        "coverage_repair_economics_reports_path": coverage_binding["path"],
        "coverage_repair_economics_reports_sha256": coverage_sha,
        "react_economics_reports_path": react_binding["path"],
        "react_economics_reports_sha256": react_sha,
        "candidate_comparison": candidate_comparison,
        "coverage_repair_comparison": coverage_comparison,
    }


def validate_frozen_efficiency_addendum(
    addendum: dict[str, Any],
) -> None:
    if addendum.get("schema_version") != "0.1.0":
        raise ValueError("efficiency addendum schema version changed")
    if addendum.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("efficiency addendum protocol mismatch")
    if addendum.get("rule_id") != EFFICIENCY_RULE_ID:
        raise ValueError("efficiency addendum rule mismatch")
    if addendum.get("promotion_branch") != "efficiency":
        raise ValueError("efficiency addendum promotion branch changed")

    base_path_value = addendum.get("base_validation_selection_path")
    base_sha = addendum.get("base_validation_selection_sha256")
    if not isinstance(base_path_value, str) or not base_path_value:
        raise ValueError("efficiency addendum lacks base selection path")
    if not isinstance(base_sha, str) or len(base_sha) != 64:
        raise ValueError("efficiency addendum lacks base selection SHA-256")
    base_path = Path(base_path_value)
    if not base_path.is_absolute():
        base_path = ROOT / base_path
    if not base_path.is_file():
        raise ValueError("efficiency addendum base selection is missing")
    base_raw = base_path.read_bytes()
    if _sha256_bytes(base_raw) != base_sha:
        raise ValueError("efficiency addendum base selection hash mismatch")
    base_selection = json.loads(base_raw.decode("utf-8"))
    validate_frozen_validation_selection(base_selection)

    candidate_id = addendum.get("candidate_id")
    if (
        not isinstance(candidate_id, str)
        or candidate_id not in base_selection.get(
            "pending_efficiency_candidate_ids", []
        )
    ):
        raise ValueError("efficiency addendum candidate is not pending")
    if addendum.get("round") != base_selection.get("round"):
        raise ValueError("efficiency addendum round mismatch")

    recomputed = evaluate_efficiency_promotion(
        base_selection=base_selection,
        candidate_id=candidate_id,
        candidate_reports_path=addendum[
            "candidate_economics_reports_path"
        ],
        expected_candidate_sha256=addendum.get(
            "candidate_economics_reports_sha256"
        ),
    )
    for key, value in recomputed.items():
        if addendum.get(key) != value:
            raise ValueError(
                f"efficiency addendum recomputation mismatch: {key}"
            )


def freeze_efficiency_validation_authorization(
    *,
    base_selection_path: Path,
    candidate_id: str,
    candidate_reports_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    base_raw = base_selection_path.read_bytes()
    base_sha = _sha256_bytes(base_raw)
    base_selection = json.loads(base_raw.decode("utf-8"))
    validate_frozen_validation_selection(base_selection)
    round_id = base_selection["round"]

    output_dir.mkdir(parents=True, exist_ok=True)
    with _exclusive_gate_lock(
        output_dir,
        gate_name="validation-selection",
        round_id=round_id,
    ):
        # Re-read under the same lock so the append binds to the immutable
        # base artifact observed at authorization time.
        current_raw = base_selection_path.read_bytes()
        if _sha256_bytes(current_raw) != base_sha:
            raise ValueError(
                "base validation selection changed before efficiency append"
            )
        base_selection = json.loads(current_raw.decode("utf-8"))
        validate_frozen_validation_selection(base_selection)

        promotion = evaluate_efficiency_promotion(
            base_selection=base_selection,
            candidate_id=candidate_id,
            candidate_reports_path=str(candidate_reports_path),
        )
        addendum = {
            **promotion,
            "base_validation_selection_path": str(base_selection_path),
            "base_validation_selection_sha256": base_sha,
        }
        validate_frozen_efficiency_addendum(addendum)

        addendum_path = output_dir / (
            f"validation-efficiency-addendum-round-{round_id}"
            f"--{candidate_id}.json"
        )
        auth_path = output_dir / (
            f"{candidate_id}--validation-efficiency-auth.json"
        )
        if addendum_path.exists() or auth_path.exists():
            raise ValueError(
                "refusing to overwrite frozen efficiency validation artifact"
            )

        addendum_encoded = (
            json.dumps(
                addendum,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        addendum_sha = _sha256_bytes(addendum_encoded)
        authorization = {
            "schema_version": "0.1.0",
            "protocol_id": PROTOCOL_ID,
            "candidate_id": candidate_id,
            "round": round_id,
            "phase": "validation",
            "approved": True,
            "selection_rule": RULE_ID,
            "promotion_branch": "efficiency",
            "validation_selection_path": str(base_selection_path),
            "validation_selection_sha256": base_sha,
            "validation_slot_candidate_ids": list(
                base_selection["validation_slot_candidate_ids"]
            ),
            "efficiency_addendum_path": str(addendum_path),
            "efficiency_addendum_sha256": addendum_sha,
        }
        auth_encoded = (
            json.dumps(
                authorization,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")

        committed: list[Path] = []
        try:
            with tempfile.TemporaryDirectory(
                dir=output_dir,
                prefix=".validation-efficiency-",
            ) as staging_dir:
                staging = Path(staging_dir)
                staged_addendum = staging / addendum_path.name
                staged_auth = staging / auth_path.name
                staged_addendum.write_bytes(addendum_encoded)
                staged_auth.write_bytes(auth_encoded)

                for stage, final in (
                    (staged_addendum, addendum_path),
                    (staged_auth, auth_path),
                ):
                    os.replace(stage, final)
                    committed.append(final)
        except Exception:
            for committed_path in reversed(committed):
                try:
                    committed_path.unlink()
                except FileNotFoundError:
                    pass
            raise

        return addendum_path, auth_path


def freeze_validation_selection(
    *,
    round_id: int,
    results_root: Path,
    screening_selection_path: Path,
    output_dir: Path,
) -> tuple[Path, list[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with _exclusive_gate_lock(
        output_dir,
        gate_name="validation-selection",
        round_id=round_id,
    ):
        selection = select_validation_round(
            round_id=round_id,
            results_root=results_root,
            screening_selection_path=screening_selection_path,
        )
        validate_frozen_validation_selection(selection)

        selection_path = (
            output_dir / f"validation-selection-round-{round_id}.json"
        )
        selection_encoded = (
            json.dumps(
                selection,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        selection_sha = _sha256_bytes(selection_encoded)

        authorization_payloads = []
        for candidate_id in selection["validation_selected_candidate_ids"]:
            branch = selection["promotion_branch_by_candidate"][candidate_id]
            authorization = {
                "schema_version": "0.1.0",
                "protocol_id": PROTOCOL_ID,
                "candidate_id": candidate_id,
                "round": round_id,
                "phase": "validation",
                "approved": True,
                "validation_selected_candidate_ids": list(
                    selection["validation_selected_candidate_ids"]
                ),
                "selection_rule": RULE_ID,
                "promotion_branch": branch,
                "validation_selection_path": str(selection_path),
                "validation_selection_sha256": selection_sha,
            }
            auth_path = output_dir / f"{candidate_id}--validation-auth.json"
            encoded = (
                json.dumps(
                    authorization,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            authorization_payloads.append((auth_path, encoded))

        final_paths = [
            selection_path,
            *[auth_path for auth_path, _ in authorization_payloads],
        ]
        existing = [path for path in final_paths if path.exists()]
        if existing:
            raise ValueError(
                "refusing to overwrite frozen validation gate artifact(s): "
                + ", ".join(str(path) for path in existing)
            )

        committed: list[Path] = []
        try:
            with tempfile.TemporaryDirectory(
                dir=output_dir,
                prefix=".validation-gate-",
            ) as staging_dir:
                staging = Path(staging_dir)
                staged = []

                selection_stage = staging / selection_path.name
                selection_stage.write_bytes(selection_encoded)
                staged.append((selection_stage, selection_path))

                for auth_path, encoded in authorization_payloads:
                    stage = staging / auth_path.name
                    stage.write_bytes(encoded)
                    staged.append((stage, auth_path))

                for stage, final in staged:
                    # The exclusive lock ensures another compliant selector
                    # cannot race this finalization and overwrite frozen files.
                    os.replace(stage, final)
                    committed.append(final)
        except Exception:
            for committed_path in reversed(committed):
                try:
                    committed_path.unlink()
                except FileNotFoundError:
                    pass
            raise

        return (
            selection_path,
            [auth_path for auth_path, _ in authorization_payloads],
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument(
        "--results-root",
        default="results/procureharness-architecture-search-v0.1",
    )
    parser.add_argument(
        "--screening-selection-json",
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        default="evidence/procureharness-search-gates-v0.1",
    )
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    if args.preview:
        payload = select_validation_round(
            round_id=args.round,
            results_root=Path(args.results_root),
            screening_selection_path=Path(args.screening_selection_json),
        )
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return

    selection_path, authorization_paths = freeze_validation_selection(
        round_id=args.round,
        results_root=Path(args.results_root),
        screening_selection_path=Path(args.screening_selection_json),
        output_dir=Path(args.output_dir),
    )
    print(f"selection={selection_path}")
    for path in authorization_paths:
        print(f"authorization={path}")


if __name__ == "__main__":
    main()
