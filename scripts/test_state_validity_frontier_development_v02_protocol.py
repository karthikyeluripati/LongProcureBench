"""Protocol guards for State Validity Frontier development v0.2."""
from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = (
    ROOT / "docs" / "state-validity-frontier-development-v0.2-protocol.json"
)


class StateValidityFrontierDevelopmentV02ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(
            PROTOCOL_PATH.read_text(encoding="utf-8")
        )

    def test_protocol_is_prospective_and_code_frozen(self):
        self.assertEqual(
            self.protocol["status"],
            "preregistered_no_results",
        )
        implementation = self.protocol["implementation"]
        self.assertEqual(
            implementation["controller_blob_sha"],
            "24dd50e28864fe450039e098e4d28e4518097956",
        )
        self.assertEqual(
            implementation["runner_path"],
            "scripts/run_state_validity_frontier_development_v02.py",
        )
        self.assertEqual(
            implementation["runner_blob_sha"],
            "691a8ff3b640e4d157fba1be3ce311e86c2ea554",
        )
        self.assertIn(
            "001-020",
            implementation["execution_procedure"],
        )
        self.assertIn(
            "3 repeats",
            implementation["execution_procedure"],
        )
        self.assertIn(
            "No controller",
            implementation["change_policy"],
        )

    def test_v01_stage1_verdict_is_not_rewritten(self):
        stage1 = self.protocol["stage1_reference"]
        self.assertEqual(stage1["terminal_feasible"], [3, 3])
        self.assertEqual(
            stage1["feasible_obligation_success"],
            [3, 3],
        )
        self.assertEqual(stage1["strict_v02"], [3, 3])
        self.assertEqual(stage1["economic_objective"], [3, 3])
        self.assertEqual(stage1["unresolved_obligations"], 0)
        self.assertFalse(stage1["strict_v01_gate_pass"])
        self.assertIn(
            "remain unchanged",
            self.protocol["semantic_clarification"]["anti_retcon"],
        )

    def test_v02_prerequisite_boundary_is_frozen(self):
        semantics = self.protocol["semantic_clarification"]
        self.assertIn(
            "non-committing",
            semantics["supplier_identification"],
        )
        self.assertIn(
            "send_rfq",
            semantics["sourcing_boundary"],
        )
        self.assertEqual(
            semantics["episode_013_rule"],
            (
                "For the starting-prerequisite mechanism, the first "
                "send_rfq must occur after the visible buyer_clarification "
                "response. identify_suppliers may occur before that response."
            ),
        )

    def test_exact_twenty_by_three_development_grid(self):
        grid = self.protocol["development_grid"]
        self.assertEqual(len(grid["episodes"]), 20)
        self.assertEqual(
            grid["episodes"],
            [
                "electrical-bongabon-generator-001",
                "electrical-national-museum-lighting-002",
                "electrical-neust-cable-003",
                "electrical-dla-breaker-004",
                "electrical-barrie-transformer-005",
                "electrical-bfar-generator-006",
                "electrical-negros-wire-007",
                "electrical-burauen-generator-008",
                "electrical-highpoint-transformer-009",
                "electrical-painesville-switchgear-010",
                "electrical-sagada-generator-011",
                "electrical-dla-relay-012",
                "electrical-dla-transformer-013",
                "electrical-dla-battery-supply-014",
                "electrical-dla-battery-charger-015",
                "electrical-dla-power-supply-016",
                "electrical-dla-qpl-breaker-017",
                "electrical-highpoint-cable-018",
                "electrical-usaf-ups-019",
                "electrical-vre-generator-020",
            ],
        )
        self.assertEqual(grid["repeats_per_episode"], 3)
        self.assertEqual(grid["total_runs"], 60)
        self.assertEqual(grid["model"], "openai/gpt-5.6-sol")
        self.assertEqual(grid["reasoning_effort"], "medium")
        self.assertIsNone(grid["temperature"])
        self.assertEqual(grid["max_actions"], 50)
        self.assertFalse(grid["heldout_access"])
        self.assertEqual(
            grid["sequence_requirements"],
            [
                {
                    "episode_id": "electrical-dla-transformer-013",
                    "repeats": [1, 2, 3],
                    "response_event_type": "buyer_clarification",
                    "blocked_action_type": "send_rfq",
                    "requirement": (
                        "For every repeat, the first accepted send_rfq must "
                        "occur strictly after the first visible "
                        "buyer_clarification response."
                    ),
                }
            ],
        )

    def test_frozen_comparator_anchor_values(self):
        rows = {
            row["id"]: row
            for row in self.protocol["frozen_comparators"]
        }
        self.assertEqual(
            rows["factual_context"]["feasible_obligation_success"],
            [40, 60],
        )
        self.assertEqual(rows["react"]["strict_v02"], [27, 60])
        self.assertEqual(
            rows["coverage_repair"]["feasible_obligation_success"],
            [50, 60],
        )
        self.assertEqual(
            rows["coverage_repair"]["strict_v02"],
            [30, 60],
        )
        self.assertEqual(
            rows["coverage_repair"]["economic_objective"],
            [30, 60],
        )
        self.assertAlmostEqual(
            rows["coverage_repair"]["known_cost_usd"],
            2.9776718,
        )

    def test_reporting_keeps_economic_metric_and_no_composite(self):
        reporting = self.protocol["reporting_contract"]
        self.assertEqual(
            reporting["primary_quality_metric"],
            "feasible_obligation_success",
        )
        self.assertIn(
            "economic_objective_satisfied",
            reporting["quality_metrics"],
        )
        self.assertTrue(reporting["no_composite_score"])
        economics = reporting["economics"]
        self.assertEqual(
            economics["frozen_metric"],
            "economic_objective_satisfied",
        )
        self.assertEqual(
            economics["numeric_regret_status"],
            "not_frozen_in_evaluator_v0.2",
        )

    def test_development_gate_is_exactly_frozen(self):
        gate = self.protocol["development_gate"]
        self.assertEqual(
            gate["quality_requirements"],
            [
                (
                    "feasible_obligation_success >= 47/60 (78.3%), "
                    "i.e. no more than 5 percentage points below frozen "
                    "Coverage+Repair"
                ),
                "strict_v02 >= 30/60 (50.0%)",
                "economic_objective >= 30/60 (50.0%)",
            ],
        )
        self.assertIn(
            (
                "all three electrical-dla-transformer-013 repeats pass the "
                "frozen prerequisite sequence gate: first accepted send_rfq "
                "occurs strictly after the visible buyer_clarification response"
            ),
            gate["execution_requirements"],
        )
        self.assertEqual(len(gate["contribution_branch"]), 2)
        self.assertIn("3/60", gate["contribution_branch"][0])
        self.assertIn("$7.9842032", gate["contribution_branch"][0])
        self.assertIn("20%", gate["contribution_branch"][1])

    def test_bootstrap_and_heldout_hygiene_are_frozen(self):
        bootstrap = self.protocol["reporting_contract"]["paired_bootstrap"]
        self.assertEqual(bootstrap["resamples"], 20000)
        self.assertEqual(bootstrap["seed"], 20260926)
        self.assertEqual(bootstrap["sampler"], "sha256-index-v1")
        self.assertEqual(bootstrap["cluster"], "episode")

        heldout = self.protocol["heldout_policy"]
        self.assertIn("diagnostic_only", heldout["old_021_030"])
        self.assertEqual(heldout["future_set"], "031+")


if __name__ == "__main__":
    unittest.main()
