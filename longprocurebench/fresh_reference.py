"""Oracle-aware reference control for the frozen fresh 031-050 package."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


FRESH_REFERENCE_DECISIONS = {
    "electrical-imperial-ev-phase1-031": [
        {
            "type": "request_buyer_clarification",
        },
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-31-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-31-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-31-c",
        },
        {
            "type": "send_follow_up",
            "supplier_id": "syn-31-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-31-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-31-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-imperial-ev-phase23-032": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-32-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-32-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-32-b",
        },
        {
            "type": "answer_supplier_question",
            "supplier_id": "syn-32-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-32-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-32-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-32-b",
                        "quote_event_id": "e4",
                    },
                ],
            },
        },
    ],
    "electrical-lewiston-ev-chargers-033": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-33-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-33-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-33-c",
        },
        {
            "type": "issue_amendment",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-33-a",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-33-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-33-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-33-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-33-b",
                        "quote_event_id": "e6",
                    },
                ],
            },
        },
    ],
    "electrical-idaho-falls-ev-chargers-034": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-34-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-34-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-34-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-34-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-34-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-34-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-union-township-ev-chargers-035": [
        {
            "type": "request_buyer_clarification",
        },
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-35-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-35-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-35-c",
        },
        {
            "type": "send_follow_up",
            "supplier_id": "syn-35-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-35-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-35-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-methuen-stadium-led-036": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-36-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-36-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-36-b",
        },
        {
            "type": "answer_supplier_question",
            "supplier_id": "syn-36-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-36-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-36-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-36-b",
                        "quote_event_id": "e4",
                    },
                ],
            },
        },
    ],
    "electrical-philadelphia-led-phase5-037": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-37-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-37-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-37-c",
        },
        {
            "type": "issue_amendment",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-37-a",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-37-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-37-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-37-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-37-b",
                        "quote_event_id": "e6",
                    },
                ],
            },
        },
    ],
    "electrical-hampton-fountain-led-038": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-38-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-38-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-38-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-38-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-38-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-38-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-danville-pole-transformer-039": [
        {
            "type": "request_buyer_clarification",
        },
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-39-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-39-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-39-c",
        },
        {
            "type": "send_follow_up",
            "supplier_id": "syn-39-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-39-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-39-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-danville-substation-transformers-040": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-40-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-40-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-40-b",
        },
        {
            "type": "answer_supplier_question",
            "supplier_id": "syn-40-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-40-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-40-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-40-b",
                        "quote_event_id": "e4",
                    },
                ],
            },
        },
    ],
    "electrical-danvers-transformers-041": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-41-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-41-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-41-c",
        },
        {
            "type": "issue_amendment",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-41-a",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-41-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-41-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-41-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-41-b",
                        "quote_event_id": "e6",
                    },
                ],
            },
        },
    ],
    "electrical-rocky-mount-transformer-upgrade-042": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-42-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-42-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-42-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-42-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-42-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-42-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-rocky-mount-breakers-043": [
        {
            "type": "request_buyer_clarification",
        },
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-43-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-43-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-43-c",
        },
        {
            "type": "send_follow_up",
            "supplier_id": "syn-43-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-43-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-43-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-siloam-circuit-switchers-044": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-44-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-44-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-44-b",
        },
        {
            "type": "answer_supplier_question",
            "supplier_id": "syn-44-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-44-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-44-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-44-b",
                        "quote_event_id": "e4",
                    },
                ],
            },
        },
    ],
    "electrical-eweb-mcc-vfd-plc-045": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-45-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-45-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-45-c",
        },
        {
            "type": "issue_amendment",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-45-a",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-45-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-45-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-45-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-45-b",
                        "quote_event_id": "e6",
                    },
                ],
            },
        },
    ],
    "electrical-odot-alkali-generator-046": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-46-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-46-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-46-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-46-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-46-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-46-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-portland-tx-generator-047": [
        {
            "type": "request_buyer_clarification",
        },
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-47-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-47-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-47-c",
        },
        {
            "type": "send_follow_up",
            "supplier_id": "syn-47-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-47-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-47-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
    "electrical-marshfield-generator-048": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-48-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-48-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-48-b",
        },
        {
            "type": "answer_supplier_question",
            "supplier_id": "syn-48-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-48-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-48-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-48-b",
                        "quote_event_id": "e4",
                    },
                ],
            },
        },
    ],
    "electrical-dubuque-generator-049": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-49-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-49-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-49-c",
        },
        {
            "type": "issue_amendment",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-49-a",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-49-b",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-49-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-49-b",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-49-b",
                        "quote_event_id": "e6",
                    },
                ],
            },
        },
    ],
    "electrical-philadelphia-substation-switchgear-050": [
        {
            "type": "identify_suppliers",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-50-a",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-50-b",
        },
        {
            "type": "send_rfq",
            "supplier_id": "syn-50-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "request_quote_revision",
            "supplier_id": "syn-50-c",
        },
        {
            "type": "evaluate_quotes",
        },
        {
            "type": "award_supplier",
            "supplier_id": "syn-50-c",
            "arguments": {
                "awards": [
                    {
                        "scope": "package",
                        "supplier_id": "syn-50-c",
                        "quote_event_id": "e5",
                    },
                ],
            },
        },
    ],
}


class FreshScriptedReferencePolicy:
    """Fresh-package reference control; never a competitive baseline."""

    policy_id = "scripted-fresh-reference-v0.1"
    policy_kind = "reference_control"

    def __init__(self):
        self._episode_id: str | None = None
        self._index = 0

    @classmethod
    def episode_ids(cls) -> list[str]:
        return sorted(
            FRESH_REFERENCE_DECISIONS,
            key=lambda episode_id: int(episode_id.rsplit("-", 1)[1]),
        )

    def reset(self, state: dict[str, Any]) -> None:
        episode_id = state["episode_id"]
        if episode_id not in FRESH_REFERENCE_DECISIONS:
            raise ValueError(
                f"No fresh reference script for episode: {episode_id}"
            )
        self._episode_id = episode_id
        self._index = 0

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._episode_id is None:
            raise RuntimeError("reset() must be called before act()")
        if state["episode_id"] != self._episode_id:
            raise RuntimeError("Fresh reference episode changed mid-run")
        script = FRESH_REFERENCE_DECISIONS[self._episode_id]
        if self._index >= len(script):
            raise RuntimeError(
                "Fresh reference script exhausted before episode termination"
            )
        decision = deepcopy(script[self._index])
        self._index += 1
        decision.setdefault("supplier_id", None)
        decision.setdefault("arguments", {})
        return decision
