"""Summarize the 20-episode Luna diagnostic without model calls."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean

EXPECTED_EPISODES = [
    "electrical-bongabon-generator-001",
    "electrical-national-museum-lighting-002",
    "electrical-neust-cable-003",
    "electrical-dla-breaker-004",
    "electrical-barrie-transformer-005",
    "electrical-bfar-generator-006",
    "electrical-negros-wire-007",
    "electrical-burauen-generator-008",
    "electrical-highpoint-transformer-009",
    "electrical-painesville-switchgear-010",
    "electrical-sagada-generator-011",
    "electrical-dla-relay-012",
    "electrical-dla-transformer-013",
    "electrical-dla-battery-supply-014",
    "electrical-dla-battery-charger-015",
    "electrical-dla-power-supply-016",
    "electrical-dla-qpl-breaker-017",
    "electrical-highpoint-cable-018",
    "electrical-usaf-ups-019",
    "electrical-vre-generator-020",
]

GROUPS = {
    "all_20": EXPECTED_EPISODES,
    "original_5": EXPECTED_EPISODES[:5],
    "expanded_15": EXPECTED_EPISODES[5:],
    "episodes_001_010": EXPECTED_EPISODES[:10],
    "compound_011_020": EXPECTED_EPISODES[10:],
}


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _number(value: str):
    if value is None or value == "":
        return None
    return float(value)


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        for key in (
            "episode_success",
            "feasible_process_success",
            "terminal_feasible",
            "economic_objective_satisfied",
        ):
            row[key] = _bool(row[key])
        for key in (
            "hard_constraints_passed",
            "hard_constraints_total",
            "checkpoints_completed",
            "checkpoints_total",
            "accepted_actions",
            "model_calls",
            "total_tokens",
            "latency_ms",
            "cost_usd",
        ):
            row[key] = _number(row[key])
        row["constraint_violations"] = [
            x for x in row["constraint_violations"].split(";") if x
        ]
        row["incomplete_checkpoints"] = [
            x for x in row["incomplete_checkpoints"].split(";") if x
        ]
    return rows


def validate_matrix(rows: list[dict]) -> None:
    if len(rows) != 60:
        raise ValueError(f"Expected exactly 60 runs; found {len(rows)}")

    models = {row["model"] for row in rows}
    if models != {"openai/gpt-5.6-luna"}:
        raise ValueError(f"Unexpected model set: {sorted(models)}")

    episodes = {row["episode_id"] for row in rows}
    expected = set(EXPECTED_EPISODES)
    if episodes != expected:
        raise ValueError(
            f"Episode set mismatch: missing={sorted(expected - episodes)}, "
            f"extra={sorted(episodes - expected)}"
        )

    seen = set()
    counts = Counter()
    for row in rows:
        repeat = int(row["repeat"])
        key = (row["episode_id"], repeat)
        if key in seen:
            raise ValueError(f"Duplicate episode/repeat row: {key}")
        seen.add(key)
        counts[row["episode_id"]] += 1
        if repeat not in {1, 2, 3}:
            raise ValueError(f"Unexpected repeat index: {repeat}")

    bad = {episode: count for episode, count in counts.items() if count != 3}
    if bad:
        raise ValueError(f"Each episode must have three repeats: {bad}")


def _mean_known(rows: list[dict], key: str):
    values = [row[key] for row in rows if row[key] is not None]
    return mean(values) if values else None


def summarize_rows(rows: list[dict]) -> dict:
    n = len(rows)
    hard_all = sum(
        row["hard_constraints_total"] is not None
        and row["hard_constraints_passed"] == row["hard_constraints_total"]
        for row in rows
    )
    terminal = sum(row["terminal_feasible"] for row in rows)
    process = sum(row["feasible_process_success"] for row in rows)
    economic = sum(row["economic_objective_satisfied"] for row in rows)
    strict = sum(row["episode_success"] for row in rows)

    return {
        "runs": n,
        "terminal_feasible": terminal,
        "terminal_feasible_rate": terminal / n if n else None,
        "hard_constraints_all_passed": hard_all,
        "hard_constraints_all_pass_rate": hard_all / n if n else None,
        "feasible_process_success": process,
        "feasible_process_success_rate": process / n if n else None,
        "economic_objective_satisfied": economic,
        "economic_objective_rate": economic / n if n else None,
        "episode_success": strict,
        "episode_success_rate": strict / n if n else None,
        "feasible_but_process_incomplete": sum(
            row["terminal_feasible"]
            and not row["feasible_process_success"]
            for row in rows
        ),
        "terminal_infeasible": sum(
            not row["terminal_feasible"] for row in rows
        ),
        "status_counts": dict(sorted(Counter(
            row["status"] for row in rows
        ).items())),
        "error_type_counts": dict(sorted(Counter(
            row["error_type"]
            for row in rows
            if row["error_type"]
        ).items())),
        "checkpoint_failure_counts": dict(
            Counter(
                checkpoint
                for row in rows
                for checkpoint in row["incomplete_checkpoints"]
            ).most_common()
        ),
        "constraint_failure_counts": dict(
            Counter(
                violation
                for row in rows
                for violation in row["constraint_violations"]
            ).most_common()
        ),
        "mean_accepted_actions": _mean_known(rows, "accepted_actions"),
        "mean_total_tokens": _mean_known(rows, "total_tokens"),
        "mean_latency_ms": _mean_known(rows, "latency_ms"),
        "total_known_cost_usd": sum(
            row["cost_usd"] for row in rows if row["cost_usd"] is not None
        ),
        "runs_with_unknown_cost_usd": sum(
            row["cost_usd"] is None for row in rows
        ),
    }


def build_summary(rows: list[dict]) -> dict:
    by_episode = {
        episode: summarize_rows([
            row for row in rows if row["episode_id"] == episode
        ])
        for episode in EXPECTED_EPISODES
    }
    by_group = {
        name: summarize_rows([
            row for row in rows if row["episode_id"] in episodes
        ])
        for name, episodes in GROUPS.items()
    }
    return {
        "schema_version": "0.1.0",
        "benchmark": "LongProcureBench",
        "experiment": "luna-20-episode-diagnostic-v0.1",
        "model": "openai/gpt-5.6-luna",
        "repeats_per_episode": 3,
        "episodes": 20,
        "runs": len(rows),
        "by_group": by_group,
        "by_episode": by_episode,
    }


def pct(value):
    return f"{100 * value:.1f}%" if value is not None else "n/a"


def report_markdown(summary: dict) -> str:
    lines = [
        "# Luna 20-episode diagnostic",
        "",
        "Reactive baseline: openai/gpt-5.6-luna, medium reasoning, "
        "temperature omitted, three repeats per episode.",
        "",
        "## Group results",
        "",
        "| Group | Runs | Terminal feasible | Process complete | "
        "Strict success | Hard constraints all pass |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    labels = {
        "all_20": "All 20",
        "original_5": "Original 5",
        "expanded_15": "Expanded 15",
        "episodes_001_010": "Episodes 001-010",
        "compound_011_020": "Compound 011-020",
    }
    for name in GROUPS:
        item = summary["by_group"][name]
        lines.append(
            f"| {labels[name]} | {item['runs']} | "
            f"{pct(item['terminal_feasible_rate'])} | "
            f"{pct(item['feasible_process_success_rate'])} | "
            f"{pct(item['episode_success_rate'])} | "
            f"{pct(item['hard_constraints_all_pass_rate'])} |"
        )

    all_runs = summary["by_group"]["all_20"]
    lines += [
        "",
        "## Overall failure layers",
        "",
        f"- Terminal infeasible: **{all_runs['terminal_infeasible']}/60**",
        f"- Feasible but process incomplete: "
        f"**{all_runs['feasible_but_process_incomplete']}/60**",
        f"- Strict success: **{all_runs['episode_success']}/60**",
        "",
        "## Checkpoint failures",
        "",
    ]
    for name, count in all_runs["checkpoint_failure_counts"].items():
        lines.append(f"- {name}: **{count}**")

    lines += [
        "",
        "## Per-episode results",
        "",
        "| Episode | Terminal feasible | Process complete | Strict success |",
        "| --- | ---: | ---: | ---: |",
    ]
    for episode in EXPECTED_EPISODES:
        item = summary["by_episode"][episode]
        lines.append(
            f"| {episode} | {item['terminal_feasible']}/3 | "
            f"{item['feasible_process_success']}/3 | "
            f"{item['episode_success']}/3 |"
        )

    lines += [
        "",
        "## Resource use",
        "",
        f"- Mean accepted actions/run: "
        f"**{all_runs['mean_accepted_actions']:.2f}**",
        f"- Mean tokens/run: **{all_runs['mean_total_tokens']:.0f}**",
        f"- Total known cost (USD): "
        f"**{all_runs['total_known_cost_usd']:.4f}**",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    args = parser.parse_args()
    root = Path(args.input_dir)

    rows = load_rows(root / "runs.csv")
    validate_matrix(rows)
    summary = build_summary(rows)

    (root / "diagnostic-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "diagnostic-report.md").write_text(
        report_markdown(summary) + "\n",
        encoding="utf-8",
    )
    print(report_markdown(summary))


if __name__ == "__main__":
    main()
