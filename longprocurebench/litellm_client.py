"""Thin LiteLLM adapter for model-backed benchmark policies."""
from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import litellm


class LiteLLMClient:
    """One provider-neutral structured model call through LiteLLM."""

    def __init__(self, model: str, *, temperature: float = 0.0):
        if not isinstance(model, str) or not model:
            raise ValueError("model must be a non-empty string")
        self.model = model
        self.temperature = temperature

    @staticmethod
    def _value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def generate_action(
        self,
        *,
        messages: list[dict[str, str]],
        action_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = perf_counter()
        response = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "longprocurebench_action",
                    "strict": True,
                    "schema": action_schema,
                },
            },
        )
        latency_ms = (perf_counter() - started) * 1000.0

        choice = self._value(response, "choices")[0]
        message = self._value(choice, "message")
        parsed = self._value(message, "parsed")
        if parsed is not None:
            decision = dict(parsed)
        else:
            content = self._value(message, "content")
            if not isinstance(content, str):
                raise ValueError("LiteLLM response did not contain structured content")
            decision = json.loads(content)

        usage = self._value(response, "usage", {})
        prompt_tokens = self._value(usage, "prompt_tokens", 0) or 0
        completion_tokens = self._value(usage, "completion_tokens", 0) or 0
        total_tokens = self._value(
            usage, "total_tokens", prompt_tokens + completion_tokens
        ) or (prompt_tokens + completion_tokens)

        cost_usd = None
        try:
            cost_usd = litellm.completion_cost(completion_response=response)
        except Exception:
            cost_usd = None

        return decision, {
            "model": self.model,
            "latency_ms": latency_ms,
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
            "cost_usd": (
                float(cost_usd) if cost_usd is not None else None
            ),
        }
