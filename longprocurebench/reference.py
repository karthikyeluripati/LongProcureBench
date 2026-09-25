"""Oracle-aware reference control for runner/evaluator sanity checks."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


REFERENCE_DECISIONS: dict[str, list[dict[str, Any]]] = {
    "electrical-bongabon-generator-001": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-gen-a"},
        {"type": "send_rfq", "supplier_id": "syn-gen-b"},
        {"type": "send_rfq", "supplier_id": "syn-gen-c"},
        {"type": "send_follow_up", "supplier_id": "syn-gen-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-gen-c"},
        {"type": "evaluate_quotes"},
        {
            "type": "award_supplier",
            "supplier_id": "syn-gen-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-gen-c",
                        "quote_event_id": "e5",
                    }
                ]
            },
        },
    ],
    "electrical-national-museum-lighting-002": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-light-a"},
        {"type": "send_rfq", "supplier_id": "syn-light-b"},
        {"type": "send_rfq", "supplier_id": "syn-light-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-light-c"},
        {"type": "evaluate_quotes"},
        {
            "type": "award_supplier",
            "arguments": {
                "awards": [
                    {
                        "scope": "lot-1",
                        "supplier_id": "syn-light-a",
                        "quote_event_id": "e1",
                    },
                    {
                        "scope": "lot-2",
                        "supplier_id": "syn-light-c",
                        "quote_event_id": "e4",
                    },
                ]
            },
        },
    ],
    "electrical-neust-cable-003": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-wire-a"},
        {"type": "send_rfq", "supplier_id": "syn-wire-b"},
        {"type": "send_rfq", "supplier_id": "syn-wire-c"},
        {"type": "issue_amendment"},
        {"type": "request_quote_revision", "supplier_id": "syn-wire-a"},
        {"type": "request_quote_revision", "supplier_id": "syn-wire-b"},
        {"type": "send_follow_up", "supplier_id": "syn-wire-c"},
        {"type": "evaluate_quotes"},
        {
            "type": "award_supplier",
            "supplier_id": "syn-wire-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-wire-c",
                        "quote_event_id": "e7",
                    }
                ]
            },
        },
    ],
    "electrical-dla-breaker-004": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-breaker-a"},
        {"type": "send_rfq", "supplier_id": "syn-breaker-b"},
        {"type": "send_rfq", "supplier_id": "syn-breaker-c"},
        {"type": "evaluate_quotes"},
        {"type": "request_quote_revision", "supplier_id": "syn-breaker-c"},
        {"type": "evaluate_quotes"},
        {
            "type": "award_supplier",
            "supplier_id": "syn-breaker-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-breaker-c",
                        "quote_event_id": "e5",
                    }
                ]
            },
        },
    ],
    "electrical-barrie-transformer-005": [
        {"type": "request_buyer_clarification"},
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-xfmr-a"},
        {"type": "send_rfq", "supplier_id": "syn-xfmr-b"},
        {"type": "request_quote_revision", "supplier_id": "syn-xfmr-b"},
        {"type": "answer_supplier_question", "supplier_id": "syn-xfmr-b"},
        {"type": "send_rfq", "supplier_id": "syn-xfmr-c"},
        {"type": "evaluate_quotes"},
        {
            "type": "award_supplier",
            "supplier_id": "syn-xfmr-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-xfmr-b",
                        "quote_event_id": "e5",
                    }
                ]
            },
        },
    ],
}


class ScriptedReferencePolicy:
    """Reference control; uses frozen scripts and is not a competitive baseline."""

    policy_id = "scripted-reference-v0.1"
    policy_kind = "reference_control"

    def __init__(self):
        self._episode_id: str | None = None
        self._index = 0

    @classmethod
    def episode_ids(cls) -> list[str]:
        return sorted(REFERENCE_DECISIONS)

    def reset(self, state: dict[str, Any]) -> None:
        episode_id = state["episode_id"]
        if episode_id not in REFERENCE_DECISIONS:
            raise ValueError(
                f"No reference script for episode: {episode_id}"
            )
        self._episode_id = episode_id
        self._index = 0

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._episode_id is None:
            raise RuntimeError("reset() must be called before act()")
        if state["episode_id"] != self._episode_id:
            raise RuntimeError("Reference policy episode changed mid-run")
        script = REFERENCE_DECISIONS[self._episode_id]
        if self._index >= len(script):
            raise RuntimeError(
                "Reference script exhausted before episode termination"
            )
        decision = deepcopy(script[self._index])
        self._index += 1
        decision.setdefault("supplier_id", None)
        decision.setdefault("arguments", {})
        return decision
