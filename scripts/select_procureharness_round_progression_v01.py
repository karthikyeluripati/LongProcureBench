"""Freeze Round-1 -> Round-2 ProcureHarness search progression.

This gate is offline and deterministic. It binds the completed Round-1
screening, confirmation, validation-entry, and economics evidence, recomputes
the stop/progression conditions from the frozen protocol, and emits screening
authorizations for the preregistered Round-2 candidate set.

Round-3 progression remains fail-closed in v0.1.
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
    PROTOCOL_ID,
    round_candidate_ids,
)
from select_procureharness_screening_v01 import (
    validate_frozen_screening_selection,
)
from select_procureharness_validation_v01 import (
    _load_development_economics_binding,
    validate_frozen_validation_selection,
)

RULE_ID = "frozen_round_progression_v0.1"
SCHEMA_VERSION = "0.1.0"
SUPPORTED_COMPLETED_ROUND = 1
NEXT_ROUND = 2

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

    screening_selection = _load_json(SCREENING_SELECTION_PATH)
    validate_frozen_screening_selection(screening_selection)
    if screening_selection.get("round") != 1:
        raise ValueError("Round-1 screening selection round mismatch")

    selected = screening_selection.get("selected_candidate_ids")
    if not isinstance(selected, list) or not selected:
        raise ValueError("Round-1 screening selected no confirmation candidates")

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

    validation_selection = _load_json(VALIDATION_SELECTION_PATH)
    validate_frozen_validation_selection(validation_selection)
    if validation_selection.get("round") != 1:
        raise ValueError("Round-1 validation selection round mismatch")
    if validation_selection.get("screening_selected_candidate_ids") != selected:
        raise ValueError(
            "Round-1 screening/validation-entry candidate binding changed"
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
    efficiency_selected = efficiency_result.get("authorized_candidate_ids")
    if not isinstance(efficiency_selected, list):
        raise ValueError("Round-1 efficiency authorization set invalid")

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
    rejected = efficiency_result.get("not_promoted_candidate_ids")
    if not isinstance(pending, list) or not isinstance(rejected, list):
        raise ValueError("Round-1 pending/rejected candidate sets invalid")
    if sorted(pending) != sorted(rejected):
        raise ValueError(
            "Round-1 economics gate did not resolve every pending candidate"
        )
    outcomes = efficiency_result.get("outcomes")
    if not isinstance(outcomes, dict) or set(outcomes) != set(pending):
        raise ValueError("Round-1 efficiency outcome map is incomplete")
    if any(
        not isinstance(outcomes[candidate_id], dict)
        or outcomes[candidate_id].get("approved") is not False
        or outcomes[candidate_id].get("status") != "not_promoted"
        for candidate_id in pending
    ):
        raise ValueError("Round-1 efficiency rejection evidence changed")

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
        "next_round": NEXT_ROUND if not stop_search else None,
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
    with _exclusive_progression_lock(output_dir, SUPPORTED_COMPLETED_ROUND):
        progression = compute_round1_progression()
        validate_frozen_round_progression(progression)
        if progression["decision"] != "advance":
            raise ValueError("frozen Round-1 stop rule does not authorize Round 2")
        if progression["next_round"] != NEXT_ROUND:
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
                "round": NEXT_ROUND,
                "phase": "screening",
                "approved": True,
                "selection_rule": RULE_ID,
                "completed_round": SUPPORTED_COMPLETED_ROUND,
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

        final_paths = [
            progression_path,
            *[path for path, _ in auth_payloads],
        ]
        existing = [path for path in final_paths if path.exists()]
        if existing:
            raise ValueError(
                "refusing to overwrite frozen round-progression artifact(s): "
                + ", ".join(str(path) for path in existing)
            )

        with tempfile.TemporaryDirectory(
            dir=output_dir,
            prefix=".round-progression-",
        ) as staging_dir:
            staging = Path(staging_dir)
            staged: list[tuple[Path, Path]] = []

            progression_stage = staging / progression_path.name
            progression_stage.write_bytes(progression_bytes)
            staged.append((progression_stage, progression_path))

            for path, encoded in auth_payloads:
                stage = staging / path.name
                stage.write_bytes(encoded)
                staged.append((stage, path))

            for stage, final in staged:
                os.replace(stage, final)

        return progression_path, [path for path, _ in auth_payloads]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--completed-round",
        type=int,
        choices=(1,),
        default=1,
    )
    parser.add_argument(
        "--output-dir",
        default="evidence/procureharness-search-gates-v0.1",
    )
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    if args.completed_round != SUPPORTED_COMPLETED_ROUND:
        raise SystemExit("only Round-1 -> Round-2 progression is supported")

    if args.preview:
        print(
            json.dumps(
                compute_round1_progression(),
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


if __name__ == "__main__":
    main()
