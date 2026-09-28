"""Run the static Plan-and-Execute comparator."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import PlanExecuteLLMPolicy
from run_reactive_pilot import (
    DEVELOPMENT_EPISODES,
    resolve_sampling_options,
    run_pilot,
)

TARGETED_PILOT_EPISODES = [
    "electrical-burauen-generator-008",
    "electrical-dla-transformer-013",
    "electrical-dla-power-supply-016",
]


def resolve_pilot_sampling(
    temperature,
    omit_temperature,
    reasoning_effort,
):
    """Default to the frozen pilot sampling configuration.

    Explicit sampling flags still override the default. With no sampling
    flags, use medium reasoning and omit temperature.
    """
    if (
        temperature is None
        and not omit_temperature
        and reasoning_effort is None
    ):
        reasoning_effort = "medium"
        omit_temperature = True

    resolved_temperature = resolve_sampling_options(
        temperature,
        omit_temperature,
        reasoning_effort,
    )
    return resolved_temperature, reasoning_effort


def write_diagnostics(output_dir: Path) -> dict:
    totals = {
        "planner_calls": 0,
        "executor_calls": 0,
        "unplanned_exceptions": 0,
    }
    plan_steps = []
    per_run = []

    for path in sorted(output_dir.rglob("run-*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        metrics = result.get("policy_metrics") or {}
        row = {
            "run_id": result.get("run_id"),
            "episode_id": result.get("episode_id"),
            "status": result.get("status"),
            "planner_calls": int(metrics.get("planner_calls") or 0),
            "executor_calls": int(metrics.get("executor_calls") or 0),
            "unplanned_exceptions": int(
                metrics.get("unplanned_exceptions") or 0
            ),
            "plan_steps": int(metrics.get("plan_steps") or 0),
            "plan_step_usage": metrics.get("plan_step_usage") or {},
        }
        per_run.append(row)
        totals["planner_calls"] += row["planner_calls"]
        totals["executor_calls"] += row["executor_calls"]
        totals["unplanned_exceptions"] += row["unplanned_exceptions"]
        plan_steps.append(row["plan_steps"])

    payload = {
        "schema_version": "0.1.0",
        "baseline": "plan-execute-static-v0.1",
        "runs": len(per_run),
        "totals": totals,
        "mean_plan_steps": (
            sum(plan_steps) / len(plan_steps) if plan_steps else None
        ),
        "max_plan_steps": max(plan_steps, default=0),
        "per_run": per_run,
    }
    (output_dir / "plan-execute-diagnostics.json").write_text(
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
        default="results/plan-execute-comparator-v0.1",
    )
    args = parser.parse_args()

    if args.development_suite and args.episodes:
        parser.error("--development-suite cannot be combined with --episode")

    try:
        temperature, reasoning_effort = resolve_pilot_sampling(
            args.temperature,
            args.omit_temperature,
            args.reasoning_effort,
        )
    except ValueError as exc:
        parser.error(str(exc))

    episodes = (
        DEVELOPMENT_EPISODES
        if args.development_suite
        else (args.episodes or TARGETED_PILOT_EPISODES)
    )
    output_dir = Path(args.output_dir)

    run_pilot(
        [args.model],
        episodes,
        args.repeats,
        output_dir,
        args.max_actions,
        policy_factory=PlanExecuteLLMPolicy,
        policy_kwargs={
            "temperature": temperature,
            "reasoning_effort": reasoning_effort,
        },
        run_prefix="plan-execute-static-v0.1",
        baseline_name="plan-execute-static-v0.1",
    )
    diagnostics = write_diagnostics(output_dir)
    print(json.dumps(diagnostics["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
