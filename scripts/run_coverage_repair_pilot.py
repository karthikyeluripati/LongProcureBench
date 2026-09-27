"""Run the coverage + repair diagnostic baseline."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import CoverageRepairContextPolicy
from run_reactive_pilot import (
    DEFAULT_EPISODES,
    DEVELOPMENT_EPISODES,
    resolve_sampling_options,
    run_pilot,
)


def write_diagnostics(output_dir: Path) -> dict:
    per_run = []
    totals = {
        "coverage_repair_interventions": 0,
        "coverage_forced_rfqs": 0,
        "coverage_forced_followups": 0,
        "coverage_forced_answers": 0,
        "coverage_forced_amendments": 0,
    }

    for path in sorted(output_dir.rglob("run-*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        metrics = result.get("policy_metrics") or {}
        row = {
            "run_id": result.get("run_id"),
            "episode_id": result.get("episode_id"),
            "status": result.get("status"),
        }
        for key in totals:
            value = int(metrics.get(key) or 0)
            row[key] = value
            totals[key] += value
        per_run.append(row)

    payload = {
        "schema_version": "0.1.0",
        "baseline": "coverage-repair-diagnostic-v0.1",
        "runs": len(per_run),
        "totals": totals,
        "per_run": per_run,
    }
    (output_dir / "coverage-repair-diagnostics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--episode", action="append", dest="episodes")
    parser.add_argument(
        "--development-suite",
        action="store_true",
        help="Run all 20 frozen development/calibration episodes.",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-actions", type=int, default=50)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--omit-temperature", action="store_true")
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument(
        "--output-dir",
        default="results/coverage-repair-diagnostic-v0.1",
    )
    args = parser.parse_args()

    if args.development_suite and args.episodes:
        parser.error("--development-suite cannot be combined with --episode")

    try:
        temperature = resolve_sampling_options(
            args.temperature,
            args.omit_temperature,
            args.reasoning_effort,
        )
    except ValueError as exc:
        parser.error(str(exc))

    episodes = (
        DEVELOPMENT_EPISODES
        if args.development_suite
        else (args.episodes or DEFAULT_EPISODES)
    )
    output_dir = Path(args.output_dir)

    run_pilot(
        [args.model],
        episodes,
        args.repeats,
        output_dir,
        args.max_actions,
        policy_factory=CoverageRepairContextPolicy,
        policy_kwargs={
            "temperature": temperature,
            "reasoning_effort": args.reasoning_effort,
        },
        run_prefix="coverage-repair-diagnostic-v0.1",
        baseline_name="coverage-repair-diagnostic-v0.1",
    )
    diagnostics = write_diagnostics(output_dir)
    print(json.dumps(diagnostics["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
