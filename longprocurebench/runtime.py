"""Deterministic execution environment for LongProcureBench episode-model v0.1."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .validation import InitialStateValidator


class EnvironmentError(ValueError):
    """Raised when an action is invalid for the current environment state."""


class LongProcureBenchEnv:
    """Small deterministic runtime over the frozen episode/action contracts."""

    SUPPLIER_ACTIONS = {
        "send_rfq",
        "send_follow_up",
        "answer_supplier_question",
        "request_quote_revision",
    }
    NO_SUPPLIER_ACTIONS = {
        "request_buyer_clarification",
        "identify_suppliers",
        "issue_amendment",
        "evaluate_quotes",
        "no_award",
    }
    QUOTE_EVENT_TYPES = {"quote_received", "quote_revision"}

    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root is not None
            else Path(__file__).resolve().parents[1]
        )
        self._episode_schema = self._read_json(self.repo_root / "schema/episode.schema.json")
        self._action_schema = self._read_json(self.repo_root / "schema/action.schema.json")
        self._initial_state_validator = InitialStateValidator(
            self.repo_root / "schema/initial-state.schema.json"
        )
        Draft202012Validator.check_schema(self._episode_schema)
        Draft202012Validator.check_schema(self._action_schema)
        checker = FormatChecker()
        self._episode_validator = Draft202012Validator(
            self._episode_schema, format_checker=checker
        )
        self._action_validator = Draft202012Validator(
            self._action_schema, format_checker=checker
        )
        self._clear()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _clear(self) -> None:
        self._episode: dict[str, Any] | None = None
        self._initial_state: dict[str, Any] | None = None
        self._suppliers: dict[str, dict[str, Any]] = {}
        self._initial_item_ids: set[str] = set()
        self._step = 0
        self._consumed_events: set[str] = set()
        self._revealed_events: list[dict[str, Any]] = []
        self._action_history: list[dict[str, Any]] = []
        self._action_ids: set[str] = set()
        self._suppliers_revealed = False
        self._terminated = False
        self._terminal: dict[str, Any] | None = None

    def load_episode(self, episode_id: str) -> dict[str, Any]:
        path = self.repo_root / "data/episodes/electrical" / f"{episode_id}.json"
        if not path.is_file():
            raise EnvironmentError(f"Unknown episode: {episode_id}")
        return self._read_json(path)

    def reset(self, episode: str | Path | dict[str, Any]) -> dict[str, Any]:
        """Reset to an episode and return the agent-visible state."""
        if isinstance(episode, dict):
            record = deepcopy(episode)
        else:
            candidate = Path(episode)
            if candidate.suffix == ".json" or "/" in str(episode) or "\\" in str(episode):
                path = candidate if candidate.is_absolute() else self.repo_root / candidate
                if not path.is_file():
                    raise EnvironmentError(f"Episode file not found: {path}")
                record = self._read_json(path)
            else:
                record = self.load_episode(str(episode))

        self._episode_validator.validate(record)
        initial_path = self.repo_root / record["initial_state_ref"]["path"]
        if not initial_path.is_file():
            raise EnvironmentError(f"Initial state not found: {initial_path}")
        initial = self._read_json(initial_path)
        self._initial_state_validator.validate(initial)
        if initial["package_id"] != record["initial_state_ref"]["package_id"]:
            raise EnvironmentError("Episode initial_state_ref package_id mismatch")

        supplier_ids = [supplier["supplier_id"] for supplier in record["suppliers"]]
        if len(supplier_ids) != len(set(supplier_ids)):
            raise EnvironmentError("Episode contains duplicate supplier_id values")
        event_ids = [event["event_id"] for event in record["events"]]
        if len(event_ids) != len(set(event_ids)):
            raise EnvironmentError("Episode contains duplicate event_id values")

        self._clear()
        self._episode = deepcopy(record)
        self._initial_state = deepcopy(initial)
        self._suppliers = {
            supplier["supplier_id"]: deepcopy(supplier)
            for supplier in record["suppliers"]
        }
        self._initial_item_ids = {
            item["item_id"] for item in initial["line_items"]
        }
        return self._snapshot(observations=[])

    @property
    def state(self) -> dict[str, Any]:
        self._require_reset()
        return self._snapshot(observations=[])

    def _require_reset(self) -> None:
        if self._episode is None or self._initial_state is None:
            raise EnvironmentError("Call reset() before step()")

    def _snapshot(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        self._require_reset()
        visible_suppliers = (
            [
                {
                    "supplier_id": supplier["supplier_id"],
                    "display_name": supplier["display_name"],
                    "synthetic": supplier["synthetic"],
                }
                for supplier in self._suppliers.values()
            ]
            if self._suppliers_revealed
            else []
        )
        return {
            "episode_id": self._episode["episode_id"],
            "step": self._step,
            "terminated": self._terminated,
            "terminal": deepcopy(self._terminal),
            "initial_state": deepcopy(self._initial_state),
            "visible_suppliers": visible_suppliers,
            "observations": deepcopy(observations),
            "revealed_events": deepcopy(self._revealed_events),
            "action_history": deepcopy(self._action_history),
        }

    def _validate_supplier_action(self, action: dict[str, Any]) -> None:
        action_type = action["type"]
        supplier_id = action["supplier_id"]

        if action_type in self.SUPPLIER_ACTIONS:
            if supplier_id is None:
                raise EnvironmentError(f"{action_type} requires supplier_id")
            if supplier_id not in self._suppliers:
                raise EnvironmentError(f"Unknown supplier_id: {supplier_id}")
            if not self._suppliers_revealed:
                raise EnvironmentError(
                    "Supplier directory is hidden until identify_suppliers is accepted"
                )
        elif action_type in self.NO_SUPPLIER_ACTIONS and supplier_id is not None:
            raise EnvironmentError(f"{action_type} requires supplier_id=null")

    def _covered_items(self, event: dict[str, Any]) -> set[str]:
        scope = event["offer_scope"]
        if scope["kind"] == "package":
            return set(self._initial_item_ids)
        return set(scope["item_ids"])

    def _required_items(self, scope: str) -> set[str]:
        if scope == "package":
            return set(self._initial_item_ids)
        if scope.startswith("lot-"):
            item_id = scope[len("lot-"):]
            if item_id not in self._initial_item_ids:
                raise EnvironmentError(f"Unknown award scope: {scope}")
            return {item_id}
        raise EnvironmentError(f"Unsupported award scope: {scope}")

    def _validate_award_action(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        awards = action["arguments"].get("awards")
        if not isinstance(awards, list) or not awards:
            raise EnvironmentError(
                "award_supplier requires arguments.awards with at least one entry"
            )

        top_supplier = action["supplier_id"]
        if len(awards) > 1 and top_supplier is not None:
            raise EnvironmentError(
                "Multi-award action requires top-level supplier_id=null"
            )

        revealed = {
            event["event_id"]: event for event in self._revealed_events
        }
        normalized = []
        for award in awards:
            if not isinstance(award, dict):
                raise EnvironmentError("Each award must be an object")
            required = {"scope", "supplier_id", "quote_event_id"}
            if set(award) != required:
                raise EnvironmentError(
                    "Each award requires exactly scope, supplier_id, quote_event_id"
                )
            supplier_id = award["supplier_id"]
            quote_event_id = award["quote_event_id"]
            scope = award["scope"]

            if supplier_id not in self._suppliers:
                raise EnvironmentError(f"Unknown awarded supplier: {supplier_id}")
            if not self._suppliers_revealed:
                raise EnvironmentError("Cannot award before suppliers are revealed")
            if len(awards) == 1 and top_supplier not in (None, supplier_id):
                raise EnvironmentError(
                    "Top-level supplier_id does not match the single award"
                )
            event = revealed.get(quote_event_id)
            if event is None:
                raise EnvironmentError(
                    f"Award references unrevealed quote event: {quote_event_id}"
                )
            if event["type"] not in self.QUOTE_EVENT_TYPES:
                raise EnvironmentError(
                    f"Award event is not a quote: {quote_event_id}"
                )
            if event["supplier_id"] != supplier_id:
                raise EnvironmentError(
                    "Award supplier does not match referenced quote event"
                )
            if not self._required_items(scope).issubset(self._covered_items(event)):
                raise EnvironmentError(
                    f"Quote {quote_event_id} does not cover award scope {scope}"
                )
            normalized.append(deepcopy(award))
        return normalized

    def _validate_action_semantics(self, action: dict[str, Any]) -> dict[str, Any] | None:
        if action["episode_id"] != self._episode["episode_id"]:
            raise EnvironmentError("Action episode_id does not match active episode")
        if action["action_id"] in self._action_ids:
            raise EnvironmentError(f"Duplicate action_id: {action['action_id']}")

        self._validate_supplier_action(action)

        if action["type"] == "request_quote_revision":
            supplier_id = action["supplier_id"]
            has_revealed_quote = any(
                event["type"] in self.QUOTE_EVENT_TYPES
                and event["supplier_id"] == supplier_id
                for event in self._revealed_events
            )
            if not has_revealed_quote:
                raise EnvironmentError(
                    "request_quote_revision requires a previously revealed "
                    f"quote from supplier {supplier_id}"
                )

        if action["type"] == "award_supplier":
            awards = self._validate_award_action(action)
            return {"decision": "award", "awards": awards}
        if action["type"] == "no_award":
            return {
                "decision": "no_award",
                "reason": deepcopy(action["arguments"].get("reason")),
            }
        return None

    @staticmethod
    def _matches_after_action(
        event: dict[str, Any], action: dict[str, Any]
    ) -> bool:
        trigger = event["trigger"]
        if trigger["kind"] != "after_action":
            return False
        if trigger["action_type"] != action["type"]:
            return False
        return (
            trigger["supplier_id"] is None
            or trigger["supplier_id"] == action["supplier_id"]
        )

    def _emit(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = event["event_id"]
        if event_id in self._consumed_events:
            raise EnvironmentError(f"Event already consumed: {event_id}")
        if event.get("emission_policy") != "once":
            raise EnvironmentError(
                f"Unsupported emission policy for {event_id}"
            )
        public_event = deepcopy(event)
        self._consumed_events.add(event_id)
        self._revealed_events.append(public_event)
        return public_event

    def step(self, action: dict[str, Any]) -> dict[str, Any]:
        """Apply one accepted agent action and return the new visible state."""
        self._require_reset()
        if self._terminated:
            raise EnvironmentError("Episode already terminated")

        candidate = deepcopy(action)
        self._action_validator.validate(candidate)
        terminal = self._validate_action_semantics(candidate)

        # Only accepted actions advance time.
        self._step += 1
        self._action_ids.add(candidate["action_id"])
        self._action_history.append(deepcopy(candidate))

        if candidate["type"] == "identify_suppliers":
            self._suppliers_revealed = True

        observations: list[dict[str, Any]] = []

        # Contract order: after_action first, then at_step, both in file order.
        for event in self._episode["events"]:
            if (
                event["event_id"] not in self._consumed_events
                and self._matches_after_action(event, candidate)
            ):
                observations.append(self._emit(event))

        for event in self._episode["events"]:
            trigger = event["trigger"]
            if (
                event["event_id"] not in self._consumed_events
                and trigger["kind"] == "at_step"
                and trigger["step"] == self._step
            ):
                observations.append(self._emit(event))

        if terminal is not None:
            self._terminated = True
            self._terminal = terminal

        return self._snapshot(observations=observations)
