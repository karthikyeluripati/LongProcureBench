"""Regression tests for the frozen held-out paper execution contract."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from run_heldout_paper_row import (
    EXPECTED_HELDOUT_EPISODES,
    EXPECTED_ROW_IDS,
    build_parser,
    load_execution_plan,
    run_row,
)


class HeldoutExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = load_execution_plan()

    def test_exact_frozen_rows_are_loaded(self):
        self.assertEqual(set(self.plan), EXPECTED_ROW_IDS)
        self.assertEqual(
            tuple(self.plan["raw-reactive-openai"]["episodes"]),
            EXPECTED_HELDOUT_EPISODES,
        )

    def test_model_rows_are_exactly_three_repeats_x_ten_episodes(self):
        for row_id, spec in self.plan.items():
            if row_id == "reference-control":
                self.assertEqual(spec["repeats"], 1)
                self.assertEqual(spec["expected_runs"], 10)
                continue
            self.assertEqual(spec["repeats"], 3)
            self.assertEqual(spec["expected_runs"], 30)
            self.assertEqual(spec["max_actions"], 50)
            self.assertIsNone(spec["temperature"])
            self.assertEqual(spec["temperature_mode"], "omitted")

    def test_exact_models_and_reasoning_settings_are_frozen(self):
        expected = {
            "raw-reactive-openai": (
                "openai/gpt-5.6-sol",
                "medium",
                "llm_reactive_baseline",
            ),
            "raw-reactive-anthropic": (
                "anthropic/claude-opus-5-5",
                None,
                "llm_reactive_baseline",
            ),
            "raw-reactive-gemini": (
                "gemini/gemini-3.8-flash",
                None,
                "llm_reactive_baseline",
            ),
            "context-compiled-openai": (
                "openai/gpt-5.6-sol",
                "medium",
                "llm_context_compiled_reactive",
            ),
            "react-openai": (
                "openai/gpt-5.6-sol",
                "medium",
                "llm_react_comparator",
            ),
        }
        for row_id, values in expected.items():
            spec = self.plan[row_id]
            self.assertEqual(
                (
                    spec["model"],
                    spec["reasoning_effort"],
                    spec["policy_kind"],
                ),
                values,
            )

    def test_context_and_react_identity_are_frozen(self):
        context = self.plan["context-compiled-openai"]
        self.assertEqual(
            context["context_strategy"],
            "factual_compiled_v0.1",
        )
        self.assertIsNone(context["agent_pattern"])

        react = self.plan["react-openai"]
        self.assertEqual(
            react["context_strategy"],
            "factual_compiled_v0.1",
        )
        self.assertEqual(react["agent_pattern"], "react_v0.1")

    def test_cli_exposes_no_research_setting_overrides(self):
        parser = build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        for forbidden in (
            "--model",
            "--episode",
            "--repeats",
            "--max-actions",
            "--temperature",
            "--omit-temperature",
            "--reasoning-effort",
            "--policy",
        ):
            self.assertNotIn(forbidden, option_strings)
        self.assertIn("--row", option_strings)
        self.assertIn("--output-dir", option_strings)

    def test_unknown_or_dropped_row_cannot_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "not frozen"):
                run_row(
                    "working-plan-reactive-v0.1",
                    Path(tmp) / "out",
                )

    def test_reference_row_uses_only_heldout_episodes(self):
        class StubRunner:
            def __init__(self):
                self.calls = []

            def run(
                self,
                policy,
                episode_id,
                *,
                max_actions,
                run_id,
                result_path,
            ):
                self.calls.append(
                    (episode_id, max_actions, run_id, result_path)
                )
                return {
                    "episode_id": episode_id,
                    "run_id": run_id,
                    "status": "completed",
                    "trajectory": [{"step": 1}],
                    "evaluation": {
                        "episode_success": True,
                        "episode_success_v02": True,
                        "feasible_process_success": True,
                        "feasible_obligation_success": True,
                        "terminal_outcome": {"correct": True},
                        "economic_objective": {"satisfied": True},
                        "hard_constraints": {"passed": 1, "total": 1},
                        "required_checkpoints": {
                            "completed": 1,
                            "total": 1,
                            "results": [],
                        },
                        "obligations": {
                            "actionable": 1,
                            "resolved": 1,
                            "unresolved": 0,
                            "no_opportunity": 0,
                            "not_applicable": 0,
                            "resolution_rate": 1.0,
                            "results": [],
                        },
                        "efficiency": {"accepted_actions": 1},
                        "constraint_violations": [],
                    },
                    "policy_metrics": {},
                    "error": None,
                    "evaluation_error": None,
                }

        runner = StubRunner()
        with tempfile.TemporaryDirectory() as tmp:
            rows, summary = run_row(
                "reference-control",
                Path(tmp) / "reference",
                runner=runner,
            )
        self.assertEqual(len(rows), 10)
        self.assertEqual(summary["runs"], 10)
        self.assertEqual(
            tuple(call[0] for call in runner.calls),
            EXPECTED_HELDOUT_EPISODES,
        )
        self.assertTrue(all(call[1] == 50 for call in runner.calls))


if __name__ == "__main__":
    unittest.main()
