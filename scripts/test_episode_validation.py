"""Regression tests for the episode/event contract, not agent performance."""
import copy
import json
import unittest

from jsonschema import ValidationError
from validate_episodes import EPISODE_SCHEMA, EPISODE_VALIDATOR, ROOT, validate_action, validate_episode, validate_suite_records


class EpisodeValidationTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "data/episodes/electrical/electrical-bongabon-generator-001.json"
        self.episode = json.loads(path.read_text(encoding="utf-8"))

    def load_episode(self, name):
        path = ROOT / "data/episodes/electrical" / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_valid_episode(self):
        validate_episode(self.episode)

    def test_suite_retains_original_grounding_and_can_expand(self):
        paths = sorted((ROOT / "data/episodes/electrical").glob("*.json"))
        self.assertGreaterEqual(len(paths), 5)
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in paths
        ]
        self.assertEqual(
            len({r["episode_id"] for r in records}),
            len(records),
        )
        self.assertEqual(
            len({r["initial_state_ref"]["package_id"] for r in records}),
            len(records),
        )
        self.assertTrue(
            all(
                r["initial_state_ref"]["grounding"] == "real_public"
                for r in records
            )
        )

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

    def test_award_scope_must_be_covered_by_quote(self):
        record = self.load_episode("electrical-national-museum-lighting-002")
        record["oracle"]["acceptable_terminal_outcomes"][0]["awards"][1]["quote_event_id"] = "e1"
        record["oracle"]["acceptable_terminal_outcomes"][0]["awards"][1]["supplier_id"] = "syn-light-a"
        with self.assertRaises(ValueError):
            validate_episode(record)

    def test_quote_event_requires_offer_scope_in_schema(self):
        record = copy.deepcopy(self.episode)
        record["events"][0].pop("offer_scope")
        with self.assertRaises(ValidationError):
            EPISODE_VALIDATOR.validate(record)

    def test_nonquote_event_rejects_offer_scope_in_schema(self):
        record = copy.deepcopy(self.episode)
        nonquote = next(event for event in record["events"] if event["type"] == "supplier_non_response")
        nonquote["offer_scope"] = {"kind": "package"}
        with self.assertRaises(ValidationError):
            EPISODE_VALIDATOR.validate(record)

    def test_event_emission_policy_is_one_shot(self):
        record = copy.deepcopy(self.episode)
        record["events"][0]["emission_policy"] = "repeat"
        with self.assertRaises(ValidationError):
            EPISODE_VALIDATOR.validate(record)

        record = copy.deepcopy(self.episode)
        record["events"][0].pop("emission_policy")
        with self.assertRaises(ValidationError):
            EPISODE_VALIDATOR.validate(record)

    def test_no_award_outcome_is_representable(self):
        record = copy.deepcopy(self.episode)
        record["objective"]["terminal_state"] = "no_award"
        record["objective"]["description"] = "Conclude that no valid award can be made."
        record["oracle"]["acceptable_terminal_outcomes"] = [{
            "outcome_id": "o1",
            "decision": "no_award",
            "awards": [],
            "rationale": "No revealed supplier satisfies the required constraints."
        }]
        validate_episode(record)

    def test_no_award_outcome_rejects_award_entries(self):
        record = copy.deepcopy(self.episode)
        record["objective"]["terminal_state"] = "no_award"
        record["oracle"]["acceptable_terminal_outcomes"][0]["decision"] = "no_award"
        with self.assertRaises(ValidationError):
            validate_episode(record)

    def test_award_outcome_rejects_empty_awards(self):
        record = copy.deepcopy(self.episode)
        record["oracle"]["acceptable_terminal_outcomes"][0]["awards"] = []
        with self.assertRaises(ValidationError):
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

    def test_at_step_semantics_are_explicit(self):
        trigger = EPISODE_SCHEMA["properties"]["events"]["items"]["properties"]["trigger"]
        self.assertIn("accepted agent actions", trigger["properties"]["step"]["description"])
        self.assertIn("after matching after_action events", trigger["properties"]["step"]["description"])

    def test_two_event_type_episode_is_valid(self):
        record = self.load_episode("electrical-national-museum-lighting-002")
        self.assertEqual(len({event["type"] for event in record["events"]}), 2)
        validate_episode(record)

    def test_scenario_coverage_is_broad(self):
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (ROOT / "data/episodes/electrical").glob("*.json")
        ]
        tags = {tag for record in records for tag in record["scenario"]["tags"]}
        required = {
            "requirement_gap","supplier_non_response","quote_revision","requirement_change",
            "quantity_change","lead_time_conflict","supplier_withdrawal","budget_conflict",
            "multi_lot","supplier_eligibility","compliance_conflict"
        }
        self.assertTrue(required.issubset(tags))

    def test_action_contract(self):
        validate_action({
            "action_id":"a1",
            "episode_id":self.episode["episode_id"],
            "type":"send_rfq",
            "supplier_id":"syn-gen-a",
            "arguments":{"scope":"package"}
        })
        with self.assertRaises(ValidationError):
            validate_action({
                "action_id":"a2",
                "episode_id":self.episode["episode_id"],
                "type":"invent_supplier",
                "supplier_id":None,
                "arguments":{}
            })

    def test_economic_preferred_outcomes_must_be_acceptable(self):
        record = copy.deepcopy(self.episode)
        record["oracle"]["economic_objective"]["preferred_outcome_ids"] = ["o999"]
        with self.assertRaisesRegex(ValueError, "unknown acceptable outcomes"):
            validate_episode(record)

    def test_economic_objective_is_required(self):
        record = copy.deepcopy(self.episode)
        record["oracle"].pop("economic_objective")
        with self.assertRaises(ValidationError):
            EPISODE_VALIDATOR.validate(record)

    def test_bongabon_has_feasible_nonpreferred_outcome(self):
        record = self.load_episode("electrical-bongabon-generator-001")
        ids = {o["outcome_id"] for o in record["oracle"]["acceptable_terminal_outcomes"]}
        self.assertIn("o2", ids)
        self.assertEqual(record["oracle"]["economic_objective"]["preferred_outcome_ids"], ["o1"])

    def test_economic_preference_must_match_lowest_package_price(self):
        record = copy.deepcopy(self.episode)
        revision = next(
            event
            for event in record["events"]
            if event["event_id"] == "e5"
        )
        revision["details"]["total_price"] = 390000
        with self.assertRaisesRegex(
            ValueError,
            "preferred outcomes do not match minimum-price",
        ):
            validate_episode(record)

    def test_economic_preference_uses_sum_of_multi_lot_prices(self):
        record = self.load_episode("electrical-national-museum-lighting-002")
        lot1_a = next(
            event
            for event in record["events"]
            if event["event_id"] == "e1"
        )
        lot1_a["details"]["lots"]["1"]["price"] = 2400000
        with self.assertRaisesRegex(
            ValueError,
            "preferred outcomes do not match minimum-price",
        ):
            validate_episode(record)

    def test_economic_preference_includes_all_minimum_price_ties(self):
        record = copy.deepcopy(self.episode)
        supplier_a = next(
            event
            for event in record["events"]
            if event["event_id"] == "e1"
        )
        supplier_c = next(
            event
            for event in record["events"]
            if event["event_id"] == "e5"
        )
        supplier_a["details"]["total_price"] = supplier_c["details"]["total_price"]
        with self.assertRaisesRegex(
            ValueError,
            "preferred outcomes do not match minimum-price",
        ):
            validate_episode(record)
if __name__ == "__main__":
    unittest.main()
