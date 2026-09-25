"""Validate the committed electrical initial-state dataset."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench.validation import InitialStateValidator, leaves, pointer

_INITIAL_VALIDATOR = InitialStateValidator(
    ROOT / "schema/initial-state.schema.json"
)


def validate_record(record):
    _INITIAL_VALIDATOR.validate(record)


def main():
    files = sorted((ROOT / "data/initial_states/electrical").glob("*.json"))
    if len(files) < 20:
        raise ValueError(
            "The dataset must retain at least the 20 frozen development "
            f"packages; found {len(files)}"
        )
    ids = set()
    count = 0
    for file in files:
        record = json.loads(file.read_text(encoding="utf-8"))
        validate_record(record)
        if record["package_id"] in ids or file.stem != record["package_id"]:
            raise ValueError("Duplicate package ID or filename mismatch")
        ids.add(record["package_id"])
        count += len(record["line_items"])
        print(f"PASS {file.name}")
    print(f"Validated {len(files)} packages and {count} line items.")


if __name__ == "__main__":
    main()
