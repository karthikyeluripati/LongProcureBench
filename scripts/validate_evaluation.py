"""Validate Evaluator v0.1 machine-check configurations."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema/evaluation.schema.json").read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)

REQUIRED_FIELDS = {
    "award_quote_max": {"path", "value"},
    "award_quote_min": {"path", "value"},
    "award_quote_equals": {"path", "value"},
    "award_supplier_equals": {"supplier_field"},
    "award_quote_latest": set(),
    "award_supplier_not_withdrawn": set(),
    "event_before_action": {"event_id", "action_type"},
    "award_scope_complete": set(),
}


def validate_config(config):
    VALIDATOR.validate(config)
    episode_path = ROOT / "data/episodes/electrical" / f"{config['episode_id']}.json"
    if not episode_path.is_file():
        raise ValueError("Evaluation config references missing episode")
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    expected = {x["constraint_id"] for x in episode["oracle"]["hard_constraints"]}
    configured = [x["constraint_id"] for x in config["constraint_rules"]]
    if len(configured) != len(set(configured)):
        raise ValueError("Duplicate evaluation constraint_id")
    if set(configured) != expected:
        raise ValueError("Evaluation constraints do not match episode oracle")
    for rule in config["constraint_rules"]:
        for check in rule["checks"]:
            for field in REQUIRED_FIELDS[check["kind"]]:
                if check[field] is None:
                    raise ValueError(f"{check['kind']} requires {field}")


def main():
    files = sorted((ROOT / "data/evaluation/electrical").glob("*.json"))
    if len(files) != 5:
        raise ValueError(f"Evaluator v0.1 requires exactly 5 configs; found {len(files)}")
    ids = set()
    for file in files:
        config = json.loads(file.read_text(encoding="utf-8"))
        validate_config(config)
        if file.stem != config["episode_id"]:
            raise ValueError("Evaluation filename must match episode_id")
        ids.add(config["episode_id"])
        print(f"PASS {file.name}")
    if len(ids) != 5:
        raise ValueError("Evaluation configs must cover five distinct episodes")
    print(f"Validated {len(files)} evaluation configs.")


if __name__ == "__main__":
    main()
