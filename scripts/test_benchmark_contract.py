"""Regression tests for the benchmark observability/split freeze."""
import copy
import unittest

from validate_benchmark_contract import (
    load_episodes,
    load_initial_states,
    load_matrix,
    load_split,
    validate_contract,
)


class BenchmarkContractTests(unittest.TestCase):
    def setUp(self):
        self.rows = load_matrix()
        self.split = load_split()
        self.episodes = load_episodes()
        self.initial_states = load_initial_states()

    def test_current_contract_is_valid(self):
        validate_contract(
            self.rows, self.split, self.episodes, self.initial_states
        )

    def test_matrix_cannot_relabel_current_episode_as_held_out(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["paper_split"] = "held_out_test"
        with self.assertRaises(ValueError):
            validate_contract(rows, self.split, self.episodes, self.initial_states)

    def test_current_calibration_episode_cannot_move_to_held_out(self):
        rows = copy.deepcopy(self.rows)
        split = copy.deepcopy(self.split)
        episode_id = rows[0]["episode_id"]
        rows[0]["paper_split"] = "held_out_test"
        split["development_calibration_episodes"].remove(episode_id)
        split["held_out_test"]["episode_ids"].append(episode_id)
        with self.assertRaises(ValueError):
            validate_contract(rows, split, self.episodes, self.initial_states)

    def test_source_family_must_match_supporting_document_provenance(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["source_family"] = "SAM.gov"
        with self.assertRaises(ValueError):
            validate_contract(rows, self.split, self.episodes, self.initial_states)

    def test_matrix_cannot_claim_future_events_are_visible(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["future_event_visibility"] = "visible_at_reset"
        with self.assertRaises(ValueError):
            validate_contract(rows, self.split, self.episodes, self.initial_states)

    def test_matrix_failure_mechanisms_must_match_episode_tags(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["primary_failure_mechanisms"] = "quote_received"
        with self.assertRaises(ValueError):
            validate_contract(rows, self.split, self.episodes, self.initial_states)

    def test_held_out_initial_states_must_exist(self):
        split = copy.deepcopy(self.split)
        split["held_out_test"]["initial_state_package_ids"].append(
            "missing-heldout-package"
        )
        with self.assertRaises(ValueError):
            validate_contract(
                self.rows, split, self.episodes, self.initial_states
            )

    def test_held_out_initial_states_cannot_reuse_development_packages(self):
        split = copy.deepcopy(self.split)
        development_package = next(
            iter(self.episodes.values())
        )["initial_state_ref"]["package_id"]
        split["held_out_test"]["initial_state_package_ids"].append(
            development_package
        )
        with self.assertRaises(ValueError):
            validate_contract(
                self.rows, split, self.episodes, self.initial_states
            )

    def test_split_must_assign_every_committed_episode(self):
        split = copy.deepcopy(self.split)
        split["development_calibration_episodes"].pop()
        with self.assertRaises(ValueError):
            validate_contract(self.rows, split, self.episodes, self.initial_states)


if __name__ == "__main__":
    unittest.main()
