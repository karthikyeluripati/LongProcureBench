"""Shared validation for LongProcureBench initial-state records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from rfc3986_validator import validate_rfc3986


def pointer(record: dict[str, Any], path: str) -> Any:
    if not path.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer: {path}")
    value: Any = record
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def leaves(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, path + "/" + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, path + "/" + str(index))
    else:
        yield path, value


class InitialStateValidator:
    """Schema + repository invariants shared by dataset checks and runtime reset."""

    def __init__(self, schema_path: str | Path):
        self.schema_path = Path(schema_path)
        self.schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)
        checker = FormatChecker()

        @checker.checks("uri")
        def valid_uri(value):
            return not isinstance(value, str) or bool(
                validate_rfc3986(value, rule="URI")
            )

        self.validator = Draft202012Validator(
            self.schema, format_checker=checker
        )

    def validate(self, record: dict[str, Any]) -> None:
        self.validator.validate(record)

        docs = [doc["document_id"] for doc in record["supporting_documents"]]
        if len(docs) != len(set(docs)):
            raise ValueError("Duplicate document IDs")
        doc_ids = set(docs)

        items = [item["item_id"] for item in record["line_items"]]
        if len(items) != len(set(items)):
            raise ValueError("Duplicate item IDs")

        evidence_paths = []
        for evidence in record["source_provenance"]:
            if evidence["document_id"] not in doc_ids:
                raise ValueError("Unresolved provenance document")
            for path in evidence["field_paths"]:
                if isinstance(pointer(record, path), (dict, list)):
                    raise ValueError(
                        f"Evidence must identify a scalar field: {path}"
                    )
                evidence_paths.append(path)

        missing = {
            entry["field_path"] for entry in record["missing_information"]
        }
        for entry in record["missing_information"]:
            value = pointer(record, entry["field_path"])
            if (
                entry["reason"]
                in (
                    "not_stated",
                    "bidder_to_provide",
                    "source_snapshot_unavailable",
                )
                and value is not None
            ):
                raise ValueError(
                    f"Absence reason requires null: {entry['field_path']}"
                )

        sourced = (
            "/project/",
            "/package_subscope",
            "/line_items/",
            "/total_estimated_budget",
            "/schedule/",
            "/supplier_eligibility_constraints",
            "/certifications_compliance",
            "/initial_state/source_issue_date",
        )
        for path, value in leaves(record):
            if (
                value is None
                and not path.endswith("/verbatim_excerpt")
                and path not in missing
            ):
                raise ValueError(f"Unexplained null: {path}")
            if value is not None and path.startswith(sourced):
                if path not in evidence_paths:
                    raise ValueError(f"Unsupported field: {path}")

        for item in record["line_items"]:
            unit = item["estimated_unit_cost"]
            total = item["estimated_total_cost"]
            if unit and total:
                if unit["currency"] != total["currency"]:
                    raise ValueError("Currency mismatch")
                if item["quantity"] is not None:
                    if (
                        abs(
                            unit["amount"] * item["quantity"]
                            - total["amount"]
                        )
                        > 0.01
                    ):
                        raise ValueError("Line estimate arithmetic mismatch")
