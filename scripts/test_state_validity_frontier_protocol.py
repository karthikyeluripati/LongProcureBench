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

    def test_episode_mechanism_assertions_are_frozen(self):
        episodes = {
            row["episode_id"]: row
            for row in self.protocol["targeted_pilot"]["episodes"]
        }
        expected = {
            "electrical-burauen-generator-008": {
                "mechanism": (
                    "supplier withdrawal invalidates evaluation and "
                    "reopens recovery frontier"
                ),
                "assertions": [
                    "supplier A is marked inactive after visible withdrawal",
                    "pre-withdrawal evaluation becomes invalid",
                    "withdrawn supplier is excluded from later terminal actions",
                    (
                        "after withdrawal, at least one active non-withdrawn "
                        "supplier produces a newly revealed quote_received or "
                        "quote_revision from a post-withdrawal recovery action, "
                        "and evaluate_quotes is accepted after that new quote "
                        "before any terminal action"
                    ),
                    (
                        "request_buyer_clarification is not used after "
                        "withdrawal unless a new requirement epoch exists"
                    ),
                ],
            },
            "electrical-dla-transformer-013": {
                "mechanism": (
                    "clarification lease closes the prerequisite loop and "
                    "allows sourcing to advance"
                ),
                "assertions": [
                    (
                        "at most one request_buyer_clarification occurs in "
                        "requirement epoch 0"
                    ),
                    (
                        "after buyer clarification, clarification is absent "
                        "from the frontier"
                    ),
                    (
                        "supplier discovery/RFQ begins after the "
                        "clarification response"
                    ),
                    (
                        "terminal action is not allowed before a current "
                        "evaluation exists"
                    ),
                ],
            },
            "electrical-dla-power-supply-016": {
                "mechanism": (
                    "requirement change invalidates only dependent "
                    "procurement state and creates a bounded repair frontier"
                ),
                "assertions": [
                    "requirement_change increments requirement_epoch",
                    (
                        "issue_amendment becomes required after the visible "
                        "change because sourcing already started"
                    ),
                    "pre-change offers are marked stale",
                    (
                        "post-amendment frontier repairs stale offers/"
                        "non-response before terminal decision"
                    ),
                    (
                        "no clarification loop occurs in the unchanged "
                        "requirement epoch"
                    ),
                ],
            },
        }
        self.assertEqual(set(episodes), set(expected))
        for episode_id, frozen in expected.items():
            self.assertEqual(
                episodes[episode_id]["mechanism"],
                frozen["mechanism"],
            )
            self.assertEqual(
                episodes[episode_id]["assertions"],
                frozen["assertions"],
            )

    def test_mechanism_go_gate_is_frozen(self):
        self.assertEqual(
            self.protocol["go_gate"]["mechanism_requirements"],
            [
                "all three runs execute without policy/protocol errors",
                "all episode-specific mechanism assertions pass",
                "zero runs hit max_actions",
                (
                    "controller diagnostics show at least one "
                    "validity/frontier intervention in each episode"
                ),
            ],
        )

    def test_go_gate_does_not_authorize_unfrozen_broad_run(self):
        gate = self.protocol["go_gate"]
        self.assertIn(
            "separate repeated-development protocol",
            gate["decision"],
        )
        self.assertEqual(
            gate["quality_requirements"],
            [
                "terminal_feasible >= 2/3",
                "feasible_obligation_success >= 2/3",
            ],
        )


if __name__ == "__main__":
    unittest.main()
