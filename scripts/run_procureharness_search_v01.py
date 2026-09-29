"""Plan or execute frozen ProcureHarness architecture-search candidate runs.

Default behavior is plan-only and makes no model/provider calls. Model-backed
execution requires --execute. Episodes 041-050 are intentionally not exposed as
an executable phase in this search runner.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import BenchmarkRunner
from longprocurebench.procureharness import (
    CANDIDATE_CONFIGS,
    ProcureHarnessPolicy,
    candidate_registry,
    get_candidate,
    validate_candidate_registry,
)

PROTOCOL_ID = "procureharness-architecture-search-v0.1"
MODEL = "openai/gpt-5.6-sol"
REASONING_EFFORT = "medium"
TEMPERATURE = None
MAX_ACTIONS = 50

DEVELOPMENT_EPISODES = [
    "electrical-bongabon-generator-001",
    "electrical-national-museum-lighting-002",
    "electrical-neust-cable-003",
    "electrical-dla-breaker-004",
    "electrical-barrie-transformer-005",
    "electrical-bfar-generator-006",
    "electrical-negros-wire-007",
    "electrical-burauen-generator-008",
    "electrical-highpoint-transformer-009",
    "electrical-painesville-switchgear-010",
    "electrical-sagada-generator-011",
    "electrical-dla-relay-012",
    "electrical-dla-transformer-013",
    "electrical-dla-battery-supply-014",
    "electrical-dla-battery-charger-015",
    "electrical-dla-power-supply-016",
    "electrical-dla-qpl-breaker-017",
    "electrical-highpoint-cable-018",
    "electrical-usaf-ups-019",
    "electrical-vre-generator-020",
]

VALIDATION_EPISODES = [
    "electrical-imperial-ev-phase1-031",
    "electrical-imperial-ev-phase23-032",
    "electrical-lewiston-ev-chargers-033",
    "electrical-idaho-falls-ev-chargers-034",
    "electrical-union-township-ev-chargers-035",
    "electrical-methuen-stadium-led-036",
    "electrical-philadelphia-led-phase5-037",
    "electrical-hampton-fountain-led-038",
    "electrical-danville-pole-transformer-039",
    "electrical-danville-substation-transformers-040",
]

PHASES = {
    "screening": {
        "episodes": DEVELOPMENT_EPISODES,
        "repeats": 1,
        "purpose": "cheap development screening",
    },
    "development_confirmation": {
        "episodes": DEVELOPMENT_EPISODES,
        "repeats": 3,
        "purpose": "development confirmation for selected candidates",
    },
    "validation": {
        "episodes": VALIDATION_EPISODES,
        "repeats": 3,
        "purpose": "fresh architecture-search validation",
    },
}


def round_candidate_ids(round_id: int) -> list[str]:
    return [
        config.candidate_id
        for config in CANDIDATE_CONFIGS
        if config.round == round_id
    ]


def _validate_selected_candidates(
    *,
    authorization: dict[str, Any],
    field: str,
    candidate_id: str,
    round_id: int,
    max_count: int,
) -> list[str]:
    selected = authorization.get(field)
    if not isinstance(selected, list) or not selected:
        raise ValueError(f"authorization requires non-empty {field}")
    if len(selected) != len(set(selected)):
        raise ValueError(f"authorization {field} contains duplicates")
    if len(selected) > max_count:
        raise ValueError(
            f"authorization {field} exceeds max {max_count} candidates"
        )
    allowed = set(round_candidate_ids(round_id))
    if not set(selected).issubset(allowed):
        raise ValueError(
            f"authorization {field} contains candidate outside round {round_id}"
        )
    if candidate_id not in selected:
        raise ValueError(
            f"candidate is not included in authorization {field}"
        )
    return selected


def _assert_output_tree_fresh(
    *,
    output_dir: Path,
    candidate_id: str,
    phase: str,
) -> Path:
    phase_root = output_dir / candidate_id / phase
    if phase_root.exists() and any(phase_root.rglob("*")):
        raise ValueError(
            "Refusing to rerun candidate/phase into nonempty output tree: "
            f"{phase_root}"
        )
    return phase_root


def _load_bound_json_artifact(
    *,
    authorization: dict[str, Any],
    path_field: str,
    sha_field: str,
) -> dict[str, Any]:
    path_value = authorization.get(path_field)
    expected_sha = authorization.get(sha_field)
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"authorization requires {path_field}")
    if (
        not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or any(ch not in "0123456789abcdef" for ch in expected_sha)
    ):
        raise ValueError(f"authorization requires lowercase SHA-256 {sha_field}")

    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise ValueError(f"bound authorization artifact is missing: {path}")

    raw = path.read_bytes()
    observed = sha256(raw).hexdigest()
    if observed != expected_sha:
        raise ValueError(
            f"bound authorization artifact hash mismatch: {path}"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"bound authorization artifact is not valid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("bound authorization artifact must be a JSON object")
    return payload


def _authorization_sha256(
    authorization: dict[str, Any] | None,
) -> str | None:
    if authorization is None:
        return None
    encoded = json.dumps(
        authorization,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def model_slug(model: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-") or "model"
    digest = sha256(model.encode("utf-8")).hexdigest()[:10]
    readable = readable[:108].rstrip("._-") or "model"
    return f"{readable}--{digest}"


def phase_plan(candidate_id: str, phase: str) -> dict[str, Any]:
    config = get_candidate(candidate_id)
    if phase not in PHASES:
        raise ValueError(f"Unknown executable search phase: {phase}")
    spec = PHASES[phase]
    rows = [
        {
            "episode_id": episode_id,
            "repeat": repeat,
        }
        for repeat in range(1, spec["repeats"] + 1)
        for episode_id in spec["episodes"]
    ]
    return {
        "protocol_id": PROTOCOL_ID,
        "candidate": {
            key: value
            for key, value in candidate_registry()[
                [c.candidate_id for c in CANDIDATE_CONFIGS].index(candidate_id)
            ].items()
        },
        "phase": phase,
        "round": config.round,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "temperature": TEMPERATURE,
        "max_actions": MAX_ACTIONS,
        "run_count": len(rows),
        "runs": rows,
        "final_041_050_executable": False,
    }


def _load_authorization(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_phase_authorization(
    *,
    candidate_id: str,
    phase: str,
    authorization: dict[str, Any] | None,
) -> None:
    config = get_candidate(candidate_id)

    if phase == "screening" and config.round == 1:
        if authorization is not None:
            raise ValueError(
                "round-1 screening does not accept an authorization file"
            )
        return

    if authorization is None:
        raise ValueError(
            f"{phase} for round {config.round} requires "
            "--authorization-json from the prior frozen gate"
        )
    if authorization.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("authorization protocol_id mismatch")
    if authorization.get("candidate_id") != candidate_id:
        raise ValueError("authorization candidate_id mismatch")
    if authorization.get("phase") != phase:
        raise ValueError("authorization phase mismatch")
    if authorization.get("approved") is not True:
        raise ValueError("authorization must record approved=true")
    if authorization.get("round") != config.round:
        raise ValueError("authorization round mismatch")

    if phase == "screening":
        expected_ids = round_candidate_ids(config.round)
        if authorization.get("round_candidate_ids") != expected_ids:
            raise ValueError(
                "screening authorization round_candidate_ids must match "
                "the frozen six-candidate round registry"
            )
        if authorization.get("prior_round") != config.round - 1:
            raise ValueError("screening authorization prior_round mismatch")
        if authorization.get("prior_round_validation_complete") is not True:
            raise ValueError(
                "later-round screening requires "
                "prior_round_validation_complete=true"
            )
        if authorization.get("plateau_stop_fired") is not False:
            raise ValueError(
                "later-round screening requires plateau_stop_fired=false"
            )
        if authorization.get("search_budget_exhausted") is not False:
            raise ValueError(
                "later-round screening requires search_budget_exhausted=false"
            )
        return

    if phase == "development_confirmation":
        if authorization.get("screening_complete") is not True:
            raise ValueError(
                "development confirmation requires screening_complete=true"
            )
        selected = _validate_selected_candidates(
            authorization=authorization,
            field="screening_selected_candidate_ids",
            candidate_id=candidate_id,
            round_id=config.round,
            max_count=2,
        )
        if authorization.get("selection_rule") != (
            "frozen_screening_selection_v0.1"
        ):
            raise ValueError(
                "development confirmation selection_rule mismatch"
            )

        selection = _load_bound_json_artifact(
            authorization=authorization,
            path_field="screening_selection_path",
            sha_field="screening_selection_sha256",
        )
        if selection.get("protocol_id") != PROTOCOL_ID:
            raise ValueError("screening selection protocol mismatch")
        if selection.get("rule_id") != "frozen_screening_selection_v0.1":
            raise ValueError("screening selection rule mismatch")
        if selection.get("round") != config.round:
            raise ValueError("screening selection round mismatch")
        if selection.get("selected_candidate_ids") != selected:
            raise ValueError(
                "screening selection artifact/authorization candidate mismatch"
            )
        return

    if authorization.get("development_confirmation_complete") is not True:
        raise ValueError(
            "validation requires development_confirmation_complete=true"
        )
    if authorization.get("development_confirmation_floor_passed") is not True:
        raise ValueError(
            "validation requires development_confirmation_floor_passed=true"
        )
    branch = authorization.get("promotion_branch")
    if branch not in {"quality", "efficiency"}:
        raise ValueError(
            "validation authorization requires quality/efficiency "
            "promotion_branch"
        )
    _validate_selected_candidates(
        authorization=authorization,
        field="validation_selected_candidate_ids",
        candidate_id=candidate_id,
        round_id=config.round,
        max_count=2,
    )
    if authorization.get("selection_rule") != (
        "frozen_validation_entry_lexicographic_v0.1"
    ):
        raise ValueError("validation selection_rule mismatch")


def validate_frozen_implementation_for_execution() -> None:
    """Fail closed on any controller/config/runner drift before a model call."""
    try:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_procureharness_harness_v01.py"),
            ],
            cwd=ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            "ProcureHarness implementation freeze validation failed"
        ) from exc


def _assert_phase_exposure(phase: str) -> None:
    suffixes = {
        int(episode_id.rsplit("-", 1)[1])
        for episode_id in PHASES[phase]["episodes"]
    }
    if any(41 <= suffix <= 50 for suffix in suffixes):
        raise ValueError("Architecture search may not execute episodes 041-050")
    if phase == "validation" and suffixes != set(range(31, 41)):
        raise ValueError("Validation phase must remain exactly episodes 031-040")
    if phase != "validation" and suffixes != set(range(1, 21)):
        raise ValueError(
            "Development search phases must remain exactly episodes 001-020"
        )


def execute_candidate(
    *,
    candidate_id: str,
    phase: str,
    output_dir: Path,
    authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    phase_root = _assert_output_tree_fresh(
        output_dir=output_dir,
        candidate_id=candidate_id,
        phase=phase,
    )
    validate_frozen_implementation_for_execution()
    validate_candidate_registry()
    validate_phase_authorization(
        candidate_id=candidate_id,
        phase=phase,
        authorization=authorization,
    )
    _assert_phase_exposure(phase)
    plan = phase_plan(candidate_id, phase)
    runner = BenchmarkRunner()

    completed = 0
    execution_failures = 0
    rows = []

    for row in plan["runs"]:
        episode_id = row["episode_id"]
        repeat = row["repeat"]
        run_id = (
            f"{candidate_id}--{phase}--{episode_id}--r{repeat}"
        )
        policy = ProcureHarnessPolicy(
            MODEL,
            config=candidate_id,
            temperature=TEMPERATURE,
            reasoning_effort=REASONING_EFFORT,
        )
        path = (
            output_dir
            / candidate_id
            / phase
            / f"r{repeat}"
            / f"{episode_id}.json"
        )
        result = runner.run(
            policy,
            episode_id,
            max_actions=MAX_ACTIONS,
            run_id=run_id,
            result_path=path,
        )
        evaluation = result.get("evaluation") or {}
        clean = result["status"] in {"completed", "max_actions"}
        if not clean:
            execution_failures += 1
        completed += 1
        metrics = result.get("policy_metrics") or {}
        obligations = evaluation.get("obligations") or {}
        summary = {
            "episode_id": episode_id,
            "repeat": repeat,
            "status": result["status"],
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
        rows.append(summary)
        print(
            f"{candidate_id} | {phase} | {episode_id} | r{repeat}: "
            f"status={result['status']} "
            f"feasible_obligation={summary['feasible_obligation_success']} "
            f"strict={summary['strict_v02']} "
            f"calls={summary['model_calls']} "
            f"cost={summary['known_cost_usd']}"
        )

    implementation_manifest = json.loads(
        (
            ROOT
            / "evidence"
            / "procureharness-architecture-harness-v0.1"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    summary_payload = {
        "protocol_id": PROTOCOL_ID,
        "implementation_freeze_commit": implementation_manifest[
            "freeze_commit"
        ],
        "candidate_id": candidate_id,
        "round": get_candidate(candidate_id).round,
        "phase": phase,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "temperature": TEMPERATURE,
        "planned_runs": plan["run_count"],
        "completed_runs": completed,
        "execution_failures": execution_failures,
        "authorization_sha256": _authorization_sha256(authorization),
        "authorization": deepcopy(authorization),
        "rows": rows,
    }
    summary_path = phase_root / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            summary_payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )
    return summary_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        choices=[c.candidate_id for c in CANDIDATE_CONFIGS],
    )
    parser.add_argument(
        "--phase",
        choices=sorted(PHASES),
        default="screening",
    )
    parser.add_argument(
        "--authorization-json",
        help=(
            "Frozen gate authorization required for development_confirmation "
            "and validation."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform model-backed candidate runs. Omit for plan-only.",
    )
    parser.add_argument(
        "--list-candidates",
        action="store_true",
    )
    parser.add_argument(
        "--output-dir",
        default="results/procureharness-architecture-search-v0.1",
    )
    parser.add_argument(
        "--plan-output",
        help="Optional JSON file for the plan-only payload.",
    )
    args = parser.parse_args()

    validate_candidate_registry()

    if args.list_candidates:
        print(json.dumps(candidate_registry(), indent=2))
        return

    if not args.candidate:
        parser.error("--candidate is required unless --list-candidates is used")

    plan = phase_plan(args.candidate, args.phase)
    _assert_phase_exposure(args.phase)

    authorization = (
        _load_authorization(args.authorization_json)
        if args.authorization_json
        else None
    )
    if args.execute:
        execute_candidate(
            candidate_id=args.candidate,
            phase=args.phase,
            output_dir=Path(args.output_dir),
            authorization=authorization,
        )
        return

    if args.authorization_json:
        validate_phase_authorization(
            candidate_id=args.candidate,
            phase=args.phase,
            authorization=authorization,
        )

    encoded = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.plan_output:
        path = Path(args.plan_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
