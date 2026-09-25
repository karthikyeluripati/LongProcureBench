"""Thin LiteLLM adapter for model-backed benchmark policies."""
from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import litellm


class ModelCallError(RuntimeError):
    """Model/provider/parse failure with the call metrics captured so far."""

    def __init__(self, message: str, *, metrics: dict[str, Any]):
        super().__init__(message)
        self.metrics = metrics


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

    def _metrics(
        self,
        *,
        response: Any,
        latency_ms: float,
        success: bool,
        error: Exception | None,
    ) -> dict[str, Any]:
        usage = self._value(response, "usage", None) if response is not None else None
        prompt_raw = self._value(usage, "prompt_tokens", None)
        completion_raw = self._value(usage, "completion_tokens", None)
        total_raw = self._value(usage, "total_tokens", None)

        usage_available = (
            usage is not None
            and prompt_raw is not None
            and completion_raw is not None
        )
        prompt_tokens = prompt_raw or 0
        completion_tokens = completion_raw or 0
        total_tokens = (
            total_raw
            if total_raw is not None
            else prompt_tokens + completion_tokens
        )

        cost_usd = None
        if response is not None:
            try:
                cost_usd = litellm.completion_cost(
                    completion_response=response
                )
            except Exception:
                cost_usd = None

        return {
            "model": self.model,
            "success": success,
            "latency_ms": latency_ms,
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
            "cost_usd": (
                float(cost_usd) if cost_usd is not None else None
            ),
            "usage_available": usage_available,
            "error": (
                {
                    "type": type(error).__name__,
                    "message": str(error),
                }
                if error is not None
                else None
            ),
        }

    def generate_action(
        self,
        *,
        messages: list[dict[str, str]],
        action_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = perf_counter()
        response = None
        try:
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

            choice = self._value(response, "choices")[0]
            message = self._value(choice, "message")
            parsed = self._value(message, "parsed")
            if parsed is not None:
                decision = dict(parsed)
            else:
                content = self._value(message, "content")
                if not isinstance(content, str):
                    raise ValueError(
                        "LiteLLM response did not contain structured content"
                    )
                decision = json.loads(content)
        except Exception as exc:
            metrics = self._metrics(
                response=response,
                latency_ms=(perf_counter() - started) * 1000.0,
                success=False,
                error=exc,
            )
            raise ModelCallError(
                f"Model action call failed: {exc}",
                metrics=metrics,
            ) from exc

        return decision, self._metrics(
            response=response,
            latency_ms=(perf_counter() - started) * 1000.0,
            success=True,
            error=None,
        )
