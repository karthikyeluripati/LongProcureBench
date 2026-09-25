"""Regression tests for the episode/event contract, not agent performance."""
import copy
import json
import unittest

from jsonschema import ValidationError
from validate_episodes import ROOT, validate_action, validate_episode

class EpisodeValidationTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "data/episodes/electrical/electrical-bongabon-generator-001.json"
        self.episode = json.loads(path.read_text(encoding="utf-8"))

    def test_valid_episode(self):
        validate_episode(self.episode)

    def test_v01_has_five_distinct_real_initial_states(self):
        paths = sorted((ROOT / "data/episodes/electrical").glob("*.json"))
        self.assertEqual(len(paths), 5)
        records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        self.assertEqual(len({r["episode_id"] for r in records}), 5)
        self.assertEqual(len({r["initial_state_ref"]["package_id"] for r in records}), 5)
        self.assertTrue(all(r["initial_state_ref"]["grounding"] == "real_public" for r in records))

    def test_unknown_initial_state_rejected(self):
        record = copy.deepcopy(self.episode)
        record["initial_state_ref"]["path"] = "data/initial_states/electrical/does-not-exist.json"
        with self.assertRaises(ValueError):
            validate_episode(record)

    def test_unknown_event_supplier_rejected(self):
        record = copy.deepcopy(self.episode)
        record["events"][0]["supplier_id"] = "syn-does-not-exist"
        with self.assertRaises(ValueError):
            validate_episode(record)

    def test_duplicate_event_id_rejected(self):
        record = copy.deepcopy(self.episode)
        record["events"][1]["event_id"] = record["events"][0]["event_id"]
        with self.assertRaises(ValueError):
            validate_episode(record)

    def test_award_must_match_quote_supplier(self):
        record = copy.deepcopy(self.episode)
        record["oracle"]["acceptable_terminal_outcomes"][0]["awards"][0]["supplier_id"] = "syn-gen-b"
        with self.assertRaises(ValueError):
            validate_episode(record)

    def test_synthetic_event_cannot_be_marked_real(self):
        record = copy.deepcopy(self.episode)
        record["events"][0]["synthetic"] = False
        with self.assertRaises(ValidationError):
            validate_episode(record)

    def test_after_action_trigger_requires_action_type(self):
        record = copy.deepcopy(self.episode)
        record["events"][0]["trigger"]["action_type"] = None
        with self.assertRaises(ValueError):
            validate_episode(record)

    def test_scenario_coverage_is_broad(self):
        records = [json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "data/episodes/electrical").glob("*.json")]
        tags = {tag for record in records for tag in record["scenario"]["tags"]}
        required = {"requirement_gap","supplier_non_response","quote_revision","requirement_change","quantity_change","lead_time_conflict","supplier_withdrawal","budget_conflict","multi_lot","supplier_eligibility","compliance_conflict"}
        self.assertTrue(required.issubset(tags))

    def test_action_contract(self):
        validate_action({"action_id":"a1","episode_id":self.episode["episode_id"],"type":"send_rfq","supplier_id":"syn-gen-a","arguments":{"scope":"package"}})
        with self.assertRaises(ValidationError):
            validate_action({"action_id":"a2","episode_id":self.episode["episode_id"],"type":"invent_supplier","supplier_id":None,"arguments":{}})

if __name__ == "__main__":
    unittest.main()
