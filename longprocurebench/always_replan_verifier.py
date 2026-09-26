"""Always-replan plus pre-terminal-verifier policy over factual compiled context."""
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


TERMINAL_ACTIONS = {"award_supplier", "no_award"}
NONTERMINAL_ACTIONS = [x for x in ACTION_TYPES if x not in TERMINAL_ACTIONS]


class DeliberationProtocolError(ValueError):
    """Raised when structured planner/verifier output violates local bounds."""


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objective": {"type": "string"},
        "key_facts": {
            "type": "array",
            "items": {"type": "string"},
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_action_type": {
            "type": "string",
            "enum": ACTION_TYPES,
        },
        "supplier_id": {"type": ["string", "null"]},
    },
    "required": [
        "objective",
        "key_facts",
        "risks",
        "recommended_action_type",
        "supplier_id",
    ],
    "additionalProperties": False,
}


VERIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_action_type": {
            "type": "string",
            "enum": ACTION_TYPES,
        },
        "supplier_id": {"type": ["string", "null"]},
    },
    "required": [
        "approve",
        "issues",
        "recommended_action_type",
        "supplier_id",
    ],
    "additionalProperties": False,
}


class AlwaysReplanVerifierLLMPolicy(ContextCompiledReactiveLLMPolicy):
    """Quality-heavy comparator with fresh planning and terminal verification."""

    policy_kind = "llm_always_replan_verifier"
    state_strategy = "always_replan_preterminal_verifier_v0.1"

    PLANNER_PROMPT = """You are the planning pass for a procurement agent in
LongProcureBench. Re-plan from scratch from the current visible state before
the next action. Use only facts already visible in the supplied state.

Return a compact external deliberation record, not private chain-of-thought:
an objective, at most six key visible facts, at most four concrete risks, and
one recommended next action type with an optional currently visible supplier.
Do not infer evaluator checkpoints, oracle obligations, hidden suppliers,
future events, or unrevealed quotes. Treat changed requirements, amendments,
withdrawals, non-response, quote revisions, eligibility, compliance, budget,
delivery, and award scope as relevant only when visibly supported."""

    ACTION_PROMPT = """You are the action-selection pass for LongProcureBench.
Choose exactly one next semantic procurement action using the current visible
state and the fresh external deliberation record. The deliberation is advice,
not an oracle; correct it when it conflicts with visible facts.

Use only visible facts. Do not assume hidden suppliers, future events, evaluator
state, oracle answers, or unrevealed quotes.

Action contract:
- request_buyer_clarification, identify_suppliers, issue_amendment,
  evaluate_quotes, and no_award require supplier_id = null.
- send_rfq, send_follow_up, answer_supplier_question, and
  request_quote_revision require a currently visible supplier_id.
- award_supplier requires arguments.awards to be a non-empty list. Each award
  must contain exactly scope, supplier_id, and quote_event_id. scope must be
  one of the allowed award-scope values. quote_event_id must refer to a
  revealed quote/revision from that supplier and cover the award scope.
- no_award may use arguments.reason.
- For every non-award action set arguments.awards = null.
- When reason is irrelevant set arguments.reason = null.

Return only the structured action."""

    VERIFIER_PROMPT = """You are an independent pre-terminal procurement
verifier. Check the proposed award_supplier or no_award decision against only
the supplied current visible state.

Approve only when the proposed terminal decision is supported by visible facts
and there is no visible reason to continue procurement first. Check generic
visible-state concerns such as changed requirements/amendments, supplier
withdrawal or non-response, unanswered supplier questions, quote revisions,
scope coverage, eligibility/compliance, budget, delivery, and whether a
terminal no-award is actually supported. Do not use evaluator checkpoints,
hidden obligations, future events, oracle answers, or unrevealed information.

If rejecting, identify at most four concise visible issues and recommend one
NON-TERMINAL next action type, plus a currently visible supplier when needed.
This is a structured external critique, not private chain-of-thought."""

    REPAIR_PROMPT = """The independent verifier rejected a proposed terminal
decision. Choose exactly one NON-TERMINAL procurement action that addresses
the verifier feedback using only the current visible state. Do not return
award_supplier or no_award. Do not assume hidden or future information."""

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
        self.policy_id = f"always-replan-verifier--{model}"
        self._planner_calls = 0
        self._action_calls = 0
        self._verifier_calls = 0
        self._verifier_rejections = 0
        self._repair_calls = 0
        self._deliberation_trace: list[dict[str, Any]] = []
        self._verification_trace: list[dict[str, Any]] = []

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._planner_calls = 0
        self._action_calls = 0
        self._verifier_calls = 0
        self._verifier_rejections = 0
        self._repair_calls = 0
        self._deliberation_trace = []
        self._verification_trace = []

    @staticmethod
    def _visible_supplier_ids(state: dict[str, Any]) -> set[str]:
        suppliers = state.get("visible_suppliers")
        if not isinstance(suppliers, list):
            return set()
        return {
            row["supplier_id"]
            for row in suppliers
            if isinstance(row, dict)
            and isinstance(row.get("supplier_id"), str)
        }

    @staticmethod
    def _bounded_strings(
        values: Any,
        *,
        name: str,
        maximum_items: int,
        maximum_chars: int,
    ) -> None:
        if not isinstance(values, list) or len(values) > maximum_items:
            raise DeliberationProtocolError(
                f"{name} must contain at most {maximum_items} items"
            )
        for value in values:
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > maximum_chars
            ):
                raise DeliberationProtocolError(
                    f"{name} entries must be 1-{maximum_chars} characters"
                )

    def _validate_supplier_reference(
        self,
        supplier_id: Any,
        state: dict[str, Any],
    ) -> None:
        if supplier_id is None:
            return
        if supplier_id not in self._visible_supplier_ids(state):
            raise DeliberationProtocolError(
                f"Structured deliberation references non-visible supplier: {supplier_id}"
            )

    def _validate_plan(
        self,
        plan: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        objective = plan["objective"]
        if (
            not isinstance(objective, str)
            or not objective.strip()
            or len(objective) > 240
        ):
            raise DeliberationProtocolError(
                "objective must be 1-240 characters"
            )
        self._bounded_strings(
            plan["key_facts"],
            name="key_facts",
            maximum_items=6,
            maximum_chars=220,
        )
        self._bounded_strings(
            plan["risks"],
            name="risks",
            maximum_items=4,
            maximum_chars=220,
        )
        self._validate_supplier_reference(plan["supplier_id"], state)

    def _validate_verification(
        self,
        verdict: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        self._bounded_strings(
            verdict["issues"],
            name="issues",
            maximum_items=4,
            maximum_chars=240,
        )
        self._validate_supplier_reference(verdict["supplier_id"], state)
        if not verdict["approve"]:
            if verdict["recommended_action_type"] in TERMINAL_ACTIONS:
                raise DeliberationProtocolError(
                    "Rejected terminal decision must recommend a non-terminal action"
                )

    @classmethod
    def _nonterminal_action_schema(cls, state: dict[str, Any]) -> dict[str, Any]:
        schema = cls._action_schema(state)
        schema["properties"]["type"]["enum"] = deepcopy(NONTERMINAL_ACTIONS)
        return schema

    def _call(
        self,
        *,
        role: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        started = perf_counter()
        try:
            response, metrics = self._client.generate_action(
                messages=messages,
                action_schema=schema,
            )
        except ModelCallError as exc:
            row = deepcopy(exc.metrics)
            row["call_role"] = role
            self._calls.append(row)
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
                "call_role": role,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            })
            raise

        normalized = deepcopy(metrics)
        normalized.setdefault("success", True)
        normalized.setdefault("usage_available", True)
        normalized.setdefault("error", None)
        normalized["call_role"] = role
        self._calls.append(normalized)
        Draft202012Validator(schema).validate(response)
        return response

    def _fresh_plan(
        self,
        state: dict[str, Any],
        prompt_state: dict[str, Any],
    ) -> dict[str, Any]:
        self._planner_calls += 1
        plan = self._call(
            role="planner",
            messages=[
                {"role": "system", "content": self.PLANNER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Current agent-visible benchmark state:\n"
                        + json.dumps(prompt_state, sort_keys=True)
                    ),
                },
            ],
            schema=deepcopy(PLAN_SCHEMA),
        )
        self._validate_plan(plan, state)
        self._deliberation_trace.append({
            "state_step": state.get("step"),
            "plan": deepcopy(plan),
        })
        return plan

    def _select_action(
        self,
        state: dict[str, Any],
        prompt_state: dict[str, Any],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        self._action_calls += 1
        allowed_scopes = self._allowed_award_scopes(state)
        decision = self._call(
            role="action",
            messages=[
                {"role": "system", "content": self.ACTION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Allowed award scope values this episode: "
                        + ", ".join(allowed_scopes)
                        + "\n\nFresh external deliberation:\n"
                        + json.dumps(plan, sort_keys=True)
                        + "\n\nCurrent agent-visible benchmark state:\n"
                        + json.dumps(prompt_state, sort_keys=True)
                    ),
                },
            ],
            schema=self._action_schema(state),
        )
        return self._runtime_decision(decision)

    def _verify_terminal(
        self,
        state: dict[str, Any],
        prompt_state: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        self._verifier_calls += 1
        verdict = self._call(
            role="verifier",
            messages=[
                {"role": "system", "content": self.VERIFIER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Proposed terminal decision:\n"
                        + json.dumps(decision, sort_keys=True)
                        + "\n\nCurrent agent-visible benchmark state:\n"
                        + json.dumps(prompt_state, sort_keys=True)
                    ),
                },
            ],
            schema=deepcopy(VERIFIER_SCHEMA),
        )
        self._validate_verification(verdict, state)
        self._verification_trace.append({
            "state_step": state.get("step"),
            "proposed_action": deepcopy(decision),
            "verdict": deepcopy(verdict),
        })
        return verdict

    def _repair_action(
        self,
        state: dict[str, Any],
        prompt_state: dict[str, Any],
        plan: dict[str, Any],
        verdict: dict[str, Any],
    ) -> dict[str, Any]:
        self._repair_calls += 1
        repaired = self._call(
            role="repair_action",
            messages=[
                {"role": "system", "content": self.REPAIR_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Fresh external deliberation:\n"
                        + json.dumps(plan, sort_keys=True)
                        + "\n\nVerifier feedback:\n"
                        + json.dumps(verdict, sort_keys=True)
                        + "\n\nCurrent agent-visible benchmark state:\n"
                        + json.dumps(prompt_state, sort_keys=True)
                    ),
                },
            ],
            schema=self._nonterminal_action_schema(state),
        )
        return self._runtime_decision(repaired)

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt_state = compile_visible_state(state)
        plan = self._fresh_plan(state, prompt_state)
        decision = self._select_action(state, prompt_state, plan)

        if decision.get("type") not in TERMINAL_ACTIONS:
            return decision

        verdict = self._verify_terminal(
            state,
            prompt_state,
            decision,
        )
        if verdict["approve"]:
            return decision

        self._verifier_rejections += 1
        return self._repair_action(
            state,
            prompt_state,
            plan,
            verdict,
        )

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        metadata.update({
            "state_strategy": self.state_strategy,
            "planner_calls": self._planner_calls,
            "action_calls": self._action_calls,
            "verifier_calls": self._verifier_calls,
            "verifier_rejections": self._verifier_rejections,
            "repair_calls": self._repair_calls,
            "deliberation_trace": deepcopy(self._deliberation_trace),
            "verification_trace": deepcopy(self._verification_trace),
        })
        return metadata
