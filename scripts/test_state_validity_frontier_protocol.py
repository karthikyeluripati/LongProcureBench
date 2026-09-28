"""Protocol guards for State Validity Frontier v0.1."""
from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "docs" / "state-validity-frontier-v0.1-protocol.json"


class StateValidityFrontierProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(
            PROTOCOL_PATH.read_text(encoding="utf-8")
        )

    def test_protocol_is_preregistered_without_results(self):
        self.assertEqual(
            self.protocol["status"],
            "preregistered_no_results",
        )
        self.assertEqual(
            self.protocol["role"],
            "proposed_method_candidate",
        )

    def test_information_boundary_matches_factual_context(self):
        boundary = self.protocol["information_boundary"]
        self.assertEqual(
            boundary["context_view"],
            "factual_compiled_v0.1",
        )
        forbidden = " ".join(boundary["forbidden"]).lower()
        self.assertIn("oracle", forbidden)
        self.assertIn("evaluator", forbidden)
        self.assertIn("future events", forbidden)
        self.assertIn("hidden event triggers", forbidden)

    def test_stage_one_is_exactly_three_development_runs(self):
        pilot = self.protocol["targeted_pilot"]
        self.assertEqual(
            [row["episode_id"] for row in pilot["episodes"]],
            [
                "electrical-burauen-generator-008",
                "electrical-dla-transformer-013",
                "electrical-dla-power-supply-016",
            ],
        )
        self.assertEqual(pilot["repeats"], 1)
        self.assertEqual(pilot["paid_runs_total"], 3)
        self.assertFalse(pilot["heldout_access"])

    def test_stage_one_sampling_is_frozen(self):
        pilot = self.protocol["targeted_pilot"]
        self.assertEqual(pilot["model"], "openai/gpt-5.6-sol")
        self.assertEqual(pilot["reasoning_effort"], "medium")
        self.assertIsNone(pilot["temperature"])
        self.assertEqual(pilot["max_actions"], 50)

    def test_prior_heldout_is_disqualified_for_new_method(self):
        policy = self.protocol["heldout_policy"]
        self.assertIn(
            "diagnostic_only",
            policy["prior_heldout_021_030"],
        )
        self.assertIn("031+", policy["future_test_set"])

    def test_controller_cannot_encode_episode_specific_rules(self):
        forbidden = " ".join(
            self.protocol["information_boundary"]["forbidden"]
        ).lower()
        self.assertIn("episode-specific", forbidden)
        self.assertIn("supplier-specific", forbidden)

        rules = json.dumps(
            self.protocol["controller"]["invalidation_rules"],
            sort_keys=True,
        )
        for episode_id in (
            "electrical-burauen-generator-008",
            "electrical-dla-transformer-013",
            "electrical-dla-power-supply-016",
        ):
            self.assertNotIn(episode_id, rules)

    def test_go_gate_does_not_authorize_unfrozen_broad_run(self):
        gate = self.protocol["go_gate"]
        self.assertIn(
            "separate repeated-development protocol",
            gate["decision"],
        )
        self.assertIn(
            "terminal_feasible >= 2/3",
            gate["quality_requirements"],
        )
        self.assertIn(
            "feasible_obligation_success >= 2/3",
            gate["quality_requirements"],
        )


if __name__ == "__main__":
    unittest.main()
