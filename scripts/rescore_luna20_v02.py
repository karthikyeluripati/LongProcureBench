"""Rescore the frozen 60-run Luna diagnostic with Evaluator v0.2."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator

EPISODE_NUMBER_RE = re.compile(r"-(\d{3})$")


def load_frozen_runs(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Frozen Luna source not found: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        runs = [json.loads(line) for line in handle if line.strip()]
    if len(runs) != 60:
        raise ValueError(f"Expected exactly 60 frozen runs; found {len(runs)}")
    return runs


def accepted_actions(run: dict[str, Any]) -> list[dict[str, Any]]:
    trajectory = run.get("trajectory")
    if not isinstance(trajectory, list):
        raise ValueError("Frozen run is missing trajectory")
    actions = []
    for row in trajectory:
        if not isinstance(row, dict) or not isinstance(row.get("action"), dict):
            raise ValueError("Frozen trajectory row is missing action")
        actions.append(dict(row["action"]))
    return actions


def episode_number(episode_id: str) -> int:
    match = EPISODE_NUMBER_RE.search(episode_id)
    if match is None:
        raise ValueError(f"Episode ID lacks numeric suffix: {episode_id}")
    return int(match.group(1))


def group_names(episode_id: str) -> list[str]:
    number = episode_number(episode_id)
    groups = ["all_20"]
    if number <= 5:
        groups.append("original_5")
    else:
        groups.append("expanded_15")
    if number <= 10:
        groups.append("episodes_001_010")
    else:
        groups.append("compound_011_020")
    return groups


def rescore_runs(
    runs: list[dict[str, Any]],
    evaluator: LongProcureBenchEvaluator | None = None,
) -> list[dict[str, Any]]:
    evaluator = evaluator or LongProcureBenchEvaluator()
    out = []
    seen = set()
    episode_counts = Counter()

    for run in runs:
        episode_id = run.get("episode_id")
        run_id = run.get("run_id")
        if not isinstance(episode_id, str) or not isinstance(run_id, str):
            raise ValueError("Frozen run missing episode_id/run_id")
        if run_id in seen:
            raise ValueError(f"Duplicate frozen run_id: {run_id}")
        seen.add(run_id)
        episode_counts[episode_id] += 1

        legacy = run.get("evaluation") or {}
        evaluation = evaluator.evaluate_actions(
            episode_id,
            accepted_actions(run),
        )
        out.append({
            "episode_id": episode_id,
            "run_id": run_id,
            "source_status": run.get("status"),
            "accepted_actions": len(run.get("trajectory") or []),
            "legacy": {
                "terminal_feasible": bool(
                    (legacy.get("terminal_outcome") or {}).get("correct")
                ),
                "hard_constraints_all_passed": bool(
                    (legacy.get("hard_constraints") or {}).get("all_passed")
                ),
                "feasible_process_success": bool(
                    legacy.get("feasible_process_success")
                ),
                "episode_success": bool(legacy.get("episode_success")),
            },
            "v02": evaluation,
        })

    if len(episode_counts) != 20 or any(
        count != 3 for count in episode_counts.values()
    ):
        raise ValueError(
            "Expected 20 episodes x 3 repeats; found "
            f"{dict(sorted(episode_counts.items()))}"
        )
    return out


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    terminal = sum(
        record["v02"]["terminal_outcome"]["correct"]
        for record in records
    )
    hard = sum(
        record["v02"]["hard_constraints"]["all_passed"]
        for record in records
    )
    legacy_process = sum(
        record["legacy"]["feasible_process_success"]
        for record in records
    )
    legacy_strict = sum(
        record["legacy"]["episode_success"]
        for record in records
    )
    obligation_success = sum(
        record["v02"]["feasible_obligation_success"]
        for record in records
    )
    strict_v02 = sum(
        record["v02"]["episode_success_v02"]
        for record in records
    )
    economic = sum(
        record["v02"]["economic_objective"]["satisfied"]
        for record in records
    )

    actionable = sum(
        record["v02"]["obligations"]["actionable"]
        for record in records
    )
    resolved = sum(
        record["v02"]["obligations"]["resolved"]
        for record in records
    )
    unresolved = sum(
        record["v02"]["obligations"]["unresolved"]
        for record in records
    )
    no_opportunity = sum(
        record["v02"]["obligations"]["no_opportunity"]
        for record in records
    )
    not_applicable = sum(
        record["v02"]["obligations"]["not_applicable"]
        for record in records
    )

    unresolved_types = Counter()
    no_opportunity_types = Counter()
    not_applicable_types = Counter()
    for record in records:
        for obligation in record["v02"]["obligations"]["results"]:
            status = obligation["status"]
            checkpoint = obligation["checkpoint"]
            if status == "unresolved":
                unresolved_types[checkpoint] += 1
            elif status == "no_opportunity":
                no_opportunity_types[checkpoint] += 1
            elif status == "not_applicable":
                not_applicable_types[checkpoint] += 1

    def rate(value):
        return value / n if n else None

    return {
        "runs": n,
        "terminal_feasible": terminal,
        "terminal_feasible_rate": rate(terminal),
        "hard_constraints_all_passed": hard,
        "hard_constraints_all_pass_rate": rate(hard),
        "economic_objective_satisfied": economic,
        "economic_objective_rate": rate(economic),
        "legacy_feasible_process_success": legacy_process,
        "legacy_feasible_process_success_rate": rate(legacy_process),
        "legacy_episode_success": legacy_strict,
        "legacy_episode_success_rate": rate(legacy_strict),
        "feasible_obligation_success": obligation_success,
        "feasible_obligation_success_rate": rate(obligation_success),
        "episode_success_v02": strict_v02,
        "episode_success_v02_rate": rate(strict_v02),
        "actionable_obligations": actionable,
        "resolved_obligations": resolved,
        "unresolved_obligations": unresolved,
        "obligation_resolution_rate": (
            resolved / actionable if actionable else None
        ),
        "no_opportunity_obligations": no_opportunity,
        "not_applicable_obligations": not_applicable,
        "unresolved_obligation_counts": dict(
            unresolved_types.most_common()
        ),
        "no_opportunity_obligation_counts": dict(
            no_opportunity_types.most_common()
        ),
        "not_applicable_obligation_counts": dict(
            not_applicable_types.most_common()
        ),
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {
        "all_20": [],
        "original_5": [],
        "expanded_15": [],
        "episodes_001_010": [],
        "compound_011_020": [],
    }
    per_episode: dict[str, list[dict[str, Any]]] = {}

    for record in records:
        episode_id = record["episode_id"]
        per_episode.setdefault(episode_id, []).append(record)
        for group in group_names(episode_id):
            groups[group].append(record)

    return {
        "schema_version": "0.2.0",
        "benchmark": "LongProcureBench",
        "experiment": "luna20-evaluator-v0.2-rescore",
        "source": "evidence/luna20-diagnostic-v0.1/fairness-source.jsonl.gz",
        "runs": len(records),
        "by_group": {
            name: _summarize(group_records)
            for name, group_records in groups.items()
        },
        "by_episode": {
            episode_id: _summarize(per_episode[episode_id])
            for episode_id in sorted(per_episode)
        },
    }


def pct(value):
    return "n/a" if value is None else f"{100 * value:.1f}%"


def report_markdown(summary: dict[str, Any]) -> str:
    labels = {
        "all_20": "All 20",
        "original_5": "Original 5",
        "expanded_15": "Expanded 15",
        "episodes_001_010": "Episodes 001-010",
        "compound_011_020": "Compound 011-020",
    }
    lines = [
        "# Evaluator v0.2 Luna rescore",
        "",
        "Zero model/API calls. The same frozen 60 Luna trajectories are replayed "
        "under trigger-aware obligation semantics.",
        "",
        "## Group comparison",
        "",
        "| Group | Runs | Terminal feasible | Legacy process success | "
        "v0.2 obligation success | v0.2 strict success | Obligation resolution |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in (
        "all_20",
        "original_5",
        "expanded_15",
        "episodes_001_010",
        "compound_011_020",
    ):
        item = summary["by_group"][name]
        lines.append(
            f"| {labels[name]} | {item['runs']} | "
            f"{pct(item['terminal_feasible_rate'])} | "
            f"{pct(item['legacy_feasible_process_success_rate'])} | "
            f"{pct(item['feasible_obligation_success_rate'])} | "
            f"{pct(item['episode_success_v02_rate'])} | "
            f"{pct(item['obligation_resolution_rate'])} |"
        )

    overall = summary["by_group"]["all_20"]
    lines += [
        "",
        "## Obligation accounting",
        "",
        f"- Actionable obligations: **{overall['actionable_obligations']}**",
        f"- Resolved: **{overall['resolved_obligations']}**",
        f"- Unresolved: **{overall['unresolved_obligations']}**",
        f"- No opportunity: **{overall['no_opportunity_obligations']}**",
        f"- Not applicable: **{overall['not_applicable_obligations']}**",
        f"- Resolution rate: **{pct(overall['obligation_resolution_rate'])}**",
        "",
        "## Unresolved obligation types",
        "",
    ]
    if overall["unresolved_obligation_counts"]:
        for name, count in overall["unresolved_obligation_counts"].items():
            lines.append(f"- {name}: **{count}**")
    else:
        lines.append("- None")

    lines += [
        "",
        "## Per-episode v0.2 results",
        "",
        "| Episode | Feasible | Obligation success | Strict v0.2 | "
        "Resolved/actionable |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for episode_id, item in summary["by_episode"].items():
        lines.append(
            f"| {episode_id} | {item['terminal_feasible']}/3 | "
            f"{item['feasible_obligation_success']}/3 | "
            f"{item['episode_success_v02']}/3 | "
            f"{item['resolved_obligations']}/{item['actionable_obligations']} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "rescored-runs.json").write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = report_markdown(summary)
    (output_dir / "report.md").write_text(
        report + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=(
            "evidence/luna20-diagnostic-v0.1/"
            "fairness-source.jsonl.gz"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="results/luna20-evaluator-v02",
    )
    args = parser.parse_args()

    records = rescore_runs(load_frozen_runs(Path(args.input)))
    summary = build_summary(records)
    write_outputs(records, summary, Path(args.output_dir))
    print(report_markdown(summary))


if __name__ == "__main__":
    main()
