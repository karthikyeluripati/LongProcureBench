"""Persistent model-maintained operational ledger over factual compiled context."""
from __future__ import annotations

from copy import deepcopy
import json
from time import perf_counter
from typing import Any

from jsonschema import Draft202012Validator

from .context_compiled_reactive import (
    ContextCompiledReactiveLLMPolicy,
    compile_visible_state,
)
from .litellm_client import ModelCallError
from .reactive_llm import ActionModelClient


LEDGER_CATEGORIES = [
    "requirement",
    "supplier",
    "offer",
    "decision",
    "other",
]

NEW_LEDGER_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": LEDGER_CATEGORIES,
        },
        "supplier_id": {
            "type": ["string", "null"],
        },
        "source_event_ids": {
            "type": "array",
            "items": {
                "type": "string",
                "minLength": 1,
            },
            "uniqueItems": True,
            "maxItems": 12,
        },
        "description": {
            "type": "string",
            "minLength": 1,
            "maxLength": 240,
        },
    },
    "required": [
        "category",
        "supplier_id",
        "source_event_ids",
        "description",
    ],
    "additionalProperties": False,
}

LEDGER_UPDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "new_items": {
            "type": "array",
            "items": NEW_LEDGER_ITEM_SCHEMA,
            "maxItems": 8,
        },
        "resolve_item_ids": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^l[0-9]{3,}$",
            },
            "uniqueItems": True,
            "maxItems": 16,
        },
    },
    "required": [
        "new_items",
        "resolve_item_ids",
    ],
    "additionalProperties": False,
}


class OperationalLedgerReactiveLLMPolicy(ContextCompiledReactiveLLMPolicy):
    """One-call reactive policy with an auditable persistent commitment ledger."""

    policy_kind = "llm_operational_ledger_reactive"
    state_strategy = "operational_ledger_v0.1"

    SYSTEM_PROMPT = """You are a procurement agent in LongProcureBench.
Choose exactly one next semantic action from the allowed structured schema.

Use only facts in the visible state. Do not assume hidden suppliers, future
events, oracle answers, evaluator state, or unrevealed quotes. Preserve changed
requirements, supplier scope, eligibility, compliance, budget, delivery, and
quote revisions.

Action contract:
- request_buyer_clarification, identify_suppliers, issue_amendment,
  evaluate_quotes, and no_award require supplier_id = null.
- send_rfq, send_follow_up, answer_supplier_question, and
  request_quote_revision require a supplier_id that is currently visible.
- award_supplier requires arguments.awards to be a non-empty list. Each award
  must contain exactly scope, supplier_id, and quote_event_id. scope must be
  exactly one of the allowed award-scope values supplied with the current
  state; never write a descriptive scope. quote_event_id must refer to a
  revealed quote/revision from that supplier and cover the award scope. For
  one award, top-level supplier_id may name that supplier; for multiple
  awards, top-level supplier_id must be null.
- no_award may put a short explanation in arguments.reason.
- For every non-award action, set arguments.awards = null.
- When reason is irrelevant, set arguments.reason = null.

You also maintain the persistent operational ledger shown in the state.
The ledger is external task state, not private reasoning:
- Add a concise open item only when visible facts create future procurement
  work that could otherwise be forgotten.
- Do not add evaluator checkpoints, hidden requirements, predictions, or
  chain-of-thought. A description should be a short operational task.
- source_event_ids may name only events already visible in the current state.
  Initial-state work may use an empty source_event_ids list.
- supplier_id may be non-null only for a currently visible supplier.
- Do not duplicate an item that is already open.
- Resolve only a previously open item. If resolution depends on a future
  supplier/buyer response, keep the item open until that response is visible.
- The chosen action may resolve a prior item only when that action itself
  discharges the commitment.

Return only the structured action plus ledger_update object."""

    def __init__(
        self,
        model: str,
        *,
        client: ActionModelClient | None = None,
        temperature: float | None = 0.0,
        reasoning_effort: str | None = None,
    ):
        super().__init__(
            model,
            client=client,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )
        self.policy_id = f"operational-ledger-reactive--{model}"
        self._open_items: dict[str, dict[str, Any]] = {}
        self._resolved_items: list[dict[str, Any]] = []
        self._ledger_sequence = 0
        self._ledger_trace: list[dict[str, Any]] = []

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._open_items = {}
        self._resolved_items = []
        self._ledger_sequence = 0
        self._ledger_trace = []

    @classmethod
    def _response_schema(cls, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": cls._action_schema(state),
                "ledger_update": deepcopy(LEDGER_UPDATE_SCHEMA),
            },
            "required": [
                "action",
                "ledger_update",
            ],
            "additionalProperties": False,
        }

    def _ledger_view(self) -> dict[str, Any]:
        return {
            "open_items": [
                deepcopy(item)
                for item in self._open_items.values()
            ],
            "resolved_items": deepcopy(self._resolved_items),
        }

    def _prompt_state(self, state: dict[str, Any]) -> dict[str, Any]:
        compiled = compile_visible_state(state)
        compiled["persistent_operational_ledger"] = self._ledger_view()
        return compiled

    @staticmethod
    def _visible_event_ids(state: dict[str, Any]) -> set[str]:
        events = state.get("revealed_events")
        if not isinstance(events, list):
            return set()
        return {
            event["event_id"]
            for event in events
            if isinstance(event, dict)
            and isinstance(event.get("event_id"), str)
        }

    @staticmethod
    def _visible_supplier_ids(state: dict[str, Any]) -> set[str]:
        suppliers = state.get("visible_suppliers")
        if not isinstance(suppliers, list):
            return set()
        return {
            supplier["supplier_id"]
            for supplier in suppliers
            if isinstance(supplier, dict)
            and isinstance(supplier.get("supplier_id"), str)
        }

    def _apply_ledger_update(
        self,
        update: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        resolve_ids = update["resolve_item_ids"]
        for item_id in resolve_ids:
            if item_id not in self._open_items:
                raise ValueError(
                    f"Cannot resolve unknown open ledger item: {item_id}"
                )

        visible_events = self._visible_event_ids(state)
        visible_suppliers = self._visible_supplier_ids(state)
        for item in update["new_items"]:
            supplier_id = item["supplier_id"]
            if (
                supplier_id is not None
                and supplier_id not in visible_suppliers
            ):
                raise ValueError(
                    "Ledger item references non-visible supplier: "
                    f"{supplier_id}"
                )
            for event_id in item["source_event_ids"]:
                if event_id not in visible_events:
                    raise ValueError(
                        "Ledger item references unrevealed event: "
                        f"{event_id}"
                    )

        resolved_now = []
        for item_id in resolve_ids:
            item = self._open_items.pop(item_id)
            resolved = deepcopy(item)
            resolved["resolved_on_model_call"] = len(self._calls)
            self._resolved_items.append(resolved)
            resolved_now.append(item_id)

        new_ids = []
        for item in update["new_items"]:
            self._ledger_sequence += 1
            item_id = f"l{self._ledger_sequence:03d}"
            stored = {
                "item_id": item_id,
                **deepcopy(item),
            }
            self._open_items[item_id] = stored
            new_ids.append(item_id)

        self._ledger_trace.append({
            "model_call": len(self._calls),
            "state_step": state.get("step"),
            "new_item_ids": new_ids,
            "resolved_item_ids": resolved_now,
            "open_item_ids_after": list(self._open_items),
            "resolved_item_ids_after": [
                item["item_id"] for item in self._resolved_items
            ],
        })

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        allowed_scopes = self._allowed_award_scopes(state)
        response_schema = self._response_schema(state)
        prompt_state = self._prompt_state(state)
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Allowed award scope values this episode: "
                    + ", ".join(allowed_scopes)
                    + "\n\nCurrent agent-visible benchmark state:\n"
                    + json.dumps(prompt_state, sort_keys=True)
                ),
            },
        ]

        started = perf_counter()
        try:
            response, metrics = self._client.generate_action(
                messages=messages,
                action_schema=response_schema,
            )
        except ModelCallError as exc:
            self._calls.append(deepcopy(exc.metrics))
            raise
        except Exception as exc:
            self._calls.append({
                "model": self.model,
                "success": False,
                "latency_ms": (perf_counter() - started) * 1000.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": None,
                "usage_available": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            })
            raise

        normalized_metrics = deepcopy(metrics)
        normalized_metrics.setdefault("success", True)
        normalized_metrics.setdefault("usage_available", True)
        normalized_metrics.setdefault("error", None)
        self._calls.append(normalized_metrics)

        Draft202012Validator(response_schema).validate(response)
        self._apply_ledger_update(response["ledger_update"], state)
        return self._runtime_decision(response["action"])

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        metadata["context_strategy"] = self.context_strategy
        metadata["state_strategy"] = self.state_strategy
        metadata["ledger_open_items"] = len(self._open_items)
        metadata["ledger_resolved_items"] = len(self._resolved_items)
        metadata["final_ledger"] = self._ledger_view()
        metadata["ledger_trace"] = deepcopy(self._ledger_trace)
        return metadata
