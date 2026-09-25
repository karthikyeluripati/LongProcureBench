"""Audit checkpoint fairness against saved benchmark trajectories."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from typing import Any

EVENT_OBLIGATIONS = {
    "follow_up_nonresponse": {"supplier_non_response"},
    "handle_supplier_question": {"supplier_question"},
    "handle_amendment": {"requirement_change", "quantity_change"},
    "recover_from_withdrawal": {"supplier_withdrawal"},
}
STARTING_STATE_OBLIGATIONS = {"resolve_requirement_gap"}
BRANCH_CONDITIONAL = {"request_quote_revision"}
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


def discover_runs(root: Path) -> list[Path]:
    runs = sorted(root.glob("**/run-*.json"))
    if not runs:
        raise ValueError(f"No raw run JSON found under {root}")
    return runs


def _observations(run: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [
        (row["step"], event)
        for row in run.get("trajectory", [])
        for event in row.get("observations", [])
    ]


def _terminal_step(run: dict[str, Any]) -> int | None:
    trajectory = run.get("trajectory") or []
    return trajectory[-1]["step"] if trajectory else None


def _terminal_awards(run: dict[str, Any]) -> list[dict[str, Any]]:
    trajectory = run.get("trajectory") or []
    if not trajectory:
        return []
    action = trajectory[-1].get("action") or {}
    if action.get("type") != "award_supplier":
        return []
    awards = (action.get("arguments") or {}).get("awards") or []
    return [award for award in awards if isinstance(award, dict)]


def _awarded_event_ids(run: dict[str, Any]) -> set[str]:
    return {
        award["quote_event_id"]
        for award in _terminal_awards(run)
        if "quote_event_id" in award
    }


def _event_steps(run: dict[str, Any]) -> dict[str, int]:
    return {
        event["event_id"]: step
        for step, event in _observations(run)
        if isinstance(event.get("event_id"), str)
    }


def _revision_repair_branch(run, episode):
    observations = _observations(run)
    trigger_steps: list[int] = []
    applicable: bool | None
    opportunity: bool | None
    applicability_reason: str | None = None

    if category == "event_obligation":
        trigger_steps = [
            step
            for step, event in observations
            if event["type"] in EVENT_OBLIGATIONS[name]
        ]
        applicable = bool(trigger_steps)
        applicability_reason = "matching_event_revealed" if applicable else "trigger_not_revealed"
        opportunity = (
            applicable
            and terminal_step is not None
            and min(trigger_steps) < terminal_step
        )
    elif category == "starting_state_obligation":
        applicable = True
        applicability_reason = "visible_from_initial_state"
        opportunity = terminal_step is not None and terminal_step >= 1
    elif category == "branch_conditional":
        applicable, trigger_steps, applicability_reason = _revision_repair_branch(
            run, episode
        )
        opportunity = (
            applicable
            and terminal_step is not None
            and bool(trigger_steps)
            and min(trigger_steps) < terminal_step
        )
    else:
        applicable = None
        opportunity = None

    current_failed = not bool(checkpoint["complete"])
    non_applicable_failure = (
        current_failed
        and applicable is False
        and category in {"event_obligation", "branch_conditional"}
    )
    no_opportunity_failure = (
        current_failed
        and applicable is True
        and opportunity is False
        and category in {
            "event_obligation",
            "starting_state_obligation",
            "branch_conditional",
        }
    )
    applicable_obligation_failure = (
        current_failed
        and applicable is True
        and opportunity is True
        and category in {
            "event_obligation",
            "starting_state_obligation",
            "branch_conditional",
        }
    )

    return {
        "checkpoint": name,
        "category": category,
        "current_complete": bool(checkpoint["complete"]),
        "evidence_mode": checkpoint.get("evidence_mode"),
        "applicable": applicable,
        "opportunity": opportunity,
        "applicability_reason": applicability_reason,
        "trigger_steps": trigger_steps,
        "terminal_step": terminal_step,
        "non_applicable_failure": non_applicable_failure,
        "no_opportunity_failure": no_opportunity_failure,
        "applicable_obligation_failure": applicable_obligation_failure,
        "detail": checkpoint.get("detail"),
    }


def _overprescriptive_recovery(run: dict[str, Any], audited: dict[str, Any]) -> bool:
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
        step
        for step, event in observations
        if event["type"] == "supplier_withdrawal"
    ]
    if not withdrawal_steps:
        return False
    withdrawal_step = min(withdrawal_steps)

    awarded_ids = _awarded_event_ids(run)
    awarded_steps = [
        step
        for step, event in observations
        if event.get("event_id") in awarded_ids
    ]
    return bool(awarded_steps) and max(awarded_steps) < withdrawal_step


def _load_episode(repo_root: Path, episode_id: str) -> dict[str, Any]:
    path = repo_root / "data" / "episodes" / "electrical" / f"{episode_id}.json"
    if not path.is_file():
        raise ValueError(f"Missing episode for audit: {episode_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def audit_runs(runs: list[dict[str, Any]], repo_root: Path) -> dict[str, Any]:
    checkpoint_failures = Counter()
    non_applicable = Counter()
    no_opportunity = Counter()
    applicable_failures = Counter()
    proxy_failures = Counter()
    procedural_failures = Counter()
    overprescriptive_recovery = []
    runs_detail = []

    for run in runs:
        evaluation = run.get("evaluation") or {}
        episode = _load_episode(repo_root, run["episode_id"])
        checkpoints = (evaluation.get("required_checkpoints") or {}).get("results") or []
        audited_checkpoints = []

        for checkpoint in checkpoints:
            audited = audit_checkpoint(run, checkpoint, episode)
            audited_checkpoints.append(audited)
            if not audited["current_complete"]:
                checkpoint_failures[audited["checkpoint"]] += 1
            if audited["non_applicable_failure"]:
                non_applicable[audited["checkpoint"]] += 1
            if audited["no_opportunity_failure"]:
                no_opportunity[audited["checkpoint"]] += 1
            if audited["applicable_obligation_failure"]:
                applicable_failures[audited["checkpoint"]] += 1
            if not audited["current_complete"] and audited["category"] == "proxy":
                proxy_failures[audited["checkpoint"]] += 1
            if not audited["current_complete"] and audited["category"] == "procedural":
                procedural_failures[audited["checkpoint"]] += 1
            if _overprescriptive_recovery(run, audited):
                overprescriptive_recovery.append({
                    "episode_id": run["episode_id"],
                    "run_id": run["run_id"],
                    "checkpoint": audited["checkpoint"],
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

    return {
        "schema_version": "0.2.0",
        "runs": len(runs),
        "checkpoint_failure_counts": dict(checkpoint_failures.most_common()),
        "non_applicable_current_failure_counts": dict(non_applicable.most_common()),
        "no_opportunity_failure_counts": dict(no_opportunity.most_common()),
        "applicable_obligation_failure_counts": dict(applicable_failures.most_common()),
        "proxy_failure_counts": dict(proxy_failures.most_common()),
        "procedural_failure_counts": dict(procedural_failures.most_common()),
        "overprescriptive_recovery_cases": overprescriptive_recovery,
        "runs_detail": runs_detail,
    }


def static_episode_audit(repo_root: Path) -> dict[str, Any]:
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

        if (
            "request_quote_revision" in checkpoints
            and "quote_revision" not in event_types
        ):
            issues.append({
                "episode_id": episode["episode_id"],
                "checkpoint": "request_quote_revision",
                "issue": "revision_checkpoint_without_revision_event",
            })

        if "resolve_requirement_gap" in checkpoints:
            initial_path = repo_root / episode["initial_state_ref"]["path"]
            initial = json.loads(initial_path.read_text(encoding="utf-8"))
            if not initial.get("missing_information"):
                issues.append({
                    "episode_id": episode["episode_id"],
                    "checkpoint": "resolve_requirement_gap",
                    "issue": "gap_checkpoint_without_visible_missing_information",
                })

    return {"episodes": len(paths), "issues": issues}


def _fmt_counts(counts: dict[str, int]) -> list[str]:
    if not counts:
        return ["- None"]
    return [f"- {name}: **{count}**" for name, count in counts.items()]


def report_markdown(
    audit: dict[str, Any],
    static: dict[str, Any],
) -> str:
    non_app_total = sum(
        audit["non_applicable_current_failure_counts"].values()
    )
    no_opp_total = sum(audit["no_opportunity_failure_counts"].values())
    applicable_total = sum(
        audit["applicable_obligation_failure_counts"].values()
    )
    proxy_total = sum(audit["proxy_failure_counts"].values())
    procedural_total = sum(audit["procedural_failure_counts"].values())

    lines = [
        "# Checkpoint fairness audit v0.1",
        "",
        f"Audited **{audit['runs']}** saved trajectories across "
        f"**{static['episodes']}** episodes.",
        "",
        "This audit does not change scores. It asks whether current checkpoint "
        "failures represent an agent-visible, actionable obligation.",
        "",
        "## Headline",
        "",
        f"- Current checkpoint failures on a branch/event that never became "
        f"applicable: **{non_app_total}**",
        f"- Applicable event obligations revealed with no later action "
        f"opportunity before termination: **{no_opp_total}**",
        f"- Applicable/actionable obligation failures: **{applicable_total}**",
        f"- Failures from evaluator proxy checkpoints: **{proxy_total}**",
        f"- Failures from procedural-policy checkpoints: **{procedural_total}**",
        f"- Potentially over-prescriptive withdrawal-recovery cases: "
        f"**{len(audit['overprescriptive_recovery_cases'])}**",
        "",
        "## Non-applicable failures in the current evaluator",
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
        "## Proxy checkpoint failures",
        "",
        *_fmt_counts(audit["proxy_failure_counts"]),
        "",
        "## Static episode audit",
        "",
        f"- Static checkpoint/trigger issues: **{len(static['issues'])}**",
        f"- Complete per-run checkpoint records: **{len(audit['runs_detail'])}** trajectories",
    ]
    for issue in static["issues"]:
        lines.append(
            f"- {issue['episode_id']} / "
            f"{issue['checkpoint']}: {issue['issue']}"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "The current feasible_process_success metric should not be used as "
        "the paper's primary long-horizon obligation metric until checkpoint "
        "applicability is explicit. Event-driven obligations should be scored "
        "only after their trigger is visible and only when the agent has a "
        "subsequent action opportunity. Branch-conditional revision work "
        "should not be mandatory when the chosen feasible award path does not "
        "use a revision. Proxy and procedural checkpoints should remain "
        "reported separately from event obligations.",
        "",
    ]
    return "\n".join(lines)


def _load_frozen_gzip(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Frozen trajectory source not found: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        runs = [json.loads(line) for line in handle if line.strip()]
    if not runs:
        raise ValueError(f"Frozen trajectory source is empty: {path}")
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-dir")
    source.add_argument("--input-jsonl-gz")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runs = (
        [
            json.loads(path.read_text(encoding="utf-8"))
            for path in discover_runs(Path(args.input_dir))
        ]
        if args.input_dir
        else _load_frozen_gzip(Path(args.input_jsonl_gz))
    )
    audit = audit_runs(runs, repo_root)
    static = static_episode_audit(repo_root)

    payload = {
        "trajectory_audit": audit,
        "static_episode_audit": static,
    }
    (output_dir / "checkpoint-fairness-audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = report_markdown(audit, static)
    (output_dir / "checkpoint-fairness-report.md").write_text(
        report + "\n",
        encoding="utf-8",
    )
    print(report)


if __name__ == "__main__":
    main()
