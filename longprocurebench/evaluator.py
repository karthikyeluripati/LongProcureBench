"""Deterministic evaluator for LongProcureBench trajectories."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .runtime import LongProcureBenchEnv


class EvaluationError(ValueError):
    """Raised for invalid evaluator configuration or trajectory input."""


class LongProcureBenchEvaluator:
    QUOTE_TYPES = {"quote_received", "quote_revision"}

    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[1]
        self._schema = self._read_json(self.repo_root / "schema/evaluation.schema.json")
        Draft202012Validator.check_schema(self._schema)
        self._validator = Draft202012Validator(self._schema)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def load_config(self, episode_id: str) -> dict[str, Any]:
        path = self.repo_root / "data/evaluation/electrical" / f"{episode_id}.json"
        if not path.is_file():
            raise EvaluationError(f"Missing evaluation config for episode: {episode_id}")
        config = self._read_json(path)
        self._validator.validate(config)
        if config["episode_id"] != episode_id:
            raise EvaluationError("Evaluation config episode_id mismatch")
        return config

    def _replay(self, episode_id: str, actions: list[dict[str, Any]]):
        env = LongProcureBenchEnv(repo_root=self.repo_root)
        state = env.reset(episode_id)
        trace = []
        for action in actions:
            state = env.step(deepcopy(action))
            trace.append({"step": state["step"], "action": deepcopy(action), "observations": deepcopy(state["observations"])})
        return state, trace

    @staticmethod
    def _get_path(value: Any, path: str) -> Any:
        current = value
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise EvaluationError(f"Missing evaluation path: {path}")
        return current

    @staticmethod
    def _normalize_awards(awards):
        return sorted((a["scope"], a["supplier_id"], a["quote_event_id"]) for a in awards)

    def _terminal_result(self, episode, terminal):
        if terminal is None:
            return {"correct": False, "matched_outcome_id": None, "detail": "Trajectory did not terminate."}
        for outcome in episode["oracle"]["acceptable_terminal_outcomes"]:
            if outcome["decision"] != terminal.get("decision"):
                continue
            if outcome["decision"] == "no_award":
                return {"correct": True, "matched_outcome_id": outcome["outcome_id"], "detail": "Terminal no-award decision matches an acceptable outcome."}
            if self._normalize_awards(outcome["awards"]) == self._normalize_awards(terminal.get("awards", [])):
                return {"correct": True, "matched_outcome_id": outcome["outcome_id"], "detail": "Terminal award set matches an acceptable outcome."}
        return {"correct": False, "matched_outcome_id": None, "detail": "Terminal decision or award set does not match any acceptable outcome."}

    @staticmethod
    def _economic_result(episode, terminal_result):
        objective = episode["oracle"]["economic_objective"]
        matched = terminal_result["matched_outcome_id"]
        satisfied = (
            terminal_result["correct"]
            and matched in objective["preferred_outcome_ids"]
        )
        return {
            "kind": objective["kind"],
            "description": objective["description"],
            "satisfied": satisfied,
            "matched_outcome_id": matched,
            "preferred_outcome_ids": list(objective["preferred_outcome_ids"]),
        }

    @staticmethod
    def _required_items(scope, initial_item_ids):
        if scope == "package":
            return set(initial_item_ids)
        if scope.startswith("lot-"):
            return {scope[len("lot-"):]}
        raise EvaluationError(f"Unsupported award scope: {scope}")

    @staticmethod
    def _covered_items(event, initial_item_ids):
        scope = event["offer_scope"]
        return set(initial_item_ids) if scope["kind"] == "package" else set(scope["item_ids"])

    def _check_rule(self, check, terminal, episode, final_state, trace):
        kind = check["kind"]
        initial_ids = {i["item_id"] for i in final_state["initial_state"]["line_items"]}
        revealed = {e["event_id"]: e for e in final_state["revealed_events"]}
        suppliers = {s["supplier_id"]: s for s in episode["suppliers"]}
        awards = terminal.get("awards", []) if terminal and terminal.get("decision") == "award" else []

        if kind == "event_before_action":
            event_step = None
            action_step = None
            for row in trace:
                if action_step is None and row["action"]["type"] == check["action_type"]:
                    action_step = row["step"]
                if any(obs["event_id"] == check["event_id"] for obs in row["observations"]):
                    event_step = row["step"]
            passed = event_step is not None and action_step is not None and event_step < action_step
            return passed, f"event_step={event_step}, first_action_step={action_step}"

        if kind == "award_scope_complete":
            counts = {item_id: 0 for item_id in initial_ids}
            for award in awards:
                for item_id in self._required_items(award["scope"], initial_ids):
                    if item_id in counts:
                        counts[item_id] += 1
            passed = bool(counts) and all(v == 1 for v in counts.values())
            return passed, f"award item counts={counts}"

        applicable = [a for a in awards if check["scope"] is None or a["scope"] == check["scope"]]
        if not applicable:
            return False, f"No award matches scope {check['scope']!r}"

        results = []
        for award in applicable:
            event = revealed.get(award["quote_event_id"])
            if event is None:
                results.append((False, f"{award['quote_event_id']} not revealed"))
                continue
            supplier = suppliers[award["supplier_id"]]

            if kind in {"award_quote_max", "award_quote_min", "award_quote_equals"}:
                actual = self._get_path(event["details"], check["path"])
                expected = check["value"]
                if kind == "award_quote_max":
                    passed, op = actual <= expected, "<="
                elif kind == "award_quote_min":
                    passed, op = actual >= expected, ">="
                else:
                    passed, op = actual == expected, "=="
                results.append((passed, f"{award['scope']} {check['path']}={actual!r} {op} {expected!r}"))
            elif kind == "award_supplier_equals":
                actual = supplier.get(check["supplier_field"])
                expected = check["value"]
                results.append((actual == expected, f"{award['supplier_id']} {check['supplier_field']}={actual!r} == {expected!r}"))
            elif kind == "award_supplier_not_withdrawn":
                withdrawn = any(e["type"] == "supplier_withdrawal" and e["supplier_id"] == award["supplier_id"] for e in final_state["revealed_events"])
                results.append((not withdrawn, f"{award['supplier_id']} withdrawn={withdrawn}"))
            elif kind == "award_quote_latest":
                required = self._required_items(award["scope"], initial_ids)
                candidates = []
                for idx, candidate in enumerate(final_state["revealed_events"]):
                    if candidate["type"] not in self.QUOTE_TYPES or candidate["supplier_id"] != award["supplier_id"]:
                        continue
                    if not required.issubset(self._covered_items(candidate, initial_ids)):
                        continue
                    candidates.append((candidate["details"].get("revision", -1), idx, candidate["event_id"]))
                latest = max(candidates) if candidates else None
                latest_id = latest[2] if latest else None
                results.append((latest_id == award["quote_event_id"], f"selected={award['quote_event_id']}, latest={latest_id}"))
            else:
                raise EvaluationError(f"Unsupported check kind: {kind}")

        return all(x[0] for x in results), "; ".join(x[1] for x in results)

    def _hard_constraints(self, episode, config, final_state, trace):
        rules = {r["constraint_id"]: r["checks"] for r in config["constraint_rules"]}
        results = []
        for constraint in episode["oracle"]["hard_constraints"]:
            checks = rules.get(constraint["constraint_id"])
            if not checks:
                raise EvaluationError(f"No machine checks for {constraint['constraint_id']}")
            check_results = []
            for check in checks:
                passed, detail = self._check_rule(check, final_state["terminal"], episode, final_state, trace)
                check_results.append({"kind": check["kind"], "passed": passed, "detail": detail})
            results.append({
                "constraint_id": constraint["constraint_id"],
                "description": constraint["description"],
                "passed": all(c["passed"] for c in check_results),
                "checks": check_results,
            })
        return {
            "passed": sum(r["passed"] for r in results),
            "total": len(results),
            "all_passed": all(r["passed"] for r in results),
            "results": results,
        }

    @staticmethod
    def _prior_events(trace, step):
        out = []
        for row in trace:
            if row["step"] >= step:
                break
            out.extend(row["observations"])
        return out

    def _checkpoint(self, name, trace, final_state, hard, config):
        actions = [r["action"] for r in trace]
        if name == "solicit_competition":
            n = len({a["supplier_id"] for a in actions if a["type"] == "send_rfq"})
            return n >= 2, f"RFQs sent to {n} suppliers", "direct"
        if name == "follow_up_nonresponse":
            for row in trace:
                a = row["action"]
                if a["type"] == "send_follow_up" and any(e["type"] == "supplier_non_response" and e["supplier_id"] == a["supplier_id"] for e in self._prior_events(trace, row["step"])):
                    return True, f"Followed up {a['supplier_id']} after non-response", "direct"
            return False, "No follow-up after non-response", "direct"
        if name == "handle_supplier_question":
            for row in trace:
                a = row["action"]
                if a["type"] == "answer_supplier_question" and any(e["type"] == "supplier_question" and e["supplier_id"] == a["supplier_id"] for e in self._prior_events(trace, row["step"])):
                    return True, f"Answered {a['supplier_id']} after supplier question", "direct"
            return False, "No answer after supplier question", "direct"
        if name == "handle_amendment":
            change_step = None
            amendment_step = None
            for row in trace:
                if any(
                    event["type"] in {"requirement_change", "quantity_change"}
                    for event in row["observations"]
                ):
                    change_step = row["step"]
                if (
                    row["action"]["type"] == "issue_amendment"
                    and change_step is not None
                    and row["step"] > change_step
                ):
                    amendment_step = row["step"]

            if change_step is None:
                return False, "No requirement change was revealed", "direct"
            if amendment_step is None:
                return False, (
                    f"No amendment was issued after requirement change at step "
                    f"{change_step}"
                ), "direct"

            terminal = final_state["terminal"]
            if terminal is None or terminal.get("decision") != "award":
                return False, "No terminal award available after amendment", "direct"

            awarded_quote_ids = {
                award["quote_event_id"] for award in terminal.get("awards", [])
            }
            quote_steps = {}
            for row in trace:
                for event in row["observations"]:
                    if event["event_id"] in awarded_quote_ids:
                        quote_steps[event["event_id"]] = row["step"]

            missing = awarded_quote_ids - set(quote_steps)
            if missing:
                return False, (
                    f"Awarded quote events were not observed: {sorted(missing)}"
                ), "direct"

            stale = {
                event_id: step
                for event_id, step in quote_steps.items()
                if step < amendment_step
            }
            complete = not stale
            return complete, (
                f"change_step={change_step}, amendment_step={amendment_step}, "
                f"awarded_quote_steps={quote_steps}, stale_awards={stale}"
            ), "direct"
        if name == "request_quote_revision":
            ok = any(a["type"] == "request_quote_revision" for a in actions)
            return ok, "Quote revision request observed" if ok else "No quote revision request", "direct"
        if name == "evaluate_quotes":
            ok = any(a["type"] == "evaluate_quotes" for a in actions)
            return ok, "Quote evaluation action observed" if ok else "No quote evaluation action", "direct"
        if name == "normalize_quotes":
            count = 0
            for row in trace:
                count += sum(e["type"] in self.QUOTE_TYPES for e in row["observations"])
                if row["action"]["type"] == "evaluate_quotes" and count >= 2:
                    return True, f"Evaluation occurred with {count} revealed quotes", "proxy"
            return False, "No evaluation after at least two quotes", "proxy"
        if name == "resolve_requirement_gap":
            cstep = None
            rstep = None
            for row in trace:
                if rstep is None and row["action"]["type"] == "send_rfq":
                    rstep = row["step"]
                if any(e["type"] == "buyer_clarification" for e in row["observations"]):
                    cstep = row["step"]
            ok = cstep is not None and rstep is not None and cstep < rstep
            return ok, f"clarification_step={cstep}, first_rfq_step={rstep}", "direct"
        if name == "recover_from_withdrawal":
            withdrawal_step = None
            withdrawn_suppliers = set()
            for row in trace:
                for event in row["observations"]:
                    if event["type"] == "supplier_withdrawal":
                        withdrawal_step = row["step"]
                        withdrawn_suppliers.add(event["supplier_id"])
            if withdrawal_step is None:
                return False, "No supplier withdrawal revealed", "direct"

            replacement_quote_step = None
            replacement_quote_id = None
            for row in trace:
                if row["step"] <= withdrawal_step:
                    continue
                for event in row["observations"]:
                    if (
                        event["type"] in self.QUOTE_TYPES
                        and event["supplier_id"] not in withdrawn_suppliers
                    ):
                        replacement_quote_step = row["step"]
                        replacement_quote_id = event["event_id"]
                        break
                if replacement_quote_step is not None:
                    break

            if replacement_quote_step is None:
                return False, (
                    f"withdrawal_step={withdrawal_step}; no new quote/revision "
                    f"was revealed after withdrawal"
                ), "direct"

            reevaluation_step = next(
                (
                    row["step"]
                    for row in trace
                    if row["step"] > replacement_quote_step
                    and row["action"]["type"] == "evaluate_quotes"
                ),
                None,
            )
            complete = reevaluation_step is not None
            return complete, (
                f"withdrawal_step={withdrawal_step}, "
                f"replacement_quote={replacement_quote_id}@{replacement_quote_step}, "
                f"reevaluation_step={reevaluation_step}"
            ), "direct"
        if name == "award_or_recommend":
            ok = final_state["terminal"] is not None
            return ok, "Terminal decision reached" if ok else "No terminal decision", "direct"
        if name == "validate_eligibility":
            has_rule = any(c["kind"] == "award_supplier_equals" for r in config["constraint_rules"] for c in r["checks"])
            ok = has_rule and hard["all_passed"] and any(a["type"] == "evaluate_quotes" for a in actions)
            return ok, "Eligibility rule passed with evaluate_quotes" if ok else "Eligibility proxy not satisfied", "proxy"
        if name == "validate_compliance":
            ok = hard["all_passed"] and any(a["type"] == "evaluate_quotes" for a in actions)
            return ok, "Hard constraints passed with evaluate_quotes" if ok else "Compliance proxy not satisfied", "proxy"
        raise EvaluationError(f"Unsupported checkpoint: {name}")

    def _checkpoints(self, episode, config, final_state, trace, hard):
        results = []
        for name in episode["oracle"]["required_checkpoints"]:
            complete, detail, mode = self._checkpoint(name, trace, final_state, hard, config)
            results.append({"checkpoint": name, "complete": complete, "evidence_mode": mode, "detail": detail})
        return {
            "completed": sum(r["complete"] for r in results),
            "total": len(results),
            "all_completed": all(r["complete"] for r in results),
            "results": results,
        }

    def evaluate_actions(self, episode_id: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
        env = LongProcureBenchEnv(repo_root=self.repo_root)
        episode = env.load_episode(episode_id)
        config = self.load_config(episode_id)
        final_state, trace = self._replay(episode_id, actions)
        terminal = self._terminal_result(episode, final_state["terminal"])
        hard = self._hard_constraints(episode, config, final_state, trace)
        checkpoints = self._checkpoints(episode, config, final_state, trace, hard)
        violations = [r["constraint_id"] for r in hard["results"] if not r["passed"]]
        economic = self._economic_result(episode, terminal)
        feasible_process_success = (
            terminal["correct"]
            and hard["all_passed"]
            and checkpoints["all_completed"]
        )
        success = feasible_process_success and economic["satisfied"]
        return {
            "episode_id": episode_id,
            "episode_success": success,
            "feasible_process_success": feasible_process_success,
            "terminal_outcome": terminal,
            "economic_objective": economic,
            "hard_constraints": hard,
            "required_checkpoints": checkpoints,
            "constraint_violations": violations,
            "efficiency": {"accepted_actions": len(final_state["action_history"])},
            "terminated": final_state["terminated"],
        }

    def evaluate_state(self, state: dict[str, Any]) -> dict[str, Any]:
        episode_id = state.get("episode_id")
        actions = state.get("action_history")
        if not isinstance(episode_id, str) or not isinstance(actions, list):
            raise EvaluationError("State must contain episode_id and action_history")
        return self.evaluate_actions(episode_id, actions)
