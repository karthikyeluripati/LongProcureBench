"""Validate observability/source-family contract for fresh episodes 031-050."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

from validate_procureharness_fresh_package_v01 import (
    EXPECTED_FINAL,
    EXPECTED_PACKAGES,
    EXPECTED_VALIDATION,
)

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "OBSERVABILITY_MATRIX_PROCUREHARNESS_031_050.csv"
EPISODE_DIR = ROOT / "data" / "episodes" / "electrical"
STATE_DIR = ROOT / "data" / "initial_states" / "electrical"

REQUIRED_COLUMNS = [
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
    "primary_failure_mechanisms"
]
CONTROLLED_REQUIREMENT_EVENT_TYPES = {
    "buyer_clarification",
    "requirement_change",
    "quantity_change",
    "lead_time_change",
}
SOURCE_FAMILY_BY_HOST = {
    "www.imperial.ca.gov": "Imperial municipal portal",
    "www.lewistonmaine.gov": "Lewiston municipal portal",
    "www.idahofallsidaho.gov": "Idaho Falls municipal portal",
    "utclermont.gov": "Union Township municipal portal",
    "www.methuen.gov": "Methuen municipal portal",
    "www.phlcontracts.phila.gov": "Philadelphia PHLContracts",
    "www.hampton.gov": "Hampton municipal portal",
    "www.danville-va.gov": "Danville municipal portal",
    "danville-va.gov": "Danville municipal portal",
    "www.danversma.gov": "Danvers municipal portal",
    "www.rockymountnc.gov": "Rocky Mount municipal portal",
    "siloamsprings.gov": "Siloam Springs municipal portal",
    "oregonbuys.gov": "OregonBuys",
    "www.portlandtx.gov": "Portland TX municipal portal",
    "www.marshfieldmo.gov": "Marshfield municipal portal",
    "dubuquecountyiowa.gov": "Dubuque County municipal portal",
}
FIXED_VISIBILITY = {
    "initial_state_grounding": "real_public",
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


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_matrix(path: Path = MATRIX_PATH):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REQUIRED_COLUMNS:
            raise ValueError("Fresh observability matrix columns changed")
        return list(reader)


def _source_family(episode):
    ref = episode["initial_state_ref"]
    state = _load_json(ROOT / ref["path"])
    documents = state.get("supporting_documents") or []
    if not documents:
        raise ValueError(
            f"Fresh initial state lacks public source: {episode['episode_id']}"
        )
    hosts = {
        (urlparse(doc["url"]).hostname or "").lower()
        for doc in documents
    }
    families = set()
    for host in hosts:
        family = SOURCE_FAMILY_BY_HOST.get(host)
        if family is None:
            raise ValueError(
                f"Unreviewed fresh source host for {episode['episode_id']}: {host}"
            )
        families.add(family)
    if len(families) != 1:
        raise ValueError(
            f"Fresh episode spans multiple source families: {episode['episode_id']}"
        )
    return next(iter(families))


def validate_fresh_observability(rows=None):
    rows = load_matrix() if rows is None else rows
    expected_ids = EXPECTED_VALIDATION + EXPECTED_FINAL
    expected_packages = dict(zip(expected_ids, EXPECTED_PACKAGES))

    ids = [row.get("episode_id") for row in rows]
    if ids != expected_ids:
        raise ValueError(
            "Fresh observability rows must remain exactly ordered 031-050"
        )
    if len(set(ids)) != 20:
        raise ValueError("Fresh observability episode IDs must be unique")

    for row in rows:
        episode_id = row["episode_id"]
        episode = _load_json(EPISODE_DIR / f"{episode_id}.json")

        expected_split = (
            "architecture_validation"
            if episode_id in EXPECTED_VALIDATION
            else "final_method_test"
        )
        if row["paper_split"] != expected_split:
            raise ValueError(
                f"Fresh paper split drift for {episode_id}: {row['paper_split']}"
            )
        if row["package_id"] != expected_packages[episode_id]:
            raise ValueError(f"Fresh package mapping drift for {episode_id}")
        if episode["initial_state_ref"]["package_id"] != row["package_id"]:
            raise ValueError(f"Episode/matrix package mismatch for {episode_id}")

        for field, expected in FIXED_VISIBILITY.items():
            if row[field] != expected:
                raise ValueError(
                    f"Fresh observability drift for {episode_id}: "
                    f"{field}={row[field]!r}"
                )

        if row["source_family"] != _source_family(episode):
            raise ValueError(f"Fresh source-family mismatch for {episode_id}")

        expected_events = {
            event["type"]
            for event in episode["events"]
            if event["type"] in CONTROLLED_REQUIREMENT_EVENT_TYPES
        }
        observed_events = {
            value
            for value in row["synthetic_requirement_events"].split(";")
            if value
        }
        if observed_events != expected_events:
            raise ValueError(
                f"Fresh requirement-event observability drift for {episode_id}"
            )

        observed_tags = {
            value
            for value in row["primary_failure_mechanisms"].split(";")
            if value
        }
        if observed_tags != set(episode["scenario"]["tags"]):
            raise ValueError(
                f"Fresh failure-mechanism observability drift for {episode_id}"
            )

    return {
        "rows": len(rows),
        "validation": len(EXPECTED_VALIDATION),
        "final": len(EXPECTED_FINAL),
    }


def main():
    summary = validate_fresh_observability()
    print(
        "PASS fresh ProcureHarness observability: "
        f"{summary['rows']} rows "
        f"({summary['validation']} validation, {summary['final']} final)"
    )


if __name__ == "__main__":
    main()
