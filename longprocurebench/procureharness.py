"""ProcureHarness architecture-search controller v0.1.

The controller implements the frozen obligation-centric architecture grammar
without adding memory, knowledge graphs, forecasting, model routing, multi-agent
or checkpoint-rehydration features.

Only agent-visible factual_compiled_v0.1 state is consumed. Clear obligations
are handled through deterministic forced transitions; model calls are reserved
for ambiguous routing, bounded local planning, skill reasoning, terminal
critique, and bounded fallback according to the candidate configuration.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
from time import perf_counter
from typing import Any, Iterable

from .context_compiled_reactive import compile_visible_state
from .litellm_client import ModelCallError
from .reactive_llm import ReactiveLLMPolicy


class ProcureHarnessProtocolError(RuntimeError):
    """Candidate or controller behavior violated the frozen protocol."""


PROCUREMENT_SKILLS = (
    "resolve_requirement_gap",
    "supplier_discovery",
    "rfq_coverage",
    "nonresponse_followup",
    "supplier_question_handling",
    "amendment_handling",
    "quote_revision",
    "withdrawal_recovery",
    "quote_leveling",
    "terminal_decision",
)

ROUTING_CHOICES = ("deterministic_priority", "hybrid_llm_tiebreak")
PLANNING_CHOICES = ("none", "bounded_local_plan")
REASONING_CHOICES = ("direct_action", "bounded_mini_react")
VERIFICATION_CHOICES = (
    "none",
    "deterministic_visible_invariants",
    "single_terminal_llm_critique",
)
FALLBACK_CHOICES = ("none", "bounded_react_fallback")

MAX_MODEL_CALLS_BETWEEN_ACCEPTED_ACTIONS = 3
MAX_LOCAL_PLAN_STEPS = 4
MAX_REACT_FALLBACK_ACTIONS = 3

EVENT_SKILL_MAP = {
    "supplier_non_response": "nonresponse_followup",
    "supplier_question": "supplier_question_handling",
    "requirement_change": "amendment_handling",
    "quantity_change": "amendment_handling",
    "substitution_proposed": "quote_revision",
    "supplier_withdrawal": "withdrawal_recovery",
}

SKILL_ACTION_TYPES = {
    "resolve_requirement_gap": ("request_buyer_clarification",),
    "supplier_discovery": ("identify_suppliers",),
    "rfq_coverage": ("send_rfq",),
    "nonresponse_followup": ("send_follow_up",),
    "supplier_question_handling": ("answer_supplier_question",),
    "amendment_handling": ("issue_amendment",),
    "quote_revision": ("request_quote_revision",),
    "withdrawal_recovery": (
        "request_quote_revision",
        "send_rfq",
        "evaluate_quotes",
        "no_award",
    ),
    "quote_leveling": ("evaluate_quotes",),
    "terminal_decision": ("award_supplier", "no_award"),
}

FORCED_SKILLS = {
    "resolve_requirement_gap",
    "supplier_discovery",
    "rfq_coverage",
    "nonresponse_followup",
    "supplier_question_handling",
    "amendment_handling",
    "withdrawal_recovery",
    "quote_leveling",
}

PRIORITY = {
    "amendment_handling": 10,
    "supplier_question_handling": 20,
    "nonresponse_followup": 20,
    "withdrawal_recovery": 25,
    "resolve_requirement_gap": 30,
    "supplier_discovery": 40,
    "rfq_coverage": 50,
    "quote_revision": 60,
    "quote_leveling": 70,
    "terminal_decision": 90,
}


@dataclass(frozen=True)
class ProcureHarnessConfig:
    candidate_id: str
    round: int
    obligation_routing: str
    local_planning: str
    skill_reasoning: str
    verification: str
    fallback: str

    def validate(self) -> None:
        if self.round not in (1, 2, 3):
            raise ProcureHarnessProtocolError("candidate round must be 1, 2, or 3")
        if self.obligation_routing not in ROUTING_CHOICES:
            raise ProcureHarnessProtocolError("invalid obligation_routing")
        if self.local_planning not in PLANNING_CHOICES:
            raise ProcureHarnessProtocolError("invalid local_planning")
        if self.skill_reasoning not in REASONING_CHOICES:
            raise ProcureHarnessProtocolError("invalid skill_reasoning")
        if self.verification not in VERIFICATION_CHOICES:
            raise ProcureHarnessProtocolError("invalid verification")
        if self.fallback not in FALLBACK_CHOICES:
            raise ProcureHarnessProtocolError("invalid fallback")


CANDIDATE_CONFIGS = (
    ProcureHarnessConfig("ph-r1-c01", 1, "deterministic_priority", "none", "direct_action", "none", "none"),
    ProcureHarnessConfig("ph-r1-c02", 1, "deterministic_priority", "none", "direct_action", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r1-c03", 1, "hybrid_llm_tiebreak", "none", "direct_action", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r1-c04", 1, "deterministic_priority", "bounded_local_plan", "direct_action", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r1-c05", 1, "deterministic_priority", "none", "bounded_mini_react", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r1-c06", 1, "deterministic_priority", "none", "direct_action", "single_terminal_llm_critique", "none"),

    ProcureHarnessConfig("ph-r2-c07", 2, "deterministic_priority", "none", "direct_action", "deterministic_visible_invariants", "bounded_react_fallback"),
    ProcureHarnessConfig("ph-r2-c08", 2, "hybrid_llm_tiebreak", "bounded_local_plan", "direct_action", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r2-c09", 2, "hybrid_llm_tiebreak", "none", "bounded_mini_react", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r2-c10", 2, "deterministic_priority", "bounded_local_plan", "bounded_mini_react", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r2-c11", 2, "hybrid_llm_tiebreak", "none", "direct_action", "single_terminal_llm_critique", "none"),
    ProcureHarnessConfig("ph-r2-c12", 2, "hybrid_llm_tiebreak", "none", "direct_action", "deterministic_visible_invariants", "bounded_react_fallback"),

    ProcureHarnessConfig("ph-r3-c13", 3, "deterministic_priority", "bounded_local_plan", "direct_action", "single_terminal_llm_critique", "none"),
    ProcureHarnessConfig("ph-r3-c14", 3, "deterministic_priority", "none", "bounded_mini_react", "single_terminal_llm_critique", "none"),
    ProcureHarnessConfig("ph-r3-c15", 3, "deterministic_priority", "bounded_local_plan", "direct_action", "deterministic_visible_invariants", "bounded_react_fallback"),
    ProcureHarnessConfig("ph-r3-c16", 3, "hybrid_llm_tiebreak", "bounded_local_plan", "bounded_mini_react", "deterministic_visible_invariants", "none"),
    ProcureHarnessConfig("ph-r3-c17", 3, "hybrid_llm_tiebreak", "none", "bounded_mini_react", "deterministic_visible_invariants", "bounded_react_fallback"),
    ProcureHarnessConfig("ph-r3-c18", 3, "hybrid_llm_tiebreak", "bounded_local_plan", "bounded_mini_react", "single_terminal_llm_critique", "none"),
)

CANDIDATES_BY_ID = {config.candidate_id: config for config in CANDIDATE_CONFIGS}


def candidate_registry() -> list[dict[str, Any]]:
    return [asdict(config) for config in CANDIDATE_CONFIGS]


def validate_candidate_registry() -> None:
    if len(CANDIDATE_CONFIGS) != 18:
        raise ProcureHarnessProtocolError("frozen registry must contain 18 candidates")
    ids = [config.candidate_id for config in CANDIDATE_CONFIGS]
    if len(ids) != len(set(ids)):
        raise ProcureHarnessProtocolError("candidate IDs must be unique")
    for config in CANDIDATE_CONFIGS:
        config.validate()
    for round_id in (1, 2, 3):
        rows = [c for c in CANDIDATE_CONFIGS if c.round == round_id]
        if len(rows) != 6:
            raise ProcureHarnessProtocolError(
                "each frozen search round must contain exactly six candidates"
            )

    dimensions = {
        "obligation_routing": {c.obligation_routing for c in CANDIDATE_CONFIGS},
        "local_planning": {c.local_planning for c in CANDIDATE_CONFIGS},
        "skill_reasoning": {c.skill_reasoning for c in CANDIDATE_CONFIGS},
        "verification": {c.verification for c in CANDIDATE_CONFIGS},
        "fallback": {c.fallback for c in CANDIDATE_CONFIGS},
    }
    expected = {
        "obligation_routing": set(ROUTING_CHOICES),
        "local_planning": set(PLANNING_CHOICES),
        "skill_reasoning": set(REASONING_CHOICES),
        "verification": set(VERIFICATION_CHOICES),
        "fallback": set(FALLBACK_CHOICES),
    }
    if dimensions != expected:
        raise ProcureHarnessProtocolError(
            "candidate registry must cover every frozen architecture choice"
        )


def get_candidate(candidate_id: str) -> ProcureHarnessConfig:
    try:
        config = CANDIDATES_BY_ID[candidate_id]
    except KeyError as exc:
        raise ProcureHarnessProtocolError(
            f"unknown ProcureHarness candidate: {candidate_id}"
        ) from exc
    config.validate()
    return config


def _history(compiled: dict[str, Any]) -> list[dict[str, Any]]:
    rows = compiled.get("action_history")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _events(compiled: dict[str, Any]) -> list[dict[str, Any]]:
    rows = compiled.get("event_history")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _visible_supplier_ids(compiled: dict[str, Any]) -> list[str]:
    rows = compiled.get("visible_suppliers")
    if not isinstance(rows, list):
        return []
    return sorted({
        row.get("supplier_id")
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("supplier_id"), str)
        and row.get("supplier_id")
    })


def _current_offer_ids(compiled: dict[str, Any]) -> set[str]:
    rows = compiled.get("latest_offers")
    if not isinstance(rows, list):
        return set()
    return {
        row.get("event_id")
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("event_id"), str)
    }


def _withdrawn_supplier_ids(compiled: dict[str, Any]) -> set[str]:
    return {
        event.get("supplier_id")
        for event in _events(compiled)
        if event.get("type") == "supplier_withdrawal"
        and isinstance(event.get("supplier_id"), str)
    }


def _details_show_visible_noncompliance(details: Any) -> bool:
    """Conservative deterministic check over already visible structured facts."""
    if not isinstance(details, dict):
        return False
    for key, value in details.items():
        normalized = str(key).lower()
        if isinstance(value, bool) and value is False and (
            normalized.startswith("meets_")
            or normalized.startswith("includes_")
            or normalized.startswith("approved_")
            or normalized in {"compliant", "eligible", "qualification_met"}
        ):
            return True
    return False


class ProcureHarnessPolicy(ReactiveLLMPolicy):
    """Obligation-centric skill-graph policy assembled from a frozen config."""

    policy_kind = "procureharness_architecture_candidate"
    agent_pattern = "event_driven_obligation_centric_hierarchical_skill_graph_v0.1"
    context_strategy = "factual_compiled_v0.1"

    ROUTER_SYSTEM_PROMPT = """You are the routing tie-breaker inside ProcureHarness.
Use only the supplied agent-visible candidate obligations and factual state.
Choose one candidate_id from the provided list. Do not invent hidden facts,
future events, evaluator labels, or oracle information."""

    PLAN_SYSTEM_PROMPT = """You are a bounded local procurement planner.
Use only the supplied factual agent-visible state and available procurement
skills. Return at most four local skill steps. The plan is advisory and must not
invent suppliers, quotes, hidden constraints, future events, evaluator labels,
or oracle information."""

    ACTION_SYSTEM_PROMPT = """You are executing one selected ProcureHarness
procurement skill. Use only the supplied factual agent-visible state, selected
skill, visible suppliers, and revealed offers/events. Choose a semantically
valid benchmark action. Never use hidden supplier profiles, future events,
oracle data, evaluator labels, or episode-specific hard-coded rules."""

    MINI_REACT_SYSTEM_PROMPT = """You are executing one selected ProcureHarness
skill with a bounded mini-ReAct step. Produce a short thought_summary grounded
only in visible facts, followed by one semantic action. Do not reveal or assume
hidden supplier profiles, future events, oracle data, or evaluator labels."""

    CRITIQUE_SYSTEM_PROMPT = """You are a single terminal verifier for
ProcureHarness. Check the proposed terminal action only against agent-visible
facts. Return approve=true when it is supportable. If approve=false, provide a
replacement terminal action using only visible suppliers and revealed quotes.
Do not use oracle/evaluator information."""

    FALLBACK_SYSTEM_PROMPT = """You are the bounded ProcureHarness ReAct
fallback. The prior proposed action failed a visible-state/controller check.
Choose one safe next semantic action from the current visible state. Do not use
hidden facts, future events, oracle data, or evaluator labels."""

    def __init__(
        self,
        model: str,
        *,
        config: ProcureHarnessConfig | str,
        client=None,
        temperature: float | None = None,
        reasoning_effort: str | None = "medium",
    ):
        config_obj = get_candidate(config) if isinstance(config, str) else config
        config_obj.validate()
        super().__init__(
            model,
            client=client,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )
        self.config = config_obj
        self.policy_id = f"procureharness--{config_obj.candidate_id}--{model}"
        self._reset_controller()

    def _reset_controller(self) -> None:
        self._seen_event_ids: set[str] = set()
        self._handled_event_ids: set[str] = set()
        self._pending_event_skills: dict[str, dict[str, Any]] = {}
        self._last_evaluated_offer_ids: set[str] = set()
        self._fallback_actions_used = 0
        self._calls_between_actions = 0
        self._max_calls_between_actions_observed = 0
        self._accepted_actions_seen = 0
        self._deterministic_actions_accepted = 0
        self._model_actions_accepted = 0
        self._fallback_actions_accepted = 0
        self._skill_counts: dict[str, int] = {}
        self._call_purposes: dict[str, int] = {}
        self._local_plan_history: list[dict[str, Any]] = []
        self._pending_meta: dict[str, Any] | None = None
        self._pending_compiled: dict[str, Any] | None = None

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._reset_controller()

    def _record_model_metrics(
        self,
        metrics: dict[str, Any],
        *,
        purpose: str,
        error: Exception | None = None,
    ) -> None:
        normalized = deepcopy(metrics)
        normalized.setdefault("model", self.model)
        normalized["success"] = error is None and bool(
            normalized.get("success", True)
        )
        normalized.setdefault("usage_available", True)
        if error is not None:
            normalized["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        else:
            normalized.setdefault("error", None)
        normalized["procureharness_call_purpose"] = purpose
        self._calls.append(normalized)
        self._call_purposes[purpose] = self._call_purposes.get(purpose, 0) + 1

    def _model_json(
        self,
        *,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        purpose: str,
    ) -> dict[str, Any]:
        self._calls_between_actions += 1
        self._max_calls_between_actions_observed = max(
            self._max_calls_between_actions_observed,
            self._calls_between_actions,
        )
        if self._calls_between_actions > MAX_MODEL_CALLS_BETWEEN_ACCEPTED_ACTIONS:
            raise ProcureHarnessProtocolError(
                "candidate exceeded max_model_calls_between_accepted_actions=3"
            )

        started = perf_counter()
        try:
            decision, metrics = self._client.generate_action(
                messages=messages,
                action_schema=schema,
            )
        except ModelCallError as exc:
            self._record_model_metrics(
                exc.metrics,
                purpose=purpose,
                error=exc,
            )
            raise
        except Exception as exc:
            self._record_model_metrics(
                {
                    "model": self.model,
                    "latency_ms": (perf_counter() - started) * 1000.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": None,
                    "usage_available": False,
                },
                purpose=purpose,
                error=exc,
            )
            raise
        self._record_model_metrics(metrics, purpose=purpose)
        return deepcopy(decision)

    @staticmethod
    def _candidate(
        *,
        skill: str,
        supplier_id: str | None,
        reason: str,
        forced: bool,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "candidate_id": (
                f"{skill}:{supplier_id or '-'}:{event_id or '-'}"
            ),
            "skill": skill,
            "supplier_id": supplier_id,
            "reason": reason,
            "forced": forced,
            "event_id": event_id,
            "priority": PRIORITY[skill],
        }

    def _ingest_new_events(self, compiled: dict[str, Any]) -> None:
        for event in _events(compiled):
            event_id = event.get("event_id")
            if (
                not isinstance(event_id, str)
                or not event_id
                or event_id in self._seen_event_ids
            ):
                continue
            self._seen_event_ids.add(event_id)
            skill = EVENT_SKILL_MAP.get(event.get("type"))
            if skill is None:
                continue
            self._pending_event_skills[event_id] = self._candidate(
                skill=skill,
                supplier_id=(
                    event.get("supplier_id")
                    if isinstance(event.get("supplier_id"), str)
                    else None
                ),
                reason=f"visible event {event.get('type')} requires {skill}",
                forced=skill in FORCED_SKILLS,
                event_id=event_id,
            )

    @staticmethod
    def _has_requirement_gap(compiled: dict[str, Any]) -> bool:
        initial = compiled.get("initial_state")
        if not isinstance(initial, dict):
            return False
        rows = initial.get("operational_missing_information")
        return isinstance(rows, list) and bool(rows)

    @staticmethod
    def _action_types(history: list[dict[str, Any]]) -> list[str]:
        return [
            row.get("type")
            for row in history
            if isinstance(row.get("type"), str)
        ]

    def _offer_revision_candidates(
        self,
        compiled: dict[str, Any],
    ) -> list[dict[str, Any]]:
        out = []
        for offer in compiled.get("latest_offers") or []:
            if not isinstance(offer, dict):
                continue
            event_id = offer.get("event_id")
            if (
                isinstance(event_id, str)
                and event_id in self._handled_event_ids
            ):
                continue
            supplier_id = offer.get("supplier_id")
            if (
                isinstance(supplier_id, str)
                and _details_show_visible_noncompliance(
                    offer.get("details")
                )
            ):
                out.append(self._candidate(
                    skill="quote_revision",
                    supplier_id=supplier_id,
                    reason="latest visible offer has explicit structured noncompliance",
                    forced=False,
                    event_id=offer.get("event_id"),
                ))
        return out

    def _withdrawal_recovery_candidate(
        self,
        pending: dict[str, Any],
        compiled: dict[str, Any],
    ) -> dict[str, Any]:
        withdrawn = _withdrawn_supplier_ids(compiled)
        active = [
            supplier_id
            for supplier_id in _visible_supplier_ids(compiled)
            if supplier_id not in withdrawn
        ]
        offers = {
            row.get("supplier_id"): row
            for row in (compiled.get("latest_offers") or [])
            if isinstance(row, dict)
            and isinstance(row.get("supplier_id"), str)
            and row.get("supplier_id") not in withdrawn
        }
        supplier_id = next(
            (sid for sid in active if sid in offers),
            next(iter(active), None),
        )
        return {
            **pending,
            "supplier_id": supplier_id,
            "candidate_id": (
                f"withdrawal_recovery:{supplier_id or '-'}:"
                f"{pending.get('event_id') or '-'}"
            ),
        }

    def _build_candidates(
        self,
        compiled: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self._ingest_new_events(compiled)
        history = _history(compiled)
        action_types = self._action_types(history)
        visible_suppliers = _visible_supplier_ids(compiled)

        out: list[dict[str, Any]] = []

        for event_id, pending in self._pending_event_skills.items():
            if event_id in self._handled_event_ids:
                continue
            if pending["skill"] == "withdrawal_recovery":
                out.append(
                    self._withdrawal_recovery_candidate(
                        pending,
                        compiled,
                    )
                )
            else:
                out.append(deepcopy(pending))

        if (
            self._has_requirement_gap(compiled)
            and "request_buyer_clarification" not in action_types
        ):
            out.append(self._candidate(
                skill="resolve_requirement_gap",
                supplier_id=None,
                reason="public starting state contains operational missing information",
                forced=True,
            ))

        if not visible_suppliers and "identify_suppliers" not in action_types:
            out.append(self._candidate(
                skill="supplier_discovery",
                supplier_id=None,
                reason="supplier directory is not yet visible",
                forced=True,
            ))

        if visible_suppliers:
            solicited = {
                row.get("supplier_id")
                for row in history
                if row.get("type") == "send_rfq"
                and isinstance(row.get("supplier_id"), str)
            }
            withdrawn = _withdrawn_supplier_ids(compiled)
            for supplier_id in visible_suppliers:
                if (
                    supplier_id not in solicited
                    and supplier_id not in withdrawn
                ):
                    out.append(self._candidate(
                        skill="rfq_coverage",
                        supplier_id=supplier_id,
                        reason="visible supplier has not received an RFQ",
                        forced=True,
                    ))

        out.extend(self._offer_revision_candidates(compiled))

        offer_ids = _current_offer_ids(compiled)
        pending_urgent = any(
            row["priority"] < PRIORITY["quote_leveling"]
            for row in out
        )
        if (
            len(offer_ids) >= 2
            and offer_ids != self._last_evaluated_offer_ids
            and not pending_urgent
        ):
            out.append(self._candidate(
                skill="quote_leveling",
                supplier_id=None,
                reason="current revealed offer set has not been evaluated",
                forced=True,
            ))

        if (
            offer_ids
            and offer_ids == self._last_evaluated_offer_ids
            and not out
        ):
            out.append(self._candidate(
                skill="terminal_decision",
                supplier_id=None,
                reason="current revealed offers have been leveled and no visible obligation remains",
                forced=False,
            ))

        deduped = {}
        for row in out:
            deduped[row["candidate_id"]] = row
        return sorted(
            deduped.values(),
            key=lambda row: (
                row["priority"],
                row["skill"],
                row.get("supplier_id") or "",
                row.get("event_id") or "",
            ),
        )

    def _routing_schema(
        self,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "candidate_id": {
                    "type": "string",
                    "enum": [row["candidate_id"] for row in candidates],
                },
            },
            "required": ["candidate_id"],
        }

    def _route_candidate(
        self,
        compiled: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], str]:
        if not candidates:
            raise ProcureHarnessProtocolError("router has no available skill candidate")
        min_priority = min(row["priority"] for row in candidates)
        frontier = [
            row for row in candidates
            if row["priority"] == min_priority
        ]

        forced = [row for row in frontier if row["forced"]]
        if forced:
            return deepcopy(forced[0]), "deterministic_forced_transition"

        if (
            self.config.obligation_routing == "hybrid_llm_tiebreak"
            and len(frontier) > 1
        ):
            decision = self._model_json(
                messages=[
                    {"role": "system", "content": self.ROUTER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps({
                            "candidate_obligations": frontier,
                            "factual_visible_state": compiled,
                        }, sort_keys=True),
                    },
                ],
                schema=self._routing_schema(frontier),
                purpose="obligation_routing",
            )
            selected = decision.get("candidate_id")
            for row in frontier:
                if row["candidate_id"] == selected:
                    return deepcopy(row), "hybrid_llm_tiebreak"
            raise ProcureHarnessProtocolError(
                "routing model selected an unknown candidate"
            )

        return deepcopy(frontier[0]), "deterministic_priority"

    def _plan_schema(
        self,
        candidate_skills: Iterable[str],
    ) -> dict[str, Any]:
        skills = sorted(set(candidate_skills))
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_LOCAL_PLAN_STEPS,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "skill": {
                                "type": "string",
                                "enum": skills,
                            },
                            "supplier_id": {
                                "type": ["string", "null"],
                            },
                            "objective": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 300,
                            },
                        },
                        "required": [
                            "skill",
                            "supplier_id",
                            "objective",
                        ],
                    },
                },
            },
            "required": ["steps"],
        }

    def _bounded_plan(
        self,
        compiled: dict[str, Any],
        selected: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if self.config.local_planning == "none" or selected["forced"]:
            return None

        allowed_skills = {
            row["skill"] for row in candidates
        } | {selected["skill"]}
        plan = self._model_json(
            messages=[
                {"role": "system", "content": self.PLAN_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({
                        "selected_obligation": selected,
                        "available_skills": sorted(allowed_skills),
                        "factual_visible_state": compiled,
                    }, sort_keys=True),
                },
            ],
            schema=self._plan_schema(allowed_skills),
            purpose="local_planning",
        )
        steps = plan.get("steps")
        if not isinstance(steps, list) or not (1 <= len(steps) <= MAX_LOCAL_PLAN_STEPS):
            raise ProcureHarnessProtocolError("local plan violates max_local_plan_steps=4")
        self._local_plan_history.append(deepcopy(plan))
        return plan

    def _restricted_action_schema(
        self,
        state: dict[str, Any],
        skill: str,
    ) -> dict[str, Any]:
        schema = self._action_schema(state)
        schema["properties"]["type"]["enum"] = list(SKILL_ACTION_TYPES[skill])
        return schema

    def _mini_react_schema(
        self,
        state: dict[str, Any],
        skill: str,
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "thought_summary": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 800,
                },
                "action": self._restricted_action_schema(state, skill),
            },
            "required": ["thought_summary", "action"],
        }

    def _deterministic_action(
        self,
        selected: dict[str, Any],
        compiled: dict[str, Any],
    ) -> dict[str, Any] | None:
        skill = selected["skill"]
        supplier_id = selected.get("supplier_id")
        if skill == "resolve_requirement_gap":
            return {"type": "request_buyer_clarification", "supplier_id": None, "arguments": {}}
        if skill == "supplier_discovery":
            return {"type": "identify_suppliers", "supplier_id": None, "arguments": {}}
        if skill == "rfq_coverage":
            return {"type": "send_rfq", "supplier_id": supplier_id, "arguments": {}}
        if skill == "nonresponse_followup":
            return {"type": "send_follow_up", "supplier_id": supplier_id, "arguments": {}}
        if skill == "supplier_question_handling":
            return {"type": "answer_supplier_question", "supplier_id": supplier_id, "arguments": {}}
        if skill == "amendment_handling":
            return {"type": "issue_amendment", "supplier_id": None, "arguments": {}}
        if skill == "quote_revision":
            return {"type": "request_quote_revision", "supplier_id": supplier_id, "arguments": {}}
        if skill == "quote_leveling":
            return {"type": "evaluate_quotes", "supplier_id": None, "arguments": {}}
        if skill == "withdrawal_recovery":
            if isinstance(supplier_id, str):
                offer_suppliers = {
                    row.get("supplier_id")
                    for row in (compiled.get("latest_offers") or [])
                    if isinstance(row, dict)
                }
                if supplier_id in offer_suppliers:
                    return {
                        "type": "request_quote_revision",
                        "supplier_id": supplier_id,
                        "arguments": {},
                    }
                return {
                    "type": "send_rfq",
                    "supplier_id": supplier_id,
                    "arguments": {},
                }
            return None
        return None

    def _reasoned_action(
        self,
        state: dict[str, Any],
        compiled: dict[str, Any],
        selected: dict[str, Any],
        plan: dict[str, Any] | None,
    ) -> dict[str, Any]:
        skill = selected["skill"]
        payload = {
            "selected_skill": skill,
            "selected_obligation": selected,
            "local_plan": plan,
            "factual_visible_state": compiled,
        }
        if self.config.skill_reasoning == "bounded_mini_react":
            result = self._model_json(
                messages=[
                    {"role": "system", "content": self.MINI_REACT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(payload, sort_keys=True),
                    },
                ],
                schema=self._mini_react_schema(state, skill),
                purpose="skill_reasoning_mini_react",
            )
            action = result.get("action")
            if not isinstance(action, dict):
                raise ProcureHarnessProtocolError("mini-ReAct did not return an action")
            return self._runtime_decision(action)

        decision = self._model_json(
            messages=[
                {"role": "system", "content": self.ACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, sort_keys=True),
                },
            ],
            schema=self._restricted_action_schema(state, skill),
            purpose="skill_reasoning_direct",
        )
        return self._runtime_decision(decision)

    @staticmethod
    def _visible_current_quotes(
        compiled: dict[str, Any],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        out = {}
        for row in compiled.get("latest_offers") or []:
            if not isinstance(row, dict):
                continue
            supplier = row.get("supplier_id")
            event_id = row.get("event_id")
            if isinstance(supplier, str) and isinstance(event_id, str):
                out[(supplier, event_id)] = row
        return out

    def _basic_visible_validation(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
        compiled: dict[str, Any],
        selected: dict[str, Any],
    ) -> tuple[bool, str]:
        action_type = action.get("type")
        if action_type not in SKILL_ACTION_TYPES[selected["skill"]]:
            return False, "action type is outside selected skill contract"

        visible_suppliers = set(_visible_supplier_ids(compiled))
        supplier_id = action.get("supplier_id")
        if action_type in {
            "send_rfq",
            "send_follow_up",
            "answer_supplier_question",
            "request_quote_revision",
        }:
            if supplier_id not in visible_suppliers:
                return False, "supplier action references a non-visible supplier"

        if action_type == "request_quote_revision":
            has_offer = any(
                row.get("supplier_id") == supplier_id
                for row in (compiled.get("latest_offers") or [])
                if isinstance(row, dict)
            ) or any(
                event.get("supplier_id") == supplier_id
                and event.get("type") == "substitution_proposed"
                for event in _events(compiled)
            )
            if not has_offer:
                return False, "quote revision lacks a revealed prior offer"

        if action_type == "award_supplier":
            awards = (action.get("arguments") or {}).get("awards")
            if not isinstance(awards, list) or not awards:
                return False, "award action lacks awards"
            current = self._visible_current_quotes(compiled)
            withdrawn = _withdrawn_supplier_ids(compiled)
            allowed_scopes = set(self._allowed_award_scopes(state))
            for award in awards:
                if not isinstance(award, dict):
                    return False, "award entry is not an object"
                key = (
                    award.get("supplier_id"),
                    award.get("quote_event_id"),
                )
                quote = current.get(key)
                if quote is None:
                    return False, "award references a stale or unrevealed quote"
                if award.get("supplier_id") in withdrawn:
                    return False, "award references a withdrawn supplier"
                if award.get("scope") not in allowed_scopes:
                    return False, "award scope is outside visible episode scopes"
                if _details_show_visible_noncompliance(quote.get("details")):
                    return False, "award quote has explicit visible noncompliance"

        return True, "visible-state action checks passed"

    def _deterministic_verify(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
        compiled: dict[str, Any],
        selected: dict[str, Any],
    ) -> tuple[bool, str]:
        return self._basic_visible_validation(
            action,
            state,
            compiled,
            selected,
        )

    def _critique_schema(
        self,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "approve": {"type": "boolean"},
                "concern": {
                    "type": ["string", "null"],
                },
                "replacement_action": self._restricted_action_schema(
                    state,
                    "terminal_decision",
                ),
            },
            "required": [
                "approve",
                "concern",
                "replacement_action",
            ],
        }

    def _terminal_critique(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
        compiled: dict[str, Any],
    ) -> dict[str, Any]:
        result = self._model_json(
            messages=[
                {"role": "system", "content": self.CRITIQUE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({
                        "proposed_terminal_action": action,
                        "factual_visible_state": compiled,
                    }, sort_keys=True),
                },
            ],
            schema=self._critique_schema(state),
            purpose="terminal_critique",
        )
        if result.get("approve") is True:
            return action
        replacement = result.get("replacement_action")
        if not isinstance(replacement, dict):
            raise ProcureHarnessProtocolError(
                "terminal critique rejected without replacement action"
            )
        return self._runtime_decision(replacement)

    def _fallback_action(
        self,
        *,
        state: dict[str, Any],
        compiled: dict[str, Any],
        selected: dict[str, Any],
        failed_action: dict[str, Any],
        failure_reason: str,
    ) -> dict[str, Any]:
        if self.config.fallback != "bounded_react_fallback":
            raise ProcureHarnessProtocolError(failure_reason)
        if self._fallback_actions_used >= MAX_REACT_FALLBACK_ACTIONS:
            raise ProcureHarnessProtocolError(
                "candidate exceeded max_react_fallback_actions=3"
            )
        decision = self._model_json(
            messages=[
                {"role": "system", "content": self.FALLBACK_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({
                        "selected_skill": selected["skill"],
                        "failed_action": failed_action,
                        "failure_reason": failure_reason,
                        "factual_visible_state": compiled,
                    }, sort_keys=True),
                },
            ],
            schema=self._action_schema(state),
            purpose="bounded_react_fallback",
        )
        self._fallback_actions_used += 1
        action = self._runtime_decision(decision)

        fallback_selected = {
            **selected,
            "skill": self._skill_for_action(action.get("type")),
        }
        ok, reason = self._basic_visible_validation(
            action,
            state,
            compiled,
            fallback_selected,
        )
        if not ok:
            raise ProcureHarnessProtocolError(
                f"fallback action failed visible-state validation: {reason}"
            )
        return action

    @staticmethod
    def _skill_for_action(action_type: str | None) -> str:
        matches = [
            skill
            for skill, actions in SKILL_ACTION_TYPES.items()
            if action_type in actions
        ]
        if not matches:
            raise ProcureHarnessProtocolError(
                f"action type has no ProcureHarness skill: {action_type}"
            )
        # Prefer the narrowest non-terminal skill when actions are shared.
        order = [
            "resolve_requirement_gap",
            "supplier_discovery",
            "rfq_coverage",
            "nonresponse_followup",
            "supplier_question_handling",
            "amendment_handling",
            "quote_revision",
            "withdrawal_recovery",
            "quote_leveling",
            "terminal_decision",
        ]
        return next(skill for skill in order if skill in matches)

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("terminated"):
            raise ProcureHarnessProtocolError("act() called after terminal state")

        self._calls_between_actions = 0
        compiled = compile_visible_state(state)
        candidates = self._build_candidates(compiled)
        selected, route_origin = self._route_candidate(
            compiled,
            candidates,
        )
        plan = self._bounded_plan(
            compiled,
            selected,
            candidates,
        )

        action = self._deterministic_action(selected, compiled)
        origin = "deterministic"
        if action is None:
            action = self._reasoned_action(
                state,
                compiled,
                selected,
                plan,
            )
            origin = "model"

        if self.config.verification == "deterministic_visible_invariants":
            ok, reason = self._deterministic_verify(
                action,
                state,
                compiled,
                selected,
            )
            if not ok:
                action = self._fallback_action(
                    state=state,
                    compiled=compiled,
                    selected=selected,
                    failed_action=action,
                    failure_reason=reason,
                )
                origin = "fallback"

        elif (
            self.config.verification == "single_terminal_llm_critique"
            and selected["skill"] == "terminal_decision"
        ):
            ok, reason = self._basic_visible_validation(
                action,
                state,
                compiled,
                selected,
            )
            if not ok:
                action = self._fallback_action(
                    state=state,
                    compiled=compiled,
                    selected=selected,
                    failed_action=action,
                    failure_reason=reason,
                )
                origin = "fallback"
            action = self._terminal_critique(
                action,
                state,
                compiled,
            )
            ok, reason = self._basic_visible_validation(
                action,
                state,
                compiled,
                selected,
            )
            if not ok:
                raise ProcureHarnessProtocolError(
                    f"terminal critique produced invalid action: {reason}"
                )

        else:
            ok, reason = self._basic_visible_validation(
                action,
                state,
                compiled,
                selected,
            )
            if not ok:
                action = self._fallback_action(
                    state=state,
                    compiled=compiled,
                    selected=selected,
                    failed_action=action,
                    failure_reason=reason,
                )
                origin = "fallback"

        self._pending_meta = {
            "skill": selected["skill"],
            "event_id": selected.get("event_id"),
            "origin": origin,
            "route_origin": route_origin,
            "model_calls_before_action": self._calls_between_actions,
        }
        self._pending_compiled = deepcopy(compiled)
        return deepcopy(action)

    def on_action_accepted(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        meta = self._pending_meta or {}
        skill = meta.get("skill")
        if isinstance(skill, str):
            self._skill_counts[skill] = self._skill_counts.get(skill, 0) + 1
        event_id = meta.get("event_id")
        if isinstance(event_id, str):
            self._handled_event_ids.add(event_id)

        self._accepted_actions_seen += 1
        origin = meta.get("origin")
        if origin == "deterministic":
            self._deterministic_actions_accepted += 1
        elif origin == "fallback":
            self._fallback_actions_accepted += 1
            self._model_actions_accepted += 1
        else:
            self._model_actions_accepted += 1

        if action.get("type") == "evaluate_quotes":
            compiled = compile_visible_state(state)
            self._last_evaluated_offer_ids = _current_offer_ids(compiled)

        self._pending_meta = None
        self._pending_compiled = None
        self._calls_between_actions = 0

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        accepted = self._accepted_actions_seen
        metadata.update({
            "agent_pattern": self.agent_pattern,
            "context_strategy": self.context_strategy,
            "procureharness_candidate": asdict(self.config),
            "required_core": [
                "obligation_router",
                "procurement_skill_graph",
                "event_interrupt_control",
                "deterministic_forced_transitions",
            ],
            "procurement_skills": list(PROCUREMENT_SKILLS),
            "accepted_actions_seen": accepted,
            "deterministic_actions_accepted": self._deterministic_actions_accepted,
            "model_actions_accepted": self._model_actions_accepted,
            "fallback_actions_accepted": self._fallback_actions_accepted,
            "deterministic_action_fraction": (
                self._deterministic_actions_accepted / accepted
                if accepted
                else 0.0
            ),
            "skill_counts": deepcopy(self._skill_counts),
            "model_call_purposes": deepcopy(self._call_purposes),
            "local_plan_count": len(self._local_plan_history),
            "max_model_calls_between_accepted_actions_observed": (
                self._max_calls_between_actions_observed
            ),
            "fallback_actions_used": self._fallback_actions_used,
            "hard_complexity_limits": {
                "max_model_calls_between_accepted_actions": (
                    MAX_MODEL_CALLS_BETWEEN_ACCEPTED_ACTIONS
                ),
                "max_local_plan_steps": MAX_LOCAL_PLAN_STEPS,
                "max_react_fallback_actions": MAX_REACT_FALLBACK_ACTIONS,
                "multi_agent": False,
                "persistent_cross_episode_memory": False,
            },
        })
        return metadata


validate_candidate_registry()
