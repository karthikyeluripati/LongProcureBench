"""Checkpoint fairness audit v0.2."""
from __future__ import annotations
import argparse, gzip, json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__('sys').path:
    __import__('sys').path.insert(0, str(ROOT))

from frozen_luna20_source import load_frozen_luna20_source

EVENT_OBLIGATIONS = {
    "follow_up_nonresponse": {"supplier_non_response"},
    "handle_supplier_question": {"supplier_question"},
    "handle_amendment": {"requirement_change", "quantity_change"},
    "recover_from_withdrawal": {"supplier_withdrawal"},
}
STARTING_STATE_OBLIGATIONS = {"resolve_requirement_gap"}
BRANCH_CONDITIONAL = {"request_quote_revision"}
PROXY_CHECKPOINTS = {"normalize_quotes", "validate_eligibility", "validate_compliance"}
PROCEDURAL_CHECKPOINTS = {"solicit_competition", "evaluate_quotes", "award_or_recommend"}


def discover_runs(root: Path):
    runs = sorted(root.glob("**/run-*.json"))
    if not runs:
        raise ValueError(f"No raw run JSON found under {root}")
    return runs


def _observations(run):
    return [
        (row["step"], event)
        for row in run.get("trajectory", [])
        for event in row.get("observations", [])
    ]


def _terminal_step(run):
    trajectory = run.get("trajectory") or []
    return trajectory[-1]["step"] if trajectory else None


def _terminal_awards(run):
    trajectory = run.get("trajectory") or []
    if not trajectory:
        return []
    action = trajectory[-1].get("action") or {}
    if action.get("type") != "award_supplier":
        return []
    return [
        award
        for award in (action.get("arguments") or {}).get("awards") or []
        if isinstance(award, dict)
    ]


def _awarded_event_ids(run):
    return {
        award["quote_event_id"]
        for award in _terminal_awards(run)
        if "quote_event_id" in award
    }


def _event_steps(run):
    return {
        event["event_id"]: step
        for step, event in _observations(run)
        if isinstance(event.get("event_id"), str)
    }


def checkpoint_category(name):
    if name in EVENT_OBLIGATIONS:
        return "event_obligation"
    if name in STARTING_STATE_OBLIGATIONS:
        return "starting_state_obligation"
    if name in BRANCH_CONDITIONAL:
        return "branch_conditional"
    if name in PROXY_CHECKPOINTS:
        return "proxy"
    if name in PROCEDURAL_CHECKPOINTS:
        return "procedural"
    return "unknown"


def _revision_repair_branch(run, episode):
    observations = _observations(run)
    awarded_ids = _awarded_event_ids(run)
    steps = _event_steps(run)
    awarded_types = {
        event["type"]
        for _, event in observations
        if event.get("event_id") in awarded_ids
    }
    if "quote_revision" in awarded_types:
        return True, [steps[x] for x in awarded_ids if x in steps], "selected_award_uses_revision"
    if episode is None:
        return False, [], None

    evaluation = run.get("evaluation") or {}
    if (
        (evaluation.get("terminal_outcome") or {}).get("correct")
        and (evaluation.get("hard_constraints") or {}).get("all_passed")
    ):
        return False, [], None

    by_event = {e["event_id"]: e for e in episode.get("events", [])}
    repair_pairs = {
        (award["supplier_id"], award["scope"])
        for outcome in episode.get("oracle", {}).get("acceptable_terminal_outcomes", [])
        for award in outcome.get("awards", [])
        if by_event.get(award.get("quote_event_id"), {}).get("type") == "quote_revision"
    }
    trigger_steps = []
    for award in _terminal_awards(run):
        event_id = award.get("quote_event_id")
        if (
            (award.get("supplier_id"), award.get("scope")) in repair_pairs
            and by_event.get(event_id, {}).get("type") == "quote_received"
            and event_id in steps
        ):
            trigger_steps.append(steps[event_id])
    if trigger_steps:
        return True, trigger_steps, "infeasible_original_offer_has_revision_repair_path"
    return False, [], None


def audit_checkpoint(run, checkpoint, episode=None):
    name = checkpoint["checkpoint"]
    category = checkpoint_category(name)
    observations = _observations(run)
    terminal_step = _terminal_step(run)
    trigger_steps = []
    applicable = opportunity = None
    reason = None

    if category == "event_obligation":
        trigger_steps = [
            step
            for step, event in observations
            if event["type"] in EVENT_OBLIGATIONS[name]
        ]
        applicable = bool(trigger_steps)
        reason = "matching_event_revealed" if applicable else "trigger_not_revealed"
        opportunity = applicable and terminal_step is not None and min(trigger_steps) < terminal_step
    elif category == "starting_state_obligation":
        applicable = True
        opportunity = terminal_step is not None and terminal_step >= 1
        reason = "visible_from_initial_state"
    elif category == "branch_conditional":
        applicable, trigger_steps, reason = _revision_repair_branch(run, episode)
        opportunity = (
            applicable and terminal_step is not None
            and bool(trigger_steps) and min(trigger_steps) < terminal_step
        )

    failed = not bool(checkpoint["complete"])
    non_applicable_failure = (
        failed and applicable is False
        and category in {"event_obligation", "branch_conditional"}
    )
    no_opportunity_failure = (
        failed and applicable is True and opportunity is False
        and category in {"event_obligation", "starting_state_obligation", "branch_conditional"}
    )
    applicable_obligation_failure = (
        failed and applicable is True and opportunity is True
        and category in {"event_obligation", "starting_state_obligation", "branch_conditional"}
    )
    return {
        "checkpoint": name,
        "category": category,
        "current_complete": bool(checkpoint["complete"]),
        "evidence_mode": checkpoint.get("evidence_mode"),
        "applicable": applicable,
        "opportunity": opportunity,
        "applicability_reason": reason,
        "trigger_steps": trigger_steps,
        "terminal_step": terminal_step,
        "non_applicable_failure": non_applicable_failure,
        "no_opportunity_failure": no_opportunity_failure,
        "applicable_obligation_failure": applicable_obligation_failure,
        "detail": checkpoint.get("detail"),
    }


def _overprescriptive_recovery(run, audited):
    if audited["checkpoint"] != "recover_from_withdrawal":
        return False
    if audited["current_complete"] or not audited["applicable"]:
        return False
    evaluation = run.get("evaluation") or {}
    if not (evaluation.get("terminal_outcome") or {}).get("correct"):
        return False
    if not (evaluation.get("hard_constraints") or {}).get("all_passed"):
        return False
    observations = _observations(run)
    withdrawal_steps = [
        step for step, event in observations
        if event["type"] == "supplier_withdrawal"
    ]
    if not withdrawal_steps:
        return False
    awarded_ids = _awarded_event_ids(run)
    awarded_steps = [
        step for step, event in observations
        if event.get("event_id") in awarded_ids
    ]
    return bool(awarded_steps) and max(awarded_steps) < min(withdrawal_steps)


def _load_episode(repo_root, episode_id):
    path = repo_root / "data" / "episodes" / "electrical" / f"{episode_id}.json"
    if not path.is_file():
        raise ValueError(f"Missing episode for audit: {episode_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def audit_runs(runs, repo_root):
    counters = {
        "checkpoint_failure_counts": Counter(),
        "non_applicable_current_failure_counts": Counter(),
        "no_opportunity_failure_counts": Counter(),
        "applicable_obligation_failure_counts": Counter(),
        "proxy_failure_counts": Counter(),
        "procedural_failure_counts": Counter(),
    }
    recovery = []
    runs_detail = []

    for run in runs:
        evaluation = run.get("evaluation") or {}
        episode = _load_episode(repo_root, run["episode_id"])
        checkpoints = (evaluation.get("required_checkpoints") or {}).get("results") or []
        audited_checkpoints = []
        for checkpoint in checkpoints:
            audited = audit_checkpoint(run, checkpoint, episode)
            audited_checkpoints.append(audited)
            name = audited["checkpoint"]
            if not audited["current_complete"]:
                counters["checkpoint_failure_counts"][name] += 1
            if audited["non_applicable_failure"]:
                counters["non_applicable_current_failure_counts"][name] += 1
            if audited["no_opportunity_failure"]:
                counters["no_opportunity_failure_counts"][name] += 1
            if audited["applicable_obligation_failure"]:
                counters["applicable_obligation_failure_counts"][name] += 1
            if not audited["current_complete"] and audited["category"] == "proxy":
                counters["proxy_failure_counts"][name] += 1
            if not audited["current_complete"] and audited["category"] == "procedural":
                counters["procedural_failure_counts"][name] += 1
            if _overprescriptive_recovery(run, audited):
                recovery.append({
                    "episode_id": run["episode_id"],
                    "run_id": run["run_id"],
                    "checkpoint": name,
                })
        runs_detail.append({
            "episode_id": run["episode_id"],
            "run_id": run["run_id"],
            "source_status": run.get("status"),
            "terminal_feasible": bool((evaluation.get("terminal_outcome") or {}).get("correct")),
            "hard_constraints_all_passed": bool((evaluation.get("hard_constraints") or {}).get("all_passed")),
            "current_feasible_process_success": bool(evaluation.get("feasible_process_success")),
            "checkpoints": audited_checkpoints,
        })

    result = {"schema_version": "0.2.0", "runs": len(runs)}
    for key, counter in counters.items():
        result[key] = dict(counter.most_common())
    result["overprescriptive_recovery_cases"] = recovery
    result["runs_detail"] = runs_detail
    return result


def static_episode_audit(repo_root):
    issues = []
    episode_dir = repo_root / "data" / "episodes" / "electrical"
    paths = sorted(episode_dir.glob("*.json"))
    for path in paths:
        episode = json.loads(path.read_text(encoding="utf-8"))
        event_types = {event["type"] for event in episode["events"]}
        checkpoints = set(episode["oracle"]["required_checkpoints"])
        for checkpoint, triggers in EVENT_OBLIGATIONS.items():
            if checkpoint in checkpoints and not (triggers & event_types):
                issues.append({
                    "episode_id": episode["episode_id"],
                    "checkpoint": checkpoint,
                    "issue": "checkpoint_has_no_matching_trigger_event_type",
                })
        if "request_quote_revision" in checkpoints and "quote_revision" not in event_types:
            issues.append({
                "episode_id": episode["episode_id"],
                "checkpoint": "request_quote_revision",
                "issue": "revision_checkpoint_without_revision_event",
            })
    return {"episodes": len(paths), "issues": issues}


def _fmt_counts(counts):
    return ["- None"] if not counts else [f"- {k}: **{v}**" for k, v in counts.items()]


def report_markdown(audit, static):
    total = lambda key: sum(audit[key].values())
    lines = [
        "# Checkpoint fairness audit v0.2",
        "",
        f"Audited **{audit['runs']}** saved trajectories across **{static['episodes']}** episodes.",
        "",
        "## Headline",
        "",
        f"- Non-applicable current failures: **{total('non_applicable_current_failure_counts')}**",
        f"- No-opportunity failures: **{total('no_opportunity_failure_counts')}**",
        f"- Applicable/actionable obligation failures: **{total('applicable_obligation_failure_counts')}**",
        f"- Proxy checkpoint failures: **{total('proxy_failure_counts')}**",
        f"- Procedural-policy failures: **{total('procedural_failure_counts')}**",
        f"- Potentially over-prescriptive recovery cases: **{len(audit['overprescriptive_recovery_cases'])}**",
        f"- Complete per-run records: **{len(audit['runs_detail'])}**",
        "",
        "## Non-applicable failures",
        "",
        *_fmt_counts(audit["non_applicable_current_failure_counts"]),
        "",
        "## No-opportunity failures",
        "",
        *_fmt_counts(audit["no_opportunity_failure_counts"]),
        "",
        "## Applicable obligation failures",
        "",
        *_fmt_counts(audit["applicable_obligation_failure_counts"]),
        "",
        "## Proxy failures",
        "",
        *_fmt_counts(audit["proxy_failure_counts"]),
        "",
        "## Static episode audit",
        "",
        f"- Static checkpoint/trigger issues: **{len(static['issues'])}**",
    ]
    return "\n".join(lines) + "\n"


def _load_frozen_gzip(path=None):
    """Load a requested gzip JSONL source, or the committed frozen source."""
    if path is None:
        return load_frozen_luna20_source(ROOT)

    candidate = Path(path)
    if not candidate.is_file():
        raise ValueError(f"Input JSONL gzip not found: {candidate}")

    runs = []
    try:
        with gzip.open(candidate, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(
                        f"Input JSONL gzip line {line_number} is not an object"
                    )
                required = ("episode_id", "run_id", "trajectory", "evaluation")
                missing = [key for key in required if key not in record]
                if missing:
                    raise ValueError(
                        f"Input JSONL gzip line {line_number} missing fields: "
                        f"{', '.join(missing)}"
                    )
                if not isinstance(record["episode_id"], str):
                    raise ValueError(
                        f"Input JSONL gzip line {line_number} has invalid episode_id"
                    )
                if not isinstance(record["run_id"], str):
                    raise ValueError(
                        f"Input JSONL gzip line {line_number} has invalid run_id"
                    )
                if not isinstance(record["trajectory"], list):
                    raise ValueError(
                        f"Input JSONL gzip line {line_number} has invalid trajectory"
                    )
                if not isinstance(record["evaluation"], dict):
                    raise ValueError(
                        f"Input JSONL gzip line {line_number} has invalid evaluation"
                    )
                runs.append(record)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read gzip JSONL source: {candidate}") from exc

    if not runs:
        raise ValueError(f"Input JSONL gzip contains no records: {candidate}")
    return runs


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--input-dir")
    source.add_argument("--input-jsonl-gz")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    repo_root = Path(args.repo_root)
    if args.input_dir:
        runs = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in discover_runs(Path(args.input_dir))
        ]
    elif args.input_jsonl_gz:
        runs = _load_frozen_gzip(Path(args.input_jsonl_gz))
    else:
        runs = load_frozen_luna20_source(repo_root)
    audit = audit_runs(runs, repo_root)
    static = static_episode_audit(repo_root)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "checkpoint-fairness-audit.json").write_text(
        json.dumps({"trajectory_audit": audit, "static_episode_audit": static}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = report_markdown(audit, static)
    (out / "checkpoint-fairness-report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
