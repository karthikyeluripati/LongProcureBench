"""State Validity Frontier controller for LongProcureBench.

This is the implementation of the protocol frozen in
docs/state-validity-frontier-v0.1-protocol.json.

The controller recomputes a structured validity graph from
factual_compiled_v0.1, invalidates only dependent workflow state when visible
facts change, exposes a minimal valid-action frontier, and uses the model only
when that frontier contains multiple legitimate choices.

It is a proposed method candidate, not a frozen successful method.
"""
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


REQUIREMENT_CHANGE_EVENTS = {
    "requirement_change",
    "quantity_change",
}
QUOTE_EVENTS = {
    "quote_received",
    "quote_revision",
}
REPAIR_EVENT_ACTIONS = {
    "supplier_non_response": "send_follow_up",
    "supplier_question": "answer_supplier_question",
}
TERMINAL_ACTIONS = {
    "award_supplier",
    "no_award",
}


class StateValidityFrontierError(ValueError):
    """Raised when the frozen State Validity Frontier contract is violated."""


class StateValidityFrontierPolicy(ContextCompiledReactiveLLMPolicy):
    """Versioned validity + minimal repair frontier over visible procurement state."""

    policy_kind = "llm_state_validity_frontier"
    agent_pattern = "state_validity_frontier_v0.1"
    state_strategy = "recomputed_versioned_validity_frontier_v0.1"

    FRONTIER_SYSTEM_PROMPT = """You are the decision component inside the
State Validity Frontier controller for LongProcureBench.

The controller has already filtered the workflow to the currently valid action
frontier. Choose exactly one action from that supplied frontier.

Use only the supplied factual visible state and validity graph. Do not assume
hidden suppliers, hidden triggers, future events, oracle answers, evaluator
state, required checkpoints, or unrevealed quotes.

If award_supplier is allowed, use only active suppliers and current quote event
IDs explicitly supplied by the controller. For a single award the top-level
supplier_id may name that supplier; for multiple awards it must be null.

Return only the structured action. Do not provide chain-of-thought or prose."""

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
        self.policy_id = f"state-validity-frontier--{model}"
        self._reset_controller()

    def _reset_controller(self) -> None:
        self._requirement_epoch = 0
        self._seen_event_ids: set[str] = set()
        self._event_epochs: dict[str, int] = {}
        self._event_generations: dict[str, int] = {}
        self._event_seen_order: dict[str, int] = {}
        self._event_counter = 0

        self._amendment_required_epochs: set[int] = set()
        self._amended_epochs: set[int] = set()
        self._clarification_requested_epochs: set[int] = set()

        self._pending_repairs: dict[str, dict[str, Any]] = {}
        self._handled_repair_event_ids: set[str] = set()

        self._validity_generation = 0
        self._evaluation_generation: int | None = None
        self._last_withdrawal_generation: int | None = None
        self._revision_attempt_offer_ids: set[str] = set()

        self._frontier_trace: list[dict[str, Any]] = []
        self._pending_decision: dict[str, Any] | None = None

        self._frontier_decisions = 0
        self._frontier_interventions = 0
        self._deterministic_frontier_actions = 0
        self._llm_frontier_calls = 0
        self._validity_invalidations = 0
        self._requirement_invalidations = 0
        self._quote_invalidations = 0
        self._withdrawal_invalidations = 0
        self._clarification_lease_blocks = 0
        self._coverage_forced_rfqs = 0
        self._coverage_forced_followups = 0
        self._coverage_forced_answers = 0
        self._max_frontier_size = 0
        self._last_graph: dict[str, Any] | None = None

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._reset_controller()
        self._observe_events(compile_visible_state(state))

    @staticmethod
    def _history(compiled: dict[str, Any]) -> list[dict[str, Any]]:
        history = compiled.get("action_history")
        if not isinstance(history, list):
            return []
        return [row for row in history if isinstance(row, dict)]

    @staticmethod
    def _visible_supplier_ids(compiled: dict[str, Any]) -> list[str]:
        suppliers = compiled.get("visible_suppliers")
        if not isinstance(suppliers, list):
            return []
        return sorted({
            row.get("supplier_id")
            for row in suppliers
            if isinstance(row, dict)
            and isinstance(row.get("supplier_id"), str)
            and row.get("supplier_id")
        })

    @classmethod
    def _sourcing_started(cls, compiled: dict[str, Any]) -> bool:
        return any(
            row.get("type") == "send_rfq"
            for row in cls._history(compiled)
        )

    @classmethod
    def _rfq_suppliers(cls, compiled: dict[str, Any]) -> set[str]:
        return {
            row.get("supplier_id")
            for row in cls._history(compiled)
            if row.get("type") == "send_rfq"
            and isinstance(row.get("supplier_id"), str)
        }

    @staticmethod
    def _operational_missing(compiled: dict[str, Any]) -> list[dict[str, Any]]:
        initial = compiled.get("initial_state")
        if not isinstance(initial, dict):
            return []
        rows = initial.get("operational_missing_information")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _invalidate(self, kind: str) -> None:
        self._validity_generation += 1
        self._validity_invalidations += 1
        if kind == "requirement":
            self._requirement_invalidations += 1
        elif kind == "quote":
            self._quote_invalidations += 1
        elif kind == "withdrawal":
            self._withdrawal_invalidations += 1

    def _observe_events(self, compiled: dict[str, Any]) -> None:
        """Ingest newly visible events using only factual_compiled_v0.1 fields."""
        events = compiled.get("event_history")
        if not isinstance(events, list):
            return

        sourcing_started = self._sourcing_started(compiled)

        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("event_id")
            event_type = event.get("type")
            if (
                not isinstance(event_id, str)
                or not event_id
                or event_id in self._seen_event_ids
            ):
                continue

            self._event_counter += 1
            self._event_seen_order[event_id] = self._event_counter

            if event_type in REQUIREMENT_CHANGE_EVENTS:
                self._requirement_epoch += 1
                self._invalidate("requirement")
                if sourcing_started:
                    self._amendment_required_epochs.add(
                        self._requirement_epoch
                    )
                self._event_epochs[event_id] = self._requirement_epoch
                self._event_generations[event_id] = (
                    self._validity_generation
                )
            else:
                self._event_epochs[event_id] = self._requirement_epoch

                if event_type in QUOTE_EVENTS:
                    self._invalidate("quote")
                elif event_type == "supplier_withdrawal":
                    self._invalidate("withdrawal")
                    self._last_withdrawal_generation = (
                        self._validity_generation
                    )

                self._event_generations[event_id] = (
                    self._validity_generation
                )

            repair_action = REPAIR_EVENT_ACTIONS.get(event_type)
            supplier_id = event.get("supplier_id")
            if (
                repair_action is not None
                and isinstance(supplier_id, str)
                and supplier_id
            ):
                self._pending_repairs[event_id] = {
                    "event_id": event_id,
                    "event_type": event_type,
                    "action_type": repair_action,
                    "supplier_id": supplier_id,
                    "seen_order": self._event_seen_order[event_id],
                }

            self._seen_event_ids.add(event_id)

    def _record_accepted_action(self, action: dict[str, Any]) -> None:
        action_type = action.get("type")
        supplier_id = action.get("supplier_id")

        if action_type == "request_buyer_clarification":
            self._clarification_requested_epochs.add(
                self._requirement_epoch
            )
        elif action_type == "issue_amendment":
            self._amended_epochs.add(self._requirement_epoch)
        elif action_type == "evaluate_quotes":
            self._evaluation_generation = self._validity_generation
        if action_type in {"send_follow_up", "answer_supplier_question"}:
            matching = sorted(
                (
                    row
                    for event_id, row in self._pending_repairs.items()
                    if event_id not in self._handled_repair_event_ids
                    and row["action_type"] == action_type
                    and row["supplier_id"] == supplier_id
                ),
                key=lambda row: row["seen_order"],
            )
            if matching:
                self._handled_repair_event_ids.add(
                    matching[0]["event_id"]
                )

    def _withdrawn_suppliers(
        self,
        compiled: dict[str, Any],
    ) -> set[str]:
        events = compiled.get("event_history")
        if not isinstance(events, list):
            return set()
        return {
            event.get("supplier_id")
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "supplier_withdrawal"
            and isinstance(event.get("supplier_id"), str)
        }

    def _validity_graph(
        self,
        compiled: dict[str, Any],
    ) -> dict[str, Any]:
        self._observe_events(compiled)

        visible = set(self._visible_supplier_ids(compiled))
        withdrawn = self._withdrawn_suppliers(compiled)
        active = sorted(visible - withdrawn)

        latest_offers = []
        for offer in compiled.get("latest_offers") or []:
            if not isinstance(offer, dict):
                continue
            supplier_id = offer.get("supplier_id")
            event_id = offer.get("event_id")
            if (
                not isinstance(supplier_id, str)
                or not isinstance(event_id, str)
            ):
                continue
            epoch = self._event_epochs.get(
                event_id,
                self._requirement_epoch,
            )
            latest_offers.append({
                "event_id": event_id,
                "type": offer.get("type"),
                "supplier_id": supplier_id,
                "details": deepcopy(offer.get("details") or {}),
                "offer_scope": deepcopy(
                    offer.get("offer_scope") or {"kind": "package"}
                ),
                "requirement_epoch": epoch,
                "current": (
                    supplier_id in active
                    and epoch == self._requirement_epoch
                ),
            })

        current_offers = [
            row
            for row in latest_offers
            if row["current"]
        ]
        stale_offers = [
            row
            for row in latest_offers
            if row["supplier_id"] in active
            and row["requirement_epoch"] < self._requirement_epoch
        ]
        stale_suppliers = sorted({
            row["supplier_id"] for row in stale_offers
        })
        pending_stale_offers = [
            row
            for row in stale_offers
            if row["event_id"] not in self._revision_attempt_offer_ids
        ]
        pending_stale_suppliers = sorted({
            row["supplier_id"] for row in pending_stale_offers
        })
        exhausted_stale_suppliers = sorted({
            row["supplier_id"]
            for row in stale_offers
            if row["event_id"] in self._revision_attempt_offer_ids
        })

        pending_repairs = sorted(
            (
                deepcopy(row)
                for event_id, row in self._pending_repairs.items()
                if event_id not in self._handled_repair_event_ids
                and row["supplier_id"] in active
            ),
            key=lambda row: row["seen_order"],
        )

        amendment_required = (
            self._requirement_epoch in self._amendment_required_epochs
            and self._requirement_epoch not in self._amended_epochs
        )

        evaluation_valid = (
            self._evaluation_generation is not None
            and self._evaluation_generation == self._validity_generation
            and not amendment_required
            and not pending_repairs
            and not pending_stale_suppliers
        )

        post_withdrawal_offer = False
        if self._last_withdrawal_generation is not None:
            for event in compiled.get("event_history") or []:
                if not isinstance(event, dict):
                    continue
                if event.get("type") not in QUOTE_EVENTS:
                    continue
                event_id = event.get("event_id")
                supplier_id = event.get("supplier_id")
                generation = self._event_generations.get(event_id)
                if (
                    isinstance(event_id, str)
                    and isinstance(supplier_id, str)
                    and supplier_id in active
                    and generation is not None
                    and generation > self._last_withdrawal_generation
                ):
                    post_withdrawal_offer = True
                    break

        graph = {
            "requirement_epoch": self._requirement_epoch,
            "validity_generation": self._validity_generation,
            "evaluation_generation": self._evaluation_generation,
            "evaluation_current": evaluation_valid,
            "amendment_required": amendment_required,
            "clarification_available": (
                bool(self._operational_missing(compiled))
                and self._requirement_epoch
                not in self._clarification_requested_epochs
            ),
            "visible_supplier_ids": sorted(visible),
            "active_supplier_ids": active,
            "withdrawn_supplier_ids": sorted(withdrawn),
            "rfq_supplier_ids": sorted(self._rfq_suppliers(compiled)),
            "sourcing_started": self._sourcing_started(compiled),
            "latest_offers": latest_offers,
            "current_offers": current_offers,
            "stale_supplier_ids": stale_suppliers,
            "pending_stale_supplier_ids": pending_stale_suppliers,
            "exhausted_stale_supplier_ids": exhausted_stale_suppliers,
            "pending_stale_offers": deepcopy(pending_stale_offers),
            "revision_opportunities": [
                deepcopy(row)
                for row in current_offers
                if row["type"] == "quote_received"
                and row["event_id"] not in self._revision_attempt_offer_ids
            ],
            "pending_repairs": pending_repairs,
            "last_withdrawal_generation": self._last_withdrawal_generation,
            "post_withdrawal_new_offer": post_withdrawal_offer,
        }
        self._last_graph = deepcopy(graph)
        return graph

    @staticmethod
    def _candidate(
        action_type: str,
        supplier_id: str | None = None,
        *,
        reason: str,
        terminal_award: bool = False,
        allowed_supplier_ids: list[str] | None = None,
        allowed_quote_event_ids: list[str] | None = None,
        basis_offer_event_id: str | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "type": action_type,
            "supplier_id": supplier_id,
            "reason": reason,
        }
        if basis_offer_event_id is not None:
            row["basis_offer_event_id"] = basis_offer_event_id
        if terminal_award:
            row["terminal_award"] = True
            row["allowed_supplier_ids"] = list(
                allowed_supplier_ids or []
            )
            row["allowed_quote_event_ids"] = list(
                allowed_quote_event_ids or []
            )
        return row

    def _frontier(
        self,
        compiled: dict[str, Any],
        graph: dict[str, Any],
    ) -> list[dict[str, Any]]:
        active = graph["active_supplier_ids"]

        if graph["amendment_required"]:
            return [
                self._candidate(
                    "issue_amendment",
                    reason="visible requirement epoch changed after sourcing",
                )
            ]

        if graph["pending_repairs"]:
            row = graph["pending_repairs"][0]
            return [
                self._candidate(
                    row["action_type"],
                    row["supplier_id"],
                    reason=f"visible {row['event_type']} requires bounded repair",
                )
            ]

        if graph["sourcing_started"]:
            covered = set(graph["rfq_supplier_ids"])
            uncovered = [
                supplier_id
                for supplier_id in active
                if supplier_id not in covered
            ]
            if uncovered:
                return [
                    self._candidate(
                        "send_rfq",
                        uncovered[0],
                        reason="complete supplier RFQ coverage",
                    )
                ]

        if graph["pending_stale_offers"]:
            candidates = [
                self._candidate(
                    "request_quote_revision",
                    row["supplier_id"],
                    reason="visible requirement epoch made offer stale",
                    basis_offer_event_id=row["event_id"],
                )
                for row in graph["pending_stale_offers"]
            ]
            return candidates

        if (
            self._last_withdrawal_generation is not None
            and not graph["evaluation_current"]
        ):
            if not graph["post_withdrawal_new_offer"]:
                candidates = [
                    self._candidate(
                        "request_quote_revision",
                        row["supplier_id"],
                        reason=(
                            "withdrawal invalidated evaluation; acquire "
                            "replacement evidence from an active supplier"
                        ),
                        basis_offer_event_id=row["event_id"],
                    )
                    for row in graph["current_offers"]
                    if row["event_id"]
                    not in self._revision_attempt_offer_ids
                ]
                if candidates:
                    return candidates
                raise StateValidityFrontierError(
                    "Withdrawal recovery has no unattempted active-supplier "
                    "quote evidence left; replacement evidence was not obtained"
                )

            return [
                self._candidate(
                    "evaluate_quotes",
                    reason=(
                        "new active-supplier quote evidence arrived after "
                        "withdrawal; reevaluate before terminal decision"
                    ),
                )
            ]

        if not graph["sourcing_started"]:
            candidates = []
            if (
                self._operational_missing(compiled)
                and not graph["clarification_available"]
            ):
                self._clarification_lease_blocks += 1

            if graph["clarification_available"]:
                candidates.append(
                    self._candidate(
                        "request_buyer_clarification",
                        reason=(
                            "one clarification lease is available in the "
                            "current requirement epoch"
                        ),
                    )
                )

            if not graph["visible_supplier_ids"]:
                candidates.append(
                    self._candidate(
                        "identify_suppliers",
                        reason="supplier directory is not yet visible",
                    )
                )
            else:
                for supplier_id in active:
                    candidates.append(
                        self._candidate(
                            "send_rfq",
                            supplier_id,
                            reason="begin sourcing with a visible active supplier",
                        )
                    )

            if candidates:
                return candidates

        if not graph["evaluation_current"]:
            candidates = []
            if self._evaluation_generation is None:
                candidates.extend(
                    self._candidate(
                        "request_quote_revision",
                        row["supplier_id"],
                        reason=(
                            "visible unrevised offer may warrant additional "
                            "evidence before the first evaluation"
                        ),
                        basis_offer_event_id=row["event_id"],
                    )
                    for row in graph["revision_opportunities"]
                )
            candidates.append(
                self._candidate(
                    "evaluate_quotes",
                    reason="current visible evidence has not been evaluated",
                )
            )
            return candidates

        current_suppliers = sorted({
            row["supplier_id"]
            for row in graph["current_offers"]
        })
        current_quote_ids = sorted({
            row["event_id"]
            for row in graph["current_offers"]
        })

        terminal = [
            self._candidate(
                "no_award",
                reason="current evaluation may support no-award",
            )
        ]
        if current_suppliers and current_quote_ids:
            terminal.insert(
                0,
                self._candidate(
                    "award_supplier",
                    reason="current evaluation may support award",
                    terminal_award=True,
                    allowed_supplier_ids=current_suppliers,
                    allowed_quote_event_ids=current_quote_ids,
                ),
            )
        return terminal

    @staticmethod
    def _public_frontier(
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [deepcopy(row) for row in candidates]

    @staticmethod
    def _deterministic_action(
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        if candidate["type"] in TERMINAL_ACTIONS:
            raise StateValidityFrontierError(
                "Terminal actions require model selection"
            )
        return {
            "type": candidate["type"],
            "supplier_id": candidate.get("supplier_id"),
            "arguments": {},
        }

    def _frontier_action_schema(
        self,
        state: dict[str, Any],
        candidates: list[dict[str, Any]],
        graph: dict[str, Any],
    ) -> dict[str, Any]:
        schema = self._action_schema(state)
        allowed_types = [
            action_type
            for action_type in ACTION_TYPES
            if any(row["type"] == action_type for row in candidates)
        ]
        schema["properties"]["type"]["enum"] = allowed_types

        supplier_values: set[str | None] = set()
        for row in candidates:
            if row.get("terminal_award"):
                supplier_values.add(None)
                supplier_values.update(row["allowed_supplier_ids"])
            else:
                supplier_values.add(row.get("supplier_id"))
        schema["properties"]["supplier_id"]["enum"] = sorted(
            supplier_values,
            key=lambda value: "" if value is None else value,
        )

        award_candidates = [
            row for row in candidates if row.get("terminal_award")
        ]
        if award_candidates:
            allowed_suppliers = sorted({
                supplier_id
                for row in award_candidates
                for supplier_id in row["allowed_supplier_ids"]
            })
            allowed_quotes = sorted({
                quote_id
                for row in award_candidates
                for quote_id in row["allowed_quote_event_ids"]
            })
            award_item = (
                schema["properties"]["arguments"]["properties"]["awards"][
                    "items"
                ]
            )
            award_item["properties"]["supplier_id"]["enum"] = (
                allowed_suppliers
            )
            award_item["properties"]["quote_event_id"]["enum"] = (
                allowed_quotes
            )

        return schema

    @staticmethod
    def _current_quote_map(
        graph: dict[str, Any],
    ) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for row in graph["current_offers"]:
            out.setdefault(row["supplier_id"], set()).add(row["event_id"])
        return out

    def _validate_model_choice(
        self,
        decision: dict[str, Any],
        candidates: list[dict[str, Any]],
        graph: dict[str, Any],
    ) -> None:
        action_type = decision.get("type")
        supplier_id = decision.get("supplier_id")

        if action_type == "award_supplier":
            if not any(row.get("terminal_award") for row in candidates):
                raise StateValidityFrontierError(
                    "award_supplier is outside the current frontier"
                )
            awards = (decision.get("arguments") or {}).get("awards")
            if not isinstance(awards, list) or not awards:
                raise StateValidityFrontierError(
                    "award_supplier requires a non-empty awards list"
                )
            quote_map = self._current_quote_map(graph)
            active = set(graph["active_supplier_ids"])
            for award in awards:
                award_supplier = award.get("supplier_id")
                quote_id = award.get("quote_event_id")
                if award_supplier not in active:
                    raise StateValidityFrontierError(
                        "Award references an inactive or withdrawn supplier"
                    )
                if quote_id not in quote_map.get(award_supplier, set()):
                    raise StateValidityFrontierError(
                        "Award references a stale or non-current quote"
                    )
            if len(awards) > 1 and supplier_id is not None:
                raise StateValidityFrontierError(
                    "Multi-award action requires top-level supplier_id=null"
                )
            if (
                len(awards) == 1
                and supplier_id not in (None, awards[0]["supplier_id"])
            ):
                raise StateValidityFrontierError(
                    "Top-level supplier_id does not match single award"
                )
            return

        for candidate in candidates:
            if (
                candidate["type"] == action_type
                and not candidate.get("terminal_award")
                and candidate.get("supplier_id") == supplier_id
            ):
                return

        raise StateValidityFrontierError(
            "Model chose an action outside the current validity frontier"
        )

    def _record_model_metrics(
        self,
        *,
        started: float,
        metrics: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        if metrics is not None:
            normalized = deepcopy(metrics)
            normalized["success"] = error is None
            normalized.setdefault("usage_available", True)
            normalized["error"] = (
                {
                    "type": type(error).__name__,
                    "message": str(error),
                }
                if error is not None
                else None
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

    def _model_frontier_action(
        self,
        state: dict[str, Any],
        compiled: dict[str, Any],
        graph: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        schema = self._frontier_action_schema(
            state,
            candidates,
            graph,
        )
        payload = {
            "validity_graph": graph,
            "valid_action_frontier": self._public_frontier(candidates),
            "factual_visible_state": compiled,
        }
        messages = [
            {
                "role": "system",
                "content": self.FRONTIER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Allowed award scope values this episode: "
                    + ", ".join(self._allowed_award_scopes(state))
                    + "\n\nState Validity Frontier context:\n"
                    + json.dumps(payload, sort_keys=True)
                ),
            },
        ]

        started = perf_counter()
        try:
            decision, metrics = self._client.generate_action(
                messages=messages,
                action_schema=schema,
            )
        except ModelCallError as exc:
            self._calls.append(deepcopy(exc.metrics))
            raise
        except Exception as exc:
            self._record_model_metrics(
                started=started,
                error=exc,
            )
            raise

        try:
            Draft202012Validator(schema).validate(decision)
            self._validate_model_choice(
                decision,
                candidates,
                graph,
            )
            runtime = self._runtime_decision(decision)
        except Exception as exc:
            self._record_model_metrics(
                started=started,
                metrics=metrics,
                error=exc,
            )
            raise

        self._record_model_metrics(
            started=started,
            metrics=metrics,
        )
        self._llm_frontier_calls += 1
        return runtime

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._pending_decision is not None:
            raise StateValidityFrontierError(
                "Previous frontier decision is still pending acceptance"
            )

        compiled = compile_visible_state(state)
        graph = self._validity_graph(compiled)
        candidates = self._frontier(compiled, graph)
        if not candidates:
            raise StateValidityFrontierError(
                "Validity frontier is empty"
            )

        self._frontier_decisions += 1
        self._max_frontier_size = max(
            self._max_frontier_size,
            len(candidates),
        )

        terminal_frontier = any(
            row["type"] in TERMINAL_ACTIONS
            for row in candidates
        )
        if len(candidates) == 1 and not terminal_frontier:
            decision = self._deterministic_action(candidates[0])
            source = "deterministic"
            self._deterministic_frontier_actions += 1
            self._frontier_interventions += 1

            action_type = decision["type"]
            if action_type == "send_rfq":
                self._coverage_forced_rfqs += 1
            elif action_type == "send_follow_up":
                self._coverage_forced_followups += 1
            elif action_type == "answer_supplier_question":
                self._coverage_forced_answers += 1
        else:
            decision = self._model_frontier_action(
                state,
                compiled,
                graph,
                candidates,
            )
            source = "model_frontier"
            self._frontier_interventions += 1

        trace = {
            "proposed_state_step": compiled.get("step"),
            "requirement_epoch_before": self._requirement_epoch,
            "validity_generation_before": self._validity_generation,
            "evaluation_current_before": graph["evaluation_current"],
            "frontier": self._public_frontier(candidates),
            "decision_source": source,
            "chosen_action": deepcopy(decision),
            "accepted": False,
            "accepted_state_step": None,
            "observation_event_ids": [],
            "requirement_epoch_after": None,
            "validity_generation_after": None,
            "evaluation_current_after": None,
        }
        self._frontier_trace.append(trace)
        chosen_candidate = next(
            (
                deepcopy(row)
                for row in candidates
                if row["type"] == decision["type"]
                and (
                    row.get("supplier_id") == decision.get("supplier_id")
                    or row.get("terminal_award")
                )
            ),
            None,
        )
        self._pending_decision = {
            "action": deepcopy(decision),
            "trace_index": len(self._frontier_trace) - 1,
            "candidate": chosen_candidate,
        }
        return decision

    @staticmethod
    def _semantic_action(action: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": action.get("type"),
            "supplier_id": action.get("supplier_id"),
            "arguments": deepcopy(action.get("arguments") or {}),
        }

    def on_action_accepted(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        if self._pending_decision is None:
            raise StateValidityFrontierError(
                "Accepted action has no pending frontier decision"
            )

        accepted = self._semantic_action(action)
        if accepted != self._pending_decision["action"]:
            raise StateValidityFrontierError(
                "Accepted action does not match pending frontier decision"
            )

        self._record_accepted_action(accepted)
        candidate = self._pending_decision.get("candidate") or {}
        basis_offer_event_id = candidate.get("basis_offer_event_id")
        if (
            accepted.get("type") == "request_quote_revision"
            and isinstance(basis_offer_event_id, str)
        ):
            self._revision_attempt_offer_ids.add(basis_offer_event_id)

        compiled = compile_visible_state(state)
        self._observe_events(compiled)
        after_graph = self._validity_graph(compiled)

        trace = self._frontier_trace[
            self._pending_decision["trace_index"]
        ]
        trace["accepted"] = True
        trace["accepted_state_step"] = state.get("step")
        trace["observation_event_ids"] = [
            row.get("event_id")
            for row in state.get("observations") or []
            if isinstance(row, dict)
            and isinstance(row.get("event_id"), str)
        ]
        trace["requirement_epoch_after"] = self._requirement_epoch
        trace["validity_generation_after"] = self._validity_generation
        trace["evaluation_current_after"] = after_graph[
            "evaluation_current"
        ]

        self._pending_decision = None

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        metadata.update({
            "agent_pattern": self.agent_pattern,
            "state_strategy": self.state_strategy,
            "requirement_epoch": self._requirement_epoch,
            "validity_generation": self._validity_generation,
            "evaluation_generation": self._evaluation_generation,
            "evaluation_current": (
                bool(self._last_graph)
                and bool(self._last_graph.get("evaluation_current"))
            ),
            "frontier_decisions": self._frontier_decisions,
            "validity_frontier_interventions": (
                self._frontier_interventions
            ),
            "deterministic_frontier_actions": (
                self._deterministic_frontier_actions
            ),
            "llm_frontier_calls": self._llm_frontier_calls,
            "max_frontier_size": self._max_frontier_size,
            "validity_invalidations": self._validity_invalidations,
            "requirement_invalidations": self._requirement_invalidations,
            "quote_invalidations": self._quote_invalidations,
            "withdrawal_invalidations": self._withdrawal_invalidations,
            "clarification_lease_blocks": (
                self._clarification_lease_blocks
            ),
            "clarification_epochs_used": sorted(
                self._clarification_requested_epochs
            ),
            "amendment_required_epochs": sorted(
                self._amendment_required_epochs
            ),
            "amended_epochs": sorted(self._amended_epochs),
            "handled_repair_event_ids": sorted(
                self._handled_repair_event_ids
            ),
            "revision_attempt_offer_ids": sorted(
                self._revision_attempt_offer_ids
            ),
            "coverage_forced_rfqs": self._coverage_forced_rfqs,
            "coverage_forced_followups": self._coverage_forced_followups,
            "coverage_forced_answers": self._coverage_forced_answers,
            "validity_graph": deepcopy(self._last_graph),
            "frontier_trace": deepcopy(self._frontier_trace),
        })
        return metadata
