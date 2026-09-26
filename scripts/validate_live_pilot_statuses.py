"""Validate live pilot statuses without treating agent mistakes as infra failures."""
from __future__ import annotations

import csv
from pathlib import Path
import sys

INFRASTRUCTURE_ERRORS = {
    "environment_error",
    "setup_error",
    "evaluation_error",
    "metadata_error",
}
MEASURED_POLICY_ERRORS = {
    "EnvironmentError",
    "OperationalLedgerError",
    "ValidationError",
    "RunnerError",
}


def invalid_rows(rows):
    return [
        row
        for row in rows
        if row.get("status") in INFRASTRUCTURE_ERRORS
        or bool(row.get("evaluation_error_type"))
        or (
            row.get("status") == "policy_error"
            and row.get("error_type") not in MEASURED_POLICY_ERRORS
        )
    ]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: python scripts/validate_live_pilot_statuses.py runs.csv"
        )

    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"Pilot did not produce runs.csv: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    bad = invalid_rows(rows)
    if bad:
        print(f"{len(bad)} live pilot run(s) had execution/model errors:")
        for row in bad:
            print(
                f"- {row.get('model')} | {row.get('episode_id')} | "
                f"repeat={row.get('repeat')} | status={row.get('status')} | "
                f"error={row.get('error_type')} | "
                f"evaluation_error={row.get('evaluation_error_type')}"
            )
        raise SystemExit(1)

    measured = [
        row
        for row in rows
        if row.get("status") == "policy_error"
        and row.get("error_type") in MEASURED_POLICY_ERRORS
    ]
    print(
        f"Validated {len(rows)} live pilot run(s); "
        f"{len(measured)} measured agent-action rejection(s)."
    )


if __name__ == "__main__":
    main()
