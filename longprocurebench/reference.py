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
    "electrical-bfar-generator-006": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-bfar-a"},
        {"type": "send_rfq", "supplier_id": "syn-bfar-b"},
        {"type": "send_rfq", "supplier_id": "syn-bfar-c"},
        {"type": "send_follow_up", "supplier_id": "syn-bfar-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-bfar-c"},
        {"type": "answer_supplier_question", "supplier_id": "syn-bfar-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-bfar-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-bfar-c", "quote_event_id": "e6"}]}},
    ],
    "electrical-negros-wire-007": [
        {"type": "request_buyer_clarification"},
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-negros-a"},
        {"type": "send_rfq", "supplier_id": "syn-negros-b"},
        {"type": "send_rfq", "supplier_id": "syn-negros-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-negros-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-negros-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-negros-c", "quote_event_id": "e5"}]}},
    ],
    "electrical-burauen-generator-008": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-burauen-a"},
        {"type": "send_rfq", "supplier_id": "syn-burauen-b"},
        {"type": "send_rfq", "supplier_id": "syn-burauen-c"},
        {"type": "evaluate_quotes"},
        {"type": "request_quote_revision", "supplier_id": "syn-burauen-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-burauen-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-burauen-c", "quote_event_id": "e5"}]}},
    ],
    "electrical-highpoint-transformer-009": [
        {"type": "request_buyer_clarification"},
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-hp-xfmr-a"},
        {"type": "send_rfq", "supplier_id": "syn-hp-xfmr-b"},
        {"type": "send_rfq", "supplier_id": "syn-hp-xfmr-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-hp-xfmr-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-hp-xfmr-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-hp-xfmr-c", "quote_event_id": "e5"}]}},
    ],
    "electrical-painesville-switchgear-010": [
        {"type": "request_buyer_clarification"},
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-pain-a"},
        {"type": "send_rfq", "supplier_id": "syn-pain-b"},
        {"type": "send_rfq", "supplier_id": "syn-pain-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-pain-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "arguments": {"awards": [
            {"scope": "lot-1", "supplier_id": "syn-pain-b", "quote_event_id": "e3"},
            {"scope": "lot-2", "supplier_id": "syn-pain-c", "quote_event_id": "e5"}
        ]}},
    ],
    "electrical-sagada-generator-011": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-sagada-a"},
        {"type": "send_rfq", "supplier_id": "syn-sagada-b"},
        {"type": "send_rfq", "supplier_id": "syn-sagada-c"},
        {"type": "issue_amendment"},
        {"type": "request_quote_revision", "supplier_id": "syn-sagada-a"},
        {"type": "send_follow_up", "supplier_id": "syn-sagada-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-sagada-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-sagada-c", "quote_event_id": "e6"}]}},
    ],
    "electrical-dla-relay-012": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-relay-a"},
        {"type": "send_rfq", "supplier_id": "syn-relay-b"},
        {"type": "send_rfq", "supplier_id": "syn-relay-c"},
        {"type": "evaluate_quotes"},
        {"type": "send_follow_up", "supplier_id": "syn-relay-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-relay-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-relay-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-relay-c", "quote_event_id": "e6"}]}},
    ],
    "electrical-dla-transformer-013": [
        {"type": "request_buyer_clarification"},
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-dla-xfmr-a"},
        {"type": "send_rfq", "supplier_id": "syn-dla-xfmr-b"},
        {"type": "send_rfq", "supplier_id": "syn-dla-xfmr-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-dla-xfmr-c"},
        {"type": "answer_supplier_question", "supplier_id": "syn-dla-xfmr-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-dla-xfmr-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-dla-xfmr-c", "quote_event_id": "e6"}]}},
    ],
    "electrical-dla-battery-supply-014": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-bps-a"},
        {"type": "send_rfq", "supplier_id": "syn-bps-b"},
        {"type": "send_rfq", "supplier_id": "syn-bps-c"},
        {"type": "send_rfq", "supplier_id": "syn-bps-d"},
        {"type": "request_quote_revision", "supplier_id": "syn-bps-d"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "arguments": {"awards": [
            {"scope": "lot-0001", "supplier_id": "syn-bps-c", "quote_event_id": "e3"},
            {"scope": "lot-0002", "supplier_id": "syn-bps-c", "quote_event_id": "e3"},
            {"scope": "lot-0003", "supplier_id": "syn-bps-c", "quote_event_id": "e3"},
            {"scope": "lot-0004", "supplier_id": "syn-bps-d", "quote_event_id": "e5"},
            {"scope": "lot-0005", "supplier_id": "syn-bps-d", "quote_event_id": "e5"}
        ]}},
    ],
    "electrical-dla-battery-charger-015": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-charger-a"},
        {"type": "send_rfq", "supplier_id": "syn-charger-b"},
        {"type": "send_rfq", "supplier_id": "syn-charger-c"},
        {"type": "evaluate_quotes"},
        {"type": "request_quote_revision", "supplier_id": "syn-charger-c"},
        {"type": "answer_supplier_question", "supplier_id": "syn-charger-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-charger-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-charger-c", "quote_event_id": "e6"}]}},
    ],
    "electrical-dla-power-supply-016": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-ps-a"},
        {"type": "send_rfq", "supplier_id": "syn-ps-b"},
        {"type": "send_rfq", "supplier_id": "syn-ps-c"},
        {"type": "issue_amendment"},
        {"type": "request_quote_revision", "supplier_id": "syn-ps-a"},
        {"type": "request_quote_revision", "supplier_id": "syn-ps-b"},
        {"type": "send_follow_up", "supplier_id": "syn-ps-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-ps-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-ps-c", "quote_event_id": "e7"}]}},
    ],
    "electrical-dla-qpl-breaker-017": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-qpl-a"},
        {"type": "send_rfq", "supplier_id": "syn-qpl-b"},
        {"type": "send_rfq", "supplier_id": "syn-qpl-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-qpl-c"},
        {"type": "answer_supplier_question", "supplier_id": "syn-qpl-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-qpl-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-qpl-c", "quote_event_id": "e5"}]}},
    ],
    "electrical-highpoint-cable-018": [
        {"type": "request_buyer_clarification"},
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-hpc-a"},
        {"type": "send_rfq", "supplier_id": "syn-hpc-b"},
        {"type": "send_rfq", "supplier_id": "syn-hpc-c"},
        {"type": "request_quote_revision", "supplier_id": "syn-hpc-b"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "arguments": {"awards": [
            {"scope": "lot-2904", "supplier_id": "syn-hpc-b", "quote_event_id": "e5"},
            {"scope": "lot-79", "supplier_id": "syn-hpc-b", "quote_event_id": "e5"},
            {"scope": "lot-80", "supplier_id": "syn-hpc-b", "quote_event_id": "e5"},
            {"scope": "lot-4523", "supplier_id": "syn-hpc-c", "quote_event_id": "e4"},
            {"scope": "lot-59", "supplier_id": "syn-hpc-c", "quote_event_id": "e4"}
        ]}},
    ],
    "electrical-usaf-ups-019": [
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-ups-a"},
        {"type": "send_rfq", "supplier_id": "syn-ups-b"},
        {"type": "send_rfq", "supplier_id": "syn-ups-c"},
        {"type": "evaluate_quotes"},
        {"type": "request_quote_revision", "supplier_id": "syn-ups-c"},
        {"type": "answer_supplier_question", "supplier_id": "syn-ups-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-ups-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-ups-c", "quote_event_id": "e6"}]}},
    ],
    "electrical-vre-generator-020": [
        {"type": "request_buyer_clarification"},
        {"type": "identify_suppliers"},
        {"type": "send_rfq", "supplier_id": "syn-vre-a"},
        {"type": "send_rfq", "supplier_id": "syn-vre-b"},
        {"type": "send_rfq", "supplier_id": "syn-vre-c"},
        {"type": "issue_amendment"},
        {"type": "request_quote_revision", "supplier_id": "syn-vre-a"},
        {"type": "request_quote_revision", "supplier_id": "syn-vre-b"},
        {"type": "send_follow_up", "supplier_id": "syn-vre-c"},
        {"type": "evaluate_quotes"},
        {"type": "award_supplier", "supplier_id": "syn-vre-c", "arguments": {"awards": [{"scope": "package", "supplier_id": "syn-vre-c", "quote_event_id": "e8"}]}},
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
