"""Freeze the screening -> development-confirmation selection for one round.

This is an offline selector. It reads completed 001-020 x1 screening summaries,
requires the complete six-candidate round, applies the preregistered
quality-first lexicographic ordering, and emits at most two candidate
authorizations. It makes no model/provider calls.
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

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX local environments
    fcntl = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench.procureharness import get_candidate
from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    PROTOCOL_ID,
    round_candidate_ids,
)

REGISTRY_PATH = ROOT / "docs" / "procureharness-candidate-registry-v0.1.json"
RULE_ID = "frozen_screening_selection_v0.1"
SCREENING_RANKING_PRIORITY = [
    {"metric": "feasible_obligation_success", "direction": "desc"},
    {"metric": "strict_v02", "direction": "desc"},
    {"metric": "economic_objective", "direction": "desc"},
    {"metric": "obligation_resolution_rate", "direction": "desc"},
    {"metric": "known_cost_usd", "direction": "asc"},
    {"metric": "total_tokens", "direction": "asc"},
    {"metric": "candidate_id", "direction": "asc"},
]


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


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _expected_run_keys() -> list[tuple[str, int]]:
    return [(episode_id, 1) for episode_id in DEVELOPMENT_EPISODES]


def _aggregate_candidate(
    *,
    candidate_id: str,
    round_id: int,
    summary_path: Path,
) -> dict[str, Any]:
    raw = summary_path.read_bytes()
    summary = json.loads(raw.decode("utf-8"))

    if summary.get("protocol_id") != PROTOCOL_ID:
        raise ValueError(f"screening protocol mismatch: {candidate_id}")
    if summary.get("candidate_id") != candidate_id:
        raise ValueError(f"screening candidate mismatch: {candidate_id}")
    if summary.get("round") != round_id:
        raise ValueError(f"screening round mismatch: {candidate_id}")
    if summary.get("phase") != "screening":
        raise ValueError(f"candidate is not a screening summary: {candidate_id}")
    if summary.get("planned_runs") != 20:
        raise ValueError(f"screening planned_runs must equal 20: {candidate_id}")
    if summary.get("completed_runs") != 20:
        raise ValueError(f"screening must complete 20 runs: {candidate_id}")
    if summary.get("execution_failures") != 0:
        raise ValueError(f"screening execution is not clean: {candidate_id}")

    rows = summary.get("rows")
    if not isinstance(rows, list) or len(rows) != 20:
        raise ValueError(f"screening summary requires 20 rows: {candidate_id}")

    observed_keys = [
        (row.get("episode_id"), row.get("repeat"))
        for row in rows
        if isinstance(row, dict)
    ]
    if observed_keys != _expected_run_keys():
        raise ValueError(
            f"screening run grid changed for {candidate_id}"
        )

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
                f"screening row missing obligation_resolved: {candidate_id}"
            )
        if not isinstance(row_actionable, int) or isinstance(row_actionable, bool):
            raise ValueError(
                f"screening row missing obligation_actionable: {candidate_id}"
            )
        if row_resolved < 0 or row_actionable < 0 or row_resolved > row_actionable:
            raise ValueError(
                f"invalid obligation counts in screening: {candidate_id}"
            )
        resolved += row_resolved
        actionable += row_actionable

    if actionable <= 0:
        raise ValueError(
            f"screening round has no actionable obligations: {candidate_id}"
        )
    obligation_resolution_rate = resolved / actionable

    costs = [row.get("known_cost_usd") for row in rows]
    cost_complete = all(_finite_number(value) for value in costs)
    known_cost_usd = (
        math.fsum(float(value) for value in costs)
        if cost_complete
        else None
    )
    if known_cost_usd is not None and not math.isfinite(known_cost_usd):
        raise ValueError(f"screening cost total is non-finite: {candidate_id}")

    tokens = [row.get("total_tokens") for row in rows]
    tokens_complete = all(
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        for value in tokens
    )
    total_tokens = (
        sum(tokens)
        if tokens_complete
        else None
    )

    return {
        "candidate_id": candidate_id,
        "round": round_id,
        "feasible_obligation_success": feasible,
        "strict_v02": strict,
        "economic_objective": economic,
        "obligation_resolved": resolved,
        "obligation_actionable": actionable,
        "obligation_resolution_rate": obligation_resolution_rate,
        "known_cost_usd": known_cost_usd,
        "known_cost_complete": cost_complete,
        "total_tokens": total_tokens,
        "total_tokens_complete": tokens_complete,
        "screening_summary_path": str(summary_path),
        "screening_summary_sha256": _sha256_bytes(raw),
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
        raise ValueError(f"non-numeric screening ranking metric: {metric}")
    return -value if direction == "desc" else value


def _ranking_key(row: dict[str, Any]):
    return tuple(
        _ranking_value(
            row,
            metric=entry["metric"],
            direction=entry["direction"],
        )
        for entry in SCREENING_RANKING_PRIORITY
    )


def select_screening_round(
    *,
    round_id: int,
    results_root: Path,
) -> dict[str, Any]:
    if round_id not in (1, 2, 3):
        raise ValueError("round must be 1, 2, or 3")

    registry = _load_json(REGISTRY_PATH)
    rule = registry.get("screening_selection_rule")
    if not isinstance(rule, dict) or rule.get("rule_id") != RULE_ID:
        raise ValueError("screening selection rule is not frozen")
    if rule.get("required_candidates_per_round") != 6:
        raise ValueError("screening selection must require six candidates")
    if rule.get("max_selected_candidates") != 2:
        raise ValueError("screening selection max must remain two")
    if rule.get("method") != "lexicographic":
        raise ValueError("screening selection method changed")
    if rule.get("missing_resource_values") != "rank_last":
        raise ValueError("screening missing-resource policy changed")
    if rule.get("priority") != SCREENING_RANKING_PRIORITY:
        raise ValueError("screening ranking priority changed")

    candidate_ids = round_candidate_ids(round_id)
    if len(candidate_ids) != 6:
        raise ValueError("frozen round registry must contain six candidates")

    ranking_rows = []
    for candidate_id in candidate_ids:
        config = get_candidate(candidate_id)
        if config.round != round_id:
            raise ValueError("candidate registry round mismatch")
        summary_path = (
            results_root
            / candidate_id
            / "screening"
            / "summary.json"
        )
        if not summary_path.is_file():
            raise ValueError(
                f"missing screening summary for {candidate_id}: {summary_path}"
            )
        ranking_rows.append(_aggregate_candidate(
            candidate_id=candidate_id,
            round_id=round_id,
            summary_path=summary_path,
        ))

    ranking_rows.sort(key=_ranking_key)
    selected = [
        row["candidate_id"]
        for row in ranking_rows[:2]
    ]

    return {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "rule_id": RULE_ID,
        "round": round_id,
        "candidate_ids": candidate_ids,
        "selected_candidate_ids": selected,
        "ranking": ranking_rows,
    }


def validate_frozen_screening_selection(
    selection: dict[str, Any],
) -> None:
    if selection.get("schema_version") != "0.1.0":
        raise ValueError("screening selection schema version changed")
    if selection.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("screening selection protocol mismatch")
    if selection.get("rule_id") != RULE_ID:
        raise ValueError("screening selection rule mismatch")

    round_id = selection.get("round")
    if round_id not in (1, 2, 3):
        raise ValueError("screening selection round is invalid")
    candidate_ids = round_candidate_ids(round_id)
    if selection.get("candidate_ids") != candidate_ids:
        raise ValueError("screening selection candidate grid changed")

    ranking = selection.get("ranking")
    if not isinstance(ranking, list) or len(ranking) != 6:
        raise ValueError("screening selection must contain six ranking rows")

    recomputed = []
    for row in ranking:
        if not isinstance(row, dict):
            raise ValueError("screening ranking row must be an object")
        candidate_id = row.get("candidate_id")
        if candidate_id not in candidate_ids:
            raise ValueError("screening ranking contains unknown candidate")
        path_value = row.get("screening_summary_path")
        expected_sha = row.get("screening_summary_sha256")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError("screening ranking row lacks summary path")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise ValueError("screening ranking row lacks summary SHA-256")
        summary_path = Path(path_value)
        if not summary_path.is_absolute():
            summary_path = ROOT / summary_path
        if not summary_path.is_file():
            raise ValueError(
                f"bound screening summary missing: {summary_path}"
            )
        raw = summary_path.read_bytes()
        if _sha256_bytes(raw) != expected_sha:
            raise ValueError(
                f"bound screening summary hash mismatch: {summary_path}"
            )
        aggregate = _aggregate_candidate(
            candidate_id=candidate_id,
            round_id=round_id,
            summary_path=Path(path_value),
        )
        if aggregate != row:
            raise ValueError(
                f"screening ranking row does not match bound summary: "
                f"{candidate_id}"
            )
        recomputed.append(aggregate)

    if len({row["candidate_id"] for row in recomputed}) != 6:
        raise ValueError("screening ranking candidate IDs are not unique")
    recomputed.sort(key=_ranking_key)
    if recomputed != ranking:
        raise ValueError("screening ranking order changed")
    expected_selected = [
        row["candidate_id"]
        for row in recomputed[:2]
    ]
    if selection.get("selected_candidate_ids") != expected_selected:
        raise ValueError("screening selected candidates changed")


def freeze_selection(
    *,
    round_id: int,
    results_root: Path,
    output_dir: Path,
) -> tuple[Path, list[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with _exclusive_gate_lock(
        output_dir,
        gate_name="screening-selection",
        round_id=round_id,
    ):
        selection = select_screening_round(
            round_id=round_id,
            results_root=results_root,
        )
        validate_frozen_screening_selection(selection)

        selection_path = (
            output_dir / f"screening-selection-round-{round_id}.json"
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
        for candidate_id in selection["selected_candidate_ids"]:
            authorization = {
                "schema_version": "0.1.0",
                "protocol_id": PROTOCOL_ID,
                "candidate_id": candidate_id,
                "round": round_id,
                "phase": "development_confirmation",
                "approved": True,
                "screening_complete": True,
                "screening_selected_candidate_ids": list(
                    selection["selected_candidate_ids"]
                ),
                "selection_rule": RULE_ID,
                "screening_selection_path": str(selection_path),
                "screening_selection_sha256": selection_sha,
            }
            auth_path = output_dir / (
                f"{candidate_id}--development-confirmation-auth.json"
            )
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
                "refusing to overwrite frozen screening gate artifact(s): "
                + ", ".join(str(path) for path in existing)
            )

        committed: list[Path] = []
        try:
            with tempfile.TemporaryDirectory(
                dir=output_dir,
                prefix=".screening-gate-",
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
        "--output-dir",
        default="evidence/procureharness-search-gates-v0.1",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the deterministic selection without writing freeze files.",
    )
    args = parser.parse_args()

    if args.preview:
        payload = select_screening_round(
            round_id=args.round,
            results_root=Path(args.results_root),
        )
        print(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return

    selection_path, authorization_paths = freeze_selection(
        round_id=args.round,
        results_root=Path(args.results_root),
        output_dir=Path(args.output_dir),
    )
    print(f"selection={selection_path}")
    for path in authorization_paths:
        print(f"authorization={path}")


if __name__ == "__main__":
    main()
