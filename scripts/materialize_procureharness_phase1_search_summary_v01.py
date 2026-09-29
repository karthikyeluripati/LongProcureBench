"""Materialize a durable ProcureHarness Phase-1 search termination summary.

Offline only. This script binds the frozen Round-1/Round-2 development-search
evidence and the preregistered plateau-stop artifact. It does not call a model
or execute any benchmark episode.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_procureharness_search_v01 import PROTOCOL_ID, round_candidate_ids
from select_procureharness_screening_v01 import (
    validate_frozen_screening_selection,
)
from select_procureharness_validation_v01 import (
    validate_frozen_validation_selection,
)
from select_procureharness_round_progression_v01 import (
    validate_frozen_round2_progression,
    validate_frozen_round_progression,
)

PACKAGE_REL = Path("evidence/procureharness-phase1-search-summary-v0.1")
SUMMARY_REL = PACKAGE_REL / "summary.json"
README_REL = PACKAGE_REL / "README.md"
MANIFEST_REL = PACKAGE_REL / "manifest.json"

PROTOCOL_REL = Path(
    "docs/procureharness-architecture-search-v0.1-protocol.json"
)
REGISTRY_REL = Path("docs/procureharness-candidate-registry-v0.1.json")
HARNESS_MANIFEST_REL = Path(
    "evidence/procureharness-architecture-harness-v0.1/manifest.json"
)

R1_SCREEN_MANIFEST_REL = Path(
    "evidence/procureharness-round1-screening-v0.1/manifest.json"
)
R1_SCREEN_SELECTION_REL = Path(
    "evidence/procureharness-search-gates-v0.1/"
    "screening-selection-round-1.json"
)
R1_CONFIRM_MANIFEST_REL = Path(
    "evidence/procureharness-round1-confirmation-v0.1/manifest.json"
)
R1_VALIDATION_SELECTION_REL = Path(
    "evidence/procureharness-search-gates-v0.1/"
    "validation-selection-round-1.json"
)
R1_ECONOMICS_MANIFEST_REL = Path(
    "evidence/procureharness-development-economics-v0.1/manifest.json"
)
R1_EFFICIENCY_RESULT_REL = Path(
    "evidence/procureharness-development-economics-v0.1/"
    "efficiency-gate-result.json"
)
R1_PROGRESSION_REL = Path(
    "evidence/procureharness-search-gates-v0.1/"
    "round-progression-after-round-1.json"
)

R2_SCREEN_MANIFEST_REL = Path(
    "evidence/procureharness-round2-screening-v0.1/manifest.json"
)
R2_SCREEN_SELECTION_REL = Path(
    "evidence/procureharness-search-gates-v0.1/"
    "screening-selection-round-2.json"
)
R2_CONFIRM_MANIFEST_REL = Path(
    "evidence/procureharness-round2-confirmation-v0.1/manifest.json"
)
R2_VALIDATION_SELECTION_REL = Path(
    "evidence/procureharness-search-gates-v0.1/"
    "validation-selection-round-2.json"
)
R2_ECONOMICS_MANIFEST_REL = Path(
    "evidence/procureharness-round2-economics-v0.1/manifest.json"
)
R2_EFFICIENCY_RESULT_REL = Path(
    "evidence/procureharness-round2-economics-v0.1/"
    "efficiency-gate-result.json"
)
R2_PROGRESSION_REL = Path(
    "evidence/procureharness-search-gates-v0.1/"
    "round-progression-after-round-2.json"
)

SOURCE_PATHS = {
    "protocol": PROTOCOL_REL,
    "candidate_registry": REGISTRY_REL,
    "architecture_harness_manifest": HARNESS_MANIFEST_REL,
    "round1_screening_manifest": R1_SCREEN_MANIFEST_REL,
    "round1_screening_selection": R1_SCREEN_SELECTION_REL,
    "round1_confirmation_manifest": R1_CONFIRM_MANIFEST_REL,
    "round1_validation_selection": R1_VALIDATION_SELECTION_REL,
    "round1_economics_manifest": R1_ECONOMICS_MANIFEST_REL,
    "round1_efficiency_result": R1_EFFICIENCY_RESULT_REL,
    "round1_progression": R1_PROGRESSION_REL,
    "round2_screening_manifest": R2_SCREEN_MANIFEST_REL,
    "round2_screening_selection": R2_SCREEN_SELECTION_REL,
    "round2_confirmation_manifest": R2_CONFIRM_MANIFEST_REL,
    "round2_validation_selection": R2_VALIDATION_SELECTION_REL,
    "round2_economics_manifest": R2_ECONOMICS_MANIFEST_REL,
    "round2_efficiency_result": R2_EFFICIENCY_RESULT_REL,
    "round2_progression_stop": R2_PROGRESSION_REL,
}


def _read_json(path: Path) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return sha256((ROOT / path).read_bytes()).hexdigest()


def _binding(path: Path) -> dict[str, Any]:
    raw = (ROOT / path).read_bytes()
    return {
        "path": path.as_posix(),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _write_recoverable(path: Path, raw: bytes) -> None:
    target = ROOT / path
    if target.exists():
        if not target.is_file() or target.read_bytes() != raw:
            raise ValueError(
                "existing Phase-1 summary artifact does not match "
                f"recomputed content: {path}"
            )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    temporary.write_bytes(raw)
    temporary.replace(target)


def _compact_screening_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row["candidate_id"],
        "feasible_obligation_success": row["feasible_obligation_success"],
        "strict_v02": row["strict_v02"],
        "economic_objective": row["economic_objective"],
        "obligation_resolution_rate": row["obligation_resolution_rate"],
        "known_cost_usd": row["known_cost_usd"],
        "total_tokens": row["total_tokens"],
    }


def _compact_confirmation_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row["candidate_id"],
        "feasible_obligation_success": row["feasible_obligation_success"],
        "strict_v02": row["strict_v02"],
        "economic_objective": row["economic_objective"],
        "obligation_resolution_rate": row["obligation_resolution_rate"],
        "known_cost_usd": row["known_cost_usd"],
        "total_tokens": row["total_tokens"],
        "development_confirmation_floor_passed": (
            row["development_confirmation_floor_passed"]
        ),
        "quality_promotion_passed": row["quality_promotion_passed"],
        "quality_improved_metrics": row["quality_improved_metrics"],
    }


def _compact_efficiency_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    comparison = outcome["comparison"]
    return {
        "candidate_id": outcome["candidate_id"],
        "approved": outcome["approved"],
        "status": outcome["status"],
        "reason": outcome.get("reason"),
        "reference_cohort_count": comparison["reference_cohort_count"],
        "regret_eligible_count": comparison[
            "candidate_regret_eligible_count_on_reference_cohort"
        ],
        "regret_eligibility_rate": comparison[
            "candidate_regret_eligibility_rate_on_reference_cohort"
        ],
        "regret_comparable": comparison["regret_comparable"],
        "comparison_status": comparison["status"],
    }


def _round_summary(
    *,
    round_id: int,
    screen_selection: dict[str, Any],
    validation_selection: dict[str, Any],
    efficiency_result: dict[str, Any],
) -> dict[str, Any]:
    ranking = [
        _compact_screening_row(row)
        for row in screen_selection["ranking"]
    ]
    confirmation = [
        _compact_confirmation_row(row)
        for row in validation_selection["confirmation_rows"]
    ]
    efficiency = [
        _compact_efficiency_outcome(
            efficiency_result["outcomes"][candidate_id]
        )
        for candidate_id in validation_selection[
            "pending_efficiency_candidate_ids"
        ]
    ]

    return {
        "round": round_id,
        "screened_candidate_ids": screen_selection["candidate_ids"],
        "screening_ranking": ranking,
        "screening_selected_candidate_ids": screen_selection[
            "selected_candidate_ids"
        ],
        "confirmation": confirmation,
        "quality_validation_selected_candidate_ids": validation_selection[
            "validation_selected_candidate_ids"
        ],
        "efficiency_outcomes": efficiency,
        "efficiency_validation_authorized_candidate_ids": (
            efficiency_result["authorized_candidate_ids"]
        ),
        "final_validation_candidate_ids": list(
            dict.fromkeys(
                [
                    *validation_selection[
                        "validation_selected_candidate_ids"
                    ],
                    *efficiency_result["authorized_candidate_ids"],
                ]
            )
        ),
        "round_added_new_frontier_point": False,
    }


def _validate_sources() -> dict[str, Any]:
    protocol = _read_json(PROTOCOL_REL)
    registry = _read_json(REGISTRY_REL)

    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Phase-1 summary protocol identity changed")

    procedure = protocol.get("search_procedure")
    if not isinstance(procedure, dict):
        raise ValueError("Phase-1 search procedure missing")
    if procedure.get("max_rounds") != 3:
        raise ValueError("Phase-1 max_rounds changed")
    if procedure.get("max_unique_candidates") != 18:
        raise ValueError("Phase-1 max_unique_candidates changed")
    if (
        (procedure.get("ceiling_stop_rule") or {}).get("plateau_rounds")
        != 2
    ):
        raise ValueError("Phase-1 plateau threshold changed")

    candidates = registry.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 18:
        raise ValueError("Phase-1 candidate registry cardinality changed")

    r1_screen = _read_json(R1_SCREEN_SELECTION_REL)
    r2_screen = _read_json(R2_SCREEN_SELECTION_REL)
    validate_frozen_screening_selection(r1_screen)
    validate_frozen_screening_selection(r2_screen)

    r1_validation = _read_json(R1_VALIDATION_SELECTION_REL)
    r2_validation = _read_json(R2_VALIDATION_SELECTION_REL)
    validate_frozen_validation_selection(r1_validation)
    validate_frozen_validation_selection(r2_validation)

    r1_economics = _read_json(R1_EFFICIENCY_RESULT_REL)
    r2_economics = _read_json(R2_EFFICIENCY_RESULT_REL)
    for round_id, result in ((1, r1_economics), (2, r2_economics)):
        if result.get("schema_version") != "0.1.0":
            raise ValueError(
                f"Round-{round_id} economics result schema changed"
            )
        if result.get("protocol_id") != PROTOCOL_ID:
            raise ValueError(
                f"Round-{round_id} economics result protocol changed"
            )
        if result.get("provider_calls") != 0:
            raise ValueError(
                f"Round-{round_id} economics gate used provider calls"
            )
        if result.get("authorized_candidate_ids") != []:
            raise ValueError(
                f"Round-{round_id} unexpectedly authorized validation"
            )

    r1_progression = _read_json(R1_PROGRESSION_REL)
    r2_progression = _read_json(R2_PROGRESSION_REL)
    validate_frozen_round_progression(r1_progression)
    validate_frozen_round2_progression(r2_progression)

    if r1_progression.get("decision") != "advance":
        raise ValueError("Round-1 progression no longer advances to Round 2")
    if r2_progression.get("decision") != "stop":
        raise ValueError("Round-2 progression no longer stops the search")
    if r2_progression.get("plateau_stop_fired") is not True:
        raise ValueError("Round-2 plateau stop no longer fires")
    if r2_progression.get("screening_authorized_candidate_ids") != []:
        raise ValueError("Round-2 stop unexpectedly authorizes Round 3")

    for candidate_id in round_candidate_ids(3):
        auth = (
            ROOT
            / "evidence"
            / "procureharness-search-gates-v0.1"
            / f"{candidate_id}--screening-auth.json"
        )
        if auth.exists():
            raise ValueError(
                f"Round-3 authorization exists after plateau stop: {auth}"
            )

    manifests = [
        _read_json(R1_SCREEN_MANIFEST_REL),
        _read_json(R1_CONFIRM_MANIFEST_REL),
        _read_json(R2_SCREEN_MANIFEST_REL),
        _read_json(R2_CONFIRM_MANIFEST_REL),
    ]
    expected_runs = [120, 120, 120, 120]
    for manifest, expected in zip(manifests, expected_runs):
        if manifest.get("protocol_id") != PROTOCOL_ID:
            raise ValueError("development evidence protocol changed")
        if manifest.get("total_runs") != expected:
            raise ValueError("development evidence run count changed")

    return {
        "protocol": protocol,
        "registry": registry,
        "r1_screen": r1_screen,
        "r1_validation": r1_validation,
        "r1_economics": r1_economics,
        "r1_progression": r1_progression,
        "r2_screen": r2_screen,
        "r2_validation": r2_validation,
        "r2_economics": r2_economics,
        "r2_progression": r2_progression,
        "manifests": manifests,
    }


def build_summary() -> dict[str, Any]:
    source = _validate_sources()

    round1 = _round_summary(
        round_id=1,
        screen_selection=source["r1_screen"],
        validation_selection=source["r1_validation"],
        efficiency_result=source["r1_economics"],
    )
    round2 = _round_summary(
        round_id=2,
        screen_selection=source["r2_screen"],
        validation_selection=source["r2_validation"],
        efficiency_result=source["r2_economics"],
    )

    screening_rows = [
        *round1["screening_ranking"],
        *round2["screening_ranking"],
    ]
    confirmation_rows = [
        *round1["confirmation"],
        *round2["confirmation"],
    ]
    resource_rows = [*screening_rows, *confirmation_rows]

    total_known_cost = sum(
        float(row["known_cost_usd"]) for row in resource_rows
    )
    total_tokens = sum(int(row["total_tokens"]) for row in resource_rows)

    registry_rows = source["registry"]["candidates"]
    executed_designs = [
        row for row in registry_rows if row.get("round") in {1, 2}
    ]
    unexecuted_designs = [
        row for row in registry_rows if row.get("round") == 3
    ]

    return {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "package_id": "procureharness-phase1-search-summary-v0.1",
        "phase": "phase1_architecture_search",
        "search_status": "terminated",
        "termination": {
            "completed_round": 2,
            "decision": source["r2_progression"]["decision"],
            "stop_reason": source["r2_progression"]["stop_reason"],
            "plateau_stop_threshold": source["r2_progression"][
                "plateau_stop_threshold"
            ],
            "consecutive_no_new_frontier_rounds": source[
                "r2_progression"
            ]["consecutive_no_new_frontier_rounds"],
            "max_rounds_stop_fired": source["r2_progression"][
                "max_rounds_stop_fired"
            ],
            "unique_candidate_budget_stop_fired": source[
                "r2_progression"
            ]["unique_candidate_budget_stop_fired"],
        },
        "execution_accounting": {
            "preregistered_rounds": 3,
            "completed_rounds": 2,
            "preregistered_candidates": 18,
            "screened_candidates": 12,
            "development_confirmed_candidates": 4,
            "development_runs": sum(
                int(manifest["total_runs"])
                for manifest in source["manifests"]
            ),
            "search_validation_031_040_runs": 0,
            "final_test_041_050_runs": 0,
            "round3_executed": False,
            "known_cost_usd_across_executed_search_rows": total_known_cost,
            "total_tokens_across_executed_search_rows": total_tokens,
            "summary_provider_calls": 0,
        },
        "rounds": {
            "1": round1,
            "2": round2,
        },
        "candidate_designs": {
            "executed": executed_designs,
            "not_executed_due_plateau_stop": unexecuted_designs,
        },
        "development_gate_result": {
            "quality_promoted_candidate_ids": [],
            "efficiency_promoted_candidate_ids": [],
            "validation_authorized_candidate_ids": [],
            "repeated_efficiency_failure_pattern": {
                "affected_candidate_ids": [
                    "ph-r1-c02",
                    "ph-r1-c05",
                    "ph-r2-c12",
                    "ph-r2-c09",
                ],
                "reason": (
                    "candidate lacks full frozen regret "
                    "reference-cohort comparability"
                ),
                "regret_eligible_count": 42,
                "reference_cohort_count": 48,
                "regret_eligibility_rate": 0.875,
            },
        },
        "claim_boundary": {
            "supported": [
                (
                    "The preregistered Phase-1 development architecture "
                    "search terminated after Round 2 under the frozen "
                    "two-round plateau rule."
                ),
                (
                    "No tested ProcureHarness candidate satisfied the "
                    "frozen development promotion requirements needed to "
                    "enter 031-040 search validation."
                ),
            ],
            "not_supported": [
                "global-optimum claim over agent architectures",
                "ProcureHarness superiority on 031-040 search validation",
                "ProcureHarness superiority on 041-050 final test",
            ],
        },
        "evidence_bindings": {
            name: _binding(path)
            for name, path in SOURCE_PATHS.items()
        },
    }


def build_readme(summary: dict[str, Any]) -> str:
    r1 = summary["rounds"]["1"]
    r2 = summary["rounds"]["2"]
    accounting = summary["execution_accounting"]
    termination = summary["termination"]

    lines = [
        "# ProcureHarness Phase-1 Search Termination Summary v0.1",
        "",
        "This package is an offline, evidence-bound summary of the "
        "preregistered ProcureHarness Phase-1 architecture search.",
        "",
        "## Search accounting",
        "",
        f"- Completed rounds: {accounting['completed_rounds']} / "
        f"{accounting['preregistered_rounds']}",
        f"- Screened candidates: {accounting['screened_candidates']} / "
        f"{accounting['preregistered_candidates']}",
        f"- Development-confirmed candidates: "
        f"{accounting['development_confirmed_candidates']}",
        f"- Development runs: {accounting['development_runs']}",
        f"- 031-040 search-validation runs: "
        f"{accounting['search_validation_031_040_runs']}",
        f"- 041-050 final-test runs: "
        f"{accounting['final_test_041_050_runs']}",
        f"- Round 3 executed: {str(accounting['round3_executed']).lower()}",
        f"- Known model cost across executed search rows: USD "
        f"{accounting['known_cost_usd_across_executed_search_rows']:.7f}",
        f"- Total tokens across executed search rows: "
        f"{accounting['total_tokens_across_executed_search_rows']}",
        "",
        "## Round outcomes",
        "",
        "Round 1 screened C01-C06 and selected "
        + ", ".join(r1["screening_selected_candidate_ids"])
        + " for 001-020 x3 confirmation. Both passed the development "
        "floor, neither passed the quality-promotion branch, and neither "
        "passed the frozen efficiency branch.",
        "",
        "Round 2 screened C07-C12 and selected "
        + ", ".join(r2["screening_selected_candidate_ids"])
        + " for 001-020 x3 confirmation. Both passed the development "
        "floor, neither passed the quality-promotion branch, and neither "
        "passed the frozen efficiency branch.",
        "",
        "Across all four confirmed candidates, the efficiency branch "
        "failed full regret comparability: 42/48 frozen reference-cohort "
        "runs were eligible (87.5%), while 48/48 was required.",
        "",
        "## Termination",
        "",
        f"The frozen progression gate recorded "
        f"{termination['consecutive_no_new_frontier_rounds']} consecutive "
        "completed rounds with no new validation-frontier point. The "
        f"plateau threshold is {termination['plateau_stop_threshold']}, "
        "so the search decision is **stop**. No Round-3 screening "
        "authorization exists.",
        "",
        "## Claim boundary",
        "",
        "This is a development-search termination result. It does **not** "
        "establish a global optimum, a 031-040 validation advantage, or a "
        "041-050 final-test advantage. Those claims are not supported "
        "because no ProcureHarness candidate entered search validation.",
        "",
    ]
    return "\n".join(lines)


def materialize() -> dict[str, Any]:
    summary = build_summary()
    summary_bytes = _canonical_json_bytes(summary)
    readme_bytes = build_readme(summary).encode("utf-8")

    _write_recoverable(SUMMARY_REL, summary_bytes)
    _write_recoverable(README_REL, readme_bytes)

    manifest = {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "package_id": "procureharness-phase1-search-summary-v0.1",
        "execution": {
            "mode": "offline_evidence_summary",
            "provider_calls": 0,
        },
        "generated_files": {
            "summary": _binding(SUMMARY_REL),
            "readme": _binding(README_REL),
        },
        "source_evidence": {
            name: _binding(path)
            for name, path in SOURCE_PATHS.items()
        },
    }
    _write_recoverable(MANIFEST_REL, _canonical_json_bytes(manifest))
    return summary


def main() -> None:
    summary = materialize()
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
