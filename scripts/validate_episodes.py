"""Validate the five-episode LongProcureBench episode-model v0.1 milestone."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EPISODE_SCHEMA = json.loads((ROOT / "schema/episode.schema.json").read_text(encoding="utf-8"))
ACTION_SCHEMA = json.loads((ROOT / "schema/action.schema.json").read_text(encoding="utf-8"))
Draft202012Validator.check_schema(EPISODE_SCHEMA)
Draft202012Validator.check_schema(ACTION_SCHEMA)
FORMAT_CHECKER = FormatChecker()
EPISODE_VALIDATOR = Draft202012Validator(EPISODE_SCHEMA, format_checker=FORMAT_CHECKER)
ACTION_VALIDATOR = Draft202012Validator(ACTION_SCHEMA, format_checker=FORMAT_CHECKER)

SUPPLIER_EVENT_TYPES = {"supplier_non_response","supplier_question","quote_received","quote_revision","substitution_proposed","lead_time_change","supplier_withdrawal"}
BUYER_EVENT_TYPES = {"buyer_clarification","requirement_change","quantity_change"}
QUOTE_EVENT_TYPES = {"quote_received","quote_revision"}


def _covered_item_ids(event, initial_item_ids):
    scope = event.get("offer_scope")
    if scope is None:
        raise ValueError(f"Quote event missing offer_scope: {event['event_id']}")
    if scope["kind"] == "package":
        return set(initial_item_ids)
    item_ids = set(scope["item_ids"])
    unknown = item_ids - set(initial_item_ids)
    if unknown:
        raise ValueError(f"Quote event covers unknown initial-state items: {sorted(unknown)}")
    return item_ids


def _required_item_ids_for_award(scope, initial_item_ids):
    if scope == "package":
        return set(initial_item_ids)
    if scope.startswith("lot-"):
        item_id = scope[len("lot-"):]
        if item_id not in initial_item_ids:
            raise ValueError(f"Award scope references unknown initial-state item: {scope}")
        return {item_id}
    raise ValueError(f"Unsupported award scope in v0.1: {scope}")


def validate_episode(record):
    EPISODE_VALIDATOR.validate(record)
    initial_path = ROOT / record["initial_state_ref"]["path"]
    if not initial_path.is_file():
        raise ValueError(f"Missing initial-state file: {initial_path}")
    initial = json.loads(initial_path.read_text(encoding="utf-8"))
    if initial["package_id"] != record["initial_state_ref"]["package_id"]:
        raise ValueError("Initial-state package_id mismatch")
    initial_item_ids = {item["item_id"] for item in initial["line_items"]}

    suppliers = [s["supplier_id"] for s in record["suppliers"]]
    if len(suppliers) != len(set(suppliers)):
        raise ValueError("Duplicate supplier_id")
    supplier_ids = set(suppliers)

    events = record["events"]
    event_ids = [e["event_id"] for e in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("Duplicate event_id")
    by_event = {e["event_id"]: e for e in events}
    quote_coverage = {}

    for event in events:
        supplier_id = event["supplier_id"]
        if supplier_id is not None and supplier_id not in supplier_ids:
            raise ValueError(f"Unknown event supplier: {supplier_id}")
        if event["type"] in SUPPLIER_EVENT_TYPES and supplier_id is None:
            raise ValueError(f"Supplier event missing supplier_id: {event['event_id']}")
        if event["type"] in BUYER_EVENT_TYPES and supplier_id is not None:
            raise ValueError(f"Buyer event unexpectedly has supplier_id: {event['event_id']}")

        if event["type"] in QUOTE_EVENT_TYPES:
            quote_coverage[event["event_id"]] = _covered_item_ids(event, initial_item_ids)
        elif "offer_scope" in event:
            raise ValueError(f"Non-quote event must not declare offer_scope: {event['event_id']}")

        trigger = event["trigger"]
        trigger_supplier = trigger["supplier_id"]
        if trigger_supplier is not None and trigger_supplier not in supplier_ids:
            raise ValueError(f"Unknown trigger supplier: {trigger_supplier}")
        if trigger["kind"] == "after_action":
            if trigger["action_type"] is None or trigger["step"] is not None:
                raise ValueError(f"Invalid after_action trigger: {event['event_id']}")
        else:
            if trigger["step"] is None or trigger["action_type"] is not None or trigger["supplier_id"] is not None:
                raise ValueError(f"Invalid at_step trigger: {event['event_id']}")

    expected_decision = "award" if record["objective"]["terminal_state"] == "award_ready" else "no_award"
    for outcome in record["oracle"]["acceptable_terminal_outcomes"]:
        if outcome["decision"] != expected_decision:
            raise ValueError("Outcome decision does not match objective terminal_state")
        if outcome["decision"] == "no_award":
            continue

        for award in outcome["awards"]:
            supplier_id = award["supplier_id"]
            quote_event_id = award["quote_event_id"]
            if supplier_id not in supplier_ids:
                raise ValueError(f"Unknown awarded supplier: {supplier_id}")
            if quote_event_id not in by_event:
                raise ValueError(f"Unknown awarded quote event: {quote_event_id}")
            event = by_event[quote_event_id]
            if event["type"] not in QUOTE_EVENT_TYPES:
                raise ValueError("Award must reference quote_received or quote_revision")
            if event["supplier_id"] != supplier_id:
                raise ValueError("Award supplier does not match quote event supplier")
            required_items = _required_item_ids_for_award(award["scope"], initial_item_ids)
            if not required_items.issubset(quote_coverage[quote_event_id]):
                raise ValueError(
                    f"Award scope {award['scope']} is not covered by quote event {quote_event_id}"
                )


def validate_action(action):
    ACTION_VALIDATOR.validate(action)


def main():
    files = sorted((ROOT / "data/episodes/electrical").glob("*.json"))
    if len(files) != 5:
        raise ValueError(f"Episode-model v0.1 requires exactly 5 episodes; found {len(files)}")
    episode_ids = set()
    package_ids = set()
    all_event_types = set()
    for file in files:
        record = json.loads(file.read_text(encoding="utf-8"))
        validate_episode(record)
        if file.stem != record["episode_id"]:
            raise ValueError("Episode filename must match episode_id")
        if record["episode_id"] in episode_ids:
            raise ValueError("Duplicate episode_id")
        episode_ids.add(record["episode_id"])
        package_ids.add(record["initial_state_ref"]["package_id"])
        all_event_types.update(event["type"] for event in record["events"])
        print(f"PASS {file.name}")
    if len(package_ids) != 5:
        raise ValueError("The first five episodes must use five distinct initial states")
    if len(all_event_types) < 8:
        raise ValueError("Episode suite does not exercise enough event-type diversity")
    print(f"Validated {len(files)} episodes across {len(package_ids)} initial states.")


if __name__ == "__main__":
    main()
