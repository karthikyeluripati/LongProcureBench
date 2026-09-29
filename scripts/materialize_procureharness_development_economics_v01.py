"""Materialize frozen ProcureHarness Round-1 development economics.

This script is offline only. It reconstructs already-frozen development
trajectories, scores deterministic procurement economics, freezes the baseline
binding package, and applies the preregistered late efficiency-promotion gate.
It never calls a model/provider API.
"""
from __future__ import annotations

import argparse
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from longprocurebench import (
    EconomicRegretEvaluator,
    LongProcureBenchEvaluator,
    compare_candidate_on_reference_cohort,
    freeze_reference_cohort,
)
from frozen_coverage_repair_confirmatory_v01 import (
    EPISODES as COVERAGE_EPISODES,
    load_frozen_coverage_repair_source,
    reconstruct_actions as reconstruct_coverage_actions,
)
from frozen_react_comparator_v01 import (
    EPISODES as REACT_EPISODES,
    load_frozen_react_source,
    reconstruct_actions as reconstruct_react_actions,
)
from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MODEL,
    PROTOCOL_ID,
    validate_phase_authorization,
)
from select_procureharness_validation_v01 import (
    DEVELOPMENT_ECONOMICS_BINDING_PACKAGE,
    _load_development_economics_binding,
    evaluate_efficiency_promotion,
    freeze_efficiency_validation_authorization,
    validate_frozen_efficiency_addendum,
    validate_frozen_validation_selection,
)

PACKAGE_REL = Path("evidence/procureharness-development-economics-v0.1")
GATE_REL = Path("evidence/procureharness-search-gates-v0.1")
BASE_SELECTION_REL = GATE_REL / "validation-selection-round-1.json"
CANDIDATES = ("ph-r1-c02", "ph-r1-c05")
BASELINE_REPORT_FILES = {
    "coverage_repair": PACKAGE_REL / "coverage-repair-reports.json",
    "react": PACKAGE_REL / "react-reports.json",
}
CANDIDATE_REPORT_FILES = {
    candidate_id: PACKAGE_REL / f"{candidate_id}-reports.json"
    for candidate_id in CANDIDATES
}
DESCRIPTOR_REL = PACKAGE_REL / "binding.json"
REFERENCE_COHORT_REL = PACKAGE_REL / "reference-cohort.json"
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


def _read_json(path: Path) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str:
    return sha256((ROOT / path).read_bytes()).hexdigest()


def _git_blob_sha1_bytes(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return sha1(header + raw).hexdigest()


def _git_blob_sha1_path(path: Path) -> str:
    return _git_blob_sha1_bytes((ROOT / path).read_bytes())


def _git_blob_at(commit: str, path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{commit}:{path.as_posix()}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    blob = result.stdout.strip()
    if len(blob) != 40:
        raise ValueError(f"invalid Git blob for {path}: {blob!r}")
    return blob


def _file_binding(path: Path) -> dict[str, Any]:
    raw = (ROOT / path).read_bytes()
    return {
        "path": path.as_posix(),
        "git_blob_sha1": _git_blob_sha1_bytes(raw),
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


def _baseline_result(
    *,
    record: dict[str, Any],
    policy_id: str,
    actions: list[dict[str, Any]],
    evaluator: LongProcureBenchEvaluator,
) -> dict[str, Any]:
    episode_id = record["episode_id"]
    evaluation = evaluator.evaluate_actions(episode_id, actions)
    return {
        "episode_id": episode_id,
        "run_id": f"{policy_id}--{episode_id}--r{record['repeat']}",
        "policy": {
            "policy_id": policy_id,
            "policy_kind": "frozen_development_comparator",
        },
        "evaluation": evaluation,
    }


def _score_coverage_repair() -> list[dict[str, Any]]:
    if COVERAGE_EPISODES != DEVELOPMENT_EPISODES:
        raise ValueError("Coverage+Repair frozen episode grid changed")
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    economics = EconomicRegretEvaluator(repo_root=ROOT)
    reports = []
    records = load_frozen_coverage_repair_source(ROOT)
    for record in records:
        result = _baseline_result(
            record=record,
            policy_id="coverage-repair--openai/gpt-5.6-sol",
            actions=reconstruct_coverage_actions(record),
            evaluator=evaluator,
        )
        reports.append(
            economics.score_result(result, repeat=record["repeat"])
        )
    return _ordered_reports(reports, label="Coverage+Repair")


def _score_react() -> list[dict[str, Any]]:
    if REACT_EPISODES != DEVELOPMENT_EPISODES:
        raise ValueError("ReAct frozen episode grid changed")
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    economics = EconomicRegretEvaluator(repo_root=ROOT)
    reports = []
    records = load_frozen_react_source(ROOT)
    for record in records:
        result = _baseline_result(
            record=record,
            policy_id="react--openai/gpt-5.6-sol",
            actions=reconstruct_react_actions(record),
            evaluator=evaluator,
        )
        reports.append(
            economics.score_result(result, repeat=record["repeat"])
        )
    return _ordered_reports(reports, label="ReAct")


def _candidate_result_path(
    candidate_id: str,
    episode_id: str,
    repeat: int,
) -> Path:
    return (
        Path("evidence/procureharness-round1-confirmation-v0.1/results")
        / candidate_id
        / "development_confirmation"
        / f"r{repeat}"
        / f"{episode_id}.json"
    )


def _score_candidate(candidate_id: str) -> list[dict[str, Any]]:
    economics = EconomicRegretEvaluator(repo_root=ROOT)
    reports = []
    expected_policy_id = f"procureharness--{candidate_id}--{MODEL}"
    for episode_id, repeat in _expected_run_keys():
        path = _candidate_result_path(candidate_id, episode_id, repeat)
        result = _read_json(path)
        if result.get("episode_id") != episode_id:
            raise ValueError(f"{candidate_id} raw result episode mismatch")
        if result.get("status") not in {"completed", "max_actions"}:
            raise ValueError(
                f"{candidate_id} raw result is not clean: {path}"
            )
        policy_id = (result.get("policy") or {}).get("policy_id")
        if policy_id != expected_policy_id:
            raise ValueError(
                f"{candidate_id} raw result policy mismatch: {policy_id!r}"
            )
        reports.append(
            economics.score_result(result, repeat=repeat)
        )
    return _ordered_reports(reports, label=candidate_id)


def build_economics_payloads() -> dict[str, Any]:
    coverage = _score_coverage_repair()
    react = _score_react()
    candidates = {
        candidate_id: _score_candidate(candidate_id)
        for candidate_id in CANDIDATES
    }
    cohort = freeze_reference_cohort(coverage, react)
    coverage_comparison = compare_candidate_on_reference_cohort(
        coverage,
        coverage_repair_reports=coverage,
        react_reports=react,
        reference_cohort=cohort,
    )
    comparisons = {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "reference_cohort": cohort,
        "coverage_repair": coverage_comparison,
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
        "coverage_repair": coverage,
        "react": react,
        "candidates": candidates,
        "reference_cohort": cohort,
        "comparisons": comparisons,
    }


def prepare() -> None:
    package = ROOT / PACKAGE_REL
    if package.exists():
        raise ValueError(
            f"refusing to overwrite development economics package: {package}"
        )
    package.mkdir(parents=True)

    payloads = build_economics_payloads()
    _write_json(
        BASELINE_REPORT_FILES["coverage_repair"],
        payloads["coverage_repair"],
    )
    _write_json(BASELINE_REPORT_FILES["react"], payloads["react"])
    for candidate_id, path in CANDIDATE_REPORT_FILES.items():
        _write_json(path, payloads["candidates"][candidate_id])
    _write_json(REFERENCE_COHORT_REL, payloads["reference_cohort"])
    _write_json(COMPARISONS_REL, payloads["comparisons"])

    descriptor = {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "package": DEVELOPMENT_ECONOMICS_BINDING_PACKAGE,
        "reports": {
            name: {
                key: value
                for key, value in _file_binding(path).items()
                if key in {"path", "git_blob_sha1", "sha256"}
            }
            for name, path in BASELINE_REPORT_FILES.items()
        },
    }
    _write_json(DESCRIPTOR_REL, descriptor)
    print(
        "prepared frozen development economics inputs: "
        "Coverage+Repair, ReAct, C02, C05"
    )


def _verify_freeze_commit(
    freeze_commit: str,
    paths: list[Path],
) -> None:
    for path in paths:
        current_blob = _git_blob_sha1_path(path)
        frozen_blob = _git_blob_at(freeze_commit, path)
        if current_blob != frozen_blob:
            raise ValueError(
                f"economics freeze mismatch for {path}: "
                f"current={current_blob}, frozen={frozen_blob}"
            )


def _manifest_payload(freeze_commit: str) -> dict[str, Any]:
    descriptor = _read_json(DESCRIPTOR_REL)
    descriptor_binding = _file_binding(DESCRIPTOR_REL)
    candidate_bindings = {
        candidate_id: {
            **_file_binding(path),
            "policy_id": f"procureharness--{candidate_id}--{MODEL}",
        }
        for candidate_id, path in CANDIDATE_REPORT_FILES.items()
    }
    return {
        "schema_version": "0.1.0",
        "protocol_id": PROTOCOL_ID,
        "package": DEVELOPMENT_ECONOMICS_BINDING_PACKAGE,
        "freeze_commit": freeze_commit,
        "binding_descriptor": {
            key: descriptor_binding[key]
            for key in ("path", "git_blob_sha1", "sha256")
        },
        "reports": descriptor["reports"],
        "candidate_reports": candidate_bindings,
        "reference_cohort": _file_binding(REFERENCE_COHORT_REL),
        "comparisons": _file_binding(COMPARISONS_REL),
        "source_evidence": {
            "coverage_repair": (
                "evidence/coverage-repair-confirmatory-v0.1"
            ),
            "react": "evidence/react-comparator-v0.1",
            "procureharness_confirmation": (
                "evidence/procureharness-round1-confirmation-v0.1"
            ),
        },
        "execution": {
            "provider_calls": 0,
            "mode": "offline_deterministic_replay_and_economics",
        },
    }


def _is_expected_rejection(message: str) -> bool:
    return any(
        message.startswith(prefix)
        for prefix in EXPECTED_REJECTION_PREFIXES
    )


def finalize(freeze_commit: str) -> None:
    if (
        len(freeze_commit) != 40
        or any(ch not in "0123456789abcdef" for ch in freeze_commit)
    ):
        raise ValueError("freeze commit must be a lowercase 40-hex SHA")

    required_frozen_paths = [
        DESCRIPTOR_REL,
        *BASELINE_REPORT_FILES.values(),
        *CANDIDATE_REPORT_FILES.values(),
        REFERENCE_COHORT_REL,
        COMPARISONS_REL,
    ]
    _verify_freeze_commit(freeze_commit, required_frozen_paths)

    if (ROOT / MANIFEST_REL).exists():
        raise ValueError("development economics manifest already exists")
    manifest = _manifest_payload(freeze_commit)
    _write_json(MANIFEST_REL, manifest)

    loaded_binding = _load_development_economics_binding()
    if loaded_binding.get("freeze_commit") != freeze_commit:
        raise ValueError("loaded economics binding freeze commit mismatch")

    base_selection = _read_json(BASE_SELECTION_REL)
    validate_frozen_validation_selection(base_selection)
    if base_selection.get("pending_efficiency_candidate_ids") != list(
        CANDIDATES
    ):
        raise ValueError("unexpected pending efficiency candidate set")
    if base_selection.get("validation_slot_candidate_ids") != list(
        CANDIDATES
    ):
        raise ValueError("unexpected reserved validation slot set")

    comparisons = _read_json(COMPARISONS_REL)
    outcomes = {}
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
        "base_validation_selection_path": BASE_SELECTION_REL.as_posix(),
        "development_economics_manifest_path": MANIFEST_REL.as_posix(),
        "development_economics_manifest_sha256": _sha256_path(MANIFEST_REL),
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
    _write_json(GATE_RESULT_REL, result)

    # The base validation selection is immutable; late efficiency promotion
    # may only append separate addendum/authorization artifacts.
    post_selection = _read_json(BASE_SELECTION_REL)
    if post_selection != base_selection:
        raise ValueError("base validation selection changed during append")

    print(json.dumps(result, indent=2, sort_keys=True))


def main() -> None:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--freeze-commit", required=True)
    args = parser.parse_args()

    if args.command == "prepare":
        prepare()
    else:
        finalize(args.freeze_commit)


if __name__ == "__main__":
    main()
