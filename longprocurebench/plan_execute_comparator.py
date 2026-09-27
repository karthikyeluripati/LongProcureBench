"""Static Plan-and-Execute comparator over factual compiled context."""
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


MAX_PLAN_STEPS = 10

PLAN_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "step_id": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_PLAN_STEPS,
        },
        "operation": {
            "type": "string",
            "enum": ACTION_TYPES,
        },
        "purpose": {"type": "string"},
        "condition": {"type": "string"},
    },
    "required": ["step_id", "operation", "purpose", "condition"],
    "additionalProperties": False,
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objective": {"type": "string"},
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_PLAN_STEPS,
            "items": PLAN_STEP_SCHEMA,
        },
        "completion_condition": {"type": "string"},
    },
    "required": ["objective", "steps", "completion_condition"],
    "additionalProperties": False,
}


class PlanExecuteProtocolError(ValueError):
    """Raised when the Plan-and-Execute protocol is violated."""


class PlanExecuteLLMPolicy(ContextCompiledReactiveLLMPolicy):
    """Generate one fixed plan, then execute against it without replanning."""

    policy_kind = "llm_plan_execute_comparator"
    agent_pattern = "plan_execute_static_v0.1"

    PLANNER_PROMPT = """You are the planner in a Plan-and-Execute procurement
agent for LongProcureBench.

Before any procurement action occurs, create one concise fixed plan for solving
the visible procurement task. The executor will use this same plan for the
entire episode; you will not get to rewrite it later.

Use only the visible factual state. Do not assume hidden suppliers, future
events, oracle answers, evaluator state, or unrevealed quotes.

Plan prerequisite work before work that depends on it. Account for the normal
possibility that visible facts can later require repair or recovery, but do not
pretend to know which future event will occur. Each step names one semantic
operation from the benchmark action space and an observable condition under
which that operation is appropriate. A step may be used more than once by the
executor when its condition remains applicable.

Do not provide chain-of-thought. Return only the structured fixed plan."""

    EXECUTOR_PROMPT = """You are the executor in a Plan-and-Execute procurement
agent for LongProcureBench.

You receive:
1. one fixed plan created before any action;
2. the current factual visible state.

Choose exactly one next semantic procurement action. Use the plan when an
applicable planned operation exists. Return the 1-based plan_step_index for the
plan step you are executing.

If a newly visible fact requires a necessary action that the fixed plan did not
represent, set plan_step_index = 0 and take that necessary action as an
unplanned exception. Do not rewrite or extend the plan.

Use only visible facts. Do not assume hidden suppliers, future events, oracle
answers, evaluator state, or unrevealed quotes. Preserve changed requirements,
supplier scope, eligibility, compliance, budget, delivery, and quote revisions.

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

Return only the structured executor response."""

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
        self.policy_id = f"plan-execute-comparator--{model}"
        self._fixed_plan: dict[str, Any] | None = None
        self._planner_calls = 0
        self._executor_calls = 0
        self._execution_trace: list[dict[str, Any]] = []
        self._pending_execution: dict[str, Any] | None = None

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._fixed_plan = None
        self._planner_calls = 0
        self._executor_calls = 0
        self._execution_trace = []
        self._pending_execution = None

    @classmethod
    def _executor_schema(cls, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_step_index": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": MAX_PLAN_STEPS,
                },
                "action": cls._action_schema(state),
            },
            "required": ["plan_step_index", "action"],
            "additionalProperties": False,
        }

    def _record_model_call(
        self,
        *,
        started: float,
        response: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        if metrics is not None:
            normalized = deepcopy(metrics)
            normalized.setdefault("success", error is None)
            normalized.setdefault("usage_available", True)
            normalized.setdefault(
                "error",
                (
                    {
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                    if error is not None
                    else None
                ),
            )
            self._calls.append(normalized)
            return

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
                "type": type(error).__name__ if error else "UnknownError",
                "message": str(error) if error else "unknown model error",
            },
        })

    @staticmethod
    def _bounded_text(value: Any, label: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PlanExecuteProtocolError(f"{label} must be non-empty text")
        text = value.strip()
        if len(text) > maximum:
            raise PlanExecuteProtocolError(
                f"{label} exceeds {maximum} characters"
            )
        return text

    def _validate_plan(self, plan: dict[str, Any]) -> None:
        Draft202012Validator(PLAN_SCHEMA).validate(plan)
        self._bounded_text(plan["objective"], "objective", 240)
        self._bounded_text(
            plan["completion_condition"],
            "completion_condition",
            300,
        )
        steps = plan["steps"]
        expected_ids = list(range(1, len(steps) + 1))
        actual_ids = [step["step_id"] for step in steps]
        if actual_ids != expected_ids:
            raise PlanExecuteProtocolError(
                "Plan step_id values must be sequential from 1"
            )
        for step in steps:
            self._bounded_text(step["purpose"], "step purpose", 220)
            self._bounded_text(step["condition"], "step condition", 260)

    def _generate_plan(self, state: dict[str, Any]) -> None:
        if self._fixed_plan is not None:
            raise PlanExecuteProtocolError("Fixed plan already exists")

        compiled = compile_visible_state(state)
        messages = [
            {"role": "system", "content": self.PLANNER_PROMPT},
            {
                "role": "user",
                "content": (
                    "Visible initial procurement state:\n"
                    + json.dumps(compiled, sort_keys=True)
                ),
            },
        ]

        started = perf_counter()
        try:
            response, metrics = self._client.generate_action(
                messages=messages,
                action_schema=PLAN_SCHEMA,
            )
        except ModelCallError as exc:
            self._calls.append(deepcopy(exc.metrics))
            raise
        except Exception as exc:
            self._record_model_call(started=started, error=exc)
            raise

        try:
            if not isinstance(response, dict):
                raise PlanExecuteProtocolError(
                    "Planner response must be an object"
                )
            self._validate_plan(response)
        except Exception as exc:
            self._record_model_call(
                started=started,
                metrics=metrics,
                error=exc,
            )
            raise

        self._record_model_call(started=started, metrics=metrics)
        self._planner_calls += 1
        self._fixed_plan = deepcopy(response)

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._pending_execution is not None:
            raise PlanExecuteProtocolError(
                "Previous executor action is still pending acceptance"
            )
        if self._fixed_plan is None:
            self._generate_plan(state)

        allowed_scopes = self._allowed_award_scopes(state)
        payload = {
            "fixed_plan": deepcopy(self._fixed_plan),
            "current_visible_state": compile_visible_state(state),
        }
        schema = self._executor_schema(state)
        messages = [
            {"role": "system", "content": self.EXECUTOR_PROMPT},
            {
                "role": "user",
                "content": (
                    "Allowed award scope values this episode: "
                    + ", ".join(allowed_scopes)
                    + "\n\nPlan-and-Execute context:\n"
                    + json.dumps(payload, sort_keys=True)
                ),
            },
        ]

        started = perf_counter()
        try:
            response, metrics = self._client.generate_action(
                messages=messages,
                action_schema=schema,
            )
        except ModelCallError as exc:
            self._calls.append(deepcopy(exc.metrics))
            raise
        except Exception as exc:
            self._record_model_call(started=started, error=exc)
            raise

        try:
            Draft202012Validator(schema).validate(response)
            step_index = int(response["plan_step_index"])
            if (
                step_index > 0
                and step_index > len(self._fixed_plan["steps"])
            ):
                raise PlanExecuteProtocolError(
                    "Executor referenced a nonexistent plan step"
                )
            if step_index > 0:
                planned_operation = self._fixed_plan["steps"][
                    step_index - 1
                ]["operation"]
                action_type = response["action"].get("type")
                if action_type != planned_operation:
                    raise PlanExecuteProtocolError(
                        "Executor action type does not match selected plan step"
                    )
            runtime_action = self._runtime_decision(response["action"])
        except Exception as exc:
            self._record_model_call(
                started=started,
                metrics=metrics,
                error=exc,
            )
            raise

        self._record_model_call(started=started, metrics=metrics)
        self._executor_calls += 1
        self._pending_execution = {
            "plan_step_index": step_index,
            "action": deepcopy(runtime_action),
            "state_step": state.get("step"),
        }
        return runtime_action

    def on_action_accepted(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        if self._pending_execution is None:
            raise PlanExecuteProtocolError(
                "Accepted action has no pending executor decision"
            )

        accepted = {
            "type": action.get("type"),
            "supplier_id": action.get("supplier_id"),
            "arguments": deepcopy(action.get("arguments") or {}),
        }
        if accepted != self._pending_execution["action"]:
            raise PlanExecuteProtocolError(
                "Accepted action does not match pending executor action"
            )

        self._execution_trace.append({
            "proposed_state_step": self._pending_execution["state_step"],
            "accepted_state_step": state.get("step"),
            "plan_step_index": self._pending_execution[
                "plan_step_index"
            ],
            "action": deepcopy(accepted),
        })
        self._pending_execution = None

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        plan_step_counts: dict[str, int] = {}
        exceptions = 0
        for row in self._execution_trace:
            index = int(row["plan_step_index"])
            if index == 0:
                exceptions += 1
            key = str(index)
            plan_step_counts[key] = plan_step_counts.get(key, 0) + 1

        metadata.update({
            "context_strategy": self.context_strategy,
            "agent_pattern": self.agent_pattern,
            "planner_calls": self._planner_calls,
            "executor_calls": self._executor_calls,
            "fixed_plan": deepcopy(self._fixed_plan),
            "plan_steps": (
                len(self._fixed_plan["steps"])
                if self._fixed_plan is not None
                else 0
            ),
            "unplanned_exceptions": exceptions,
            "plan_step_usage": plan_step_counts,
            "execution_trace": deepcopy(self._execution_trace),
        })
        return metadata
