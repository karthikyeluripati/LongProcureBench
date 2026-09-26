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
    REVISION_SOURCE_TYPES = {
        "quote_received",
        "quote_revision",
        "substitution_proposed",
    }
    EVENT_OBLIGATIONS = {
        "follow_up_nonresponse": {"supplier_non_response"},
        "handle_supplier_question": {"supplier_question"},
        "handle_amendment": {"requirement_change", "quantity_change"},
        "recover_from_withdrawal": {"supplier_withdrawal"},
    }
    STARTING_STATE_OBLIGATIONS = {"resolve_requirement_gap"}
    BRANCH_OBLIGATIONS = {"request_quote_revision"}
    PROXY_CHECKPOINTS = {
        "normalize_quotes",
        "validate_eligibility",
        "validate_compliance",
    }
    PROCEDURAL_CHECKPOINTS = {
        "solicit_competition",
        "evaluate_quotes",
        "award_or_recommend",
    }

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
            required_ids = {
                item["item_id"]
                for item in final_state["initial_state"]["line_items"]
                if item.get("award_requirement", "required") == "required"
            }
            optional_ids = initial_ids - required_ids
            counts = {item_id: 0 for item_id in initial_ids}
            for award in awards:
                for item_id in self._required_items(award["scope"], initial_ids):
                    if item_id in counts:
                        counts[item_id] += 1
            required_complete = all(
                counts[item_id] == 1 for item_id in required_ids
            )
            optional_not_duplicated = all(
                counts[item_id] <= 1 for item_id in optional_ids
            )
            passed = (
                bool(initial_ids)
                and required_complete
                and optional_not_duplicated
            )
            return passed, (
                f"award item counts={counts}, "
                f"required={sorted(required_ids)}, "
                f"optional={sorted(optional_ids)}"
            )

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

    @staticmethod
    def _trace_observations(trace):
        return [
            (row["step"], event)
            for row in trace
            for event in row["observations"]
        ]

    @staticmethod
    def _trace_horizon(trace):
        return trace[-1]["step"] if trace else 0

    @staticmethod
    def _terminal_awards(final_state):
        terminal = final_state.get("terminal")
        if not terminal or terminal.get("decision") != "award":
            return []
        return list(terminal.get("awards", []))

    @staticmethod
    def _obligation_record(
        *,
        obligation_id,
        checkpoint,
        category,
        status,
        detail,
        trigger_event_id=None,
        supplier_id=None,
        trigger_step=None,
        resolution_step=None,
        applicability_reason=None,
    ):
        actionable = status in {"resolved", "unresolved"}
        return {
            "obligation_id": obligation_id,
            "checkpoint": checkpoint,
            "category": category,
            "status": status,
            "applicable": status != "not_applicable",
            "actionable": actionable,
            "resolved": (
                True if status == "resolved"
                else False if status == "unresolved"
                else None
            ),
            "trigger_event_id": trigger_event_id,
            "supplier_id": supplier_id,
            "trigger_step": trigger_step,
            "resolution_step": resolution_step,
            "applicability_reason": applicability_reason,
            "detail": detail,
        }

    def _event_obligation_records(
        self,
        name,
        trace,
        final_state,
        terminal_result,
        hard,
    ):
        trigger_types = self.EVENT_OBLIGATIONS[name]
        observations = self._trace_observations(trace)
        triggers = [
            (step, event)
            for step, event in observations
            if event["type"] in trigger_types
        ]
        if not triggers:
            return [self._obligation_record(
                obligation_id=f"{name}:na",
                checkpoint=name,
                category="event_obligation",
                status="not_applicable",
                detail="No matching trigger event was revealed.",
                applicability_reason="trigger_not_revealed",
            )]

        horizon = self._trace_horizon(trace)
        actions = [row["action"] for row in trace]
        terminal_awards = self._terminal_awards(final_state)
        records = []

        for step, event in triggers:
            event_id = event["event_id"]
            supplier_id = event.get("supplier_id")
            obligation_id = f"{name}:{event_id}"

            if step >= horizon:
                records.append(self._obligation_record(
                    obligation_id=obligation_id,
                    checkpoint=name,
                    category="event_obligation",
                    status="no_opportunity",
                    detail=(
                        f"Trigger {event_id} was revealed at the final accepted "
                        f"step {step}; no later action opportunity existed."
                    ),
                    trigger_event_id=event_id,
                    supplier_id=supplier_id,
                    trigger_step=step,
                    applicability_reason="matching_event_revealed",
                ))
                continue

            resolution_step = None
            detail = None

            if name == "follow_up_nonresponse":
                resolution_step = next(
                    (
                        row["step"]
                        for row in trace
                        if row["step"] > step
                        and row["action"]["type"] == "send_follow_up"
                        and row["action"]["supplier_id"] == supplier_id
                    ),
                    None,
                )
                detail = (
                    f"Follow-up after non-response from {supplier_id}."
                )
            elif name == "handle_supplier_question":
                resolution_step = next(
                    (
                        row["step"]
                        for row in trace
                        if row["step"] > step
                        and row["action"]["type"] == "answer_supplier_question"
                        and row["action"]["supplier_id"] == supplier_id
                    ),
                    None,
                )
                detail = (
                    f"Answer after supplier question from {supplier_id}."
                )
            elif name == "handle_amendment":
                amendment_step = next(
                    (
                        row["step"]
                        for row in trace
                        if row["step"] > step
                        and row["action"]["type"] == "issue_amendment"
                    ),
                    None,
                )
                if amendment_step is not None:
                    if terminal_awards:
                        event_steps = {
                            observed["event_id"]: observed_step
                            for observed_step, observed in observations
                        }
                        awarded_steps = [
                            event_steps.get(award["quote_event_id"])
                            for award in terminal_awards
                        ]
                        fresh = (
                            all(x is not None for x in awarded_steps)
                            and all(x > amendment_step for x in awarded_steps)
                        )
                        if fresh:
                            resolution_step = max(awarded_steps)
                            detail = (
                                f"Amendment at step {amendment_step}; all "
                                "awarded quotes were revealed afterward."
                            )
                        else:
                            detail = (
                                f"Amendment at step {amendment_step}, but "
                                f"awarded quote steps {awarded_steps} were not "
                                "all post-amendment."
                            )
                    else:
                        resolution_step = amendment_step
                        detail = f"Amendment issued at step {amendment_step}."
                else:
                    detail = "No amendment was issued after the revealed change."
            elif name == "recover_from_withdrawal":
                withdrawn_supplier = supplier_id
                selected_withdrawn = any(
                    award["supplier_id"] == withdrawn_supplier
                    for award in terminal_awards
                )
                recovered = (
                    terminal_result["correct"]
                    and hard["all_passed"]
                    and not selected_withdrawn
                )
                if recovered:
                    resolution_step = horizon
                    detail = (
                        "Terminal decision restored a feasible hard-constraint-"
                        "satisfying path without awarding the withdrawn supplier."
                    )
                else:
                    detail = (
                        "No feasible hard-constraint-satisfying terminal "
                        "recovery path was established after withdrawal."
                    )
            else:
                raise EvaluationError(f"Unknown event obligation: {name}")

            records.append(self._obligation_record(
                obligation_id=obligation_id,
                checkpoint=name,
                category="event_obligation",
                status="resolved" if resolution_step is not None else "unresolved",
                detail=detail,
                trigger_event_id=event_id,
                supplier_id=supplier_id,
                trigger_step=step,
                resolution_step=resolution_step,
                applicability_reason="matching_event_revealed",
            ))
        return records

    def _requirement_gap_records(self, trace):
        name = "resolve_requirement_gap"
        horizon = self._trace_horizon(trace)
        if horizon == 0:
            return [self._obligation_record(
                obligation_id=f"{name}:initial",
                checkpoint=name,
                category="starting_state_obligation",
                status="no_opportunity",
                detail="No accepted action opportunity was present.",
                trigger_step=0,
                applicability_reason="visible_from_initial_state",
            )]

        clarification_step = next(
            (
                row["step"]
                for row in trace
                if any(
                    event["type"] == "buyer_clarification"
                    for event in row["observations"]
                )
            ),
            None,
        )
        first_rfq_step = next(
            (
                row["step"]
                for row in trace
                if row["action"]["type"] == "send_rfq"
            ),
            None,
        )
        resolved = (
            clarification_step is not None
            and (
                first_rfq_step is None
                or clarification_step < first_rfq_step
            )
        )
        return [self._obligation_record(
            obligation_id=f"{name}:initial",
            checkpoint=name,
            category="starting_state_obligation",
            status="resolved" if resolved else "unresolved",
            detail=(
                f"clarification_step={clarification_step}, "
                f"first_rfq_step={first_rfq_step}"
            ),
            trigger_step=0,
            resolution_step=clarification_step if resolved else None,
            applicability_reason="visible_from_initial_state",
        )]

    def _revision_obligation_records(
        self,
        episode,
        trace,
        final_state,
    ):
        name = "request_quote_revision"
        awards = self._terminal_awards(final_state)
        if not awards:
            return [self._obligation_record(
                obligation_id=f"{name}:na",
                checkpoint=name,
                category="branch_conditional",
                status="not_applicable",
                detail="No terminal award path selected.",
                applicability_reason="no_selected_award_path",
            )]

        by_event = {
            event["event_id"]: event
            for event in episode["events"]
        }
        event_steps = {
            event["event_id"]: step
            for step, event in self._trace_observations(trace)
        }
        acceptable_triplets = {
            (
                award["supplier_id"],
                award["scope"],
                award["quote_event_id"],
            )
            for outcome in episode["oracle"]["acceptable_terminal_outcomes"]
            for award in outcome.get("awards", [])
        }
        revision_repairs = {}
        for outcome in episode["oracle"]["acceptable_terminal_outcomes"]:
            for award in outcome.get("awards", []):
                event = by_event.get(award["quote_event_id"])
                if event and event["type"] == "quote_revision":
                    revision_repairs.setdefault(
                        (award["supplier_id"], award["scope"]),
                        set(),
                    ).add(award["quote_event_id"])

        needs = {}
        for award in awards:
            supplier_id = award["supplier_id"]
            scope = award["scope"]
            event_id = award["quote_event_id"]
            event = by_event.get(event_id)
            if event is None:
                continue

            reason = None
            if event["type"] == "quote_revision":
                reason = "selected_award_uses_revision"
            elif (
                (supplier_id, scope, event_id) not in acceptable_triplets
                and (supplier_id, scope) in revision_repairs
            ):
                reason = "selected_original_offer_has_revision_repair_path"

            if reason is None:
                continue

            trigger_step = event_steps.get(event_id)
            if event["type"] == "quote_revision":
                request_step = next(
                    (
                        row["step"]
                        for row in trace
                        if row["action"]["type"] == "request_quote_revision"
                        and row["action"]["supplier_id"] == supplier_id
                        and row["step"] <= event_steps.get(event_id, row["step"])
                    ),
                    None,
                )
                prior_offer_steps = [
                    observed_step
                    for observed_step, observed in self._trace_observations(trace)
                    if observed_step < (request_step or 10**9)
                    and observed.get("supplier_id") == supplier_id
                    and observed["type"] in self.REVISION_SOURCE_TYPES
                ]
                if prior_offer_steps:
                    trigger_step = max(prior_offer_steps)

            current = needs.get(supplier_id)
            candidate = {
                "supplier_id": supplier_id,
                "trigger_step": trigger_step,
                "reason": reason,
                "selected_event_ids": {event_id},
            }
            if current is None:
                needs[supplier_id] = candidate
            else:
                current["selected_event_ids"].add(event_id)
                if (
                    trigger_step is not None
                    and (
                        current["trigger_step"] is None
                        or trigger_step < current["trigger_step"]
                    )
                ):
                    current["trigger_step"] = trigger_step
                if reason == "selected_award_uses_revision":
                    current["reason"] = reason

        if not needs:
            return [self._obligation_record(
                obligation_id=f"{name}:na",
                checkpoint=name,
                category="branch_conditional",
                status="not_applicable",
                detail=(
                    "Selected award path is feasible without a quote revision."
                ),
                applicability_reason="selected_path_does_not_require_revision",
            )]

        horizon = self._trace_horizon(trace)
        records = []
        for supplier_id, need in sorted(needs.items()):
            trigger_step = need["trigger_step"]
            obligation_id = f"{name}:{supplier_id}"
            if trigger_step is None or trigger_step >= horizon:
                records.append(self._obligation_record(
                    obligation_id=obligation_id,
                    checkpoint=name,
                    category="branch_conditional",
                    status="no_opportunity",
                    detail=(
                        "Revision need became applicable without a later "
                        "accepted action opportunity."
                    ),
                    supplier_id=supplier_id,
                    trigger_step=trigger_step,
                    applicability_reason=need["reason"],
                ))
                continue

            request_step = next(
                (
                    row["step"]
                    for row in trace
                    if row["step"] > trigger_step
                    and row["action"]["type"] == "request_quote_revision"
                    and row["action"]["supplier_id"] == supplier_id
                ),
                None,
            )
            selected_path_repaired = all(
                by_event.get(event_id, {}).get("type") == "quote_revision"
                for event_id in need["selected_event_ids"]
            )
            resolved = request_step is not None and selected_path_repaired
            records.append(self._obligation_record(
                obligation_id=obligation_id,
                checkpoint=name,
                category="branch_conditional",
                status="resolved" if resolved else "unresolved",
                detail=(
                    f"selected_events={sorted(need['selected_event_ids'])}, "
                    f"request_step={request_step}, "
                    f"selected_path_repaired={selected_path_repaired}"
                ),
                supplier_id=supplier_id,
                trigger_step=trigger_step,
                resolution_step=request_step if resolved else None,
                applicability_reason=need["reason"],
            ))
        return records

    def _obligations(
        self,
        episode,
        trace,
        final_state,
        terminal_result,
        hard,
    ):
        records = []
        required = episode["oracle"]["required_checkpoints"]

        for name in required:
            if name in self.EVENT_OBLIGATIONS:
                records.extend(self._event_obligation_records(
                    name,
                    trace,
                    final_state,
                    terminal_result,
                    hard,
                ))
            elif name in self.STARTING_STATE_OBLIGATIONS:
                records.extend(self._requirement_gap_records(trace))
            elif name in self.BRANCH_OBLIGATIONS:
                records.extend(self._revision_obligation_records(
                    episode,
                    trace,
                    final_state,
                ))

        encountered = sum(
            record["status"] != "not_applicable"
            for record in records
        )
        actionable = sum(record["actionable"] for record in records)
        resolved = sum(record["status"] == "resolved" for record in records)
        unresolved = sum(record["status"] == "unresolved" for record in records)
        no_opportunity = sum(
            record["status"] == "no_opportunity"
            for record in records
        )
        not_applicable = sum(
            record["status"] == "not_applicable"
            for record in records
        )
        return {
            "version": "0.2.0",
            "encountered": encountered,
            "actionable": actionable,
            "resolved": resolved,
            "unresolved": unresolved,
            "no_opportunity": no_opportunity,
            "not_applicable": not_applicable,
            "resolution_rate": (
                resolved / actionable if actionable else None
            ),
            "all_actionable_resolved": unresolved == 0,
            "has_actionable_obligations": actionable > 0,
            "results": records,
        }

    def _checkpoint_diagnostics(self, checkpoints):
        def summarize(names):
            results = [
                result
                for result in checkpoints["results"]
                if result["checkpoint"] in names
            ]
            return {
                "completed": sum(result["complete"] for result in results),
                "total": len(results),
                "all_completed": all(
                    result["complete"] for result in results
                ) if results else True,
                "results": results,
            }

        return {
            "proxy": summarize(self.PROXY_CHECKPOINTS),
            "procedural": summarize(self.PROCEDURAL_CHECKPOINTS),
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

        obligations = self._obligations(
            episode,
            trace,
            final_state,
            terminal,
            hard,
        )
        diagnostics = self._checkpoint_diagnostics(checkpoints)
        feasible_obligation_success = (
            terminal["correct"]
            and hard["all_passed"]
            and obligations["all_actionable_resolved"]
        )
        episode_success_v02 = (
            feasible_obligation_success
            and economic["satisfied"]
        )

        return {
            "episode_id": episode_id,
            "evaluation_version": "0.2.0",
            "episode_success": success,
            "feasible_process_success": feasible_process_success,
            "episode_success_v02": episode_success_v02,
            "feasible_obligation_success": feasible_obligation_success,
            "terminal_outcome": terminal,
            "economic_objective": economic,
            "hard_constraints": hard,
            "required_checkpoints": checkpoints,
            "obligations": obligations,
            "checkpoint_diagnostics": diagnostics,
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
