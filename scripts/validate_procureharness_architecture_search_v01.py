"""Validate the frozen ProcureHarness architecture-search v0.1 protocol."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = (
    ROOT / "docs" / "procureharness-architecture-search-v0.1-protocol.json"
)
COVERAGE_RESULTS_PATH = (
    ROOT / "evidence" / "coverage-repair-confirmatory-v0.1" / "results.json"
)

EXPECTED_REQUIRED_CORE = [
    "obligation_router",
    "procurement_skill_graph",
    "event_interrupt_control",
    "deterministic_forced_transitions",
]
EXPECTED_SKILLS = [
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
EXPECTED_AXES = {
    "obligation_routing": [
        "deterministic_priority",
        "hybrid_llm_tiebreak",
    ],
    "local_planning": ["none", "bounded_local_plan"],
    "skill_reasoning": ["direct_action", "bounded_mini_react"],
    "verification": [
        "none",
        "deterministic_visible_invariants",
        "single_terminal_llm_critique",
    ],
    "fallback": ["none", "bounded_react_fallback"],
}
EXPECTED_DEFERRED = [
    "persistent_memory_or_AWM",
    "knowledge_graph_or_GraphRAG",
    "cross_episode_self_improvement",
    "dynamic_model_routing_or_Jev",
    "forecasting_tools",
    "multi_agent_orchestration",
    "long_running_checkpoint_rehydration",
]
EXPECTED_PHASE2 = [
    "persistent workflow memory/AWM",
    "operational knowledge graph",
    "forecasting/risk tools",
    "dynamic low-cost/strong-model routing",
    "cross-episode self-improvement",
    "long-running checkpoint/resume state",
]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _pair(actual: Any, expected: list[int], label: str) -> None:
    if actual != expected:
        raise ValueError(
            f"{label} mismatch: expected={expected}, actual={actual}"
        )


def _validate_comparator_anchors(protocol: dict[str, Any]) -> None:
    frozen = _load(COVERAGE_RESULTS_PATH)["rows"]
    anchors = protocol["frozen_development_comparators"]

    for protocol_id, evidence_id in (
        ("coverage_repair", "coverage_repair"),
        ("react", "react"),
        ("factual_context", "factual_context"),
    ):
        actual = anchors[protocol_id]
        expected = frozen[evidence_id]
        if actual["runs"] != expected["runs"]:
            raise ValueError(f"{protocol_id}.runs drift")
        _pair(
            actual["terminal_feasible"],
            expected["terminal_feasible"],
            f"{protocol_id}.terminal_feasible",
        )
        _pair(
            actual["feasible_obligation_success"],
            expected["feasible_obligation_success"],
            f"{protocol_id}.feasible_obligation_success",
        )
        _pair(
            actual["strict_v02"],
            expected["strict_v02"],
            f"{protocol_id}.strict_v02",
        )
        _pair(
            actual["economic_objective"],
            expected["economic_objective"],
            f"{protocol_id}.economic_objective",
        )
        obligations = _load(COVERAGE_RESULTS_PATH)["unresolved_obligations"][
            evidence_id
        ]
        _pair(
            actual["obligation_resolution"],
            [obligations["resolved"], obligations["actionable"]],
            f"{protocol_id}.obligation_resolution",
        )
        for field in (
            "accepted_actions",
            "model_calls",
            "total_tokens",
        ):
            if actual[field] != expected[field]:
                raise ValueError(f"{protocol_id}.{field} drift")
        _close(
            actual["latency_ms"],
            expected["latency_ms"],
            f"{protocol_id}.latency_ms",
        )
        _close(
            actual["known_cost_usd"],
            expected["known_cost_usd"],
            f"{protocol_id}.known_cost_usd",
        )


def validate_protocol(protocol: dict[str, Any] | None = None) -> None:
    protocol = protocol or _load(PROTOCOL_PATH)

    if protocol.get("schema_version") != "0.1.0":
        raise ValueError("ProcureHarness protocol schema version drift")
    if protocol.get("protocol_id") != (
        "procureharness-architecture-search-v0.1"
    ):
        raise ValueError("ProcureHarness protocol id drift")
    if protocol.get("status") != "preregistered_no_search_runs":
        raise ValueError("Architecture search must remain prospective")

    scope = protocol.get("scientific_scope") or {}
    if scope.get("phase") != "agentic_design_pattern_search":
        raise ValueError("Phase-1 causal scope drift")
    forbidden = set(scope.get("forbidden_claims") or [])
    if "global optimum over all possible agent architectures" not in forbidden:
        raise ValueError("Global-optimum anti-claim was removed")
    if "maximum achievable LongProcureBench score" not in forbidden:
        raise ValueError("Maximum-score anti-claim was removed")

    exposure = protocol.get("benchmark_exposure") or {}
    dev = exposure.get("development_exposed") or {}
    if (dev.get("episodes"), dev.get("count")) != ("001-020", 20):
        raise ValueError("Development exposure range drift")
    if dev.get("fresh_test_claim_allowed") is not False:
        raise ValueError("001-020 cannot become fresh test evidence")

    old = exposure.get("prior_heldout_exposed") or {}
    if (old.get("episodes"), old.get("count")) != ("021-030", 10):
        raise ValueError("Prior held-out exposure range drift")
    if old.get("role") != "diagnostic_only_for_new_method":
        raise ValueError("021-030 must remain diagnostic-only")
    if old.get("fresh_test_claim_allowed") is not False:
        raise ValueError("021-030 cannot become fresh test evidence")

    future = exposure.get("required_new_collection") or []
    if len(future) != 2:
        raise ValueError("Exactly two future 10-episode slices are required")
    validation, final = future
    if (
        validation.get("episodes"),
        validation.get("count"),
        validation.get("role"),
        validation.get("may_guide_design"),
        validation.get("final_method_claim_set"),
    ) != (
        "031-040",
        10,
        "architecture_search_validation",
        True,
        False,
    ):
        raise ValueError("031-040 search-validation contract drift")
    if (
        final.get("episodes"),
        final.get("count"),
        final.get("role"),
        final.get("may_guide_design"),
        final.get("final_method_claim_set"),
    ) != (
        "041-050",
        10,
        "final_method_test",
        False,
        True,
    ):
        raise ValueError("041-050 final-test contract drift")
    if any(
        row.get("state_at_freeze") != "not_collected_or_authored"
        for row in future
    ):
        raise ValueError("Future-set freeze-state history was rewritten")

    defaults = protocol.get("execution_defaults") or {}
    expected_defaults = {
        "model": "openai/gpt-5.6-sol",
        "reasoning_effort": "medium",
        "temperature": None,
        "temperature_mode": "omitted",
        "max_actions": 50,
        "context_strategy": "factual_compiled_v0.1",
        "no_oracle_or_evaluator_access": True,
    }
    if defaults != expected_defaults:
        raise ValueError(
            f"Execution defaults drift: expected={expected_defaults!r}, "
            f"actual={defaults!r}"
        )

    _validate_comparator_anchors(protocol)

    grammar = protocol.get("architecture_grammar") or {}
    if grammar.get("required_core") != EXPECTED_REQUIRED_CORE:
        raise ValueError("Required ProcureHarness core changed")
    if grammar.get("procurement_skills") != EXPECTED_SKILLS:
        raise ValueError("Procurement skill vocabulary changed")
    axes = {
        row["name"]: row["choices"]
        for row in grammar.get("searchable_axes") or []
    }
    if axes != EXPECTED_AXES:
        raise ValueError("Frozen architecture grammar changed")
    if grammar.get("deferred_harness_axes") != EXPECTED_DEFERRED:
        raise ValueError("Deferred harness-axis boundary changed")

    limits = grammar.get("hard_complexity_limits") or {}
    if limits != {
        "max_model_calls_between_accepted_actions": 3,
        "max_local_plan_steps": 4,
        "max_react_fallback_actions": 3,
        "multi_agent": False,
        "persistent_cross_episode_memory": False,
    }:
        raise ValueError("Architecture complexity limits changed")

    search = protocol.get("search_procedure") or {}
    if search.get("max_rounds") != 3:
        raise ValueError("Search-round budget changed")
    if search.get("max_new_candidates_per_round") != 6:
        raise ValueError("Per-round candidate budget changed")
    if search.get("max_unique_candidates") != 18:
        raise ValueError("Total candidate budget changed")
    if (
        search["max_rounds"] * search["max_new_candidates_per_round"]
        != search["max_unique_candidates"]
    ):
        raise ValueError("Search budget is internally inconsistent")

    screen = search.get("screening") or {}
    if (
        screen.get("episodes"),
        screen.get("repeats_per_episode"),
        screen.get("max_runs_per_candidate"),
    ) != ("001-020", 1, 20):
        raise ValueError("Cheap screening contract changed")

    confirm = search.get("development_confirmation") or {}
    if (
        confirm.get("episodes"),
        confirm.get("repeats_per_episode"),
        confirm.get("max_candidates_per_round"),
        confirm.get("runs_per_candidate"),
    ) != ("001-020", 3, 2, 60):
        raise ValueError("Development confirmation contract changed")
    if "do not rerun" not in confirm.get("baseline_policy", ""):
        raise ValueError("Frozen development baselines may not be rerun")

    validation_cfg = search.get("search_validation") or {}
    if (
        validation_cfg.get("episodes"),
        validation_cfg.get("repeats_per_episode"),
        validation_cfg.get("matched_baselines"),
    ) != ("031-040", 3, ["coverage_repair", "react"]):
        raise ValueError("Search-validation execution contract changed")
    if validation_cfg.get("requires_package_freeze_before_calls") is not True:
        raise ValueError("031-040 package must freeze before model calls")

    ceiling = search.get("ceiling_stop_rule") or {}
    if ceiling.get("plateau_rounds") != 2:
        raise ValueError("Architecture plateau rule changed")
    if ceiling.get("not_a_global_optimum_claim") is not True:
        raise ValueError("Search plateau cannot become a global-optimum claim")

    reporting = protocol.get("reporting_contract") or {}
    if reporting.get("no_weighted_composite_score") is not True:
        raise ValueError("Weighted composite score is prohibited")
    if reporting.get("primary_quality_metric") != (
        "feasible_obligation_success"
    ):
        raise ValueError("Primary quality metric drift")

    required_quality = {
        "terminal_feasible",
        "strict_v02",
        "obligation_resolution_rate",
        "economic_objective_satisfied",
    }
    if set(reporting.get("mandatory_quality_metrics") or []) != (
        required_quality
    ):
        raise ValueError("Mandatory quality metric set changed")

    required_economic = {
        "feasible_price_regret_native",
        "feasible_price_regret_pct",
        "paired_savings_vs_baseline_native",
        "paired_savings_vs_baseline_pct",
    }
    if set(reporting.get("economic_metrics") or []) != required_economic:
        raise ValueError("Economic metric set changed")

    required_efficiency = {
        "accepted_actions",
        "model_calls",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "latency_ms",
        "known_cost_usd",
        "deterministic_action_fraction",
    }
    if set(reporting.get("efficiency_metrics") or []) != required_efficiency:
        raise ValueError("Efficiency metric set changed")

    regret = reporting.get("economic_regret_v01") or {}
    if regret.get("implementation_status") != (
        "required_before_paid_architecture_search"
    ):
        raise ValueError("Economic regret must precede paid architecture search")
    if regret.get("feasible_price_regret_native") != (
        "max(0, selected_cost - oracle_cost)"
    ):
        raise ValueError("Native regret definition changed")
    if "not_eligible" not in regret.get(
        "infeasible_or_no_award_policy", ""
    ):
        raise ValueError("Infeasible trajectories must not get arbitrary regret")
    if "never sum different native currencies" not in regret.get(
        "aggregation", ""
    ):
        raise ValueError("Cross-currency regret aggregation is prohibited")

    frontier = protocol.get("admissibility_and_frontier") or {}
    floor = frontier.get("development_confirmation_floor") or {}
    if floor != {
        "feasible_obligation_success_min": [47, 60],
        "strict_v02_min": [27, 60],
        "economic_objective_min": [27, 60],
    }:
        raise ValueError("Development quality floor changed")

    dimensions = frontier.get("frontier_dimensions") or {}
    if set(dimensions.get("maximize") or []) != {
        "feasible_obligation_success",
        "strict_v02",
        "obligation_resolution_rate",
        "economic_objective_satisfied",
    }:
        raise ValueError("Pareto maximize dimensions changed")
    if set(dimensions.get("minimize") or []) != {
        "feasible_price_regret_pct",
        "known_cost_usd",
        "total_tokens",
        "latency_ms",
        "model_calls",
    }:
        raise ValueError("Pareto minimize dimensions changed")

    promotion = frontier.get("development_promotion_branch") or []
    if len(promotion) != 2:
        raise ValueError("Exactly two development promotion branches required")
    if "3/60" not in promotion[0] or "Coverage+Repair" not in promotion[0]:
        raise ValueError("Quality promotion threshold changed")
    if "20%" not in promotion[1] or "Coverage+Repair" not in promotion[1]:
        raise ValueError("Efficiency promotion threshold changed")

    freeze = protocol.get("final_method_freeze") or {}
    final_test = freeze.get("final_test") or {}
    if final_test != {
        "episodes": "041-050",
        "repeats_per_episode": 3,
        "rows": [
            "procureharness_winner",
            "coverage_repair",
            "react",
            "reference_control",
        ],
        "no_tuning_after_first_model_call": True,
    }:
        raise ValueError("Final method-test matrix changed")
    gates = freeze.get("method_claim_gate") or []
    if len(gates) != 2:
        raise ValueError("Exactly two final method-claim branches required")
    if (
        "3/30" not in gates[0]
        or "1/30" not in gates[0]
        or "max(Coverage+Repair, ReAct)" not in gates[0]
        or "minimum regret" not in gates[0]
    ):
        raise ValueError("Final quality-branch threshold changed")
    if (
        "30%" not in gates[1]
        or "1/30" not in gates[1]
        or "max(Coverage+Repair, ReAct)" not in gates[1]
        or "cheaper of Coverage+Repair and ReAct" not in gates[1]
    ):
        raise ValueError("Final efficiency-branch threshold changed")

    phase2 = protocol.get("phase2_after_pattern_freeze") or {}
    if phase2.get("axes_to_test_one_at_a_time") != EXPECTED_PHASE2:
        raise ValueError("Phase-2 harness sequence changed")
    if "Only after" not in phase2.get("entry_condition", ""):
        raise ValueError("Harness phase may not precede design-pattern freeze")
    if "matched ablation" not in phase2.get("rule", ""):
        raise ValueError("Every phase-2 harness axis requires ablation")


def main() -> None:
    validate_protocol()
    print("ProcureHarness architecture-search v0.1 protocol validated.")
    print(
        "phase1=agent-design-pattern search; old 021-030 diagnostic-only; "
        "new 031-040 validation; untouched 041-050 final test"
    )
    print(
        "search budget=3 rounds x <=6 candidates; stop after 2 Pareto-plateau "
        "rounds; economic regret required before paid search"
    )


if __name__ == "__main__":
    main()
