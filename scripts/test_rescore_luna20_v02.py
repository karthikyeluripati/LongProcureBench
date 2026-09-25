"""Regression tests for the frozen Luna Evaluator v0.2 rescore."""
import unittest

from rescore_luna20_v02 import build_summary, load_frozen_runs


class Luna20V02RescoreTests(unittest.TestCase):
    def test_committed_frozen_source_is_complete_and_verified(self):
        runs = load_frozen_runs()
        self.assertEqual(len(runs), 60)
        counts = {}
        for run in runs:
            counts[run["episode_id"]] = (
                counts.get(run["episode_id"], 0) + 1
            )
        self.assertEqual(len(counts), 20)
        self.assertTrue(all(count == 3 for count in counts.values()))

    @staticmethod
    def record(
        episode_id,
        *,
        terminal=True,
        legacy_process=False,
        obligation_success=True,
        strict_v02=True,
        resolved=2,
        unresolved=0,
    ):
        obligation_results = [
            {
                "checkpoint": "follow_up_nonresponse",
                "status": "resolved",
            }
            for _ in range(resolved)
        ] + [
            {
                "checkpoint": "handle_amendment",
                "status": "unresolved",
            }
            for _ in range(unresolved)
        ]
        return {
            "episode_id": episode_id,
            "run_id": f"{episode_id}-r",
            "source_status": "completed",
            "accepted_actions": 3,
            "legacy": {
                "terminal_feasible": terminal,
                "hard_constraints_all_passed": terminal,
                "feasible_process_success": legacy_process,
                "episode_success": legacy_process,
            },
            "v02": {
                "terminal_outcome": {"correct": terminal},
                "hard_constraints": {"all_passed": terminal},
                "economic_objective": {"satisfied": strict_v02},
                "feasible_obligation_success": obligation_success,
                "episode_success_v02": strict_v02,
                "obligations": {
                    "actionable": resolved + unresolved,
                    "resolved": resolved,
                    "unresolved": unresolved,
                    "no_opportunity": 0,
                    "not_applicable": 1,
                    "results": obligation_results + [{
                        "checkpoint": "request_quote_revision",
                        "status": "not_applicable",
                    }],
                },
            },
        }

    def test_summary_separates_legacy_and_v02_success(self):
        records = []
        for number in range(1, 21):
            episode_id = f"electrical-test-{number:03d}"
            for repeat in range(3):
                records.append(
                    self.record(
                        episode_id,
                        legacy_process=False,
                        obligation_success=True,
                        strict_v02=True,
                    )
                )
                records[-1]["run_id"] += f"-{repeat}"
        summary = build_summary(records)
        overall = summary["by_group"]["all_20"]
        self.assertEqual(
            overall["legacy_feasible_process_success_rate"],
            0.0,
        )
        self.assertEqual(
            overall["feasible_obligation_success_rate"],
            1.0,
        )
        self.assertEqual(overall["obligation_resolution_rate"], 1.0)

    def test_unresolved_obligations_are_counted_by_type(self):
        records = [
            self.record(
                "electrical-test-001",
                obligation_success=False,
                strict_v02=False,
                resolved=1,
                unresolved=2,
            )
        ]
        summary = build_summary(records)
        overall = summary["by_group"]["all_20"]
        self.assertEqual(overall["actionable_obligations"], 3)
        self.assertEqual(overall["resolved_obligations"], 1)
        self.assertEqual(overall["unresolved_obligations"], 2)
        self.assertEqual(
            overall["unresolved_obligation_counts"],
            {"handle_amendment": 2},
        )
        self.assertAlmostEqual(
            overall["obligation_resolution_rate"],
            1 / 3,
        )


if __name__ == "__main__":
    unittest.main()
