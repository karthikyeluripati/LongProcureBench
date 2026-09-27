"""Regression checks for frozen ReAct comparator evidence."""
from pathlib import Path
import tempfile
import unittest

from audit_react_comparator_v01 import (
    build_comparison,
    check_provenance_entries,
)
from materialize_react_comparator_evidence_v01 import _validate_raw_run
from frozen_react_comparator_v01 import (
    EXPECTED_EPISODES,
    EXPECTED_REPEATS,
    EXPECTED_RUNS,
    load_frozen_react_source,
    load_frozen_react_transcripts,
)


ROOT = Path(__file__).resolve().parents[1]


def minimal_raw_run():
    episode_id = "electrical-bongabon-generator-001"
    action = {
        "action_id": "a1",
        "episode_id": episode_id,
        "type": "identify_suppliers",
        "supplier_id": None,
        "arguments": {},
    }
    observation = [{
        "event_id": "e1",
        "type": "quote_received",
        "supplier_id": "syn-gen-a",
        "details": {"price": 10},
        "trigger": {
            "kind": "after_action",
            "action_type": "identify_suppliers",
            "supplier_id": None,
        },
        "synthetic": True,
        "emission_policy": "once",
    }]
    thought = "Reveal the supplier directory before requesting quotes."
    return {
        "episode_id": episode_id,
        "status": "completed",
        "error": None,
        "evaluation_error": None,
        "evaluation": {
            "evaluation_version": "0.2.0",
            "episode_id": episode_id,
        },
        "trajectory": [{
            "step": 1,
            "action": action,
            "observations": observation,
        }],
        "policy_metrics": {
            "model": "openai/gpt-5.6-sol",
            "usage_incomplete": False,
            "cost_usd": 0.01,
            "model_calls_failed": 0,
            "context_strategy": "factual_compiled_v0.1",
            "agent_pattern": "react_v0.1",
            "temperature": None,
            "reasoning_effort": "medium",
            "model_calls_attempted": 1,
            "react_steps_proposed": 1,
            "react_steps_accepted": 1,
            "react_thought_chars_total": len(thought),
            "react_thought_chars_mean": float(len(thought)),
            "react_thought_chars_max": len(thought),
            "react_transcript": [{
                "step": 1,
                "thought_summary": thought,
                "action": {
                    "type": action["type"],
                    "supplier_id": action["supplier_id"],
                    "arguments": {},
                },
                "observation": [{
                    "event_id": "e1",
                    "type": "quote_received",
                    "supplier_id": "syn-gen-a",
                    "details": {"price": 10},
                }],
            }],
        },
    }


class FrozenReActEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comparison = build_comparison()

    def test_materializer_rejects_transcript_observation_drift(self):
        run = minimal_raw_run()
        run["policy_metrics"]["react_transcript"][0]["observation"][0][
            "details"
        ]["price"] = 999
        with self.assertRaisesRegex(
            ValueError,
            "observation does not match",
        ):
            _validate_raw_run(run, run["episode_id"])

    def test_materializer_rejects_thought_character_metric_drift(self):
        run = minimal_raw_run()
        run["policy_metrics"]["react_thought_chars_total"] += 1
        with self.assertRaisesRegex(
            ValueError,
            "thought-character total mismatch",
        ):
            _validate_raw_run(run, run["episode_id"])

    def test_frozen_grid_and_react_contract(self):
        records = load_frozen_react_source(ROOT)
        self.assertEqual(len(records), EXPECTED_RUNS)
        self.assertEqual(
            len({record["episode_id"] for record in records}),
            EXPECTED_EPISODES,
        )
        self.assertEqual(
            {record["repeat"] for record in records},
            set(range(1, EXPECTED_REPEATS + 1)),
        )
        for record in records:
            metrics = record["policy_metrics"]
            self.assertEqual(
                metrics["model_calls_attempted"],
                len(record["decisions"]),
            )
            self.assertEqual(
                metrics["react_steps_proposed"],
                len(record["decisions"]),
            )
            self.assertEqual(
                metrics["react_steps_accepted"],
                len(record["decisions"]),
            )
            self.assertEqual(metrics["model_calls_failed"], 0)
            self.assertFalse(metrics["usage_incomplete"])

    def test_durable_transcript_matches_replay_and_thought_metrics(self):
        replay = load_frozen_react_source(ROOT)
        transcripts = load_frozen_react_transcripts(ROOT)
        transcript_by_key = {
            (record["episode_id"], record["repeat"]): record
            for record in transcripts
        }
        self.assertEqual(len(transcript_by_key), EXPECTED_RUNS)

        total_thought_chars = 0
        total_steps = 0
        for record in replay:
            key = (record["episode_id"], record["repeat"])
            transcript = transcript_by_key[key]["react_transcript"]
            self.assertEqual(len(transcript), len(record["decisions"]))
            self.assertEqual(
                [step["action"] for step in transcript],
                record["decisions"],
            )
            thought_lengths = [
                len(step["thought_summary"]) for step in transcript
            ]
            self.assertEqual(
                sum(thought_lengths),
                record["policy_metrics"]["react_thought_chars_total"],
            )
            self.assertEqual(
                max(thought_lengths, default=0),
                record["policy_metrics"]["react_thought_chars_max"],
            )
            total_thought_chars += sum(thought_lengths)
            total_steps += len(transcript)

        self.assertEqual(total_steps, 488)
        self.assertEqual(total_thought_chars, 81495)

    def test_matched_result_is_frozen(self):
        comparison = self.comparison
        self.assertEqual(
            comparison["context_compiled"]["terminal_feasible"],
            46,
        )
        self.assertEqual(comparison["react"]["terminal_feasible"], 52)
        self.assertEqual(
            comparison["context_compiled"]["feasible_obligation_success"],
            40,
        )
        self.assertEqual(
            comparison["react"]["feasible_obligation_success"],
            41,
        )
        self.assertEqual(
            comparison["context_compiled"]["episode_success_v02"],
            14,
        )
        self.assertEqual(
            comparison["react"]["episode_success_v02"],
            27,
        )

    def test_react_is_external_comparator_without_inclusion_gate(self):
        comparison = self.comparison
        self.assertEqual(comparison["role"], "external_comparator")
        self.assertIsNone(comparison["decision"]["inclusion_gate"])
        self.assertEqual(
            comparison["decision"]["next_step"],
            "Freeze the development comparator set before any held-out "
            "evaluation.",
        )

    def test_strict_gain_and_resource_increase_are_preserved(self):
        comparison = self.comparison
        delta = comparison["delta"]
        self.assertGreater(delta["episode_success_v02_pp"], 20.0)
        self.assertGreater(delta["terminal_feasible_pp"], 9.0)
        self.assertGreater(delta["total_tokens_pct"], 49.0)
        self.assertGreater(delta["cost_pct"], 73.0)

        intervals = comparison["cluster_bootstrap"]["95pct_ci"]
        self.assertGreater(
            intervals["episode_success_v02_pp"][0],
            0.0,
        )
        self.assertGreater(
            intervals["total_tokens_pct"][0],
            0.0,
        )
        self.assertGreater(intervals["cost_pct"][0], 0.0)

    def test_react_diagnostic_shows_complete_thought_action_steps(self):
        diagnostic = self.comparison["react_diagnostic"]
        self.assertEqual(diagnostic["react_steps_proposed"], 488)
        self.assertEqual(diagnostic["react_steps_accepted"], 488)
        self.assertEqual(
            diagnostic["runs_with_complete_react_steps"],
            60,
        )
        self.assertEqual(diagnostic["thought_chars_total"], 81495)
        self.assertEqual(diagnostic["thought_chars_max"], 252)
        self.assertEqual(
            diagnostic["episode_effect_counts"]["episode_success_v02"],
            {"improved": 8, "tied": 12, "worsened": 0},
        )

    def test_provenance_entries_are_linked_to_compact_replay(self):
        records = load_frozen_react_source(ROOT)
        check_provenance_entries(records)

        source = (
            ROOT
            / "evidence"
            / "react-comparator-v0.1"
            / "source-provenance.txt"
        ).read_text(encoding="utf-8")
        lines = source.splitlines()
        fields = lines[0].split("|")
        fields[4] = "0" * 64
        lines[0] = "|".join(fields)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source-provenance.txt"
            path.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "does not match frozen replay",
            ):
                check_provenance_entries(records, path)


if __name__ == "__main__":
    unittest.main()
