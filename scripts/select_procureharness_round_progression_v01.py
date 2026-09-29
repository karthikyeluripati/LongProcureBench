"""Freeze ProcureHarness search progression after completed rounds.

This gate is offline and deterministic. It binds completed search evidence,
recomputes the frozen plateau/budget stop conditions, and emits later-round
screening authorizations only when the protocol permits another round.

Round 2 currently closes the search under the preregistered two-round plateau
rule, so no Round-3 screening authorization is emitted.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MODEL,
    PROTOCOL_ID,
    round_candidate_ids,
)
from select_procureharness_screening_v01 import (
    validate_frozen_screening_selection,
)
from select_procureharness_validation_v01 import (
    _load_development_economics_binding,
    evaluate_efficiency_promotion,
    validate_frozen_validation_selection,
)

RULE_ID = "frozen_round_progression_v0.1"
SCHEMA_VERSION = "0.1.0"
ROUND1_COMPLETED = 1
ROUND2_COMPLETED = 2
ROUND2 = 2
ROUND3 = 3

PROTOCOL_PATH = (
    ROOT / "docs" / "procureharness-architecture-search-v0.1-protocol.json"
)
SCREENING_MANIFEST_PATH = (
    ROOT / "evidence" / "procureharness-round1-screening-v0.1" / "manifest.json"
)
SCREENING_SELECTION_PATH = (
    ROOT / "evidence" / "procureharness-search-gates-v0.1"
    / "screening-selection-round-1.json"
)
CONFIRMATION_MANIFEST_PATH = (
    ROOT / "evidence" / "procureharness-round1-confirmation-v0.1" / "manifest.json"
)
VALIDATION_SELECTION_PATH = (
    ROOT / "evidence" / "procureharness-search-gates-v0.1"
    / "validation-selection-round-1.json"
)
ECONOMICS_MANIFEST_PATH = (
    ROOT / "evidence" / "procureharness-development-economics-v0.1"
    / "manifest.json"
)
EFFICIENCY_GATE_RESULT_PATH = (
    ROOT / "evidence" / "procureharness-development-economics-v0.1"
    / "efficiency-gate-result.json"
)

ROUND1_PROGRESSION_PATH = (
    ROOT / "evidence" / "procureharness-search-gates-v0.1"
    / "round-progression-after-round-1.json"
)
ROUND2_SCREENING_MANIFEST_PATH = (
    ROOT / "evidence" / "procureharness-round2-screening-v0.1"
    / "manifest.json"
)
ROUND2_SCREENING_SELECTION_PATH = (
    ROOT / "evidence" / "procureharness-search-gates-v0.1"
    / "screening-selection-round-2.json"
)
ROUND2_CONFIRMATION_MANIFEST_PATH = (
    ROOT / "evidence" / "procureharness-round2-confirmation-v0.1"
    / "manifest.json"
)
ROUND2_VALIDATION_SELECTION_PATH = (
    ROOT / "evidence" / "procureharness-search-gates-v0.1"
    / "validation-selection-round-2.json"
)
ROUND2_ECONOMICS_MANIFEST_PATH = (
    ROOT / "evidence" / "procureharness-round2-economics-v0.1"
    / "manifest.json"
)
ROUND2_EFFICIENCY_GATE_RESULT_PATH = (
    ROOT / "evidence" / "procureharness-round2-economics-v0.1"
    / "efficiency-gate-result.json"
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _binding(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"required progression evidence is missing: {path}")
    return {
        "path": _repo_rel(path),
        "sha256": _sha256_path(path),
    }


@contextmanager
def _exclusive_progression_lock(output_dir: Path, completed_round: int):
    if fcntl is None:
        raise RuntimeError(
            "ProcureHarness round progression requires POSIX advisory locks"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = (
        output_dir
        / f".round-progression-after-round-{completed_round}.lock"
    )
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise ValueError(
                "round progression freeze is already in progress: "
                f"{lock_path}"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "completed_round": completed_round,
                },
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _validate_manifest_entries(
    *,
    manifest: dict[str, Any],
    field: str,
    expected_paths: set[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    rows = manifest.get(field)
    if not isinstance(rows, list):
        raise ValueError(f"{label} manifest {field} must be a list")

    by_path: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label} manifest {field} row must be an object")
        path_value = row.get("path")
        expected_sha = row.get("sha256")
        expected_bytes = row.get("bytes")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError(f"{label} manifest {field} path is invalid")
        if path_value in by_path:
            raise ValueError(
                f"{label} manifest {field} contains duplicate path: "
                f"{path_value}"
            )
        if (
            not isinstance(expected_sha, str)
            or len(expected_sha) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha)
        ):
            raise ValueError(
                f"{label} manifest {field} SHA-256 is invalid: {path_value}"
            )
        if (
            not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes < 0
        ):
            raise ValueError(
                f"{label} manifest {field} byte count is invalid: "
                f"{path_value}"
            )
        by_path[path_value] = row

    if set(by_path) != expected_paths:
        missing = sorted(expected_paths - set(by_path))
        unexpected = sorted(set(by_path) - expected_paths)
        raise ValueError(
            f"{label} manifest {field} path set changed: "
            f"missing={missing}, unexpected={unexpected}"
        )

    for path_value, row in by_path.items():
        path = ROOT / path_value
        if not path.is_file():
            raise ValueError(
                f"{label} manifested file is missing: {path_value}"
            )
        raw = path.read_bytes()
        if len(raw) != row["bytes"]:
            raise ValueError(
                f"{label} manifested byte count mismatch: {path_value}"
            )
        if sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(
                f"{label} manifested SHA-256 mismatch: {path_value}"
            )
    return by_path


def _expected_summary_row(
    *,
    raw_result: dict[str, Any],
    episode_id: str,
    repeat: int,
) -> dict[str, Any]:
    evaluation = raw_result.get("evaluation") or {}
    metrics = raw_result.get("policy_metrics") or {}
    obligations = evaluation.get("obligations") or {}
    return {
        "episode_id": episode_id,
        "repeat": repeat,
        "status": raw_result["status"],
        "terminal_feasible": bool(evaluation.get("episode_success")),
        "feasible_obligation_success": bool(
            evaluation.get("feasible_obligation_success")
        ),
        "strict_v02": bool(evaluation.get("episode_success_v02")),
        "economic_objective": bool(
            (evaluation.get("economic_objective") or {}).get("satisfied")
        ),
        "obligation_resolved": obligations.get("resolved"),
        "obligation_actionable": obligations.get("actionable"),
        "obligation_resolution_rate": obligations.get("resolution_rate"),
        "accepted_actions": (
            (evaluation.get("efficiency") or {}).get("accepted_actions")
        ),
        "model_calls": metrics.get("model_calls"),
        "total_tokens": metrics.get("total_tokens"),
        "latency_ms": metrics.get("latency_ms"),
        "known_cost_usd": metrics.get("cost_usd"),
        "deterministic_action_fraction": metrics.get(
            "deterministic_action_fraction"
        ),
    }


def _expected_candidate_source_paths(
    *,
    evidence_root: Path,
    candidate_ids: list[str],
    phase: str,
    repeats: tuple[int, ...],
) -> set[str]:
    paths: set[str] = set()
    for candidate_id in candidate_ids:
        root = evidence_root / "results" / candidate_id / phase
        paths.add(_repo_rel(root / "summary.json"))
        for repeat in repeats:
            for episode_id in DEVELOPMENT_EPISODES:
                paths.add(
                    _repo_rel(
                        root
                        / f"r{repeat}"
                        / f"{episode_id}.json"
                    )
                )
    return paths


def _validate_candidate_evidence_tree(
    *,
    evidence_root: Path,
    candidate_id: str,
    phase: str,
    repeats: tuple[int, ...],
    source_entries: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    root = evidence_root / "results" / candidate_id / phase
    summary_path = root / "summary.json"
    summary_rel = _repo_rel(summary_path)
    if summary_rel not in source_entries:
        raise ValueError(
            f"{candidate_id} summary is not bound by its evidence manifest"
        )
    summary = _load_json(summary_path)

    expected_run_count = len(DEVELOPMENT_EPISODES) * len(repeats)
    if summary.get("candidate_id") != candidate_id:
        raise ValueError(f"{candidate_id} summary candidate mismatch")
    if summary.get("phase") != phase:
        raise ValueError(f"{candidate_id} summary phase mismatch")
    if summary.get("planned_runs") != expected_run_count:
        raise ValueError(f"{candidate_id} summary planned_runs mismatch")
    if summary.get("completed_runs") != expected_run_count:
        raise ValueError(f"{candidate_id} summary completed_runs mismatch")
    if summary.get("execution_failures") != 0:
        raise ValueError(f"{candidate_id} summary execution is not clean")

    rows = summary.get("rows")
    if not isinstance(rows, list) or len(rows) != expected_run_count:
        raise ValueError(f"{candidate_id} summary row count mismatch")

    expected_keys = [
        (episode_id, repeat)
        for repeat in repeats
        for episode_id in DEVELOPMENT_EPISODES
    ]
    observed_keys = [
        (row.get("episode_id"), row.get("repeat"))
        for row in rows
        if isinstance(row, dict)
    ]
    if observed_keys != expected_keys:
        raise ValueError(f"{candidate_id} summary run grid changed")

    expected_policy_id = (
        f"procureharness--{candidate_id}--{MODEL}"
    )
    expected_names = {
        f"{episode_id}.json"
        for episode_id in DEVELOPMENT_EPISODES
    }

    expected_rows = []
    for episode_id, repeat in expected_keys:
        repeat_dir = root / f"r{repeat}"
        actual_names = {
            path.name
            for path in repeat_dir.iterdir()
            if path.is_file() and path.suffix == ".json"
        }
        if actual_names != expected_names:
            raise ValueError(
                f"{candidate_id} repeat {repeat} raw filename grid changed"
            )

        raw_path = repeat_dir / f"{episode_id}.json"
        raw_rel = _repo_rel(raw_path)
        if raw_rel not in source_entries:
            raise ValueError(
                f"{candidate_id} raw result is not bound by manifest: "
                f"{raw_rel}"
            )
        raw_result = _load_json(raw_path)
        if raw_result.get("episode_id") != episode_id:
            raise ValueError(f"{candidate_id} raw episode mismatch")
        if (raw_result.get("policy") or {}).get("policy_id") != (
            expected_policy_id
        ):
            raise ValueError(f"{candidate_id} raw policy_id mismatch")
        expected_rows.append(
            _expected_summary_row(
                raw_result=raw_result,
                episode_id=episode_id,
                repeat=repeat,
            )
        )

    if rows != expected_rows:
        raise ValueError(
            f"{candidate_id} summary metrics do not match raw results"
        )
    return summary_rel, source_entries[summary_rel]["sha256"]


def _load_bound_json_row(
    *,
    row: dict[str, Any],
    label: str,
) -> Any:
    path_value = row.get("path")
    expected_sha = row.get("sha256")
    expected_bytes = row.get("bytes")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{label} binding path is invalid")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError(f"{label} binding SHA-256 is invalid")

    path = ROOT / path_value
    if not path.is_file():
        raise ValueError(f"{label} bound file is missing: {path_value}")
    raw = path.read_bytes()
    if (
        isinstance(expected_bytes, int)
        and not isinstance(expected_bytes, bool)
        and len(raw) != expected_bytes
    ):
        raise ValueError(f"{label} binding byte count mismatch")
    if sha256(raw).hexdigest() != expected_sha:
        raise ValueError(f"{label} binding SHA-256 mismatch")
    return json.loads(raw.decode("utf-8"))


def _recompute_efficiency_gate(
    *,
    validation_selection: dict[str, Any],
    economics_manifest: dict[str, Any],
    recorded_result: dict[str, Any],
) -> tuple[list[str], list[str]]:
    candidate_rows = economics_manifest.get("candidate_reports")
    comparisons_row = economics_manifest.get("comparisons")
    if not isinstance(candidate_rows, dict):
        raise ValueError("development economics candidate reports missing")
    if not isinstance(comparisons_row, dict):
        raise ValueError("development economics comparisons binding missing")

    pending = validation_selection.get("pending_efficiency_candidate_ids")
    if not isinstance(pending, list):
        raise ValueError("Round-1 pending efficiency candidate set invalid")
    if set(candidate_rows) != set(pending):
        raise ValueError(
            "development economics candidate-report set does not match "
            "pending Round-1 candidates"
        )

    comparisons = _load_bound_json_row(
        row=comparisons_row,
        label="development economics comparisons",
    )
    if (
        not isinstance(comparisons, dict)
        or not isinstance(comparisons.get("candidates"), dict)
        or set(comparisons["candidates"]) != set(pending)
    ):
        raise ValueError(
            "development economics candidate comparisons are incomplete"
        )

    recorded_outcomes = recorded_result.get("outcomes")
    if (
        not isinstance(recorded_outcomes, dict)
        or set(recorded_outcomes) != set(pending)
    ):
        raise ValueError("Round-1 efficiency outcome map is incomplete")

    approved: list[str] = []
    rejected: list[str] = []
    for candidate_id in pending:
        binding = candidate_rows[candidate_id]
        if not isinstance(binding, dict):
            raise ValueError(
                f"{candidate_id} economics report binding is invalid"
            )
        candidate_path = binding.get("path")
        candidate_sha = binding.get("sha256")
        if not isinstance(candidate_path, str) or not candidate_path:
            raise ValueError(
                f"{candidate_id} economics report path is invalid"
            )
        if not isinstance(candidate_sha, str) or len(candidate_sha) != 64:
            raise ValueError(
                f"{candidate_id} economics report SHA-256 is invalid"
            )

        outcome = recorded_outcomes[candidate_id]
        if not isinstance(outcome, dict):
            raise ValueError(
                f"{candidate_id} recorded efficiency outcome is invalid"
            )
        if outcome.get("candidate_id") != candidate_id:
            raise ValueError(
                f"{candidate_id} recorded efficiency candidate mismatch"
            )
        if outcome.get("comparison") != (
            comparisons["candidates"][candidate_id]
        ):
            raise ValueError(
                f"{candidate_id} recorded economics comparison changed"
            )

        try:
            promotion = evaluate_efficiency_promotion(
                base_selection=validation_selection,
                candidate_id=candidate_id,
                candidate_reports_path=candidate_path,
                expected_candidate_sha256=candidate_sha,
            )
        except ValueError as exc:
            reason = str(exc)
            if outcome.get("approved") is not False:
                raise ValueError(
                    f"{candidate_id} recorded approval disagrees with "
                    "recomputed efficiency rejection"
                ) from exc
            if outcome.get("status") != "not_promoted":
                raise ValueError(
                    f"{candidate_id} recorded rejection status changed"
                ) from exc
            if outcome.get("reason") != reason:
                raise ValueError(
                    f"{candidate_id} recorded rejection reason disagrees "
                    "with recomputed frozen economics"
                ) from exc
            rejected.append(candidate_id)
            continue

        if outcome.get("approved") is not True:
            raise ValueError(
                f"{candidate_id} recorded rejection disagrees with "
                "recomputed efficiency approval"
            )
        if outcome.get("status") != "authorized":
            raise ValueError(
                f"{candidate_id} recorded approval status changed"
            )
        if outcome.get("promotion") != promotion:
            raise ValueError(
                f"{candidate_id} recorded promotion does not match "
                "recomputed frozen economics"
            )
        approved.append(candidate_id)

    if recorded_result.get("authorized_candidate_ids") != approved:
        raise ValueError(
            "Round-1 efficiency authorized candidate list changed"
        )
    if recorded_result.get("not_promoted_candidate_ids") != rejected:
        raise ValueError(
            "Round-1 efficiency rejected candidate list changed"
        )
    return approved, rejected


def _write_recoverable_artifact_set(
    *,
    output_dir: Path,
    artifacts: list[tuple[Path, bytes]],
) -> None:
    for path, encoded in artifacts:
        if not path.exists():
            continue
        if path.read_bytes() != encoded:
            raise ValueError(
                "existing round-progression artifact does not match "
                f"recomputed frozen content: {path}"
            )

    with tempfile.TemporaryDirectory(
        dir=output_dir,
        prefix=".round-progression-recovery-",
    ) as staging_dir:
        staging = Path(staging_dir)
        for path, encoded in artifacts:
            if path.exists():
                continue
            stage = staging / path.name
            stage.write_bytes(encoded)
            with stage.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(stage, path)

    for path, encoded in artifacts:
        if not path.is_file() or path.read_bytes() != encoded:
            raise ValueError(
                f"round-progression artifact set incomplete: {path}"
            )


def _validate_round1_inputs() -> dict[str, Any]:
    protocol = _load_json(PROTOCOL_PATH)
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("progression protocol_id mismatch")

    procedure = protocol.get("search_procedure")
    if not isinstance(procedure, dict):
        raise ValueError("search procedure missing from frozen protocol")
    if procedure.get("max_rounds") != 3:
        raise ValueError("frozen max_rounds changed")
    if procedure.get("max_new_candidates_per_round") != 6:
        raise ValueError("frozen per-round candidate budget changed")
    if procedure.get("max_unique_candidates") != 18:
        raise ValueError("frozen unique-candidate budget changed")

    ceiling = procedure.get("ceiling_stop_rule")
    if not isinstance(ceiling, dict) or ceiling.get("plateau_rounds") != 2:
        raise ValueError("frozen plateau stop rule changed")

    round1_ids = round_candidate_ids(1)
    round2_ids = round_candidate_ids(2)
    if len(round1_ids) != 6 or len(round2_ids) != 6:
        raise ValueError("frozen candidate round cardinality changed")

    screening_manifest = _load_json(SCREENING_MANIFEST_PATH)
    if screening_manifest.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Round-1 screening manifest protocol mismatch")
    if (
        screening_manifest.get("round") != 1
        or screening_manifest.get("phase") != "screening"
        or screening_manifest.get("candidate_ids") != round1_ids
        or screening_manifest.get("repeats") != 1
        or screening_manifest.get("total_runs") != 120
    ):
        raise ValueError("Round-1 screening manifest is incomplete")

    screening_root = SCREENING_MANIFEST_PATH.parent
    screening_source_entries = _validate_manifest_entries(
        manifest=screening_manifest,
        field="source_files",
        expected_paths=_expected_candidate_source_paths(
            evidence_root=screening_root,
            candidate_ids=round1_ids,
            phase="screening",
            repeats=(1,),
        ),
        label="Round-1 screening",
    )

    screening_selection = _load_json(SCREENING_SELECTION_PATH)
    validate_frozen_screening_selection(screening_selection)
    if screening_selection.get("round") != 1:
        raise ValueError("Round-1 screening selection round mismatch")

    selected = screening_selection.get("selected_candidate_ids")
    if not isinstance(selected, list) or not selected:
        raise ValueError("Round-1 screening selected no confirmation candidates")

    expected_screening_gate_paths = {
        _repo_rel(SCREENING_SELECTION_PATH),
        *{
            _repo_rel(
                SCREENING_SELECTION_PATH.parent
                / f"{candidate_id}--development-confirmation-auth.json"
            )
            for candidate_id in selected
        },
    }
    _validate_manifest_entries(
        manifest=screening_manifest,
        field="gate_files",
        expected_paths=expected_screening_gate_paths,
        label="Round-1 screening",
    )

    screening_summary_bindings = {}
    for candidate_id in round1_ids:
        summary_rel, summary_sha = _validate_candidate_evidence_tree(
            evidence_root=screening_root,
            candidate_id=candidate_id,
            phase="screening",
            repeats=(1,),
            source_entries=screening_source_entries,
        )
        screening_summary_bindings[candidate_id] = (
            summary_rel,
            summary_sha,
        )

    for row in screening_selection.get("ranking") or []:
        candidate_id = row.get("candidate_id")
        expected_path, expected_sha = screening_summary_bindings[
            candidate_id
        ]
        if row.get("screening_summary_path") != expected_path:
            raise ValueError(
                f"{candidate_id} screening selection summary path is not "
                "the manifested summary"
            )
        if row.get("screening_summary_sha256") != expected_sha:
            raise ValueError(
                f"{candidate_id} screening selection summary hash is not "
                "the manifested summary hash"
            )

    confirmation_manifest = _load_json(CONFIRMATION_MANIFEST_PATH)
    if confirmation_manifest.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Round-1 confirmation manifest protocol mismatch")
    if (
        confirmation_manifest.get("round") != 1
        or confirmation_manifest.get("phase") != "development_confirmation"
        or confirmation_manifest.get("candidate_ids") != selected
        or confirmation_manifest.get("repeats") != 3
        or confirmation_manifest.get("total_runs") != 60 * len(selected)
    ):
        raise ValueError("Round-1 confirmation manifest is incomplete")

    confirmation_root = CONFIRMATION_MANIFEST_PATH.parent
    confirmation_source_entries = _validate_manifest_entries(
        manifest=confirmation_manifest,
        field="source_files",
        expected_paths=_expected_candidate_source_paths(
            evidence_root=confirmation_root,
            candidate_ids=selected,
            phase="development_confirmation",
            repeats=(1, 2, 3),
        ),
        label="Round-1 confirmation",
    )

    validation_selection = _load_json(VALIDATION_SELECTION_PATH)
    validate_frozen_validation_selection(validation_selection)
    if validation_selection.get("round") != 1:
        raise ValueError("Round-1 validation selection round mismatch")
    if validation_selection.get("screening_selected_candidate_ids") != selected:
        raise ValueError(
            "Round-1 screening/validation-entry candidate binding changed"
        )

    expected_confirmation_gate_paths = {
        _repo_rel(VALIDATION_SELECTION_PATH),
        *{
            _repo_rel(
                VALIDATION_SELECTION_PATH.parent
                / f"{candidate_id}--validation-auth.json"
            )
            for candidate_id in (
                validation_selection.get(
                    "validation_selected_candidate_ids"
                )
                or []
            )
        },
    }
    _validate_manifest_entries(
        manifest=confirmation_manifest,
        field="gate_files",
        expected_paths=expected_confirmation_gate_paths,
        label="Round-1 confirmation",
    )

    confirmation_summary_bindings = {}
    for candidate_id in selected:
        summary_rel, summary_sha = _validate_candidate_evidence_tree(
            evidence_root=confirmation_root,
            candidate_id=candidate_id,
            phase="development_confirmation",
            repeats=(1, 2, 3),
            source_entries=confirmation_source_entries,
        )
        confirmation_summary_bindings[candidate_id] = (
            summary_rel,
            summary_sha,
        )

    for row in validation_selection.get("confirmation_rows") or []:
        candidate_id = row.get("candidate_id")
        expected_path, expected_sha = confirmation_summary_bindings[
            candidate_id
        ]
        if row.get("confirmation_summary_path") != expected_path:
            raise ValueError(
                f"{candidate_id} validation selection summary path is not "
                "the manifested confirmation summary"
            )
        if row.get("confirmation_summary_sha256") != expected_sha:
            raise ValueError(
                f"{candidate_id} validation selection summary hash is not "
                "the manifested confirmation summary hash"
            )

    # Revalidate the frozen economics package and its real Git snapshot.
    economics_binding = _load_development_economics_binding()
    economics_manifest = _load_json(ECONOMICS_MANIFEST_PATH)
    if economics_binding.get("freeze_commit") != economics_manifest.get(
        "freeze_commit"
    ):
        raise ValueError("development economics binding freeze mismatch")

    efficiency_result = _load_json(EFFICIENCY_GATE_RESULT_PATH)
    if efficiency_result.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Round-1 efficiency gate protocol mismatch")
    if efficiency_result.get("provider_calls") != 0:
        raise ValueError("Round-1 efficiency gate unexpectedly used providers")
    if efficiency_result.get("base_validation_selection_path") != _repo_rel(
        VALIDATION_SELECTION_PATH
    ):
        raise ValueError("Round-1 efficiency gate base selection changed")
    if efficiency_result.get(
        "development_economics_manifest_sha256"
    ) != _sha256_path(ECONOMICS_MANIFEST_PATH):
        raise ValueError("Round-1 efficiency gate economics binding drift")

    quality_selected = validation_selection.get(
        "validation_selected_candidate_ids"
    )
    if not isinstance(quality_selected, list):
        raise ValueError("Round-1 validation-selected candidate set invalid")

    efficiency_selected, rejected = _recompute_efficiency_gate(
        validation_selection=validation_selection,
        economics_manifest=economics_manifest,
        recorded_result=efficiency_result,
    )

    final_validation_candidates = list(
        dict.fromkeys([*quality_selected, *efficiency_selected])
    )
    if final_validation_candidates:
        raise ValueError(
            "Round-1 progression v0.1 supports only the observed "
            "no-validation-candidate branch; validation evidence must be "
            "frontier-scored before a later-round authorization"
        )

    pending = validation_selection.get("pending_efficiency_candidate_ids")
    if not isinstance(pending, list):
        raise ValueError("Round-1 pending efficiency candidate set invalid")
    if sorted(pending) != sorted(rejected):
        raise ValueError(
            "Round-1 economics gate did not resolve every pending candidate"
        )

    return {
        "protocol": protocol,
        "round1_candidate_ids": round1_ids,
        "round2_candidate_ids": round2_ids,
        "screening_selection": screening_selection,
        "validation_selection": validation_selection,
        "efficiency_result": efficiency_result,
    }


def compute_round1_progression() -> dict[str, Any]:
    inputs = _validate_round1_inputs()
    procedure = inputs["protocol"]["search_procedure"]
    ceiling = procedure["ceiling_stop_rule"]

    # Round 1 produced no candidate authorized for 031-040, so by the frozen
    # round-update rule it cannot add a new validation-frontier point.
    round_added_new_frontier_point = False
    prior_consecutive_plateau_rounds = 0
    consecutive_plateau_rounds = prior_consecutive_plateau_rounds + 1

    completed_round = 1
    screened_unique_candidates = len(inputs["round1_candidate_ids"])
    plateau_stop_fired = (
        consecutive_plateau_rounds >= int(ceiling["plateau_rounds"])
    )
    max_rounds_stop_fired = completed_round >= int(
        procedure["max_rounds"]
    )
    unique_budget_stop_fired = screened_unique_candidates >= int(
        procedure["max_unique_candidates"]
    )
    stop_search = bool(
        plateau_stop_fired
        or max_rounds_stop_fired
        or unique_budget_stop_fired
    )

    next_round_candidates = (
        [] if stop_search else list(inputs["round2_candidate_ids"])
    )
    if not stop_search and len(next_round_candidates) != int(
        procedure["max_new_candidates_per_round"]
    ):
        raise ValueError("Round-2 preregistered screening set is incomplete")

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "rule_id": RULE_ID,
        "completed_round": completed_round,
        "round_completion_status": "complete_no_validation_candidate",
        "validation_execution_status": (
            "not_run_no_authorized_round1_candidate"
        ),
        "round_added_new_frontier_point": round_added_new_frontier_point,
        "prior_consecutive_no_new_frontier_rounds": (
            prior_consecutive_plateau_rounds
        ),
        "consecutive_no_new_frontier_rounds": consecutive_plateau_rounds,
        "plateau_stop_threshold": int(ceiling["plateau_rounds"]),
        "plateau_stop_fired": plateau_stop_fired,
        "max_rounds_stop_fired": max_rounds_stop_fired,
        "unique_candidate_budget_stop_fired": unique_budget_stop_fired,
        "screened_unique_candidate_count": screened_unique_candidates,
        "stop_search": stop_search,
        "decision": "advance" if not stop_search else "stop",
        "next_round": ROUND2 if not stop_search else None,
        "screening_authorized_candidate_ids": next_round_candidates,
        "round1_final_validation_candidate_ids": [],
        "evidence_bindings": {
            "screening_manifest": _binding(SCREENING_MANIFEST_PATH),
            "screening_selection": _binding(SCREENING_SELECTION_PATH),
            "confirmation_manifest": _binding(CONFIRMATION_MANIFEST_PATH),
            "validation_selection": _binding(VALIDATION_SELECTION_PATH),
            "development_economics_manifest": _binding(
                ECONOMICS_MANIFEST_PATH
            ),
            "efficiency_gate_result": _binding(
                EFFICIENCY_GATE_RESULT_PATH
            ),
        },
    }


def validate_frozen_round_progression(
    progression: dict[str, Any],
) -> None:
    recomputed = compute_round1_progression()
    if progression != recomputed:
        raise ValueError(
            "round progression artifact does not match recomputed frozen "
            "Round-1 evidence"
        )


def freeze_round1_progression(
    *,
    output_dir: Path,
) -> tuple[Path, list[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with _exclusive_progression_lock(output_dir, ROUND1_COMPLETED):
        progression = compute_round1_progression()
        validate_frozen_round_progression(progression)
        if progression["decision"] != "advance":
            raise ValueError("frozen Round-1 stop rule does not authorize Round 2")
        if progression["next_round"] != ROUND2:
            raise ValueError("frozen Round-1 progression target changed")

        progression_path = (
            output_dir
            / "round-progression-after-round-1.json"
        )
        progression_bytes = (
            json.dumps(
                progression,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        progression_sha = sha256(progression_bytes).hexdigest()

        authorized = progression["screening_authorized_candidate_ids"]
        auth_payloads: list[tuple[Path, bytes]] = []
        for candidate_id in authorized:
            auth = {
                "schema_version": SCHEMA_VERSION,
                "protocol_id": PROTOCOL_ID,
                "candidate_id": candidate_id,
                "round": ROUND2,
                "phase": "screening",
                "approved": True,
                "selection_rule": RULE_ID,
                "completed_round": ROUND1_COMPLETED,
                "screening_authorized_candidate_ids": list(authorized),
                "round_progression_path": _repo_rel(progression_path),
                "round_progression_sha256": progression_sha,
            }
            path = output_dir / f"{candidate_id}--screening-auth.json"
            encoded = (
                json.dumps(
                    auth,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            auth_payloads.append((path, encoded))

        artifacts = [
            (progression_path, progression_bytes),
            *auth_payloads,
        ]
        _write_recoverable_artifact_set(
            output_dir=output_dir,
            artifacts=artifacts,
        )

        return progression_path, [path for path, _ in auth_payloads]


def _validate_round2_inputs() -> dict[str, Any]:
    protocol = _load_json(PROTOCOL_PATH)
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Round-2 progression protocol_id mismatch")

    procedure = protocol.get("search_procedure")
    if not isinstance(procedure, dict):
        raise ValueError("search procedure missing from frozen protocol")
    if procedure.get("max_rounds") != 3:
        raise ValueError("frozen max_rounds changed")
    if procedure.get("max_new_candidates_per_round") != 6:
        raise ValueError("frozen per-round candidate budget changed")
    if procedure.get("max_unique_candidates") != 18:
        raise ValueError("frozen unique-candidate budget changed")
    ceiling = procedure.get("ceiling_stop_rule")
    if not isinstance(ceiling, dict) or ceiling.get("plateau_rounds") != 2:
        raise ValueError("frozen plateau stop rule changed")

    prior = _load_json(ROUND1_PROGRESSION_PATH)
    validate_frozen_round_progression(prior)
    if prior.get("completed_round") != 1:
        raise ValueError("prior progression completed_round changed")
    if prior.get("decision") != "advance" or prior.get("next_round") != 2:
        raise ValueError("prior progression did not authorize Round 2")
    if prior.get("stop_search") is not False:
        raise ValueError("prior progression unexpectedly stopped search")
    if prior.get("consecutive_no_new_frontier_rounds") != 1:
        raise ValueError("prior plateau count changed")

    round2_ids = round_candidate_ids(2)
    round3_ids = round_candidate_ids(3)
    if len(round2_ids) != 6 or len(round3_ids) != 6:
        raise ValueError("frozen later-round candidate cardinality changed")

    screening_manifest = _load_json(ROUND2_SCREENING_MANIFEST_PATH)
    if (
        screening_manifest.get("schema_version") != "0.1.0"
        or screening_manifest.get("protocol_id") != PROTOCOL_ID
        or screening_manifest.get("round") != 2
        or screening_manifest.get("phase") != "screening"
        or screening_manifest.get("candidate_ids") != round2_ids
        or screening_manifest.get("repeats") != 1
        or screening_manifest.get("total_runs") != 120
    ):
        raise ValueError("Round-2 screening manifest is incomplete")

    screening_root = ROUND2_SCREENING_MANIFEST_PATH.parent
    screening_source_entries = _validate_manifest_entries(
        manifest=screening_manifest,
        field="source_files",
        expected_paths=_expected_candidate_source_paths(
            evidence_root=screening_root,
            candidate_ids=round2_ids,
            phase="screening",
            repeats=(1,),
        ),
        label="Round-2 screening",
    )

    screening_selection = _load_json(ROUND2_SCREENING_SELECTION_PATH)
    validate_frozen_screening_selection(screening_selection)
    if screening_selection.get("round") != 2:
        raise ValueError("Round-2 screening selection round mismatch")
    selected = screening_selection.get("selected_candidate_ids")
    if not isinstance(selected, list) or len(selected) != 2:
        raise ValueError("Round-2 screening must select exactly two candidates")

    expected_screening_gate_paths = {
        _repo_rel(ROUND2_SCREENING_SELECTION_PATH),
        *{
            _repo_rel(
                ROUND2_SCREENING_SELECTION_PATH.parent
                / f"{candidate_id}--development-confirmation-auth.json"
            )
            for candidate_id in selected
        },
    }
    _validate_manifest_entries(
        manifest=screening_manifest,
        field="gate_files",
        expected_paths=expected_screening_gate_paths,
        label="Round-2 screening",
    )

    screening_summary_bindings = {}
    for candidate_id in round2_ids:
        summary_rel, summary_sha = _validate_candidate_evidence_tree(
            evidence_root=screening_root,
            candidate_id=candidate_id,
            phase="screening",
            repeats=(1,),
            source_entries=screening_source_entries,
        )
        screening_summary_bindings[candidate_id] = (
            summary_rel,
            summary_sha,
        )
    for row in screening_selection.get("ranking") or []:
        candidate_id = row.get("candidate_id")
        if candidate_id not in screening_summary_bindings:
            raise ValueError("Round-2 screening ranking candidate changed")
        expected_path, expected_sha = screening_summary_bindings[candidate_id]
        if row.get("screening_summary_path") != expected_path:
            raise ValueError(
                f"{candidate_id} Round-2 screening summary path drift"
            )
        if row.get("screening_summary_sha256") != expected_sha:
            raise ValueError(
                f"{candidate_id} Round-2 screening summary hash drift"
            )

    confirmation_manifest = _load_json(ROUND2_CONFIRMATION_MANIFEST_PATH)
    if (
        confirmation_manifest.get("schema_version") != "0.1.0"
        or confirmation_manifest.get("protocol_id") != PROTOCOL_ID
        or confirmation_manifest.get("round") != 2
        or confirmation_manifest.get("phase") != "development_confirmation"
        or confirmation_manifest.get("candidate_ids") != selected
        or confirmation_manifest.get("repeats") != 3
        or confirmation_manifest.get("total_runs") != 120
    ):
        raise ValueError("Round-2 confirmation manifest is incomplete")

    confirmation_root = ROUND2_CONFIRMATION_MANIFEST_PATH.parent
    confirmation_source_entries = _validate_manifest_entries(
        manifest=confirmation_manifest,
        field="source_files",
        expected_paths=_expected_candidate_source_paths(
            evidence_root=confirmation_root,
            candidate_ids=selected,
            phase="development_confirmation",
            repeats=(1, 2, 3),
        ),
        label="Round-2 confirmation",
    )

    validation_selection = _load_json(ROUND2_VALIDATION_SELECTION_PATH)
    validate_frozen_validation_selection(validation_selection)
    if validation_selection.get("round") != 2:
        raise ValueError("Round-2 validation selection round mismatch")
    if validation_selection.get("screening_selected_candidate_ids") != selected:
        raise ValueError(
            "Round-2 screening/validation-entry candidate binding changed"
        )

    quality_selected = validation_selection.get(
        "validation_selected_candidate_ids"
    )
    if not isinstance(quality_selected, list):
        raise ValueError("Round-2 validation-selected candidate set invalid")

    expected_confirmation_gate_paths = {
        _repo_rel(ROUND2_VALIDATION_SELECTION_PATH),
        *{
            _repo_rel(
                ROUND2_VALIDATION_SELECTION_PATH.parent
                / f"{candidate_id}--validation-auth.json"
            )
            for candidate_id in quality_selected
        },
    }
    _validate_manifest_entries(
        manifest=confirmation_manifest,
        field="gate_files",
        expected_paths=expected_confirmation_gate_paths,
        label="Round-2 confirmation",
    )

    confirmation_summary_bindings = {}
    for candidate_id in selected:
        summary_rel, summary_sha = _validate_candidate_evidence_tree(
            evidence_root=confirmation_root,
            candidate_id=candidate_id,
            phase="development_confirmation",
            repeats=(1, 2, 3),
            source_entries=confirmation_source_entries,
        )
        confirmation_summary_bindings[candidate_id] = (
            summary_rel,
            summary_sha,
        )
    for row in validation_selection.get("confirmation_rows") or []:
        candidate_id = row.get("candidate_id")
        if candidate_id not in confirmation_summary_bindings:
            raise ValueError("Round-2 confirmation row candidate changed")
        expected_path, expected_sha = confirmation_summary_bindings[
            candidate_id
        ]
        if row.get("confirmation_summary_path") != expected_path:
            raise ValueError(
                f"{candidate_id} Round-2 confirmation summary path drift"
            )
        if row.get("confirmation_summary_sha256") != expected_sha:
            raise ValueError(
                f"{candidate_id} Round-2 confirmation summary hash drift"
            )

    economics_manifest = _load_json(ROUND2_ECONOMICS_MANIFEST_PATH)
    if (
        economics_manifest.get("schema_version") != "0.1.0"
        or economics_manifest.get("protocol_id") != PROTOCOL_ID
        or economics_manifest.get("package_id")
        != "procureharness-round2-economics-v0.1"
        or economics_manifest.get("round") != 2
        or economics_manifest.get("candidate_ids") != selected
        or economics_manifest.get("execution")
        != {
            "mode": "offline_deterministic_economics",
            "provider_calls": 0,
        }
    ):
        raise ValueError("Round-2 economics manifest identity changed")

    base_binding = economics_manifest.get("base_validation_selection")
    if not isinstance(base_binding, dict):
        raise ValueError("Round-2 economics base selection binding missing")
    if (
        base_binding.get("path") != _repo_rel(ROUND2_VALIDATION_SELECTION_PATH)
        or base_binding.get("sha256")
        != _sha256_path(ROUND2_VALIDATION_SELECTION_PATH)
    ):
        raise ValueError("Round-2 economics base selection binding drift")

    confirmation_binding = economics_manifest.get(
        "source_confirmation_manifest"
    )
    if not isinstance(confirmation_binding, dict):
        raise ValueError("Round-2 economics confirmation binding missing")
    if (
        confirmation_binding.get("path")
        != _repo_rel(ROUND2_CONFIRMATION_MANIFEST_PATH)
        or confirmation_binding.get("sha256")
        != _sha256_path(ROUND2_CONFIRMATION_MANIFEST_PATH)
    ):
        raise ValueError("Round-2 economics confirmation binding drift")

    efficiency_result = _load_json(ROUND2_EFFICIENCY_GATE_RESULT_PATH)
    if (
        efficiency_result.get("schema_version") != "0.1.0"
        or efficiency_result.get("protocol_id") != PROTOCOL_ID
        or efficiency_result.get("rule")
        != "frozen_development_efficiency_promotion_v0.1"
        or efficiency_result.get("round") != 2
        or efficiency_result.get("provider_calls") != 0
    ):
        raise ValueError("Round-2 efficiency gate identity changed")
    if efficiency_result.get("base_validation_selection_path") != _repo_rel(
        ROUND2_VALIDATION_SELECTION_PATH
    ):
        raise ValueError("Round-2 efficiency gate base selection path changed")
    if efficiency_result.get("base_validation_selection_sha256") != (
        _sha256_path(ROUND2_VALIDATION_SELECTION_PATH)
    ):
        raise ValueError("Round-2 efficiency gate base selection hash changed")
    if efficiency_result.get("round2_economics_manifest_sha256") != (
        _sha256_path(ROUND2_ECONOMICS_MANIFEST_PATH)
    ):
        raise ValueError("Round-2 efficiency gate economics manifest drift")

    efficiency_selected, rejected = _recompute_efficiency_gate(
        validation_selection=validation_selection,
        economics_manifest=economics_manifest,
        recorded_result=efficiency_result,
    )

    final_validation_candidates = list(
        dict.fromkeys([*quality_selected, *efficiency_selected])
    )
    if final_validation_candidates:
        raise ValueError(
            "Round-2 stop gate cannot skip validation evidence for an "
            "authorized candidate"
        )

    pending = validation_selection.get("pending_efficiency_candidate_ids")
    if not isinstance(pending, list):
        raise ValueError("Round-2 pending efficiency candidate set invalid")
    if sorted(pending) != sorted(rejected):
        raise ValueError(
            "Round-2 economics gate did not resolve every pending candidate"
        )

    return {
        "protocol": protocol,
        "prior_progression": prior,
        "round2_candidate_ids": round2_ids,
        "round3_candidate_ids": round3_ids,
        "screening_selection": screening_selection,
        "validation_selection": validation_selection,
        "efficiency_result": efficiency_result,
    }


def compute_round2_progression() -> dict[str, Any]:
    inputs = _validate_round2_inputs()
    procedure = inputs["protocol"]["search_procedure"]
    ceiling = procedure["ceiling_stop_rule"]

    round_added_new_frontier_point = False
    prior_consecutive = int(
        inputs["prior_progression"][
            "consecutive_no_new_frontier_rounds"
        ]
    )
    consecutive = prior_consecutive + 1

    completed_round = 2
    screened_unique_candidates = (
        len(round_candidate_ids(1))
        + len(inputs["round2_candidate_ids"])
    )
    plateau_stop_fired = consecutive >= int(ceiling["plateau_rounds"])
    max_rounds_stop_fired = completed_round >= int(
        procedure["max_rounds"]
    )
    unique_budget_stop_fired = screened_unique_candidates >= int(
        procedure["max_unique_candidates"]
    )
    stop_search = bool(
        plateau_stop_fired
        or max_rounds_stop_fired
        or unique_budget_stop_fired
    )
    if not stop_search:
        raise ValueError(
            "Round-2 progression unexpectedly permits Round-3 search"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "rule_id": RULE_ID,
        "completed_round": completed_round,
        "round_completion_status": "complete_no_validation_candidate",
        "validation_execution_status": (
            "not_run_no_authorized_round2_candidate"
        ),
        "round_added_new_frontier_point": round_added_new_frontier_point,
        "prior_consecutive_no_new_frontier_rounds": prior_consecutive,
        "consecutive_no_new_frontier_rounds": consecutive,
        "plateau_stop_threshold": int(ceiling["plateau_rounds"]),
        "plateau_stop_fired": plateau_stop_fired,
        "max_rounds_stop_fired": max_rounds_stop_fired,
        "unique_candidate_budget_stop_fired": unique_budget_stop_fired,
        "screened_unique_candidate_count": screened_unique_candidates,
        "stop_search": stop_search,
        "decision": "stop",
        "stop_reason": "two_consecutive_no_new_frontier_rounds",
        "next_round": None,
        "screening_authorized_candidate_ids": [],
        "round2_final_validation_candidate_ids": [],
        "evidence_bindings": {
            "prior_round_progression": _binding(ROUND1_PROGRESSION_PATH),
            "screening_manifest": _binding(
                ROUND2_SCREENING_MANIFEST_PATH
            ),
            "screening_selection": _binding(
                ROUND2_SCREENING_SELECTION_PATH
            ),
            "confirmation_manifest": _binding(
                ROUND2_CONFIRMATION_MANIFEST_PATH
            ),
            "validation_selection": _binding(
                ROUND2_VALIDATION_SELECTION_PATH
            ),
            "round2_economics_manifest": _binding(
                ROUND2_ECONOMICS_MANIFEST_PATH
            ),
            "efficiency_gate_result": _binding(
                ROUND2_EFFICIENCY_GATE_RESULT_PATH
            ),
        },
    }


def validate_frozen_round2_progression(
    progression: dict[str, Any],
) -> None:
    recomputed = compute_round2_progression()
    if progression != recomputed:
        raise ValueError(
            "round progression artifact does not match recomputed frozen "
            "Round-2 evidence"
        )


def freeze_round2_progression(
    *,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with _exclusive_progression_lock(output_dir, ROUND2_COMPLETED):
        progression = compute_round2_progression()
        validate_frozen_round2_progression(progression)
        if progression["decision"] != "stop":
            raise ValueError("Round-2 plateau gate must stop the search")
        if progression["screening_authorized_candidate_ids"]:
            raise ValueError("Round-2 stop gate may not authorize Round 3")

        progression_path = (
            output_dir / "round-progression-after-round-2.json"
        )
        encoded = (
            json.dumps(
                progression,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        _write_recoverable_artifact_set(
            output_dir=output_dir,
            artifacts=[(progression_path, encoded)],
        )
        return progression_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--completed-round",
        type=int,
        choices=(1, 2),
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        default="evidence/procureharness-search-gates-v0.1",
    )
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    if args.completed_round == 1:
        payload = compute_round1_progression()
        if args.preview:
            print(
                json.dumps(
                    payload,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
            return
        progression_path, auth_paths = freeze_round1_progression(
            output_dir=Path(args.output_dir),
        )
        print(f"progression={progression_path}")
        for path in auth_paths:
            print(f"authorization={path}")
        return

    payload = compute_round2_progression()
    if args.preview:
        print(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return

    progression_path = freeze_round2_progression(
        output_dir=Path(args.output_dir),
    )
    print(f"progression={progression_path}")
    print("decision=stop")
    print("round3_authorizations=0")


if __name__ == "__main__":
    main()
