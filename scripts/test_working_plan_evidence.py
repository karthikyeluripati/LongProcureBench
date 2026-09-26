"""Regression tests for the frozen maintained-working-plan experiment."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

import audit_working_plan_v01 as audit_module
from audit_working_plan_v01 import BOOTSTRAP_SAMPLER, _bootstrap_index, _check_declared_replay_files, check_frozen_comparison, check_manifest, check_source_provenance, evaluate_predeclared_gate
from frozen_working_plan_v01 import EPISODES, load_frozen_working_plan_source

class WorkingPlanFrozenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_frozen_working_plan_source(ROOT); check_manifest(); check_source_provenance(); cls.comparison = check_frozen_comparison()

    def test_frozen_source_is_exact_twenty_by_three_grid(self):
        self.assertEqual(len(self.source), 60); self.assertEqual({r['episode_id'] for r in self.source}, set(EPISODES)); self.assertEqual(len({(r['episode_id'], r['repeat']) for r in self.source}), 60)

    def test_primary_result_and_gate_are_frozen(self):
        c = self.comparison['context_compiled']; w = self.comparison['working_plan']; d = self.comparison['delta']
        self.assertEqual(c['terminal_feasible'], 46); self.assertEqual(w['terminal_feasible'], 41)
        self.assertEqual(c['feasible_obligation_success'], 40); self.assertEqual(w['feasible_obligation_success'], 27)
        self.assertEqual(c['episode_success_v02'], 14); self.assertEqual(w['episode_success_v02'], 17)
        self.assertAlmostEqual(d['terminal_feasible_pp'], -8.3333333333); self.assertAlmostEqual(d['feasible_obligation_success_pp'], -21.6666666667); self.assertAlmostEqual(d['episode_success_v02_pp'], 5.0)
        self.assertFalse(self.comparison['predeclared_gate']['passed'])

    def test_plan_diagnostics_are_frozen(self):
        w = self.comparison['working_plan']
        self.assertEqual(w['plan_updates'], 473); self.assertEqual(w['plan_rejections'], 8); self.assertEqual(w['runs_with_plan_rejections'], 7); self.assertEqual(w['max_plan_steps'], 4)
        self.assertEqual(w['plan_rejection_reasons'], {'Plan stop_condition must be 1-240 characters': 8})
        self.assertEqual(w['final_empty_plan_runs'], 60)

    def test_predeclared_gate_supports_both_frozen_branches(self):
        self.assertTrue(evaluate_predeclared_gate({'terminal_feasible_pp':-5.0,'feasible_obligation_success_pp':5.0,'episode_success_v02_pp':0.0})['passed'])
        self.assertTrue(evaluate_predeclared_gate({'terminal_feasible_pp':-4.0,'feasible_obligation_success_pp':-2.0,'episode_success_v02_pp':5.0})['passed'])

    def test_bootstrap_sampler_matches_prior_audits(self):
        self.assertEqual(BOOTSTRAP_SAMPLER, 'sha256-index-v1')
        self.assertEqual([_bootstrap_index(0, d) for d in range(20)], [15,14,18,4,14,19,0,13,6,1,18,6,1,17,16,5,17,18,4,2])

    def test_undeclared_replay_fragment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); (d/'replay-source.b64').write_text('x'); (d/'replay-source.extra.b64').write_text('x')
            with self.assertRaisesRegex(ValueError, 'replay file set mismatch'): _check_declared_replay_files(d, ('replay-source.b64',))

    def test_record_provenance_drift_is_rejected(self):
        p = ROOT/'evidence'/'working-plan-reactive-v0.1'/'source-provenance.txt'; lines = p.read_text().splitlines(); f = lines[0].split('|'); f[-1] = '0'*64; lines[0] = '|'.join(f)
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp)/'source-provenance.txt'; changed.write_text('\n'.join(lines)+'\n')
            with patch.object(audit_module, 'PROVENANCE_PATH', changed):
                with self.assertRaises(ValueError): check_source_provenance()

if __name__ == '__main__': unittest.main()
