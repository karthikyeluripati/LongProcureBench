"""Naive one-call-per-step LLM baseline for LongProcureBench."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Protocol

from .litellm_client import LiteLLMClient


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

SEMANTIC_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ACTION_TYPES},
        "supplier_id": {"type": ["string", "null"]},
        "arguments": {"type": "object"},
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
Choose exactly one next semantic action from the allowed action schema.

Use only facts in the visible state. Do not assume hidden suppliers, future
events, oracle answers, or unrevealed quotes. Preserve changed requirements,
supplier scope, eligibility, compliance, budget, delivery, and quote revisions.

Return only the structured action. Do not include reasoning or prose."""

    def __init__(
        self,
        model: str,
        *,
        client: ActionModelClient | None = None,
        temperature: float = 0.0,
    ):
        self.model = model
        self.policy_id = f"reactive-llm--{model}"
        self._client = client or LiteLLMClient(
            model, temperature=temperature
        )
        self._calls: list[dict[str, Any]] = []

    def reset(self, state: dict[str, Any]) -> None:
        self._calls = []

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
        decision, metrics = self._client.generate_action(
            messages=messages,
            action_schema=SEMANTIC_ACTION_SCHEMA,
        )
        self._calls.append(deepcopy(metrics))
        return decision

    def get_run_metadata(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "model_calls": len(self._calls),
            "prompt_tokens": sum(
                int(call.get("prompt_tokens", 0)) for call in self._calls
            ),
            "completion_tokens": sum(
                int(call.get("completion_tokens", 0)) for call in self._calls
            ),
            "total_tokens": sum(
                int(call.get("total_tokens", 0)) for call in self._calls
            ),
            "latency_ms": sum(
                float(call.get("latency_ms", 0.0)) for call in self._calls
            ),
            "cost_usd": (
                sum(float(call["cost_usd"]) for call in self._calls)
                if self._calls
                and all(call.get("cost_usd") is not None for call in self._calls)
                else None
            ),
            "calls": deepcopy(self._calls),
        }
