"""Validate the frozen benchmark split and observability contract."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "OBSERVABILITY_MATRIX.csv"
SPLIT_PATH = ROOT / "data/splits/electrical-v0.3-plan.json"
EPISODE_DIR = ROOT / "data/episodes/electrical"

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


def validate_contract(
    rows: list[dict[str, str]],
    split: dict,
    episodes: dict[str, dict],
) -> None:
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
    if set(development) & set(held_out):
        raise ValueError("Development and held-out split assignments overlap")
    if set(development) | set(held_out) != set(episodes):
        raise ValueError("Split plan does not assign every committed episode exactly once")

    held_out_config = split["held_out_test"]
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

        if not row["source_family"].strip():
            raise ValueError(f"Missing source family for {episode_id}")

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
    validate_contract(rows, split, episodes)
    held_out = len(split["held_out_test"]["episode_ids"])
    print(
        f"Validated benchmark contract for {len(episodes)} episodes: "
        f"{len(split['development_calibration_episodes'])} development/calibration, "
        f"{held_out} held-out collected, "
        f"{split['held_out_test']['target_count'] - held_out} held-out remaining."
    )


if __name__ == "__main__":
    main()
