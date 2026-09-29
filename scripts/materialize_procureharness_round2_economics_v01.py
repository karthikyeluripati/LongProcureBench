"""Materialize the ProcureHarness Round-2 offline economics gate.

This script makes no model/provider calls. It scores the already-frozen C12/C09
001-020 x3 confirmation results, reuses the commit-frozen Coverage+Repair/ReAct
baseline economics package, and applies the unchanged efficiency-promotion rule.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from longprocurebench import (
    EconomicRegretEvaluator,
    compare_candidate_on_reference_cohort,
)
from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MODEL,
    PROTOCOL_ID,
    validate_phase_authorization,
)
from select_procureharness_validation_v01 import (
    _load_development_economics_binding,
    evaluate_efficiency_promotion,
    freeze_efficiency_validation_authorization,
    validate_frozen_efficiency_addendum,
    validate_frozen_validation_selection,
)

PACKAGE_REL = Path("evidence/procureharness-round2-economics-v0.1")
GATE_REL = Path("evidence/procureharness-search-gates-v0.1")
BASE_SELECTION_REL = GATE_REL / "validation-selection-round-2.json"
CONFIRMATION_MANIFEST_REL = Path(
    "evidence/procureharness-round2-confirmation-v0.1/manifest.json"
)
BASELINE_PACKAGE_REL = Path(
    "evidence/procureharness-development-economics-v0.1"
)
BASELINE_MANIFEST_REL = BASELINE_PACKAGE_REL / "manifest.json"
BASELINE_REFERENCE_COHORT_REL = BASELINE_PACKAGE_REL / "reference-cohort.json"

CANDIDATES = ("ph-r2-c12", "ph-r2-c09")
CANDIDATE_REPORT_FILES = {
    candidate_id: PACKAGE_REL / f"{candidate_id}-reports.json"
    for candidate_id in CANDIDATES
}
COMPARISONS_REL = PACKAGE_REL / "comparisons.json"
MANIFEST_REL = PACKAGE_REL / "manifest.json"
GATE_RESULT_REL = PACKAGE_REL / "efficiency-gate-result.json"

EXPECTED_REJECTION_PREFIXES = (
    "candidate fails efficiency quality deficit on ",
    "candidate fails efficiency known-cost reduction requirement",
    "candidate lacks full frozen regret reference-cohort comparability",
    "Coverage+Repair regret reference cohort is unavailable",
    "efficiency promotion requires finite comparable regret means",
    "candidate regret is worse than Coverage+Repair on frozen cohort",
)


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


def _write_json(path: Path, value: Any) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_canonical_json_bytes(value))


def _write_recoverable_json(path: Path, value: Any) -> None:
    """Create an immutable deterministic JSON artifact, or reuse an exact survivor."""
    target = ROOT / path
    encoded = _canonical_json_bytes(value)
    if target.exists():
        if not target.is_file() or target.read_bytes() != encoded:
            raise ValueError(
                "existing Round-2 economics artifact does not match "
                f"recomputed frozen content: {path}"
            )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    temporary.write_bytes(encoded)
    temporary.replace(target)


def _read_json(path: Path) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str:
    return sha256((ROOT / path).read_bytes()).hexdigest()


def _binding(path: Path) -> dict[str, Any]:
    target = ROOT / path
    raw = target.read_bytes()
    return {
        "path": path.as_posix(),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _expected_run_keys() -> list[tuple[str, int]]:
    return [
        (episode_id, repeat)
        for repeat in (1, 2, 3)
        for episode_id in DEVELOPMENT_EPISODES
    ]


def _ordered_reports(
    reports: list[dict[str, Any]],
    *,
    label: str,
) -> list[dict[str, Any]]:
    by_key = {}
    for report in reports:
        run_key = report.get("run_key") or {}
        key = (run_key.get("episode_id"), run_key.get("repeat"))
        if key in by_key:
            raise ValueError(f"duplicate {label} economics key: {key}")
        by_key[key] = report
    expected = _expected_run_keys()
    if set(by_key) != set(expected):
        raise ValueError(f"{label} economics grid is not exact 001-020 x3")
    return [by_key[key] for key in expected]


def _candidate_result_path(
    candidate_id: str,
    episode_id: str,
    repeat: int,
) -> Path:
    return (
        Path("evidence/procureharness-round2-confirmation-v0.1/results")
        / candidate_id
        / "development_confirmation"
        / f"r{repeat}"
        / f"{episode_id}.json"
    )


def _confirmation_source_bindings() -> dict[str, dict[str, Any]]:
    manifest = _read_json(CONFIRMATION_MANIFEST_REL)
    if manifest.get("candidate_ids") != list(CANDIDATES):
        raise ValueError("Round-2 confirmation manifest candidate set changed")
    if manifest.get("total_runs") != 120:
        raise ValueError("Round-2 confirmation manifest run count changed")

    rows = manifest.get("source_files")
    if not isinstance(rows, list):
        raise ValueError("Round-2 confirmation manifest source_files missing")

    by_path: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Round-2 confirmation source binding is invalid")
        path_value = row.get("path")
        expected_sha = row.get("sha256")
        expected_bytes = row.get("bytes")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError("Round-2 confirmation source path is invalid")
        if path_value in by_path:
            raise ValueError(
                f"duplicate Round-2 confirmation source path: {path_value}"
            )
        if (
            not isinstance(expected_sha, str)
            or len(expected_sha) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha)
        ):
            raise ValueError(
                f"invalid Round-2 confirmation source SHA-256: {path_value}"
            )
        if (
            not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes < 0
        ):
            raise ValueError(
                f"invalid Round-2 confirmation source byte count: {path_value}"
            )
        by_path[path_value] = row
    return by_path


def _verify_frozen_confirmation_result(
    path: Path,
    *,
    source_bindings: dict[str, dict[str, Any]],
) -> bytes:
    path_value = path.as_posix()
    row = source_bindings.get(path_value)
    if row is None:
        raise ValueError(
            f"raw confirmation result is not bound by frozen manifest: {path}"
        )
    target = ROOT / path
    if not target.is_file():
        raise ValueError(f"frozen confirmation result is missing: {path}")
    raw = target.read_bytes()
    if len(raw) != row["bytes"]:
        raise ValueError(
            f"frozen confirmation result byte count mismatch: {path}"
        )
    if sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError(
            f"frozen confirmation result SHA-256 mismatch: {path}"
        )
    return raw


def _score_candidate(candidate_id: str) -> list[dict[str, Any]]:
    economics = EconomicRegretEvaluator(repo_root=ROOT)
    expected_policy_id = f"procureharness--{candidate_id}--{MODEL}"
    reports: list[dict[str, Any]] = []
    source_bindings = _confirmation_source_bindings()

    for episode_id, repeat in _expected_run_keys():
        path = _candidate_result_path(candidate_id, episode_id, repeat)
        raw = _verify_frozen_confirmation_result(
            path,
            source_bindings=source_bindings,
        )
        result = json.loads(raw.decode("utf-8"))
        if result.get("episode_id") != episode_id:
            raise ValueError(f"{candidate_id} raw result episode mismatch")
        if result.get("status") not in {"completed", "max_actions"}:
            raise ValueError(
                f"{candidate_id} raw result is not clean: {path}"
            )
        policy_id = (result.get("policy") or {}).get("policy_id")
        if policy_id != expected_policy_id:
            raise ValueError(
                f"{candidate_id} raw policy mismatch: {policy_id!r}"
            )
        reports.append(
            economics.score_result(result, repeat=repeat)
        )

    return _ordered_reports(reports, label=candidate_id)


def _load_baseline_inputs() -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    binding = _load_development_economics_binding()
    manifest = _read_json(BASELINE_MANIFEST_REL)

    if binding.get("manifest_sha256") != _sha256_path(
        BASELINE_MANIFEST_REL
    ):
        raise ValueError("baseline economics manifest hash drift")
    if binding.get("freeze_commit") != manifest.get("freeze_commit"):
        raise ValueError("baseline economics freeze commit drift")

    reports = binding.get("reports")
    if not isinstance(reports, dict):
        raise ValueError("baseline economics reports binding missing")

    coverage_row = reports.get("coverage_repair")
    react_row = reports.get("react")
    if not isinstance(coverage_row, dict) or not isinstance(react_row, dict):
        raise ValueError("baseline economics report bindings incomplete")

    coverage_path = Path(coverage_row["path"])
    react_path = Path(react_row["path"])
    coverage = _read_json(coverage_path)
    react = _read_json(react_path)

    if _sha256_path(coverage_path) != coverage_row["sha256"]:
        raise ValueError("Coverage+Repair baseline report hash drift")
    if _sha256_path(react_path) != react_row["sha256"]:
        raise ValueError("ReAct baseline report hash drift")

    coverage = _ordered_reports(coverage, label="Coverage+Repair")
    react = _ordered_reports(react, label="ReAct")

    cohort_binding = manifest.get("reference_cohort")
    if not isinstance(cohort_binding, dict):
        raise ValueError("baseline economics reference cohort binding missing")
    if cohort_binding.get("path") != BASELINE_REFERENCE_COHORT_REL.as_posix():
        raise ValueError("baseline economics reference cohort path drift")
    if _sha256_path(BASELINE_REFERENCE_COHORT_REL) != cohort_binding.get(
        "sha256"
    ):
        raise ValueError("baseline economics reference cohort hash drift")

    cohort = _read_json(BASELINE_REFERENCE_COHORT_REL)
    if cohort.get("status") != "available":
        raise ValueError("frozen economics reference cohort unavailable")
    if cohort.get("reference_cohort_count") != 48:
        raise ValueError("frozen economics reference cohort count changed")

    return binding, coverage, react, cohort


def build_round2_economics_payloads() -> dict[str, Any]:
    baseline_binding, coverage, react, cohort = _load_baseline_inputs()

    candidates = {
        candidate_id: _score_candidate(candidate_id)
        for candidate_id in CANDIDATES
    }

    comparisons = {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "reference_cohort": cohort,
        "coverage_repair": compare_candidate_on_reference_cohort(
            coverage,
            coverage_repair_reports=coverage,
            react_reports=react,
            reference_cohort=cohort,
        ),
        "candidates": {
            candidate_id: compare_candidate_on_reference_cohort(
                reports,
                coverage_repair_reports=coverage,
                react_reports=react,
                reference_cohort=cohort,
            )
            for candidate_id, reports in candidates.items()
        },
    }

    return {
        "baseline_binding": baseline_binding,
        "candidates": candidates,
        "comparisons": comparisons,
    }


def _is_expected_rejection(message: str) -> bool:
    return any(
        message.startswith(prefix)
        for prefix in EXPECTED_REJECTION_PREFIXES
    )


def materialize() -> dict[str, Any]:
    # Validate all frozen inputs and compute deterministic payloads before
    # publishing any package artifact. A retry may then reuse exact survivors.
    base_selection = _read_json(BASE_SELECTION_REL)
    validate_frozen_validation_selection(base_selection)
    if base_selection.get("round") != 2:
        raise ValueError("Round-2 base validation selection round changed")
    if base_selection.get("pending_efficiency_candidate_ids") != list(
        CANDIDATES
    ):
        raise ValueError("unexpected Round-2 pending efficiency candidates")
    if base_selection.get("validation_slot_candidate_ids") != list(
        CANDIDATES
    ):
        raise ValueError("unexpected Round-2 reserved validation slots")
    if base_selection.get("validation_selected_candidate_ids") != []:
        raise ValueError("Round-2 already contains a quality-selected candidate")

    confirmation_manifest = _read_json(CONFIRMATION_MANIFEST_REL)
    if confirmation_manifest.get("candidate_ids") != list(CANDIDATES):
        raise ValueError("Round-2 confirmation manifest candidate set changed")
    if confirmation_manifest.get("total_runs") != 120:
        raise ValueError("Round-2 confirmation manifest run count changed")

    payloads = build_round2_economics_payloads()

    # Publish deterministic package pieces recoverably. Exact files left by an
    # interrupted attempt are reused; any mismatched survivor fails closed.
    for candidate_id, path in CANDIDATE_REPORT_FILES.items():
        _write_recoverable_json(
            path,
            payloads["candidates"][candidate_id],
        )
    _write_recoverable_json(
        COMPARISONS_REL,
        payloads["comparisons"],
    )

    manifest = {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "package_id": "procureharness-round2-economics-v0.1",
        "round": 2,
        "candidate_ids": list(CANDIDATES),
        "candidate_reports": {
            candidate_id: {
                **_binding(path),
                "policy_id": f"procureharness--{candidate_id}--{MODEL}",
            }
            for candidate_id, path in CANDIDATE_REPORT_FILES.items()
        },
        "comparisons": _binding(COMPARISONS_REL),
        "base_validation_selection": _binding(BASE_SELECTION_REL),
        "source_confirmation_manifest": _binding(
            CONFIRMATION_MANIFEST_REL
        ),
        "baseline_economics_manifest": _binding(
            BASELINE_MANIFEST_REL
        ),
        "baseline_reference_cohort": _binding(
            BASELINE_REFERENCE_COHORT_REL
        ),
        "baseline_freeze_commit": payloads["baseline_binding"][
            "freeze_commit"
        ],
        "execution": {
            "mode": "offline_deterministic_economics",
            "provider_calls": 0,
        },
    }
    _write_recoverable_json(MANIFEST_REL, manifest)

    comparisons = payloads["comparisons"]
    outcomes: dict[str, Any] = {}
    for candidate_id in CANDIDATES:
        candidate_path = CANDIDATE_REPORT_FILES[candidate_id]
        try:
            promotion = evaluate_efficiency_promotion(
                base_selection=base_selection,
                candidate_id=candidate_id,
                candidate_reports_path=candidate_path.as_posix(),
                expected_candidate_sha256=_sha256_path(candidate_path),
            )
        except ValueError as exc:
            message = str(exc)
            if not _is_expected_rejection(message):
                raise
            stale_paths = (
                ROOT
                / GATE_REL
                / (
                    f"validation-efficiency-addendum-round-2"
                    f"--{candidate_id}.json"
                ),
                ROOT
                / GATE_REL
                / f"{candidate_id}--validation-efficiency-auth.json",
            )
            if any(path.exists() for path in stale_paths):
                raise ValueError(
                    f"{candidate_id} is rejected but an efficiency "
                    "authorization artifact already exists"
                ) from exc
            outcomes[candidate_id] = {
                "candidate_id": candidate_id,
                "approved": False,
                "status": "not_promoted",
                "reason": message,
                "comparison": comparisons["candidates"][candidate_id],
            }
            continue

        addendum_path, auth_path = (
            freeze_efficiency_validation_authorization(
                base_selection_path=BASE_SELECTION_REL,
                candidate_id=candidate_id,
                candidate_reports_path=candidate_path,
                output_dir=GATE_REL,
            )
        )
        addendum = _read_json(addendum_path)
        authorization = _read_json(auth_path)
        validate_frozen_efficiency_addendum(addendum)
        validate_phase_authorization(
            candidate_id=candidate_id,
            phase="validation",
            authorization=authorization,
        )
        outcomes[candidate_id] = {
            "candidate_id": candidate_id,
            "approved": True,
            "status": "authorized",
            "promotion": promotion,
            "addendum_path": addendum_path.as_posix(),
            "authorization_path": auth_path.as_posix(),
            "comparison": comparisons["candidates"][candidate_id],
        }

    result = {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "rule": "frozen_development_efficiency_promotion_v0.1",
        "round": 2,
        "base_validation_selection_path": BASE_SELECTION_REL.as_posix(),
        "base_validation_selection_sha256": _sha256_path(
            BASE_SELECTION_REL
        ),
        "round2_economics_manifest_path": MANIFEST_REL.as_posix(),
        "round2_economics_manifest_sha256": _sha256_path(MANIFEST_REL),
        "outcomes": outcomes,
        "authorized_candidate_ids": [
            candidate_id
            for candidate_id in CANDIDATES
            if outcomes[candidate_id]["approved"]
        ],
        "not_promoted_candidate_ids": [
            candidate_id
            for candidate_id in CANDIDATES
            if not outcomes[candidate_id]["approved"]
        ],
        "provider_calls": 0,
    }
    _write_recoverable_json(GATE_RESULT_REL, result)

    if _read_json(BASE_SELECTION_REL) != base_selection:
        raise ValueError("Round-2 base validation selection changed")

    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main() -> None:
    materialize()


if __name__ == "__main__":
    main()
