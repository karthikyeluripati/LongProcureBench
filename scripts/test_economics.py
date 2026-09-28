"""Regression tests for deterministic procurement economics v0.1."""
from __future__ import annotations

import json
import math
from pathlib import Path
import unittest

from longprocurebench import (
    BenchmarkRunner,
    EconomicRegretEvaluator,
    EconomicsError,
    LongProcureBenchEvaluator,
    ScriptedReferencePolicy,
    compare_candidate_on_reference_cohort,
    freeze_reference_cohort,
    normalize_regret,
)


class EconomicsTests(unittest.TestCase):
    def setUp(self):
        self.economics = EconomicRegretEvaluator()
        self.evaluator = LongProcureBenchEvaluator()
        self.runner = BenchmarkRunner()

    @staticmethod
    def action(n, episode_id, action_type, supplier_id=None, **arguments):
        return {
            "action_id": f"a{n}",
            "episode_id": episode_id,
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": arguments,
        }

    def _result_from_actions(self, episode_id, actions, run_id="fixture"):
        return {
            "run_id": run_id,
            "episode_id": episode_id,
            "policy": {
                "policy_id": "economics-test",
                "policy_kind": "test",
            },
            "evaluation": self.evaluator.evaluate_actions(
                episode_id,
                actions,
            ),
        }

    @staticmethod
    def economics_report(
        episode_id,
        repeat,
        *,
        selected,
        oracle,
        currency="USD",
        eligible=True,
    ):
        pct, status = normalize_regret(selected, oracle)
        if not eligible:
            pct = None
            status = "not_eligible"
        return {
            "run_key": {
                "episode_id": episode_id,
                "repeat": repeat,
            },
            "eligible": eligible,
            "eligibility_reason": (
                "eligible" if eligible else "terminal_not_feasible"
            ),
            "currency": currency if eligible else None,
            "selected_cost_native": selected if eligible else None,
            "oracle_cost_native": oracle if eligible else None,
            "feasible_price_regret_native": (
                max(0.0, selected - oracle) if eligible else None
            ),
            "feasible_price_regret_pct": pct,
            "normalized_regret_status": status,
        }

    def test_reference_package_has_zero_regret(self):
        result = self.runner.run(
            ScriptedReferencePolicy(),
            "electrical-bongabon-generator-001",
        )
        report = self.economics.score_result(result, repeat=1)
        self.assertTrue(report["eligible"])
        self.assertEqual(report["currency"], "PHP")
        self.assertEqual(report["selected_cost_native"], 379000.0)
        self.assertEqual(report["oracle_cost_native"], 379000.0)
        self.assertEqual(report["feasible_price_regret_native"], 0.0)
        self.assertEqual(report["feasible_price_regret_pct"], 0.0)
        self.assertEqual(
            report["normalized_regret_status"],
            "normalizable",
        )

    def test_reference_multi_lot_uses_lot_prices(self):
        result = self.runner.run(
            ScriptedReferencePolicy(),
            "electrical-national-museum-lighting-002",
        )
        report = self.economics.score_result(result, repeat=2)
        self.assertTrue(report["eligible"])
        self.assertEqual(report["currency"], "PHP")
        self.assertEqual(report["selected_cost_native"], 4230000.0)
        self.assertEqual(report["oracle_cost_native"], 4230000.0)
        self.assertEqual(report["feasible_price_regret_native"], 0.0)

    def test_all_current_award_outcomes_have_scope_aware_prices(self):
        episode_dir = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "episodes"
            / "electrical"
        )
        for path in sorted(episode_dir.glob("*.json")):
            with self.subTest(episode=path.stem):
                episode = json.loads(path.read_text(encoding="utf-8"))
                outcomes = episode["oracle"]["acceptable_terminal_outcomes"]
                for outcome in outcomes:
                    if outcome["decision"] != "award":
                        continue
                    total, currency = self.economics._outcome_cost(
                        episode,
                        outcome,
                    )
                    self.assertGreaterEqual(total, 0.0)
                    self.assertTrue(currency)

    def test_feasible_suboptimal_award_has_positive_regret(self):
        eid = "electrical-bongabon-generator-001"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-gen-a"),
            self.action(3, eid, "send_rfq", "syn-gen-b"),
            self.action(4, eid, "send_rfq", "syn-gen-c"),
            self.action(5, eid, "send_follow_up", "syn-gen-c"),
            self.action(6, eid, "request_quote_revision", "syn-gen-c"),
            self.action(7, eid, "evaluate_quotes"),
            self.action(
                8,
                eid,
                "award_supplier",
                "syn-gen-a",
                awards=[
                    {
                        "scope": "package",
                        "supplier_id": "syn-gen-a",
                        "quote_event_id": "e1",
                    }
                ],
            ),
        ]
        result = self._result_from_actions(eid, actions)
        report = self.economics.score_result(result, repeat=1)
        self.assertTrue(report["eligible"])
        self.assertEqual(report["selected_outcome_id"], "o2")
        self.assertEqual(report["selected_cost_native"], 382000.0)
        self.assertEqual(report["oracle_cost_native"], 379000.0)
        self.assertEqual(report["feasible_price_regret_native"], 3000.0)
        self.assertTrue(
            math.isclose(
                report["feasible_price_regret_pct"],
                100.0 * 3000.0 / 379000.0,
            )
        )

    def test_result_and_evaluation_episode_must_match(self):
        result = self.runner.run(
            ScriptedReferencePolicy(),
            "electrical-bongabon-generator-001",
        )
        result["evaluation"]["episode_id"] = "different-episode"
        with self.assertRaisesRegex(EconomicsError, "does not match"):
            self.economics.score_result(result, repeat=1)

    def test_infeasible_terminal_is_not_regret_eligible(self):
        eid = "electrical-bongabon-generator-001"
        actions = [
            self.action(1, eid, "identify_suppliers"),
            self.action(2, eid, "send_rfq", "syn-gen-a"),
            self.action(3, eid, "send_rfq", "syn-gen-b"),
            self.action(
                4,
                eid,
                "award_supplier",
                "syn-gen-b",
                awards=[
                    {
                        "scope": "package",
                        "supplier_id": "syn-gen-b",
                        "quote_event_id": "e2",
                    }
                ],
            ),
        ]
        result = self._result_from_actions(eid, actions)
        report = self.economics.score_result(result, repeat=1)
        self.assertFalse(report["eligible"])
        self.assertEqual(
            report["eligibility_reason"],
            "terminal_not_feasible",
        )
        self.assertIsNone(report["feasible_price_regret_pct"])

    def test_zero_oracle_cost_is_not_normalized(self):
        pct, status = normalize_regret(0.0, 0.0)
        self.assertIsNone(pct)
        self.assertEqual(status, "not_normalizable_zero_oracle")

        pct, status = normalize_regret(10.0, 0.0)
        self.assertIsNone(pct)
        self.assertEqual(status, "not_normalizable_zero_oracle")

    def test_reference_cohort_uses_joint_positive_oracle_runs(self):
        coverage = [
            self.economics_report("e1", 1, selected=100, oracle=90),
            self.economics_report("e2", 1, selected=0, oracle=0),
            self.economics_report(
                "e3",
                1,
                selected=100,
                oracle=90,
                eligible=False,
            ),
        ]
        react = [
            self.economics_report("e1", 1, selected=95, oracle=90),
            self.economics_report("e2", 1, selected=0, oracle=0),
            self.economics_report("e3", 1, selected=99, oracle=90),
        ]
        cohort = freeze_reference_cohort(coverage, react)
        self.assertEqual(cohort["status"], "available")
        self.assertEqual(cohort["reference_cohort_count"], 1)
        self.assertEqual(cohort["joint_regret_eligible_count"], 2)
        self.assertEqual(
            cohort[
                "zero_oracle_cost_run_count_outside_percentage_reference_cohort"
            ],
            1,
        )
        self.assertEqual(
            cohort["run_keys"],
            [{"episode_id": "e1", "repeat": 1}],
        )

    def test_empty_reference_cohort_is_explicit(self):
        coverage = [
            self.economics_report("e1", 1, selected=0, oracle=0)
        ]
        react = [
            self.economics_report("e1", 1, selected=0, oracle=0)
        ]
        cohort = freeze_reference_cohort(coverage, react)
        self.assertEqual(
            cohort["status"],
            "unavailable_empty_reference_cohort",
        )
        self.assertEqual(cohort["reference_cohort_count"], 0)

        comparison = compare_candidate_on_reference_cohort(
            [],
            coverage_repair_reports=coverage,
            react_reports=react,
            reference_cohort=cohort,
        )
        self.assertEqual(
            comparison["status"],
            "unavailable_empty_reference_cohort",
        )
        self.assertIsNone(
            comparison[
                "mean_feasible_price_regret_pct_on_reference_cohort"
            ]
        )

    def test_candidate_comparison_is_paired_on_same_run_keys(self):
        coverage = [
            self.economics_report(
                "e-usd", 1, selected=110, oracle=100, currency="USD"
            ),
            self.economics_report(
                "e-php", 1, selected=220, oracle=200, currency="PHP"
            ),
        ]
        react = [
            self.economics_report(
                "e-usd", 1, selected=105, oracle=100, currency="USD"
            ),
            self.economics_report(
                "e-php", 1, selected=210, oracle=200, currency="PHP"
            ),
        ]
        candidate = [
            self.economics_report(
                "e-usd", 1, selected=102, oracle=100, currency="USD"
            ),
            self.economics_report(
                "e-php", 1, selected=204, oracle=200, currency="PHP"
            ),
        ]
        cohort = freeze_reference_cohort(coverage, react)
        comparison = compare_candidate_on_reference_cohort(
            candidate,
            coverage_repair_reports=coverage,
            react_reports=react,
            reference_cohort=cohort,
        )
        self.assertEqual(comparison["status"], "comparable")
        self.assertTrue(comparison["regret_comparable"])
        self.assertEqual(comparison["reference_cohort_count"], 2)
        self.assertEqual(
            comparison[
                "candidate_regret_eligibility_rate_on_reference_cohort"
            ],
            1.0,
        )
        self.assertTrue(
            math.isclose(
                comparison[
                    "mean_feasible_price_regret_pct_on_reference_cohort"
                ],
                2.0,
            )
        )
        coverage_savings = comparison["paired_savings"]["coverage_repair"]
        self.assertEqual(
            set(coverage_savings["native_savings_by_currency"]),
            {"USD", "PHP"},
        )
        self.assertEqual(
            coverage_savings["native_savings_by_currency"]["USD"][
                "sum_paired_savings_native"
            ],
            8.0,
        )
        self.assertEqual(
            coverage_savings["native_savings_by_currency"]["PHP"][
                "sum_paired_savings_native"
            ],
            16.0,
        )

    def test_supplied_cohort_must_match_baseline_derived_cohort(self):
        coverage = [
            self.economics_report("e1", 1, selected=110, oracle=100),
        ]
        react = [
            self.economics_report("e1", 1, selected=105, oracle=100),
        ]
        candidate = [
            self.economics_report("e1", 1, selected=101, oracle=100),
        ]
        cohort = freeze_reference_cohort(coverage, react)
        cohort["run_keys"] = []
        cohort["reference_cohort_count"] = 0
        cohort["status"] = "unavailable_empty_reference_cohort"
        with self.assertRaisesRegex(EconomicsError, "does not match"):
            compare_candidate_on_reference_cohort(
                candidate,
                coverage_repair_reports=coverage,
                react_reports=react,
                reference_cohort=cohort,
            )

    def test_incomplete_candidate_cannot_use_regret_for_ranking(self):
        coverage = [
            self.economics_report("e1", 1, selected=110, oracle=100),
            self.economics_report("e2", 1, selected=110, oracle=100),
        ]
        react = [
            self.economics_report("e1", 1, selected=105, oracle=100),
            self.economics_report("e2", 1, selected=105, oracle=100),
        ]
        candidate = [
            self.economics_report("e1", 1, selected=101, oracle=100)
        ]
        comparison = compare_candidate_on_reference_cohort(
            candidate,
            coverage_repair_reports=coverage,
            react_reports=react,
        )
        self.assertEqual(
            comparison["status"],
            "not_comparable_incomplete_candidate_cohort",
        )
        self.assertFalse(comparison["regret_comparable"])
        self.assertEqual(
            comparison[
                "candidate_regret_eligible_count_on_reference_cohort"
            ],
            1,
        )
        self.assertIsNone(
            comparison[
                "mean_feasible_price_regret_pct_on_reference_cohort"
            ]
        )

    def test_duplicate_report_run_key_is_rejected(self):
        row = self.economics_report("e1", 1, selected=100, oracle=90)
        with self.assertRaisesRegex(EconomicsError, "Duplicate"):
            freeze_reference_cohort([row, row], [row])

    def test_matched_baseline_grids_must_be_identical(self):
        coverage = [
            self.economics_report("e1", 1, selected=100, oracle=90),
            self.economics_report("e2", 1, selected=100, oracle=90),
        ]
        react = [
            self.economics_report("e1", 1, selected=100, oracle=90),
        ]
        with self.assertRaisesRegex(EconomicsError, "grids differ"):
            freeze_reference_cohort(coverage, react)


if __name__ == "__main__":
    unittest.main()
