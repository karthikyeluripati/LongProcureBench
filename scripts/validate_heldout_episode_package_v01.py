"""Validate the frozen held-out episode package before any model run."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import BenchmarkRunner
from longprocurebench.reference import REFERENCE_DECISIONS, ScriptedReferencePolicy
from validate_episodes import validate_episode
from validate_evaluation import validate_config

SPLIT_PATH = ROOT / "data/splits/electrical-v0.3-plan.json"
MATRIX_PATH = (
    ROOT
    / "evidence"
    / "development-comparator-matrix-v0.1"
    / "matrix.json"
)
MANIFEST_PATH = (
    ROOT
    / "evidence"
    / "heldout-episode-package-v0.1"
    / "manifest.json"
)

EXPECTED = {
    "electrical-columbus-switchgear-021": "us-columbus-rfq029445",
    "electrical-eweb-transformer-022": "us-eweb-rfp-25-030-g",
    "electrical-lompoc-transformer-023": "us-lompoc-rfq-3099",
    "electrical-njang-generator-024": "us-njang-w50s8f26qa022",
    "electrical-port-angeles-transformers-025": (
        "us-port-angeles-mec-2025-18"
    ),
    "electrical-greenport-transformers-026": (
        "us-greenport-transformers-2025"
    ),
    "electrical-san-bruno-ev-chargers-027": (
        "us-san-bruno-ev-chargers-51035"
    ),
    "electrical-shelter-island-solar-bess-028": (
        "us-shelter-island-solar-bess-2026"
    ),
    "electrical-philadelphia-switchgear-mcc-029": (
        "us-philadelphia-b2627071"
    ),
    "electrical-detroit-generator-ats-030": (
        "us-detroit-or-s-q10041-00016402"
    ),
}
DEVELOPMENT_FREEZE_SHA = "0a9378f005d9c66a5d991b1af77d865a4fe2f75b"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_heldout_package() -> dict:
    split = _load(SPLIT_PATH)
    if split.get("status") != "holdout_episodes_frozen":
        raise ValueError("Held-out split status must be holdout_episodes_frozen")

    held = split["held_out_test"]
    if held.get("model_evaluations_run") is not False:
        raise ValueError(
            "Held-out model evaluations must remain false before package merge"
        )
    if held.get("authored_after_development_freeze_sha") != (
        DEVELOPMENT_FREEZE_SHA
    ):
        raise ValueError("Held-out authoring base is not the merged development freeze")

    episode_ids = held.get("episode_ids")
    if episode_ids != list(EXPECTED):
        raise ValueError(
            "Held-out episode IDs/order changed from frozen 021-030 package"
        )
    if held.get("initial_state_package_ids") != list(EXPECTED.values()):
        raise ValueError(
            "Held-out reserved package order changed from frozen package"
        )

    manifest = _load(MANIFEST_PATH)
    if manifest.get("status") != "heldout_episode_package_frozen":
        raise ValueError("Held-out package manifest is not frozen")
    if manifest.get("model_evaluations_run") is not False:
        raise ValueError("Held-out manifest must record zero model evaluations")
    if manifest.get("development_comparator_freeze_merge_sha") != (
        DEVELOPMENT_FREEZE_SHA
    ):
        raise ValueError("Held-out manifest development-freeze provenance drift")
    manifest_rows = manifest.get("episodes") or []
    expected_manifest = [
        {
            "episode_id": episode_id,
            "initial_state_package_id": package_id,
            "expected_reference_outcome": "o1",
        }
        for episode_id, package_id in EXPECTED.items()
    ]
    if manifest_rows != expected_manifest:
        raise ValueError("Held-out package manifest episode mapping drift")

    matrix = _load(MATRIX_PATH)
    if matrix.get("status") != "development_comparator_set_frozen":
        raise ValueError("Development comparator matrix is not frozen")
    if matrix.get("heldout_touched") is not False:
        raise ValueError("Development matrix was not frozen before held-out authoring")
    if matrix.get("freeze_base_sha") != (
        "bd527dfb425c9f587a81bcd6377255f70e5f65ad"
    ):
        raise ValueError("Development matrix provenance drift")

    package_ids = set()
    all_event_types = set()
    all_tags = set()
    reference_summary = {}

    for episode_id, package_id in EXPECTED.items():
        episode_path = (
            ROOT / "data/episodes/electrical" / f"{episode_id}.json"
        )
        evaluation_path = (
            ROOT / "data/evaluation/electrical" / f"{episode_id}.json"
        )
        if not episode_path.is_file() or not evaluation_path.is_file():
            raise ValueError(f"Missing held-out episode/evaluation: {episode_id}")

        episode = _load(episode_path)
        config = _load(evaluation_path)
        validate_episode(episode)
        validate_config(config)

        if episode["episode_id"] != episode_id:
            raise ValueError(f"Held-out episode identity mismatch: {episode_id}")
        if episode["initial_state_ref"]["package_id"] != package_id:
            raise ValueError(f"Held-out package mapping mismatch: {episode_id}")
        if package_id in package_ids:
            raise ValueError("Held-out initial state reused across episodes")
        package_ids.add(package_id)

        realism = episode["realism"]
        if realism["initial_state_data"] != "real_public":
            raise ValueError(f"Held-out real-data boundary drift: {episode_id}")
        for field in (
            "supplier_profiles",
            "quotes_and_messages",
            "event_timeline",
        ):
            if realism[field] != "synthetic":
                raise ValueError(
                    f"Held-out synthetic interaction boundary drift: "
                    f"{episode_id} {field}"
                )
        if not all(event.get("synthetic") is True for event in episode["events"]):
            raise ValueError(f"Non-synthetic held-out event: {episode_id}")
        if not all(
            event.get("emission_policy") == "once"
            for event in episode["events"]
        ):
            raise ValueError(f"Held-out event emission drift: {episode_id}")

        all_event_types.update(event["type"] for event in episode["events"])
        all_tags.update(episode["scenario"]["tags"])

        script = REFERENCE_DECISIONS.get(episode_id)
        if not script:
            raise ValueError(f"Missing held-out reference control: {episode_id}")

        result = BenchmarkRunner().run(
            ScriptedReferencePolicy(),
            episode_id,
        )
        if result["status"] != "completed":
            raise ValueError(
                f"Held-out reference control did not complete: "
                f"{episode_id} status={result['status']}"
            )
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, dict):
            raise ValueError(
                f"Held-out reference control lacks evaluation: {episode_id}"
            )
        if not evaluation["terminal_outcome"]["correct"]:
            raise ValueError(
                f"Held-out reference terminal outcome failed: {episode_id}"
            )
        if not evaluation["hard_constraints"]["all_passed"]:
            raise ValueError(
                f"Held-out reference hard constraints failed: {episode_id}"
            )
        if not evaluation["feasible_obligation_success"]:
            raise ValueError(
                f"Held-out reference obligation success failed: {episode_id}"
            )
        if not evaluation["episode_success_v02"]:
            raise ValueError(
                f"Held-out reference strict v0.2 failed: {episode_id}"
            )
        if not evaluation["economic_objective"]["satisfied"]:
            raise ValueError(
                f"Held-out reference economic objective failed: {episode_id}"
            )
        expected_outcome = next(
            row["expected_reference_outcome"]
            for row in manifest_rows
            if row["episode_id"] == episode_id
        )
        if evaluation["terminal_outcome"]["matched_outcome_id"] != (
            expected_outcome
        ):
            raise ValueError(
                f"Held-out reference outcome drift: {episode_id}"
            )
        if evaluation["obligations"]["unresolved"] != 0:
            raise ValueError(
                f"Held-out reference left unresolved obligations: {episode_id}"
            )

        reference_summary[episode_id] = {
            "actions": len(result["trajectory"]),
            "terminal": evaluation["terminal_outcome"]["matched_outcome_id"],
            "actionable_obligations": evaluation["obligations"]["actionable"],
            "resolved_obligations": evaluation["obligations"]["resolved"],
        }

    if package_ids != set(EXPECTED.values()):
        raise ValueError("Held-out package mapping does not cover reserved pool")
    if len(all_event_types) < 8:
        raise ValueError(
            "Held-out package does not preserve event-type diversity"
        )
    required_tags = {
        "requirement_gap",
        "supplier_non_response",
        "supplier_question",
        "quote_received",
        "quote_revision",
        "requirement_change",
        "lead_time_conflict",
        "supplier_withdrawal",
        "budget_conflict",
        "multi_lot",
        "supplier_eligibility",
        "compliance_conflict",
    }
    missing_tags = required_tags - all_tags
    if missing_tags:
        raise ValueError(
            f"Held-out package missing frozen scenario coverage: "
            f"{sorted(missing_tags)}"
        )

    # No reference controls beyond the 20 development + 10 held-out episodes.
    if set(REFERENCE_DECISIONS) != (
        set(split["development_calibration_episodes"]) | set(EXPECTED)
    ):
        raise ValueError(
            "Reference-control episode set must exactly match the frozen "
            "30-episode benchmark"
        )

    return {
        "episodes": len(EXPECTED),
        "initial_states": len(package_ids),
        "event_types": sorted(all_event_types),
        "scenario_tags": sorted(all_tags),
        "reference_controls": reference_summary,
    }


def main() -> None:
    summary = validate_heldout_package()
    print(
        "Held-out episode package validated: "
        f"{summary['episodes']} episodes / "
        f"{summary['initial_states']} reserved real starting states; "
        "all deterministic reference controls pass strict v0.2."
    )


if __name__ == "__main__":
    main()
