"""Replay and summarize the frozen 180-run cross-family reactive evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
from frozen_cross_family_reactive_v01 import (
    EPISODES,
    MODELS,
    load_frozen_cross_family_source,
    reconstruct_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "cross-family-reactive-v0.1"
SUMMARY_PATH = EVIDENCE_DIR / "summary.json"


def rescore_records(
    source: list[dict[str, Any]],
    evaluator: LongProcureBenchEvaluator | None = None,
) -> list[dict[str, Any]]:
    evaluator = evaluator or LongProcureBenchEvaluator(repo_root=ROOT)
    out = []
    for record in source:
        evaluation = evaluator.evaluate_actions(
            record["episode_id"],
            reconstruct_actions(record),
        )
        out.append({
            "model": record["model"],
            "episode_id": record["episode_id"],
            "repeat": record["repeat"],
            "decisions": len(record["decisions"]),
            "policy_metrics": dict(record["policy_metrics"]),
            "evaluation": evaluation,
        })
    return out


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    runs = len(records)
    unresolved_types: Counter[str] = Counter()
    no_opportunity_types: Counter[str] = Counter()

    terminal = 0
    hard = 0
    economic = 0
    legacy = 0
    obligation_success = 0
    strict_v02 = 0
    actionable = 0
    resolved = 0
    unresolved = 0
    no_opportunity = 0
    not_applicable = 0
    actions = 0
    calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    latency_ms = 0.0
    cost_usd = 0.0

    for record in records:
        evaluation = record["evaluation"]
        obligations = evaluation["obligations"]
        metrics = record["policy_metrics"]

        terminal += int(evaluation["terminal_outcome"]["correct"])
        hard += int(evaluation["hard_constraints"]["all_passed"])
        economic += int(evaluation["economic_objective"]["satisfied"])
        legacy += int(evaluation["episode_success"])
        obligation_success += int(
            evaluation["feasible_obligation_success"]
        )
        strict_v02 += int(evaluation["episode_success_v02"])

        actionable += obligations["actionable"]
        resolved += obligations["resolved"]
        unresolved += obligations["unresolved"]
        no_opportunity += obligations["no_opportunity"]
        not_applicable += obligations["not_applicable"]

        for obligation in obligations["results"]:
            if obligation["status"] == "unresolved":
                unresolved_types[obligation["checkpoint"]] += 1
            elif obligation["status"] == "no_opportunity":
                no_opportunity_types[obligation["checkpoint"]] += 1

        actions += record["decisions"]
        calls += metrics["model_calls_attempted"]
        prompt_tokens += metrics["prompt_tokens"]
        completion_tokens += metrics["completion_tokens"]
        total_tokens += metrics["total_tokens"]
        latency_ms += metrics["latency_ms"]
        cost_usd += metrics["cost_usd"]

    def rate(value: int) -> float | None:
        return value / runs if runs else None

    return {
        "runs": runs,
        "terminal_feasible": terminal,
        "terminal_feasible_rate": rate(terminal),
        "hard_constraints_all_passed": hard,
        "hard_constraints_all_pass_rate": rate(hard),
        "economic_objective_satisfied": economic,
        "economic_objective_rate": rate(economic),
        "legacy_episode_success": legacy,
        "legacy_episode_success_rate": rate(legacy),
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
            sorted(unresolved_types.items())
        ),
        "no_opportunity_obligation_counts": dict(
            sorted(no_opportunity_types.items())
        ),
        "accepted_actions": actions,
        "mean_accepted_actions": actions / runs if runs else None,
        "model_calls_attempted": calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "mean_total_tokens": total_tokens / runs if runs else None,
        "latency_ms": latency_ms,
        "mean_latency_ms": latency_ms / runs if runs else None,
        "known_cost_usd": cost_usd,
        "mean_cost_usd": cost_usd / runs if runs else None,
    }


def build_summary(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    by_model = {
        model: _summary([
            record for record in records
            if record["model"] == model
        ])
        for model in MODELS
    }
    by_episode = {}
    for episode_id in EPISODES:
        episode_records = [
            record
            for record in records
            if record["episode_id"] == episode_id
        ]
        item = _summary(episode_records)
        item["terminal_minus_obligation_success_rate"] = (
            item["terminal_feasible_rate"]
            - item["feasible_obligation_success_rate"]
        )
        by_episode[episode_id] = item

    combined = _summary(records)
    return {
        "schema_version": "0.1.0",
        "benchmark": "LongProcureBench",
        "experiment": "cross-family-reactive-v0.1",
        "source": (
            "evidence/cross-family-reactive-v0.1/"
            "replay-source.b64.part01..06"
        ),
        "runs": len(records),
        "by_model": by_model,
        "combined": combined,
        "by_episode": by_episode,
    }


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def check_frozen_summary(summary: dict[str, Any]) -> None:
    if not SUMMARY_PATH.is_file():
        raise ValueError(f"Missing frozen summary: {SUMMARY_PATH}")
    expected = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    if _canonical(summary) != _canonical(expected):
        raise ValueError(
            "Frozen cross-family summary drifted from deterministic replay"
        )


def report_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Cross-family reactive baseline v0.1",
        "",
        "Deterministic replay of the frozen 180-run live baseline.",
        "",
        "## Model results",
        "",
        "| Model | Runs | Terminal feasible | Obligation success | "
        "Strict v0.2 | Obligation resolution | Tokens | Cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for model in MODELS:
        item = summary["by_model"][model]
        lines.append(
            f"| {model} | {item['runs']} | "
            f"{item['terminal_feasible']}/{item['runs']} "
            f"({100 * item['terminal_feasible_rate']:.1f}%) | "
            f"{item['feasible_obligation_success']}/{item['runs']} "
            f"({100 * item['feasible_obligation_success_rate']:.1f}%) | "
            f"{item['episode_success_v02']}/{item['runs']} "
            f"({100 * item['episode_success_v02_rate']:.1f}%) | "
            f"{item['resolved_obligations']}/"
            f"{item['actionable_obligations']} "
            f"({100 * item['obligation_resolution_rate']:.1f}%) | "
            f"{item['total_tokens']:,} | "
            f"${item['known_cost_usd']:.2f} |"
        )

    combined = summary["combined"]
    lines += [
        "",
        "## Combined",
        "",
        f"- Runs: **{combined['runs']}**",
        f"- Terminal feasible: **{combined['terminal_feasible']}/"
        f"{combined['runs']} "
        f"({100 * combined['terminal_feasible_rate']:.1f}%)**",
        f"- Feasible-obligation success: "
        f"**{combined['feasible_obligation_success']}/{combined['runs']} "
        f"({100 * combined['feasible_obligation_success_rate']:.1f}%)**",
        f"- Strict v0.2 success: **{combined['episode_success_v02']}/"
        f"{combined['runs']} "
        f"({100 * combined['episode_success_v02_rate']:.1f}%)**",
        f"- Obligation resolution: **{combined['resolved_obligations']}/"
        f"{combined['actionable_obligations']} "
        f"({100 * combined['obligation_resolution_rate']:.1f}%)**",
        f"- Total known API cost: **${combined['known_cost_usd']:.2f}**",
        "",
        "## Unresolved obligations",
        "",
    ]
    for name, count in sorted(
        combined["unresolved_obligation_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"- {name}: **{count}**")

    lines += [
        "",
        "## Largest terminal/obligation gaps",
        "",
        "| Episode | Terminal feasible | Obligation success | Gap |",
        "| --- | ---: | ---: | ---: |",
    ]
    ordered = sorted(
        summary["by_episode"].items(),
        key=lambda item: (
            -item[1]["terminal_minus_obligation_success_rate"],
            item[0],
        ),
    )
    for episode_id, item in ordered[:10]:
        lines.append(
            f"| {episode_id} | "
            f"{item['terminal_feasible']}/{item['runs']} | "
            f"{item['feasible_obligation_success']}/{item['runs']} | "
            f"{100 * item['terminal_minus_obligation_success_rate']:.1f} pp |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    source = load_frozen_cross_family_source(ROOT)
    records = rescore_records(source)
    summary = build_summary(records)

    if args.check:
        check_frozen_summary(summary)

    if args.output:
        Path(args.output).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(report_markdown(summary))


if __name__ == "__main__":
    main()
