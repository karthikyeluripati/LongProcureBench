"""Bounded maintained-working-plan policy over factual compiled context."""
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
from .reactive_llm import ACTION_TYPES, ActionModelClient


class WorkingPlanError(ValueError):
    """Raised when a model emits an invalid working-plan update."""


PLAN_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {
            "type": "string",
            "enum": ACTION_TYPES,
        },
        "supplier_id": {
            "type": ["string", "null"],
        },
        "purpose": {
            "type": "string",
        },
    },
    "required": [
        "action_type",
        "supplier_id",
        "purpose",
    ],
    "additionalProperties": False,
}

WORKING_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objective": {
            "type": "string",
        },
        "next_steps": {
            "type": "array",
            "items": PLAN_STEP_SCHEMA,
        },
        "stop_condition": {
            "type": "string",
        },
    },
    "required": [
        "objective",
        "next_steps",
        "stop_condition",
    ],
    "additionalProperties": False,
}


class WorkingPlanReactiveLLMPolicy(ContextCompiledReactiveLLMPolicy):
    """Reactive policy with a bounded replaceable prospective working plan."""

    policy_kind = "llm_working_plan_reactive"
    state_strategy = "maintained_working_plan_v0.1"

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

You also maintain a bounded external working plan. It is a replaceable guide,
not an obligation ledger and not private chain-of-thought:
- Use current_working_plan to guide the next action when it still fits visible
  facts.
- If visible facts make the current plan stale or unproductive, depart from it
  and replace it rather than repeating an action indefinitely.
- next_plan describes the remaining prospective plan *after* the current action
  is accepted.
- Keep next_plan to at most four future steps.
- Each planned step is concise and may reference only a currently visible
  supplier.
- stop_condition should state the observable condition under which the agent
  should make a terminal award/no-award decision or otherwise stop pursuing the
  current plan.
- If no future steps are useful, return an empty next_steps list.
- Do not encode evaluator checkpoints, hidden requirements, future events,
  oracle outcomes, or chain-of-thought in the plan.

Return only the structured action plus next_plan object."""

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
        self.policy_id = f"working-plan-reactive--{model}"
        self._current_plan: dict[str, Any] | None = None
        self._plan_trace: list[dict[str, Any]] = []
        self._plan_rejection_trace: list[dict[str, Any]] = []
        self._pending_plan: dict[str, Any] | None = None
        self._pending_action: dict[str, Any] | None = None
        self._pending_state_step: int | None = None

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._current_plan = None
        self._plan_trace = []
        self._plan_rejection_trace = []
        self._pending_plan = None
        self._pending_action = None
        self._pending_state_step = None

    @classmethod
    def _response_schema(cls, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": cls._action_schema(state),
                "next_plan": deepcopy(WORKING_PLAN_SCHEMA),
            },
            "required": ["action", "next_plan"],
            "additionalProperties": False,
        }

    def _prompt_state(self, state: dict[str, Any]) -> dict[str, Any]:
        compiled = compile_visible_state(state)
        compiled["current_working_plan"] = deepcopy(self._current_plan)
        return compiled

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

    def _validate_plan(
        self,
        plan: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        objective = plan["objective"]
        if (
            not isinstance(objective, str)
            or not objective.strip()
            or len(objective) > 200
        ):
            raise WorkingPlanError(
                "Plan objective must be 1-200 characters"
            )

        stop_condition = plan["stop_condition"]
        if (
            not isinstance(stop_condition, str)
            or not stop_condition.strip()
            or len(stop_condition) > 240
        ):
            raise WorkingPlanError(
                "Plan stop_condition must be 1-240 characters"
            )

        steps = plan["next_steps"]
        if len(steps) > 4:
            raise WorkingPlanError(
                "Working plan contains more than 4 future steps"
            )

        visible_suppliers = self._visible_supplier_ids(state)
        for step in steps:
            purpose = step["purpose"]
            if (
                not isinstance(purpose, str)
                or not purpose.strip()
                or len(purpose) > 180
            ):
                raise WorkingPlanError(
                    "Plan step purpose must be 1-180 characters"
                )

            supplier_id = step["supplier_id"]
            if (
                supplier_id is not None
                and supplier_id not in visible_suppliers
            ):
                raise WorkingPlanError(
                    "Plan step references non-visible supplier: "
                    f"{supplier_id}"
                )

    def on_action_accepted(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        """Commit the pending replacement plan after env acceptance."""
        if self._pending_plan is None:
            return

        accepted = {
            "type": action.get("type"),
            "supplier_id": action.get("supplier_id"),
            "arguments": deepcopy(action.get("arguments") or {}),
        }
        if accepted != self._pending_action:
            raise WorkingPlanError(
                "Accepted action does not match pending working plan"
            )

        previous = deepcopy(self._current_plan)
        self._current_plan = deepcopy(self._pending_plan)
        self._plan_trace.append({
            "model_call": len(self._calls),
            "proposed_state_step": self._pending_state_step,
            "accepted_state_step": state.get("step"),
            "previous_plan": previous,
            "next_plan": deepcopy(self._current_plan),
        })

        self._pending_plan = None
        self._pending_action = None
        self._pending_state_step = None

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._pending_plan is not None:
            raise WorkingPlanError(
                "Previous working plan is still pending action acceptance"
            )

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
        runtime_action = self._runtime_decision(response["action"])
        next_plan = deepcopy(response["next_plan"])

        try:
            self._validate_plan(next_plan, state)
        except WorkingPlanError as exc:
            self._plan_rejection_trace.append({
                "model_call": len(self._calls),
                "state_step": state.get("step"),
                "message": str(exc),
                "rejected_plan": deepcopy(next_plan),
            })
            return runtime_action

        self._pending_plan = next_plan
        self._pending_action = deepcopy(runtime_action)
        self._pending_state_step = state.get("step")
        return runtime_action

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        plan_lengths = [
            len(row["next_plan"]["next_steps"])
            for row in self._plan_trace
        ]
        metadata["context_strategy"] = self.context_strategy
        metadata["state_strategy"] = self.state_strategy
        metadata["plan_updates"] = len(self._plan_trace)
        metadata["plan_rejections"] = len(self._plan_rejection_trace)
        metadata["mean_plan_steps"] = (
            sum(plan_lengths) / len(plan_lengths)
            if plan_lengths
            else 0.0
        )
        metadata["max_plan_steps"] = max(plan_lengths, default=0)
        metadata["final_plan"] = deepcopy(self._current_plan)
        metadata["plan_trace"] = deepcopy(self._plan_trace)
        metadata["plan_rejection_trace"] = deepcopy(
            self._plan_rejection_trace
        )
        return metadata
