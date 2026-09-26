"""Factual context compilation for a matched reactive baseline."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from .reactive_llm import ReactiveLLMPolicy


OFFER_EVENT_TYPES = {
    "quote_received",
    "quote_revision",
    "substitution_proposed",
}
REQUIREMENT_UPDATE_TYPES = {
    "buyer_clarification",
    "requirement_change",
    "quantity_change",
}
OPERATIONAL_MISSING_PREFIXES = (
    "/project",
    "/package_subscope",
    "/line_items",
    "/total_estimated_budget",
    "/schedule",
    "/supplier_eligibility_constraints",
    "/certifications_compliance",
)


def _compact_specification(spec: Any) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    out = {}
    if "summary" in spec:
        out["summary"] = deepcopy(spec["summary"])
    if spec.get("verbatim_excerpt") is not None:
        out["verbatim_excerpt"] = deepcopy(spec["verbatim_excerpt"])
    return out


def _compact_line_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    fields = (
        "item_id",
        "description",
        "award_requirement",
        "quantity",
        "quantity_basis",
        "unit",
        "manufacturer",
        "model",
        "acceptable_alternates",
        "estimated_unit_cost",
        "estimated_total_cost",
    )
    out = {
        key: deepcopy(item[key])
        for key in fields
        if key in item
    }

    specifications = item.get("technical_specifications")
    if specifications is None:
        out["technical_specifications"] = None
    elif isinstance(specifications, list):
        out["technical_specifications"] = [
            compact
            for compact in (
                _compact_specification(spec)
                for spec in specifications
            )
            if compact is not None
        ]
    return out


def _is_operational_missing_information(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    path = row.get("field_path")
    if not isinstance(path, str):
        return False
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in OPERATIONAL_MISSING_PREFIXES
    )


def _compact_initial_state(initial: Any) -> dict[str, Any]:
    if not isinstance(initial, dict):
        return {}

    line_items = initial.get("line_items")
    compact_items = []
    if isinstance(line_items, list):
        compact_items = [
            compact
            for compact in (
                _compact_line_item(item)
                for item in line_items
            )
            if compact is not None
        ]

    boundary = initial.get("initial_state")
    source_issue_date = (
        boundary.get("source_issue_date")
        if isinstance(boundary, dict)
        else None
    )

    missing = initial.get("missing_information")
    operational_missing = []
    if isinstance(missing, list):
        operational_missing = [
            deepcopy(row)
            for row in missing
            if _is_operational_missing_information(row)
        ]

    return {
        "package_id": deepcopy(initial.get("package_id")),
        "procurement_category": deepcopy(
            initial.get("procurement_category")
        ),
        "project": deepcopy(initial.get("project")),
        "package_subscope": deepcopy(initial.get("package_subscope")),
        "source_issue_date": deepcopy(source_issue_date),
        "line_items": compact_items,
        "total_estimated_budget": deepcopy(
            initial.get("total_estimated_budget")
        ),
        "schedule": deepcopy(initial.get("schedule")),
        "supplier_eligibility_constraints": deepcopy(
            initial.get("supplier_eligibility_constraints")
        ),
        "certifications_compliance": deepcopy(
            initial.get("certifications_compliance")
        ),
        "operational_missing_information": operational_missing,
    }


def _compact_event(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    fields = (
        "event_id",
        "type",
        "supplier_id",
        "observation",
        "details",
        "offer_scope",
    )
    return {
        key: deepcopy(event[key])
        for key in fields
        if key in event
    }


def _scope_key(scope: Any) -> str:
    return json.dumps(
        scope if scope is not None else {"kind": "package"},
        sort_keys=True,
        separators=(",", ":"),
    )


def _latest_offers(
    compact_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for event in compact_events:
        if event.get("type") not in OFFER_EVENT_TYPES:
            continue
        supplier_id = event.get("supplier_id")
        if not isinstance(supplier_id, str) or not supplier_id:
            continue
        key = (supplier_id, _scope_key(event.get("offer_scope")))
        latest[key] = {
            key_name: deepcopy(event[key_name])
            for key_name in (
                "event_id",
                "type",
                "supplier_id",
                "details",
                "offer_scope",
            )
            if key_name in event
        }
    return [
        latest[key]
        for key in sorted(latest)
    ]


def _compact_action_history(history: Any) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        return []
    out = []
    for sequence, action in enumerate(history, start=1):
        if not isinstance(action, dict):
            continue
        row = {
            "sequence": sequence,
            "type": deepcopy(action.get("type")),
            "supplier_id": deepcopy(action.get("supplier_id")),
            "arguments": deepcopy(action.get("arguments") or {}),
        }
        out.append(row)
    return out


def compile_visible_state(state: dict[str, Any]) -> dict[str, Any]:
    """Compile only facts already visible to the policy.

    This deliberately does not infer obligations, feasibility, stale quotes,
    preferred suppliers, next actions, or evaluator/checkpoint state.
    """
    if not isinstance(state, dict):
        raise ValueError("state must be an object")

    revealed = state.get("revealed_events")
    compact_events = []
    if isinstance(revealed, list):
        compact_events = [
            compact
            for compact in (
                _compact_event(event)
                for event in revealed
            )
            if compact is not None
        ]

    return {
        "context_view": "factual_compiled_v0.1",
        "episode_id": deepcopy(state.get("episode_id")),
        "step": deepcopy(state.get("step")),
        "terminated": deepcopy(state.get("terminated")),
        "terminal": deepcopy(state.get("terminal")),
        "initial_state": _compact_initial_state(
            state.get("initial_state")
        ),
        "visible_suppliers": deepcopy(
            state.get("visible_suppliers") or []
        ),
        "latest_offers": _latest_offers(compact_events),
        "requirement_updates": [
            deepcopy(event)
            for event in compact_events
            if event.get("type") in REQUIREMENT_UPDATE_TYPES
        ],
        "event_history": compact_events,
        "action_history": _compact_action_history(
            state.get("action_history")
        ),
    }


class ContextCompiledReactiveLLMPolicy(ReactiveLLMPolicy):
    """Matched reactive policy with deterministic factual context compilation."""

    policy_kind = "llm_context_compiled_reactive"
    context_strategy = "factual_compiled_v0.1"

    def __init__(self, model: str, **kwargs: Any):
        super().__init__(model, **kwargs)
        self.policy_id = f"context-compiled-reactive--{model}"

    def _prompt_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return compile_visible_state(state)

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        metadata["context_strategy"] = self.context_strategy
        return metadata
