"""Validate the frozen development comparator/reporting matrix."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from audit_cross_family_reactive_v01 import load_frozen_summary


MATRIX_PATH = (
    ROOT
    / "evidence"
    / "development-comparator-matrix-v0.1"
    / "matrix.json"
)

EXPECTED_MODELS = {
    "openai/gpt-5.6-sol",
    "anthropic/claude-opus-5-5",
    "gemini/gemini-3.8-flash",
}
EXPECTED_HELDOUT_IDS = {
    "reference-control",
    "raw-reactive-openai",
    "raw-reactive-anthropic",
    "raw-reactive-gemini",
    "context-compiled-openai",
    "react-openai",
}
EXPECTED_DROPPED = {
    "operational-ledger-reactive-v0.1",
    "working-plan-reactive-v0.1",
    "always-replan-verifier-v0.1",
    "progress-aware-reactive-v0.1",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pair(value: Any, expected: tuple[int, int], label: str) -> None:
    if value != list(expected):
        raise ValueError(
            f"{label} mismatch: expected={list(expected)}, actual={value}"
        )


def _close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(
        float(actual),
        float(expected),
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"{label} mismatch: expected={expected}, actual={actual}"
        )


def _method_map(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    methods = matrix.get("development_methods")
    if not isinstance(methods, list):
        raise ValueError("development_methods must be a list")
    out = {}
    for method in methods:
        method_id = method.get("id")
        if not isinstance(method_id, str) or not method_id:
            raise ValueError("Every development method requires an id")
        if method_id in out:
            raise ValueError(f"Duplicate development method id: {method_id}")
        out[method_id] = method
    return out


def validate_matrix(matrix: dict[str, Any] | None = None) -> None:
    matrix = matrix or _load(MATRIX_PATH)

    if matrix.get("schema_version") != "0.1.0":
        raise ValueError("Comparator matrix schema version mismatch")
    if matrix.get("status") != "development_comparator_set_frozen":
        raise ValueError("Development comparator set is not frozen")
    if matrix.get("heldout_touched") is not False:
        raise ValueError("Comparator freeze must precede held-out access")

    benchmark = matrix.get("benchmark_slice") or {}
    if benchmark.get("development_episodes") != 20:
        raise ValueError("Development episode count must remain 20")
    if benchmark.get("heldout_reserved_starting_states") != 10:
        raise ValueError("Held-out reservation count must remain 10")
    if benchmark.get("heldout_episodes_authored") != 0:
        raise ValueError(
            "No held-out episode may be authored before this freeze"
        )

    reporting = matrix.get("reporting_contract") or {}
    if reporting.get("primary_quality_metric") != (
        "feasible_obligation_success"
    ):
        raise ValueError("Primary paper metric changed after development")

    required_quality = {
        "terminal_feasible",
        "feasible_obligation_success",
        "episode_success_v02",
        "obligation_resolution_rate",
        "economic_objective_satisfied",
    }
    if set(reporting.get("quality_metrics") or []) != required_quality:
        raise ValueError("Frozen quality metric set changed")

    required_efficiency = {
        "accepted_actions",
        "model_calls",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "latency_ms",
        "cost_usd",
    }
    if set(reporting.get("efficiency_metrics") or []) != required_efficiency:
        raise ValueError("Frozen efficiency metric set changed")

    methods = _method_map(matrix)
    cross = methods.get("raw-reactive-cross-family-v0.1") or {}
    if not cross.get("heldout_eligible"):
        raise ValueError("Cross-family raw baseline must remain held-out eligible")
    if set(cross.get("models") or []) != EXPECTED_MODELS:
        raise ValueError("Frozen cross-family model identifiers changed")

    for method_id in EXPECTED_DROPPED:
        method = methods.get(method_id)
        if method is None:
            raise ValueError(f"Missing dropped development method: {method_id}")
        if method.get("status") != "dropped":
            raise ValueError(f"Dropped method status changed: {method_id}")
        if method.get("heldout_eligible") is not False:
            raise ValueError(
                f"Dropped method became held-out eligible: {method_id}"
            )
        if method.get("gate_passed") is not False:
            raise ValueError(
                f"Dropped method gate status changed: {method_id}"
            )

    protocol = matrix.get("heldout_protocol") or {}
    if protocol.get("frozen_before_episode_authoring") is not True:
        raise ValueError("Held-out protocol must be frozen before authoring")
    if protocol.get("heldout_episode_count") != 10:
        raise ValueError("Held-out episode count must remain 10")
    if protocol.get("model_backed_repeats") != 3:
        raise ValueError("Held-out model-backed repeats must remain 3")
    if protocol.get("reference_control_repeats") != 1:
        raise ValueError("Reference control must run once per held-out episode")
    if protocol.get("expected_model_backed_runs") != 150:
        raise ValueError("Expected held-out model-backed run count changed")
    if protocol.get("expected_reference_control_runs") != 10:
        raise ValueError("Expected held-out reference-control count changed")

    rows = protocol.get("eligible_rows") or []
    row_ids = {row.get("id") for row in rows}
    if row_ids != EXPECTED_HELDOUT_IDS:
        raise ValueError("Held-out eligible row set changed")
    if sum(int(row["runs_if_10_episodes"]) for row in rows if row["model"]) != 150:
        raise ValueError("Held-out model-backed row counts do not sum to 150")
    for row in rows:
        model = row.get("model")
        if model is not None and model not in EXPECTED_MODELS:
            raise ValueError(f"Unexpected held-out model: {model}")

    tables = {table["id"]: table for table in matrix.get("paper_tables") or []}
    expected_tables = {
        "table-provider-diverse-raw-reactive",
        "table-openai-matched-methods",
        "table-development-mechanism-analysis",
        "table-heldout-failure-taxonomy",
    }
    if set(tables) != expected_tables:
        raise ValueError("Frozen paper table set changed")

    if tables["table-openai-matched-methods"].get(
        "paired_bootstrap_against"
    ) != "context-compiled-openai":
        raise ValueError("Matched held-out bootstrap baseline changed")

    # Cross-family anchor is reconstructed from the checksum-locked summary.
    cross_summary = load_frozen_summary()
    combined = cross_summary["combined"]
    anchors = matrix["development_anchor_results"]["cross_family_combined"]
    if anchors["runs"] != combined["runs"]:
        raise ValueError("Cross-family run anchor drift")
    _pair(
        anchors["terminal_feasible"],
        (combined["terminal_feasible"], combined["runs"]),
        "cross-family terminal",
    )
    _pair(
        anchors["feasible_obligation_success"],
        (combined["feasible_obligation_success"], combined["runs"]),
        "cross-family feasible-obligation",
    )
    _pair(
        anchors["episode_success_v02"],
        (combined["episode_success_v02"], combined["runs"]),
        "cross-family strict",
    )
    _pair(
        anchors["obligation_resolution"],
        (
            combined["resolved_obligations"],
            combined["actionable_obligations"],
        ),
        "cross-family obligation resolution",
    )
    if anchors["total_tokens"] != combined["total_tokens"]:
        raise ValueError("Cross-family token anchor drift")
    _close(
        anchors["known_cost_usd"],
        combined["known_cost_usd"],
        "cross-family cost",
    )

    context = _load(
        ROOT
        / "evidence"
        / "context-compiled-reactive-v0.1"
        / "comparison.json"
    )
    react = _load(
        ROOT
        / "evidence"
        / "react-comparator-v0.1"
        / "comparison.json"
    )
    ledger = _load(
        ROOT
        / "evidence"
        / "operational-ledger-reactive-v0.1"
        / "comparison.json"
    )
    plan = _load(
        ROOT
        / "evidence"
        / "working-plan-reactive-v0.1"
        / "comparison.json"
    )
    replan = _load(
        ROOT
        / "evidence"
        / "always-replan-verifier-v0.1"
        / "comparison.json"
    )
    progress = _load(
        ROOT
        / "evidence"
        / "progress-aware-reactive-v0.1"
        / "comparison.json"
    )

    anchor_results = matrix["development_anchor_results"]
    raw = context["raw_history"]
    ctx = context["context_compiled"]
    react_row = react["react"]

    for name, source in (
        ("openai_raw_history", raw),
        ("openai_context_compiled", ctx),
        ("openai_react", react_row),
    ):
        anchor = anchor_results[name]
        _pair(
            anchor["terminal_feasible"],
            (source["terminal_feasible"], 60),
            f"{name} terminal",
        )
        _pair(
            anchor["feasible_obligation_success"],
            (source["feasible_obligation_success"], 60),
            f"{name} feasible-obligation",
        )
        _pair(
            anchor["episode_success_v02"],
            (source["episode_success_v02"], 60),
            f"{name} strict",
        )
        _pair(
            anchor["obligation_resolution"],
            (
                source["resolved_obligations"],
                source["actionable_obligations"],
            ),
            f"{name} obligation resolution",
        )
        if anchor["total_tokens"] != source["total_tokens"]:
            raise ValueError(f"{name} token anchor drift")
        source_cost = source.get("cost_usd", source.get("known_cost_usd"))
        _close(anchor["known_cost_usd"], source_cost, f"{name} cost")

    for label, evidence in (
        ("operational-ledger-reactive-v0.1", ledger),
        ("working-plan-reactive-v0.1", plan),
        ("always-replan-verifier-v0.1", replan),
        ("progress-aware-reactive-v0.1", progress),
    ):
        gate = evidence.get("predeclared_gate") or {}
        if gate.get("passed") is not False:
            raise ValueError(f"Dropped mechanism no longer fails gate: {label}")

    if react.get("role") != "external_comparator":
        raise ValueError("ReAct role changed from external comparator")
    if react["decision"].get("inclusion_gate") is not None:
        raise ValueError("ReAct must not acquire a development inclusion gate")


def main() -> None:
    validate_matrix()
    print(
        "Development comparator/reporting matrix validated: "
        "held-out eligible set frozen, 150 model-backed runs + "
        "10 reference controls planned."
    )


if __name__ == "__main__":
    main()
