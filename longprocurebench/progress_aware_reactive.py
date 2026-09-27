"""Progress-aware reactive policy over factual compiled context."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from .context_compiled_reactive import (
    ContextCompiledReactiveLLMPolicy,
    compile_visible_state,
)


INFORMATION_SEEKING_ACTIONS = {
    "request_buyer_clarification",
    "identify_suppliers",
    "send_rfq",
    "send_follow_up",
    "request_quote_revision",
}


class ProgressControlError(ValueError):
    """Raised when the progress-control acceptance contract is violated."""


def evidence_fingerprint(state: dict[str, Any]) -> str:
    """Fingerprint only dynamic agent-visible procurement evidence."""
    compiled = compile_visible_state(state)
    payload = {
        "visible_suppliers": compiled["visible_suppliers"],
        "latest_offers": compiled["latest_offers"],
        "requirement_updates": compiled["requirement_updates"],
        "event_history": compiled["event_history"],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def action_signature(action: dict[str, Any]) -> tuple[str, str | None]:
    return (
        str(action.get("type")),
        action.get("supplier_id"),
    )


class ProgressAwareReactiveLLMPolicy(ContextCompiledReactiveLLMPolicy):
    """Reactive policy with deterministic no-progress action control."""

    policy_kind = "llm_progress_aware_reactive"
    state_strategy = "progress_aware_no_progress_guard_v0.1"

    SYSTEM_PROMPT = (
        ContextCompiledReactiveLLMPolicy.SYSTEM_PROMPT
        + """

Progress-control contract:
- progress_control.blocked_no_progress_actions lists information-seeking action
  signatures that were already accepted in the current visible-evidence epoch
  and produced no new visible supplier, event, offer, or requirement evidence.
- Do not repeat an exact blocked (action_type, supplier_id) signature while the
  evidence epoch is unchanged.
- If progress_control.guard_retry_blocked_action is non-null, the previous
  proposal was rejected by the harness because it repeated a no-progress
  signature. Choose a different unblocked action signature.
- Missing-at-source or unresolved information is not evidence that repeated
  requests will help. If no unblocked evidence-gathering path remains, choose
  the best next procurement action or terminal decision supported by visible
  facts rather than looping.
- Never invent hidden information, future events, evaluator state, or oracle
  answers."""
    )

    def __init__(self, model: str, **kwargs: Any):
        super().__init__(model, **kwargs)
        self.policy_id = f"progress-aware-reactive--{model}"
        self._evidence_fingerprint: str | None = None
        self._evidence_epoch = 0
        self._blocked: dict[tuple[str, str | None], int] = {}
        self._guard_retry_blocked: tuple[str, str | None] | None = None
        self._pending_pre_fingerprint: str | None = None
        self._pending_signature: tuple[str, str | None] | None = None
        self._no_progress_marks = 0
        self._progress_events = 0
        self._guard_interventions = 0
        self._guard_retry_calls = 0
        self._guard_retry_noncompliance = 0
        self._progress_trace: list[dict[str, Any]] = []
        self._guard_trace: list[dict[str, Any]] = []

    def reset(self, state: dict[str, Any]) -> None:
        super().reset(state)
        self._evidence_fingerprint = evidence_fingerprint(state)
        self._evidence_epoch = 0
        self._blocked = {}
        self._guard_retry_blocked = None
        self._pending_pre_fingerprint = None
        self._pending_signature = None
        self._no_progress_marks = 0
        self._progress_events = 0
        self._guard_interventions = 0
        self._guard_retry_calls = 0
        self._guard_retry_noncompliance = 0
        self._progress_trace = []
        self._guard_trace = []

    @staticmethod
    def _signature_dict(
        signature: tuple[str, str | None],
        *,
        count: int | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "action_type": signature[0],
            "supplier_id": signature[1],
        }
        if count is not None:
            row["no_progress_count"] = count
        return row

    def _blocked_rows(self) -> list[dict[str, Any]]:
        return [
            self._signature_dict(signature, count=count)
            for signature, count in sorted(
                self._blocked.items(),
                key=lambda item: (item[0][0], item[0][1] or ""),
            )
        ]

    def _prompt_state(self, state: dict[str, Any]) -> dict[str, Any]:
        compiled = compile_visible_state(state)
        compiled["progress_control"] = {
            "strategy": self.state_strategy,
            "evidence_epoch": self._evidence_epoch,
            "blocked_no_progress_actions": self._blocked_rows(),
            "guard_retry_blocked_action": (
                self._signature_dict(self._guard_retry_blocked)
                if self._guard_retry_blocked is not None
                else None
            ),
        }
        return compiled

    def _is_blocked(self, action: dict[str, Any]) -> bool:
        signature = action_signature(action)
        return (
            signature[0] in INFORMATION_SEEKING_ACTIONS
            and signature in self._blocked
        )

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._pending_pre_fingerprint is not None:
            raise ProgressControlError(
                "Previous progress-aware action is still pending acceptance"
            )

        current = evidence_fingerprint(state)
        if self._evidence_fingerprint is None:
            self._evidence_fingerprint = current
        elif current != self._evidence_fingerprint:
            self._evidence_fingerprint = current
            self._evidence_epoch += 1
            self._blocked = {}
            self._progress_events += 1

        self._guard_retry_blocked = None
        first = super().act(state)
        selected = first

        if self._is_blocked(first):
            blocked_signature = action_signature(first)
            self._guard_interventions += 1
            self._guard_retry_blocked = blocked_signature
            retry = super().act(state)
            self._guard_retry_calls += 1
            retry_blocked = self._is_blocked(retry)
            if retry_blocked:
                self._guard_retry_noncompliance += 1
            self._guard_trace.append({
                "state_step": state.get("step"),
                "evidence_epoch": self._evidence_epoch,
                "blocked_proposal": self._signature_dict(
                    blocked_signature
                ),
                "retry_action": self._signature_dict(
                    action_signature(retry)
                ),
                "retry_still_blocked": retry_blocked,
            })
            selected = retry
            self._guard_retry_blocked = None

        self._pending_pre_fingerprint = current
        self._pending_signature = action_signature(selected)
        return selected

    def on_action_accepted(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        if (
            self._pending_pre_fingerprint is None
            or self._pending_signature is None
        ):
            raise ProgressControlError(
                "Accepted action has no pending progress-aware decision"
            )

        accepted_signature = action_signature(action)
        if accepted_signature != self._pending_signature:
            raise ProgressControlError(
                "Accepted action does not match progress-aware decision"
            )

        before = self._pending_pre_fingerprint
        after = evidence_fingerprint(state)
        evidence_changed = after != before
        marked_no_progress = False

        if evidence_changed:
            self._evidence_epoch += 1
            self._blocked = {}
            self._progress_events += 1
        elif accepted_signature[0] in INFORMATION_SEEKING_ACTIONS:
            self._blocked[accepted_signature] = (
                self._blocked.get(accepted_signature, 0) + 1
            )
            self._no_progress_marks += 1
            marked_no_progress = True

        self._progress_trace.append({
            "accepted_state_step": state.get("step"),
            "action": self._signature_dict(accepted_signature),
            "evidence_changed": evidence_changed,
            "marked_no_progress": marked_no_progress,
            "evidence_epoch_after": self._evidence_epoch,
            "blocked_actions_after": self._blocked_rows(),
        })

        self._evidence_fingerprint = after
        self._pending_pre_fingerprint = None
        self._pending_signature = None

    def get_run_metadata(self) -> dict[str, Any]:
        metadata = super().get_run_metadata()
        metadata.update({
            "state_strategy": self.state_strategy,
            "information_seeking_action_types": sorted(
                INFORMATION_SEEKING_ACTIONS
            ),
            "evidence_epoch": self._evidence_epoch,
            "no_progress_marks": self._no_progress_marks,
            "progress_events": self._progress_events,
            "guard_interventions": self._guard_interventions,
            "guard_retry_calls": self._guard_retry_calls,
            "guard_retry_noncompliance": (
                self._guard_retry_noncompliance
            ),
            "blocked_actions_final": self._blocked_rows(),
            "progress_trace": deepcopy(self._progress_trace),
            "guard_trace": deepcopy(self._guard_trace),
        })
        return metadata
