"""Validate the frozen benchmark split and observability contract."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "OBSERVABILITY_MATRIX.csv"
SPLIT_PATH = ROOT / "data/splits/electrical-v0.3-plan.json"
EPISODE_DIR = ROOT / "data/episodes/electrical"
INITIAL_STATE_DIR = ROOT / "data/initial_states/electrical"

REQUIRED_COLUMNS = {
    "episode_id",
    "package_id",
    "source_family",
    "paper_split",
    "initial_state_grounding",
    "initial_state_visibility",
    "source_documents_visibility",
    "supplier_directory_grounding",
    "supplier_directory_visibility",
    "supplier_internal_profile_visibility",
    "quotes_messages_grounding",
    "future_event_visibility",
    "oracle_visibility",
    "evaluation_visibility",
    "evaluator_ground_truth",
    "synthetic_requirement_events",
    "primary_failure_mechanisms",
}
CONTROLLED_REQUIREMENT_EVENT_TYPES = {
    "buyer_clarification",
    "requirement_change",
    "quantity_change",
    "lead_time_change",
}
VALID_SPLITS = {"development_calibration", "held_out_test"}

# These episodes were already used to build/debug the runtime, fairness audit,
# Evaluator v0.2, and model diagnostics. They can never become untouched test
# data through an edit to the split metadata.
FROZEN_DEVELOPMENT_EPISODES = {
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
}

# Reviewed provenance mapping. New source hosts must be added intentionally
# rather than silently accepting an arbitrary matrix label.
SOURCE_FAMILY_BY_HOST = {
    "notices.philgeps.gov.ph": "PhilGEPS",
    "sam.gov": "SAM.gov",
    "barrie.bidsandtenders.ca": "Barrie Bids & Tenders",
    "www.highpointnc.gov": "High Point municipal PDF",
    "www.painesville.com": "Painesville municipal portal",
    "www.vre.org": "VRE procurement portal",
}


def load_matrix(path: Path = MATRIX_PATH) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or []) != REQUIRED_COLUMNS:
            raise ValueError(
                "Observability matrix columns do not match the frozen contract"
            )
        rows = list(reader)
    if not rows:
        raise ValueError("Observability matrix is empty")
    return rows


def load_split(path: Path = SPLIT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_episodes(root: Path = EPISODE_DIR) -> dict[str, dict]:
    episodes = {}
    for path in sorted(root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if path.stem != record["episode_id"]:
            raise ValueError(f"Episode filename mismatch: {path.name}")
        episodes[record["episode_id"]] = record
    return episodes


def load_initial_states(root: Path = INITIAL_STATE_DIR) -> dict[str, dict]:
    records = {}
    for path in sorted(root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if path.stem != record["package_id"]:
            raise ValueError(f"Initial-state filename mismatch: {path.name}")
        records[record["package_id"]] = record
    return records


def _expected_source_family(episode: dict) -> str:
    initial_path = ROOT / episode["initial_state_ref"]["path"]
    initial = json.loads(initial_path.read_text(encoding="utf-8"))
    documents = initial.get("supporting_documents") or []
    if not documents:
        raise ValueError(
            f"Initial state has no supporting documents: {episode['episode_id']}"
        )

    families = set()
    for document in documents:
        url = document.get("url")
        if not isinstance(url, str):
            raise ValueError(
                f"Supporting document lacks URL: {episode['episode_id']}"
            )
        host = (urlparse(url).hostname or "").lower()
        family = SOURCE_FAMILY_BY_HOST.get(host)
        if family is None:
            raise ValueError(
                f"Unreviewed source host for {episode['episode_id']}: {host}"
            )
        families.add(family)

    if len(families) != 1:
        raise ValueError(
            f"Episode spans multiple source families: {episode['episode_id']}"
        )
    return next(iter(families))


def validate_contract(
    rows: list[dict[str, str]],
    split: dict,
    episodes: dict[str, dict],
    initial_states: dict[str, dict] | None = None,
) -> None:
    initial_states = initial_states or load_initial_states()
    ids = [row["episode_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Observability matrix contains duplicate episode_id values")
    if set(ids) != set(episodes):
        raise ValueError(
            "Observability matrix episode IDs do not match committed episodes"
        )

    development = split.get("development_calibration_episodes")
    held_out = (split.get("held_out_test") or {}).get("episode_ids")
    if not isinstance(development, list) or not isinstance(held_out, list):
        raise ValueError("Split plan must define development and held-out episode lists")
    development_set = set(development)
    held_out_set = set(held_out)
    if development_set & held_out_set:
        raise ValueError("Development and held-out split assignments overlap")
    if development_set | held_out_set != set(episodes):
        raise ValueError("Split plan does not assign every committed episode exactly once")

    missing_frozen = FROZEN_DEVELOPMENT_EPISODES - development_set
    if missing_frozen:
        raise ValueError(
            "Previously used calibration episodes must remain development data: "
            f"{sorted(missing_frozen)}"
        )
    leaked_frozen = FROZEN_DEVELOPMENT_EPISODES & held_out_set
    if leaked_frozen:
        raise ValueError(
            "Previously used calibration episodes cannot enter held-out test: "
            f"{sorted(leaked_frozen)}"
        )

    held_out_config = split["held_out_test"]
    initial_state_package_ids = held_out_config.get("initial_state_package_ids", [])
    if not isinstance(initial_state_package_ids, list):
        raise ValueError("Held-out initial_state_package_ids must be a list")
    if len(initial_state_package_ids) != len(set(initial_state_package_ids)):
        raise ValueError("Held-out initial-state package IDs must be unique")
    missing_initial_states = set(initial_state_package_ids) - set(initial_states)
    if missing_initial_states:
        raise ValueError(
            "Held-out split references missing initial states: "
            f"{sorted(missing_initial_states)}"
        )
    development_package_ids = {
        episode["initial_state_ref"]["package_id"]
        for episode in episodes.values()
        if episode["episode_id"] in FROZEN_DEVELOPMENT_EPISODES
    }
    overlap = development_package_ids & set(initial_state_package_ids)
    if overlap:
        raise ValueError(
            "Held-out initial states cannot reuse development packages: "
            f"{sorted(overlap)}"
        )
    if len(initial_state_package_ids) > held_out_config.get("target_count", 0):
        raise ValueError("Collected held-out initial states exceed target count")

    if held_out_config.get("target_count") != 10:
        raise ValueError("Held-out target count must remain 10 for the v0.3 plan")
    if held_out_config.get("reserved_numeric_suffixes") != list(range(21, 31)):
        raise ValueError("Held-out suffix reservation must remain 021-030")

    expected_split = {
        episode_id: "development_calibration" for episode_id in development
    }
    expected_split.update({episode_id: "held_out_test" for episode_id in held_out})

    for row in rows:
        episode_id = row["episode_id"]
        episode = episodes[episode_id]

        if row["paper_split"] not in VALID_SPLITS:
            raise ValueError(f"Invalid paper split for {episode_id}")
        if row["paper_split"] != expected_split[episode_id]:
            raise ValueError(f"Matrix/split disagreement for {episode_id}")
        if row["package_id"] != episode["initial_state_ref"]["package_id"]:
            raise ValueError(f"Package ID mismatch for {episode_id}")
        if episode["initial_state_ref"]["grounding"] != "real_public":
            raise ValueError(f"Initial state is not real_public for {episode_id}")
        if row["initial_state_grounding"] != "real_public":
            raise ValueError(f"Matrix grounding drift for {episode_id}")

        realism = episode["realism"]
        if (
            realism["initial_state_data"] != "real_public"
            or realism["supplier_profiles"] != "synthetic"
            or realism["quotes_and_messages"] != "synthetic"
            or realism["event_timeline"] != "synthetic"
        ):
            raise ValueError(f"Episode reality boundary drift for {episode_id}")

        fixed_values = {
            "initial_state_visibility": "visible_at_reset",
            "source_documents_visibility": "not_runtime_input",
            "supplier_directory_grounding": "synthetic",
            "supplier_directory_visibility": "hidden_until_identify_suppliers",
            "supplier_internal_profile_visibility": "never_exposed_directly",
            "quotes_messages_grounding": "synthetic",
            "future_event_visibility": "hidden_until_trigger",
            "oracle_visibility": "never_exposed",
            "evaluation_visibility": "post_run_only",
            "evaluator_ground_truth": "real_initial_state+controlled_scenario_oracle",
        }
        for field, expected in fixed_values.items():
            if row[field] != expected:
                raise ValueError(
                    f"Observability contract drift for {episode_id}: "
                    f"{field}={row[field]!r}"
                )

        expected_source_family = _expected_source_family(episode)
        if row["source_family"] != expected_source_family:
            raise ValueError(
                f"Source-family audit mismatch for {episode_id}: "
                f"expected={expected_source_family!r}, "
                f"matrix={row['source_family']!r}"
            )

        expected_requirement_events = {
            event["type"]
            for event in episode["events"]
            if event["type"] in CONTROLLED_REQUIREMENT_EVENT_TYPES
        }
        matrix_requirement_events = {
            value
            for value in row["synthetic_requirement_events"].split(";")
            if value
        }
        if matrix_requirement_events != expected_requirement_events:
            raise ValueError(
                f"Synthetic requirement-event audit mismatch for {episode_id}"
            )

        matrix_failures = {
            value for value in row["primary_failure_mechanisms"].split(";") if value
        }
        if matrix_failures != set(episode["scenario"]["tags"]):
            raise ValueError(f"Failure-mechanism audit mismatch for {episode_id}")


def main() -> None:
    rows = load_matrix()
    split = load_split()
    episodes = load_episodes()
    initial_states = load_initial_states()
    validate_contract(rows, split, episodes, initial_states)
    held_out = len(split["held_out_test"]["episode_ids"])
    held_out_states = len(split["held_out_test"].get("initial_state_package_ids", []))
    print(
        f"Validated benchmark contract for {len(episodes)} episodes: "
        f"{len(split['development_calibration_episodes'])} development/calibration, "
        f"{held_out_states} held-out initial states collected, "
        f"{held_out} held-out episodes frozen."
    )


if __name__ == "__main__":
    main()
