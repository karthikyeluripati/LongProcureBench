"""Naive one-call-per-step LLM baseline for LongProcureBench."""
from __future__ import annotations

from copy import deepcopy
import json
from time import perf_counter
from typing import Any, Protocol

from .litellm_client import LiteLLMClient, ModelCallError


ACTION_TYPES = [
    "request_buyer_clarification",
    "identify_suppliers",
    "send_rfq",
    "send_follow_up",
    "answer_supplier_question",
    "issue_amendment",
    "request_quote_revision",
    "evaluate_quotes",
    "award_supplier",
    "no_award",
]

AWARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scope": {"type": "string"},
        "supplier_id": {"type": "string"},
        "quote_event_id": {"type": "string"},
    },
    "required": ["scope", "supplier_id", "quote_event_id"],
    "additionalProperties": False,
}

SEMANTIC_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ACTION_TYPES},
        "supplier_id": {"type": ["string", "null"]},
        "arguments": {
            "type": "object",
            "properties": {
                "awards": {
                    "type": ["array", "null"],
                    "items": AWARD_SCHEMA,
                },
                "reason": {"type": ["string", "null"]},
            },
            "required": ["awards", "reason"],
            "additionalProperties": False,
        },
    },
    "required": ["type", "supplier_id", "arguments"],
    "additionalProperties": False,
}


class ActionModelClient(Protocol):
    model: str

    def generate_action(
        self,
        *,
        messages: list[dict[str, str]],
        action_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ...


class ReactiveLLMPolicy:
    """Stateless reactive baseline: current visible state -> one model action."""

    policy_kind = "llm_reactive_baseline"

    SYSTEM_PROMPT = """You are a procurement agent in LongProcureBench.
Choose exactly one next semantic action from the allowed structured schema.

Use only facts in the visible state. Do not assume hidden suppliers, future
events, oracle answers, or unrevealed quotes. Preserve changed requirements,
supplier scope, eligibility, compliance, budget, delivery, and quote revisions.

Action contract:
- request_buyer_clarification, identify_suppliers, issue_amendment,
  evaluate_quotes, and no_award require supplier_id = null.
- send_rfq, send_follow_up, answer_supplier_question, and
  request_quote_revision require a supplier_id that is currently visible.
- award_supplier requires arguments.awards to be a non-empty list. Each award
  must contain exactly scope, supplier_id, and quote_event_id. quote_event_id
  must refer to a revealed quote/revision from that supplier and cover the
  award scope. For one award, top-level supplier_id may name that supplier;
  for multiple awards, top-level supplier_id must be null.
- no_award may put a short explanation in arguments.reason.
- For every non-award action, set arguments.awards = null.
- When reason is irrelevant, set arguments.reason = null.

Return only the structured action. Do not include reasoning or prose."""

    def __init__(
        self,
        model: str,
        *,
        client: ActionModelClient | None = None,
        temperature: float | None = 0.0,
        reasoning_effort: str | None = None,
    ):
        self.model = model
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.policy_id = f"reactive-llm--{model}"
        self._client = client or LiteLLMClient(
            model,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )
        self._calls: list[dict[str, Any]] = []

    def reset(self, state: dict[str, Any]) -> None:
        self._calls = []

    @staticmethod
    def _runtime_decision(decision: dict[str, Any]) -> dict[str, Any]:
        arguments = decision.get("arguments")
        if not isinstance(arguments, dict):
            return decision

        runtime_arguments: dict[str, Any] = {}
        if arguments.get("awards") is not None:
            runtime_arguments["awards"] = deepcopy(arguments["awards"])
        if arguments.get("reason") is not None:
            runtime_arguments["reason"] = arguments["reason"]

        return {
            "type": decision.get("type"),
            "supplier_id": decision.get("supplier_id"),
            "arguments": runtime_arguments,
        }

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Current agent-visible benchmark state:\n"
                    + json.dumps(state, sort_keys=True)
                ),
            },
        ]

        started = perf_counter()
        try:
            decision, metrics = self._client.generate_action(
                messages=messages,
                action_schema=SEMANTIC_ACTION_SCHEMA,
            )
        except ModelCallError as exc:
            self._calls.append(deepcopy(exc.metrics))
            raise
        except Exception as exc:
            self._calls.append(
                {
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
                }
            )
            raise

        normalized_metrics = deepcopy(metrics)
        normalized_metrics.setdefault("success", True)
        normalized_metrics.setdefault("usage_available", True)
        normalized_metrics.setdefault("error", None)
        self._calls.append(normalized_metrics)
        return self._runtime_decision(decision)

    def get_run_metadata(self) -> dict[str, Any]:
        attempts = len(self._calls)
        succeeded = sum(bool(call.get("success", True)) for call in self._calls)
        known_costs = [
            float(call["cost_usd"])
            for call in self._calls
            if call.get("cost_usd") is not None
        ]
        return {
            "model": self.model,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "model_calls": attempts,
            "model_calls_attempted": attempts,
            "model_calls_succeeded": succeeded,
            "model_calls_failed": attempts - succeeded,
            "prompt_tokens": sum(
                int(call.get("prompt_tokens", 0)) for call in self._calls
            ),
            "completion_tokens": sum(
                int(call.get("completion_tokens", 0)) for call in self._calls
            ),
            "total_tokens": sum(
                int(call.get("total_tokens", 0)) for call in self._calls
            ),
            "usage_incomplete": any(
                not bool(call.get("usage_available", False))
                for call in self._calls
            ),
            "latency_ms": sum(
                float(call.get("latency_ms", 0.0)) for call in self._calls
            ),
            "cost_usd": (
                sum(known_costs)
                if self._calls
                and len(known_costs) == len(self._calls)
                else None
            ),
            "calls": deepcopy(self._calls),
        }
