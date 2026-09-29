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
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
RULE_ID = "frozen_validation_entry_lexicographic_v0.1"

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
    """Serialize one gate freeze and fail closed on concurrent invocation."""
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / f".{gate_name}-round-{round_id}.lock"
    try:
        fd = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644,
        )
    except FileExistsError as exc:
        raise ValueError(
            f"{gate_name} round {round_id} freeze is already in progress: "
            f"{lock_path}"
        ) from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


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
    unresolved_efficiency = []
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
            unresolved_efficiency.append(candidate_id)

    if unresolved_efficiency:
        raise ValueError(
            "cannot freeze validation selection while efficiency-only "
            "promotion remains unresolved; require frozen economic comparison "
            "gate for: " + ", ".join(unresolved_efficiency)
        )

    eligible = [
        row for row in rows
        if row["development_confirmation_floor_passed"]
        and row["quality_promotion_passed"]
    ]
    eligible.sort(key=_ranking_key)
    selected = [row["candidate_id"] for row in eligible[:2]]

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

    unresolved = [
        row["candidate_id"]
        for row in recomputed
        if (
            row["development_confirmation_floor_passed"]
            and not row["quality_promotion_passed"]
        )
    ]
    if unresolved:
        raise ValueError(
            "validation selection improperly bypasses unresolved efficiency gate"
        )

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
