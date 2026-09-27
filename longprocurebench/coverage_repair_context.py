"""Coverage + repair diagnostic baseline for LongProcureBench.

This is intentionally a small deterministic workflow controller around the
factual context-compiled reactive policy. It is a diagnostic baseline, not a
ProcureHarness proposal.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .context_compiled_reactive import (
    ContextCompiledReactiveLLMPolicy,
    compile_visible_state,
)


REPAIR_EVENT_ACTIONS: dict[str, str] = {
    "supplier_non_response": "send_follow_up",
    "supplier_question": "answer_supplier_question",
}
REQUIREMENT_CHANGE_EVENT_TYPES = {
    "requirement_change",
    "quantity_change",
}


class CoverageRepairContextPolicy(ContextCompiledReactiveLLMPolicy):
    """Context-reactive policy with deterministic coverage/repair actions.

    The controller uses only the same facts exposed by factual_compiled_v0.1.
    The model decides when sourcing begins by sending the first RFQ. After that,
    the controller can:
    - respond once to a newly visible supplier non-response or question;
    - complete RFQ coverage across currently visible suppliers.

    Deterministic interventions do not call the model. Requirement amendments,
    quote revisions, evaluation, awards, and no-award remain model decisions.
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
        self._handled_repair_event_ids: set[str] = set()
        self._seen_requirement_change_ids: set[str] = set()
        self._required_amendment_count = 0

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._reset_diagnostics()

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
        ids = {
            row.get("supplier_id")
            for row in suppliers
            if isinstance(row, dict)
            and isinstance(row.get("supplier_id"), str)
            and row.get("supplier_id")
        }
        return sorted(ids)

    @classmethod
    def _sourcing_started(cls, compiled: dict[str, Any]) -> bool:
        return any(
            action.get("type") == "send_rfq"
            for action in cls._history(compiled)
        )

    @classmethod
    def _amendment_count(cls, compiled: dict[str, Any]) -> int:
        return sum(
            1
            for action in cls._history(compiled)
            if action.get("type") == "issue_amendment"
        )

    def _has_unamended_requirement_change(
        self,
        compiled: dict[str, Any],
    ) -> bool:
        """Return whether a newly visible change still needs a later amendment.

        The controller only sees factual_compiled_v0.1, which intentionally
        strips runtime trigger metadata. Ordering is therefore preserved
        statefully: when a requirement/quantity change event first becomes
        visible, record how many amendments had already happened and require
        the amendment count to increase before deterministic actions resume.

        This prevents an amendment issued *before* a later change from
        accidentally satisfying that later change.
        """
        amendments = self._amendment_count(compiled)
        events = compiled.get("event_history")
        if not isinstance(events, list):
            return amendments < self._required_amendment_count

        new_change_seen = False
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("event_id")
            if (
                event.get("type") not in REQUIREMENT_CHANGE_EVENT_TYPES
                or not isinstance(event_id, str)
                or not event_id
                or event_id in self._seen_requirement_change_ids
            ):
                continue
            self._seen_requirement_change_ids.add(event_id)
            new_change_seen = True

        if new_change_seen:
            # One amendment after the newly observed change(s) is required.
            # Multiple changes revealed in the same observation batch may be
            # addressed by that same model-selected amendment.
            self._required_amendment_count = max(
                self._required_amendment_count,
                amendments + 1,
            )

        return amendments < self._required_amendment_count

    def _unresolved_visible_repair(
        self,
        compiled: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        if not self._sourcing_started(compiled):
            return None

        events = compiled.get("event_history")
        if not isinstance(events, list):
            return None
        visible_suppliers = set(self._visible_supplier_ids(compiled))

        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("event_id")
            event_type = event.get("type")
            action_type = REPAIR_EVENT_ACTIONS.get(event_type)
            supplier_id = event.get("supplier_id")
            if (
                not isinstance(event_id, str)
                or not event_id
                or event_id in self._handled_repair_event_ids
                or action_type is None
                or not isinstance(supplier_id, str)
                or supplier_id not in visible_suppliers
            ):
                continue

            return event_id, {
                "type": action_type,
                "supplier_id": supplier_id,
                "arguments": {},
            }

        return None

    @classmethod
    def _uncovered_supplier_action(
        cls,
        compiled: dict[str, Any],
    ) -> dict[str, Any] | None:
        history = cls._history(compiled)
        rfq_suppliers = {
            action.get("supplier_id")
            for action in history
            if action.get("type") == "send_rfq"
            and isinstance(action.get("supplier_id"), str)
        }

        # The model decides when sourcing begins. Deterministic coverage starts
        # only after the first accepted RFQ is already visible in history.
        if not rfq_suppliers:
            return None

        uncovered = [
            supplier_id
            for supplier_id in cls._visible_supplier_ids(compiled)
            if supplier_id not in rfq_suppliers
        ]
        if not uncovered:
            return None

        return {
            "type": "send_rfq",
            "supplier_id": uncovered[0],
            "arguments": {},
        }

    def _record_intervention(self, action: dict[str, Any]) -> None:
        self._interventions += 1
        action_type = action.get("type")
        if action_type == "send_rfq":
            self._forced_rfqs += 1
        elif action_type == "send_follow_up":
            self._forced_followups += 1
        elif action_type == "answer_supplier_question":
            self._forced_answers += 1

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        # Use exactly the same factual view sent to the matched context baseline.
        compiled = compile_visible_state(state)

        # A newly visible requirement/quantity change must be handled by the
        # model before deterministic supplier repair/coverage resumes. This
        # prevents a forced follow-up from materializing a one-shot quote under
        # stale pre-amendment requirements (notably episode 016).
        if self._has_unamended_requirement_change(compiled):
            return super().act(state)

        repair = self._unresolved_visible_repair(compiled)
        if repair is not None:
            event_id, action = repair
            self._handled_repair_event_ids.add(event_id)
            self._record_intervention(action)
            return deepcopy(action)

        coverage = self._uncovered_supplier_action(compiled)
        if coverage is not None:
            self._record_intervention(coverage)
            return deepcopy(coverage)

        return super().act(state)

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        metadata.update({
            "agent_pattern": self.agent_pattern,
            "coverage_repair_interventions": self._interventions,
            "coverage_forced_rfqs": self._forced_rfqs,
            "coverage_forced_followups": self._forced_followups,
            "coverage_forced_answers": self._forced_answers,
        })
        return metadata
