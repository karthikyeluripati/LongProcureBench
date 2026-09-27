"""External ReAct comparator for LongProcureBench."""
from __future__ import annotations

from copy import deepcopy
import json
from time import perf_counter
from typing import Any

from .context_compiled_reactive import (
    ContextCompiledReactiveLLMPolicy,
    compact_visible_event,
    compile_visible_state,
)
from .litellm_client import ModelCallError
from .reactive_llm import SEMANTIC_ACTION_SCHEMA


MAX_THOUGHT_CHARS = 400

REACT_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "thought_summary": {"type": "string", "minLength": 1},
        "action": deepcopy(SEMANTIC_ACTION_SCHEMA),
    },
    "required": ["thought_summary", "action"],
    "additionalProperties": False,
}


class ReActProtocolError(ValueError):
    """Raised when a ReAct step violates the external comparator contract."""


class ReActLLMPolicy(ContextCompiledReactiveLLMPolicy):
    """One-call Thought -> Action -> Observation comparator."""

    policy_kind = "llm_react_comparator"
    agent_pattern = "react_v0.1"

    SYSTEM_PROMPT = """You are a procurement agent in LongProcureBench using
the ReAct pattern.

For each step, produce exactly:
1. thought_summary: one concise, decision-relevant summary of why the next
   action follows from visible evidence;
2. action: exactly one semantic procurement action from the structured schema.

The thought summary is an external audit trace, not hidden chain-of-thought.
Keep it brief and factual. Do not invent hidden facts or speculate about future
events.

Use only facts in the visible state and prior accepted ReAct transcript. Do not
assume hidden suppliers, future events, oracle answers, evaluator state, or
unrevealed quotes. Preserve changed requirements, supplier scope, eligibility,
compliance, budget, delivery, and quote revisions.

Action contract:
- request_buyer_clarification, identify_suppliers, issue_amendment,
  evaluate_quotes, and no_award require supplier_id = null.
- send_rfq, send_follow_up, answer_supplier_question, and
  request_quote_revision require a supplier_id that is currently visible.
- award_supplier requires arguments.awards to be a non-empty list. Each award
  must contain exactly scope, supplier_id, and quote_event_id. scope must be
  exactly one of the allowed award-scope values supplied with the current
  state. quote_event_id must refer to a revealed quote/revision from that
  supplier and cover the award scope.
- For every non-award action, set arguments.awards = null.
- When reason is irrelevant, set arguments.reason = null.

Return only the structured ReAct step."""

    def __init__(self, model: str, **kwargs: Any):
        super().__init__(model, **kwargs)
        self.policy_id = f"react-comparator--{model}"
        self._react_transcript: list[dict[str, Any]] = []
        self._pending_thought: str | None = None
        self._pending_action: dict[str, Any] | None = None
        self._react_steps_proposed = 0

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._react_transcript = []
        self._pending_thought = None
        self._pending_action = None
        self._react_steps_proposed = 0

    @classmethod
    def _react_schema(cls, state: dict[str, Any]) -> dict[str, Any]:
        schema = deepcopy(REACT_STEP_SCHEMA)
        schema["properties"]["action"] = cls._action_schema(state)
        return schema

    @staticmethod
    def _normalize_thought(value: Any) -> str:
        if not isinstance(value, str):
            raise ReActProtocolError("thought_summary must be a string")
        thought = value.strip()
        if not thought:
            raise ReActProtocolError("thought_summary must be non-empty")
        return thought[:MAX_THOUGHT_CHARS]

    @staticmethod
    def _semantic_from_accepted(action: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": action.get("type"),
            "supplier_id": action.get("supplier_id"),
            "arguments": deepcopy(action.get("arguments") or {}),
        }

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._pending_action is not None:
            raise ReActProtocolError(
                "Previous ReAct action is still pending acceptance"
            )

        allowed_scopes = self._allowed_award_scopes(state)
        prompt_payload = {
            "current_visible_state": compile_visible_state(state),
            "react_transcript": deepcopy(self._react_transcript),
        }
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Allowed award scope values this episode: "
                    + ", ".join(allowed_scopes)
                    + "\n\nCurrent ReAct context:\n"
                    + json.dumps(prompt_payload, sort_keys=True)
                ),
            },
        ]

        started = perf_counter()
        try:
            response, metrics = self._client.generate_action(
                messages=messages,
                action_schema=self._react_schema(state),
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

        try:
            if not isinstance(response, dict):
                raise ReActProtocolError("ReAct response must be an object")
            thought = self._normalize_thought(
                response.get("thought_summary")
            )
            action = response.get("action")
            if not isinstance(action, dict):
                raise ReActProtocolError(
                    "ReAct response requires action object"
                )
        except ReActProtocolError as exc:
            normalized_metrics["success"] = False
            normalized_metrics["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            self._calls.append(normalized_metrics)
            raise

        self._calls.append(normalized_metrics)
        runtime_action = self._runtime_decision(action)
        self._pending_thought = thought
        self._pending_action = deepcopy(runtime_action)
        self._react_steps_proposed += 1
        return runtime_action

    def on_action_accepted(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        if self._pending_action is None or self._pending_thought is None:
            raise ReActProtocolError(
                "Accepted action has no pending ReAct step"
            )

        accepted = self._semantic_from_accepted(action)
        if accepted != self._pending_action:
            raise ReActProtocolError(
                "Accepted action does not match pending ReAct action"
            )

        compact_observations = [
            compact
            for compact in (
                compact_visible_event(event)
                for event in (state.get("observations") or [])
            )
            if compact is not None
        ]
        self._react_transcript.append({
            "step": state.get("step"),
            "thought_summary": self._pending_thought,
            "action": deepcopy(accepted),
            "observation": compact_observations,
        })
        self._pending_thought = None
        self._pending_action = None

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        thought_chars = [
            len(row["thought_summary"])
            for row in self._react_transcript
        ]
        metadata.update({
            "context_strategy": self.context_strategy,
            "agent_pattern": self.agent_pattern,
            "react_steps_proposed": self._react_steps_proposed,
            "react_steps_accepted": len(self._react_transcript),
            "react_thought_chars_total": sum(thought_chars),
            "react_thought_chars_mean": (
                sum(thought_chars) / len(thought_chars)
                if thought_chars
                else 0.0
            ),
            "react_thought_chars_max": max(thought_chars, default=0),
            "react_transcript": deepcopy(self._react_transcript),
        })
        return metadata
