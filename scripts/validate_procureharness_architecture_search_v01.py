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


EXPECTED_BASELINE_POLICY = {
    "reuse_frozen_evidence": True,
    "rerun_allowed": False,
    "comparators": ["coverage_repair", "react", "factual_context"],
}
EXPECTED_VALIDATION_ENTRY = {
    "requires_execution_clean": True,
    "requires_development_confirmation_floor": True,
    "requires_development_promotion_branch": True,
    "max_candidates_per_round": 2,
    "oversubscription_selection": {
        "method": "lexicographic",
        "priority": [
            {"metric": "feasible_obligation_success", "direction": "desc"},
            {"metric": "strict_v02", "direction": "desc"},
            {"metric": "economic_objective", "direction": "desc"},
            {"metric": "obligation_resolution_rate", "direction": "desc"},
            {"metric": "known_cost_usd", "direction": "asc"},
            {"metric": "total_tokens", "direction": "asc"},
            {"metric": "candidate_id", "direction": "asc"},
        ],
    },
}
EXPECTED_FRONTIER_ADMISSION = {
    "requires_execution_clean": True,
    "quality_floor_reference": (
        "per_metric_max_of_matched_coverage_repair_and_react"
    ),
    "max_deficit_runs": {
        "feasible_obligation_success": 2,
        "strict_v02": 2,
        "economic_objective": 2,
    },
    "requires_full_regret_reference_cohort_comparability": True,
}
EXPECTED_PARETO_FRONTIER = {
    "comparison_pool": (
        "all validation-admitted ProcureHarness candidates from completed "
        "rounds plus matched Coverage+Repair and ReAct baseline rows"
    ),
    "dominance_rule": (
        "A dominates B iff A is no worse than B on every frozen frontier "
        "dimension and strictly better on at least one dimension"
    ),
    "candidate_frontier_rule": (
        "a ProcureHarness candidate is on the admissible validation frontier "
        "iff it passes frontier_admission and is not dominated by any row in "
        "the comparison_pool"
    ),
    "round_update_rule": (
        "after each completed round, recompute the cumulative frontier; the "
        "round adds a new frontier point only if at least one candidate first "
        "validated in that round is on the recomputed candidate frontier and "
        "its frozen frontier vector is not equivalent to any pre-round "
        "frontier row under frontier_vector_equivalence; an exact/numerical "
        "tie does not reset the plateau counter"
    ),
    "frontier_vector_equivalence": {
        "compared_fields": [
            "feasible_obligation_success",
            "strict_v02",
            "obligation_resolution_rate",
            "economic_objective_satisfied",
            "mean_feasible_price_regret_pct_on_reference_cohort",
            "known_cost_usd",
            "total_tokens",
            "latency_ms",
            "model_calls",
        ],
        "integer_and_count_fields": "exact equality",
        "floating_fields": {
            "rel_tol": 1e-12,
            "abs_tol": 1e-9,
        },
        "candidate_id_part_of_vector": False,
    },
    "empty_regret_cohort_rule": (
        "apply reporting_contract.economic_regret_v01."
        "eligibility_aware_comparison.empty_reference_cohort_policy uniformly "
        "before Pareto dominance/equivalence"
    ),
}
EXPECTED_CEILING_RULE = {
    "plateau_rounds": 2,
    "definition": (
        "Stop agent-design-pattern search after two consecutive completed "
        "search rounds add no new ProcureHarness candidate under "
        "search_validation.pareto_frontier.round_update_rule, or when "
        "max_rounds/max_unique_candidates is reached, whichever comes first."
    ),
    "not_a_global_optimum_claim": True,
}
EXPECTED_REGRET_CONTRACT = {
    "implementation_status": "required_before_paid_architecture_search",
    "eligible_when": (
        "terminal award matches an acceptable feasible outcome, all hard "
        "constraints pass, economic objective kind is minimize_total_price, "
        "and all awards in the compared outcome resolve to numeric prices in "
        "one native currency"
    ),
    "award_cost_contract": {
        "package": {
            "award_scope": "package",
            "price_source": "quote_event.details.total_price",
        },
        "lot": {
            "award_scope_prefix": "lot-",
            "item_id_rule": "item_id = award.scope[len('lot-'):]",
            "price_source": "quote_event.details.lots[item_id].price",
        },
        "outcome_cost": (
            "sum exactly one scope-resolved price per award in the terminal "
            "outcome; the referenced quote event must cover the award scope"
        ),
        "validator_alignment": (
            "same package/lot price semantics as "
            "scripts/validate_episodes.py::_award_price"
        ),
    },
    "oracle_cost": (
        "minimum scope-resolved summed award cost across oracle "
        "preferred_outcome_ids"
    ),
    "feasible_price_regret_native": (
        "max(0, selected_cost - oracle_cost)"
    ),
    "feasible_price_regret_pct": (
        "100 * feasible_price_regret_native / oracle_cost"
    ),
    "infeasible_or_no_award_policy": (
        "report regret as not_eligible rather than assigning an arbitrary "
        "monetary penalty; reliability metrics carry the failure"
    ),
    "eligibility_aware_comparison": {
        "run_key": ["episode_id", "repeat"],
        "reference_cohort": (
            "for each matched comparison package, freeze the intersection "
            "of run keys where both Coverage+Repair and ReAct are "
            "regret-eligible and the episode oracle_cost is strictly greater "
            "than zero"
        ),
        "required_reports": [
            "reference_cohort_count",
            "candidate_regret_eligible_count_on_reference_cohort",
            "candidate_regret_eligibility_rate_on_reference_cohort",
            "mean_feasible_price_regret_pct_on_reference_cohort",
            "zero_oracle_cost_run_count_outside_percentage_reference_cohort",
        ],
        "candidate_comparability_requirement": (
            "candidate must be regret-eligible on every run key in the frozen "
            "reference cohort before regret may be used for Pareto dominance, "
            "promotion, winner selection, or a final method claim"
        ),
        "paired_baseline_rule": (
            "compute candidate-minus-baseline regret and "
            "baseline-minus-candidate savings only on identical run keys from "
            "the frozen reference cohort; never rank candidates by an "
            "aggregate formed from each candidate's own eligible subset"
        ),
        "failure_handling": (
            "candidate ineligibility on any reference-cohort key fails regret "
            "comparability and remains visible through reliability metrics; "
            "it is not silently dropped from the denominator"
        ),
        "empty_reference_cohort_policy": {
            "status": "unavailable_empty_reference_cohort",
            "mean_regret_value": None,
            "prohibition": (
                "do not impute zero, infinity, or any sentinel numeric regret "
                "and do not rank candidates as better or worse because the "
                "cohort is empty"
            ),
            "pareto_rule": (
                "for that matched comparison package, omit "
                "mean_feasible_price_regret_pct_on_reference_cohort from every "
                "row's Pareto vector uniformly and recompute "
                "dominance/equivalence using the remaining frozen dimensions"
            ),
            "development_efficiency_promotion_rule": (
                "the efficiency promotion branch is unavailable when its "
                "required regret reference cohort is empty; a candidate may "
                "still advance only through the quality promotion branch"
            ),
            "winner_selection_rule": (
                "if the cumulative validation regret reference cohort is "
                "empty, skip the regret priority for every eligible candidate "
                "and continue the frozen lexicographic order at "
                "known_cost_usd; record winner_regret_basis = "
                "unavailable_empty_reference_cohort"
            ),
            "final_claim_rule": (
                "if the 041-050 matched regret reference cohort is empty, "
                "neither final method-claim gate may pass because both require "
                "regret evidence; report the architecture results without a "
                "paper-level better-design-pattern claim"
            ),
        },
    },
    "aggregation": (
        "report native regret separately by currency for all regret-eligible "
        "runs; aggregate normalized regret percentage only on the frozen "
        "positive-oracle-cost reference cohort after full candidate "
        "comparability; never sum different native currencies"
    ),
    "savings_contract": (
        "paired savings is baseline scope-resolved selected_cost minus "
        "candidate scope-resolved selected_cost on the same reference-cohort "
        "run key; report native currency always, and percent only when "
        "baseline selected_cost is strictly greater than zero"
    ),
    "normalized_regret_zero_oracle_policy": {
        "oracle_cost_positive": (
            "feasible_price_regret_pct = 100 * feasible_price_regret_native / "
            "oracle_cost"
        ),
        "oracle_cost_zero_selected_cost_zero": (
            "report feasible_price_regret_native = 0 and "
            "normalized_regret_status = not_normalizable_zero_oracle; do not "
            "fabricate a percentage"
        ),
        "oracle_cost_zero_selected_cost_positive": (
            "report positive native regret and normalized_regret_status = "
            "not_normalizable_zero_oracle; do not fabricate a percentage"
        ),
        "percentage_reference_cohort_rule": (
            "normalized-regret reference cohorts include only run keys whose "
            "episode oracle_cost is strictly greater than zero; because "
            "oracle_cost is episode-defined, this exclusion is identical for "
            "every method"
        ),
        "paired_savings_percentage_zero_baseline_rule": (
            "if the matched baseline selected_cost is zero, report paired "
            "native savings but paired_savings_pct = "
            "not_normalizable_zero_baseline; never divide by zero"
        ),
    },
}
EXPECTED_DEVELOPMENT_PROMOTION = {
    "quality": {
        "comparison": "coverage_repair",
        "improve_any_metric_by_runs": 3,
        "improve_any_metric": [
            "feasible_obligation_success",
            "strict_v02",
            "economic_objective",
        ],
        "max_deficit_runs_on_other_mandatory_success_metrics": 3,
        "max_known_cost_usd": 7.9842032,
        "cost_reference": "react",
    },
    "efficiency": {
        "comparison": "coverage_repair",
        "max_deficit_runs": {
            "feasible_obligation_success": 3,
            "strict_v02": 3,
            "economic_objective": 3,
        },
        "regret_requirement": "no_worse_on_full_frozen_reference_cohort",
        "min_known_cost_reduction_fraction": 0.20,
    },
}
EXPECTED_WINNER_SELECTION = {
    "eligible_set": (
        "ProcureHarness candidates on the cumulative admissible validation "
        "frontier when the search stop rule fires"
    ),
    "no_winner_rule": (
        "if eligible_set is empty, freeze a no_winner negative result and do "
        "not execute a ProcureHarness model-backed row on 041-050"
    ),
    "requires_full_regret_reference_cohort_comparability": True,
    "method": "lexicographic",
    "priority": [
        {"metric": "feasible_obligation_success", "direction": "desc"},
        {"metric": "strict_v02", "direction": "desc"},
        {"metric": "economic_objective", "direction": "desc"},
        {"metric": "obligation_resolution_rate", "direction": "desc"},
        {
            "metric": "mean_feasible_price_regret_pct_on_reference_cohort",
            "direction": "asc",
        },
        {"metric": "known_cost_usd", "direction": "asc"},
        {"metric": "total_tokens", "direction": "asc"},
        {"metric": "latency_ms", "direction": "asc"},
        {"metric": "model_calls", "direction": "asc"},
        {"metric": "candidate_id", "direction": "asc"},
    ],
    "freeze_rule": (
        "select exactly once from frozen 031-040 validation evidence, then "
        "freeze winner code/config/prompts/settings before any 041-050 "
        "model-backed call"
    ),
    "empty_regret_cohort_rule": (
        "apply the frozen empty-reference-cohort winner_selection_rule: omit "
        "only the regret priority for all candidates, then continue at "
        "known_cost_usd"
    ),
}
EXPECTED_FINAL_TEST = {
    "episodes": "041-050",
    "repeats_per_episode": 3,
    "rows_if_winner_exists": [
        "procureharness_winner",
        "coverage_repair",
        "react",
        "reference_control",
    ],
    "rows_if_no_winner": ["reference_control"],
    "no_tuning_after_first_model_call": True,
}
EXPECTED_METHOD_CLAIM_GATES = {
    "quality": {
        "primary_metric": "feasible_obligation_success",
        "primary_reference": (
            "per_metric_max_of_coverage_repair_and_react"
        ),
        "min_primary_gain_runs": 3,
        "max_deficit_runs": {
            "strict_v02": 1,
            "economic_objective": 1,
        },
        "deficit_reference": (
            "per_metric_max_of_coverage_repair_and_react"
        ),
        "regret_requirement": (
            "no_worse_than_minimum_baseline_regret_on_full_frozen_"
            "reference_cohort"
        ),
        "max_known_cost_reference": "react",
    },
    "efficiency": {
        "max_deficit_runs": {
            "feasible_obligation_success": 1,
            "strict_v02": 1,
            "economic_objective": 1,
        },
        "deficit_reference": (
            "per_metric_max_of_coverage_repair_and_react"
        ),
        "regret_requirement": (
            "no_worse_than_minimum_baseline_regret_on_full_frozen_"
            "reference_cohort"
        ),
        "cost_reference": (
            "min_known_cost_of_coverage_repair_and_react"
        ),
        "min_known_cost_reduction_fraction": 0.30,
    },
    "empty_regret_cohort_rule": (
        "both final claim branches fail when final reference_cohort_count == 0 "
        "because regret evidence is required"
    ),
}
EXPECTED_PHASE2_ENTRY = (
    "Only after a ProcureHarness design-pattern winner is frozen from the "
    "architecture-search phase."
)
EXPECTED_PHASE2_RULE = (
    "Each harness axis requires a matched ablation on the frozen skeleton "
    "before it enters the final amalgamation."
)


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
    if confirm.get("baseline_policy") != EXPECTED_BASELINE_POLICY:
        raise ValueError("Frozen development baseline policy changed")

    if search.get("validation_entry") != EXPECTED_VALIDATION_ENTRY:
        raise ValueError("Validation-entry selection contract changed")

    validation_cfg = search.get("search_validation") or {}
    if (
        validation_cfg.get("episodes"),
        validation_cfg.get("repeats_per_episode"),
        validation_cfg.get("matched_baselines"),
        validation_cfg.get("baseline_runs_once_per_frozen_package"),
        validation_cfg.get("may_guide_subsequent_search_rounds"),
    ) != (
        "031-040",
        3,
        ["coverage_repair", "react"],
        True,
        True,
    ):
        raise ValueError("Search-validation execution contract changed")
    if validation_cfg.get("requires_package_freeze_before_calls") is not True:
        raise ValueError("031-040 package must freeze before model calls")
    if validation_cfg.get("frontier_admission") != EXPECTED_FRONTIER_ADMISSION:
        raise ValueError("Validation-frontier admission contract changed")
    if validation_cfg.get("pareto_frontier") != EXPECTED_PARETO_FRONTIER:
        raise ValueError("Validation Pareto-frontier contract changed")

    if search.get("ceiling_stop_rule") != EXPECTED_CEILING_RULE:
        raise ValueError("Architecture plateau rule changed")

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
        "reference_cohort_count",
        "candidate_regret_eligible_count_on_reference_cohort",
        "candidate_regret_eligibility_rate_on_reference_cohort",
        "mean_feasible_price_regret_pct_on_reference_cohort",
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

    if reporting.get("economic_regret_v01") != EXPECTED_REGRET_CONTRACT:
        raise ValueError("Economic regret contract changed")

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
        "mean_feasible_price_regret_pct_on_reference_cohort",
        "known_cost_usd",
        "total_tokens",
        "latency_ms",
        "model_calls",
    }:
        raise ValueError("Pareto minimize dimensions changed")

    if frontier.get("development_promotion_branches") != (
        EXPECTED_DEVELOPMENT_PROMOTION
    ):
        raise ValueError("Development promotion contract changed")

    freeze = protocol.get("final_method_freeze") or {}
    if freeze.get("winner_selection") != EXPECTED_WINNER_SELECTION:
        raise ValueError("Final winner-selection contract changed")
    if freeze.get("final_test") != EXPECTED_FINAL_TEST:
        raise ValueError("Final method-test matrix changed")
    if freeze.get("method_claim_gates") != EXPECTED_METHOD_CLAIM_GATES:
        raise ValueError("Final method-claim gate changed")

    phase2 = protocol.get("phase2_after_pattern_freeze") or {}
    if phase2.get("axes_to_test_one_at_a_time") != EXPECTED_PHASE2:
        raise ValueError("Phase-2 harness sequence changed")
    if phase2.get("entry_condition") != EXPECTED_PHASE2_ENTRY:
        raise ValueError("Harness phase may not precede design-pattern freeze")
    if phase2.get("rule") != EXPECTED_PHASE2_RULE:
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
