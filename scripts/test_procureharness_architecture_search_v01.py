"""Regression tests for the ProcureHarness architecture-search protocol."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from validate_procureharness_architecture_search_v01 import (  # noqa: E402
    PROTOCOL_PATH,
    validate_protocol,
)


class ProcureHarnessArchitectureSearchV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(
            PROTOCOL_PATH.read_text(encoding="utf-8")
        )

    def test_frozen_protocol_passes(self):
        validate_protocol(deepcopy(self.protocol))

    def test_prior_heldout_cannot_be_rebranded_fresh(self):
        mutated = deepcopy(self.protocol)
        mutated["benchmark_exposure"]["prior_heldout_exposed"][
            "fresh_test_claim_allowed"
        ] = True
        with self.assertRaisesRegex(ValueError, "021-030"):
            validate_protocol(mutated)

    def test_final_method_test_cannot_guide_design(self):
        mutated = deepcopy(self.protocol)
        mutated["benchmark_exposure"]["required_new_collection"][1][
            "may_guide_design"
        ] = True
        with self.assertRaisesRegex(ValueError, "041-050"):
            validate_protocol(mutated)

    def test_memory_cannot_enter_phase1(self):
        mutated = deepcopy(self.protocol)
        mutated["architecture_grammar"]["hard_complexity_limits"][
            "persistent_cross_episode_memory"
        ] = True
        with self.assertRaisesRegex(ValueError, "complexity limits"):
            validate_protocol(mutated)

    def test_search_budget_cannot_expand_silently(self):
        mutated = deepcopy(self.protocol)
        mutated["search_procedure"]["max_rounds"] = 4
        with self.assertRaisesRegex(ValueError, "Search-round budget"):
            validate_protocol(mutated)

    def test_weighted_score_cannot_replace_pareto_contract(self):
        mutated = deepcopy(self.protocol)
        mutated["reporting_contract"]["no_weighted_composite_score"] = False
        with self.assertRaisesRegex(ValueError, "Weighted composite"):
            validate_protocol(mutated)

    def test_package_and_lot_price_paths_are_frozen(self):
        mutated = deepcopy(self.protocol)
        contract = mutated["reporting_contract"]["economic_regret_v01"][
            "award_cost_contract"
        ]
        contract["lot"]["price_source"] = "quote_event.details.total_price"
        with self.assertRaisesRegex(ValueError, "Economic regret contract"):
            validate_protocol(mutated)

    def test_candidate_specific_regret_subset_cannot_rank_candidates(self):
        mutated = deepcopy(self.protocol)
        comparison = mutated["reporting_contract"]["economic_regret_v01"][
            "eligibility_aware_comparison"
        ]
        comparison["candidate_comparability_requirement"] = (
            "candidate may compare only its own eligible runs"
        )
        with self.assertRaisesRegex(ValueError, "Economic regret contract"):
            validate_protocol(mutated)

    def test_regret_reference_cohort_is_frozen(self):
        mutated = deepcopy(self.protocol)
        comparison = mutated["reporting_contract"]["economic_regret_v01"][
            "eligibility_aware_comparison"
        ]
        comparison["reference_cohort"] = (
            "each candidate chooses its own eligible run keys"
        )
        with self.assertRaisesRegex(ValueError, "Economic regret contract"):
            validate_protocol(mutated)

    def test_zero_oracle_regret_policy_cannot_be_removed(self):
        mutated = deepcopy(self.protocol)
        regret = mutated["reporting_contract"]["economic_regret_v01"]
        regret["normalized_regret_zero_oracle_policy"][
            "oracle_cost_zero_selected_cost_zero"
        ] = "report 0 percent by convention"
        with self.assertRaisesRegex(ValueError, "Economic regret contract"):
            validate_protocol(mutated)

    def test_empty_regret_cohort_cannot_be_treated_as_zero(self):
        mutated = deepcopy(self.protocol)
        policy = mutated["reporting_contract"]["economic_regret_v01"][
            "eligibility_aware_comparison"
        ]["empty_reference_cohort_policy"]
        policy["mean_regret_value"] = 0
        with self.assertRaisesRegex(ValueError, "Economic regret contract"):
            validate_protocol(mutated)

    def test_empty_regret_cohort_must_block_final_claim(self):
        mutated = deepcopy(self.protocol)
        mutated["final_method_freeze"]["method_claim_gates"][
            "empty_regret_cohort_rule"
        ] = "ignore regret and continue"
        with self.assertRaisesRegex(ValueError, "method-claim"):
            validate_protocol(mutated)

    def test_baseline_reruns_cannot_be_enabled(self):
        mutated = deepcopy(self.protocol)
        mutated["search_procedure"]["development_confirmation"][
            "baseline_policy"
        ]["rerun_allowed"] = True
        with self.assertRaisesRegex(ValueError, "baseline policy"):
            validate_protocol(mutated)

    def test_validation_entry_requires_promotion(self):
        mutated = deepcopy(self.protocol)
        mutated["search_procedure"]["validation_entry"][
            "requires_development_promotion_branch"
        ] = False
        with self.assertRaisesRegex(ValueError, "Validation-entry"):
            validate_protocol(mutated)

    def test_validation_frontier_floor_cannot_be_weakened(self):
        mutated = deepcopy(self.protocol)
        mutated["search_procedure"]["search_validation"][
            "frontier_admission"
        ]["max_deficit_runs"]["strict_v02"] = 3
        with self.assertRaisesRegex(ValueError, "frontier admission"):
            validate_protocol(mutated)

    def test_plateau_rule_cannot_change_frontier_semantics(self):
        mutated = deepcopy(self.protocol)
        mutated["search_procedure"]["ceiling_stop_rule"][
            "plateau_rounds"
        ] = 1
        with self.assertRaisesRegex(ValueError, "plateau"):
            validate_protocol(mutated)

    def test_frontier_tie_cannot_reset_plateau(self):
        mutated = deepcopy(self.protocol)
        frontier = mutated["search_procedure"]["search_validation"][
            "pareto_frontier"
        ]
        frontier["frontier_vector_equivalence"][
            "candidate_id_part_of_vector"
        ] = True
        with self.assertRaisesRegex(ValueError, "Pareto-frontier"):
            validate_protocol(mutated)

    def test_development_quality_promotion_threshold_cannot_weaken(self):
        mutated = deepcopy(self.protocol)
        mutated["admissibility_and_frontier"][
            "development_promotion_branches"
        ]["quality"]["improve_any_metric_by_runs"] = 2
        with self.assertRaisesRegex(ValueError, "Development promotion"):
            validate_protocol(mutated)

    def test_development_efficiency_threshold_cannot_weaken(self):
        mutated = deepcopy(self.protocol)
        mutated["admissibility_and_frontier"][
            "development_promotion_branches"
        ]["efficiency"]["min_known_cost_reduction_fraction"] = 0.10
        with self.assertRaisesRegex(ValueError, "Development promotion"):
            validate_protocol(mutated)

    def test_no_winner_rule_cannot_be_removed(self):
        mutated = deepcopy(self.protocol)
        mutated["final_method_freeze"]["winner_selection"][
            "no_winner_rule"
        ] = "pick the cheapest candidate anyway"
        with self.assertRaisesRegex(ValueError, "winner-selection"):
            validate_protocol(mutated)

    def test_winner_priority_cannot_be_reordered_posthoc(self):
        mutated = deepcopy(self.protocol)
        priority = mutated["final_method_freeze"]["winner_selection"][
            "priority"
        ]
        priority[0], priority[1] = priority[1], priority[0]
        with self.assertRaisesRegex(ValueError, "winner-selection"):
            validate_protocol(mutated)

    def test_final_quality_claim_threshold_cannot_weaken(self):
        mutated = deepcopy(self.protocol)
        mutated["final_method_freeze"]["method_claim_gates"][
            "quality"
        ]["min_primary_gain_runs"] = 2
        with self.assertRaisesRegex(ValueError, "method-claim"):
            validate_protocol(mutated)

    def test_final_efficiency_claim_threshold_cannot_weaken(self):
        mutated = deepcopy(self.protocol)
        mutated["final_method_freeze"]["method_claim_gates"][
            "efficiency"
        ]["min_known_cost_reduction_fraction"] = 0.20
        with self.assertRaisesRegex(ValueError, "method-claim"):
            validate_protocol(mutated)

    def test_global_optimum_claim_is_prohibited(self):
        mutated = deepcopy(self.protocol)
        mutated["scientific_scope"]["forbidden_claims"].remove(
            "global optimum over all possible agent architectures"
        )
        with self.assertRaisesRegex(ValueError, "Global-optimum"):
            validate_protocol(mutated)


if __name__ == "__main__":
    unittest.main()
