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

    def test_regret_metric_is_required_before_paid_search(self):
        mutated = deepcopy(self.protocol)
        mutated["reporting_contract"]["economic_regret_v01"][
            "implementation_status"
        ] = "optional"
        with self.assertRaisesRegex(ValueError, "Economic regret"):
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
