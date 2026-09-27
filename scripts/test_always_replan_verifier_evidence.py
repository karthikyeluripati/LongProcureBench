"""Regression checks for frozen always-replan + verifier evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from audit_always_replan_verifier_v01 import (
    _gate,
    build_comparison,
    check_provenance_entries,
)
from materialize_always_replan_verifier_evidence_v01 import _compact_record
from frozen_always_replan_verifier_v01 import (
    EXPECTED_EPISODES,
    EXPECTED_REPEATS,
    EXPECTED_RUNS,
    load_frozen_always_replan_verifier_source,
)


class FrozenAlwaysReplanVerifierEvidenceTests(unittest.TestCase):
    def test_frozen_grid_and_usage_contract(self):
        records = load_frozen_always_replan_verifier_source(__import__('pathlib').Path(__file__).resolve().parents[1])
        self.assertEqual(len(records), EXPECTED_RUNS)
        self.assertEqual(len({r['episode_id'] for r in records}), EXPECTED_EPISODES)
        self.assertEqual({r['repeat'] for r in records}, set(range(1, EXPECTED_REPEATS + 1)))
        self.assertTrue(all(not r['policy_metrics']['usage_incomplete'] for r in records))
        self.assertTrue(all(r['policy_metrics']['model_calls_failed'] == 0 for r in records))

    def test_provenance_entries_are_linked_to_compact_replay(self):
        root = Path(__file__).resolve().parents[1]
        records = load_frozen_always_replan_verifier_source(root)
        check_provenance_entries(records)

        source = (
            root
            / "evidence"
            / "always-replan-verifier-v0.1"
            / "source-provenance.txt"
        ).read_text(encoding="utf-8")
        lines = source.splitlines()
        fields = lines[0].split("|")
        fields[4] = "0" * 64
        lines[0] = "|".join(fields)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source-provenance.txt"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "does not match frozen replay",
            ):
                check_provenance_entries(records, path)

    def test_materializer_rejects_bad_execution_or_evaluation_state(self):
        base = {
            "episode_id": "electrical-bongabon-generator-001",
            "status": "completed",
            "error": None,
            "evaluation_error": None,
            "evaluation": {
                "evaluation_version": "0.2.0",
                "episode_id": "electrical-bongabon-generator-001",
            },
            "trajectory": [],
            "policy_metrics": {},
        }
        cases = (
            ("execution", {**base, "error": {"type": "RuntimeError"}}),
            (
                "evaluation_error",
                {**base, "evaluation_error": {"type": "EvaluationError"}},
            ),
            (
                "evaluation_version",
                {
                    **base,
                    "evaluation": {
                        **base["evaluation"],
                        "evaluation_version": "0.1.0",
                    },
                },
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode_dir = root / "electrical-bongabon-generator-001"
            episode_dir.mkdir(parents=True)
            path = episode_dir / "run-001.json"
            for name, payload in cases:
                with self.subTest(name=name):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        _compact_record(path, root)

    def test_predeclared_gate_rejects_frozen_result(self):
        comparison = build_comparison()
        self.assertFalse(comparison['predeclared_gate']['passed'])
        self.assertLess(comparison['delta']['terminal_feasible_pp'], -5.0)
        self.assertLess(comparison['delta']['feasible_obligation_success_pp'], -2.0)

    def test_gate_branches_are_frozen(self):
        self.assertTrue(_gate({
            'feasible_obligation_success_pp': 5.0,
            'terminal_feasible_pp': -5.0,
            'episode_success_v02_pp': 0.0,
        })['branch1']['passed'])
        self.assertTrue(_gate({
            'feasible_obligation_success_pp': -2.0,
            'terminal_feasible_pp': -5.0,
            'episode_success_v02_pp': 5.0,
        })['branch2']['passed'])

    def test_mechanism_diagnostic_is_replay_derived(self):
        comparison = build_comparison()
        diagnostic = comparison['mechanism_diagnostic']
        self.assertEqual(diagnostic['verifier_terminal_proposals'], 585)
        self.assertEqual(diagnostic['verifier_rejections'], 557)
        self.assertEqual(
            diagnostic['rejected_verifier_recommendation_counts']['request_buyer_clarification'],
            545,
        )
        self.assertEqual(comparison['always_replan_verifier']['status_counts']['max_actions'], 32)


if __name__ == '__main__':
    unittest.main()
