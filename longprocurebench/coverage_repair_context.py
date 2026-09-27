"""Coverage + repair diagnostic baseline for LongProcureBench.

This is intentionally a small deterministic workflow controller around the
factual context-compiled reactive policy. It is a diagnostic baseline, not a
ProcureHarness proposal.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .context_compiled_reactive import ContextCompiledReactiveLLMPolicy


REPAIR_EVENT_ACTIONS: dict[str, tuple[str, bool]] = {
    "supplier_non_response": ("send_follow_up", True),
    "supplier_question": ("answer_supplier_question", True),
    "requirement_change": ("issue_amendment", False),
    "quantity_change": ("issue_amendment", False),
}


class CoverageRepairContextPolicy(ContextCompiledReactiveLLMPolicy):
    """Context-reactive policy with deterministic coverage/repair actions.

    The controller uses only agent-visible state. Once the model has started
    sourcing by sending the first RFQ, the controller:
    - discharges a small set of obvious event-triggered repairs;
    - completes RFQ coverage across currently visible suppliers.

    Deterministic interventions do not call the model. Final evaluation,
    revisions, awards, and no-award decisions remain model decisions.
    """

    policy_kind = "llm_coverage_repair_diagnostic"
    agent_pattern = "coverage_repair_v0.1"

    def __init__(self, model: str, **kwargs: Any):
        super().__init__(model, **kwargs)
        self.policy_id = f"coverage-repair-context--{model}"
        self._reset_diagnostics()

    def _reset_diagnostics(self) -> None:
        self._interventions = 0
        self._forced_rfqs = 0
        self._forced_followups = 0
        self._forced_answers = 0
        self._forced_amendments = 0

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._reset_diagnostics()

    @staticmethod
    def _history(state: dict[str, Any]) -> list[dict[str, Any]]:
        history = state.get("action_history")
        if not isinstance(history, list):
            return []
        return [row for row in history if isinstance(row, dict)]

    @staticmethod
    def _visible_supplier_ids(state: dict[str, Any]) -> list[str]:
        suppliers = state.get("visible_suppliers")
        if not isinstance(suppliers, list):
            return []
        ids = {
            row.get("supplier_id")
            for row in suppliers
            if isinstance(row, dict)
            and isinstance(row.get("supplier_id"), str)
            and row.get("supplier_id")
        }
        return sorted(ids)

    @classmethod
    def _event_trigger_step(
        cls,
        event: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> int | None:
        trigger = event.get("trigger")
        if not isinstance(trigger, dict):
            return None

        kind = trigger.get("kind")
        if kind == "at_step":
            step = trigger.get("step")
            if isinstance(step, int) and not isinstance(step, bool) and step >= 0:
                return step
            return None

        if kind != "after_action":
            return None

        action_type = trigger.get("action_type")
        supplier_id = trigger.get("supplier_id")
        for sequence, action in enumerate(history, start=1):
            if action.get("type") != action_type:
                continue
            if supplier_id is not None and action.get("supplier_id") != supplier_id:
                continue
            return sequence
        return None

    @classmethod
    def _unresolved_visible_repair(
        cls,
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        history = cls._history(state)
        events = state.get("revealed_events")
        if not isinstance(events, list):
            return None

        visible_suppliers = set(cls._visible_supplier_ids(state))

        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            mapping = REPAIR_EVENT_ACTIONS.get(event_type)
            if mapping is None:
                continue

            action_type, supplier_scoped = mapping
            trigger_step = cls._event_trigger_step(event, history)
            if trigger_step is None:
                continue

            supplier_id = event.get("supplier_id") if supplier_scoped else None
            if supplier_scoped:
                if not isinstance(supplier_id, str) or not supplier_id:
                    continue
                if supplier_id not in visible_suppliers:
                    continue

            already_repaired = False
            for action in history[trigger_step:]:
                if action.get("type") != action_type:
                    continue
                if supplier_scoped and action.get("supplier_id") != supplier_id:
                    continue
                already_repaired = True
                break

            if not already_repaired:
                return {
                    "type": action_type,
                    "supplier_id": supplier_id,
                    "arguments": {},
                }

        return None

    @classmethod
    def _uncovered_supplier_action(
        cls,
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        history = cls._history(state)
        rfq_suppliers = {
            action.get("supplier_id")
            for action in history
            if action.get("type") == "send_rfq"
            and isinstance(action.get("supplier_id"), str)
        }

        # Do not decide when sourcing should begin. The model must send the
        # first RFQ itself; only then does deterministic coverage take over.
        if not rfq_suppliers:
            return None

        uncovered = [
            supplier_id
            for supplier_id in cls._visible_supplier_ids(state)
            if supplier_id not in rfq_suppliers
        ]
        if not uncovered:
            return None

        return {
            "type": "send_rfq",
            "supplier_id": uncovered[0],
            "arguments": {},
        }

    def _forced_action(self, state: dict[str, Any]) -> dict[str, Any] | None:
        repair = self._unresolved_visible_repair(state)
        if repair is not None:
            return repair
        return self._uncovered_supplier_action(state)

    def _record_intervention(self, action: dict[str, Any]) -> None:
        self._interventions += 1
        action_type = action.get("type")
        if action_type == "send_rfq":
            self._forced_rfqs += 1
        elif action_type == "send_follow_up":
            self._forced_followups += 1
        elif action_type == "answer_supplier_question":
            self._forced_answers += 1
        elif action_type == "issue_amendment":
            self._forced_amendments += 1

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        forced = self._forced_action(state)
        if forced is not None:
            self._record_intervention(forced)
            return deepcopy(forced)
        return super().act(state)

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        metadata.update({
            "agent_pattern": self.agent_pattern,
            "coverage_repair_interventions": self._interventions,
            "coverage_forced_rfqs": self._forced_rfqs,
            "coverage_forced_followups": self._forced_followups,
            "coverage_forced_answers": self._forced_answers,
            "coverage_forced_amendments": self._forced_amendments,
        })
        return metadata
