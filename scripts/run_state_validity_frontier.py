"""Run the frozen State Validity Frontier Stage-1 mechanism pilot.

This runner deliberately exposes no development-suite or repeat-count option.
The protocol frozen before implementation permits exactly three runs:
008 / 013 / 016 x 1 with GPT-5.6 Sol, medium reasoning, temperature omitted.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import StateValidityFrontierPolicy
from run_reactive_pilot import run_pilot


TARGET_MODEL = "openai/gpt-5.6-sol"
TARGETED_PILOT_EPISODES = [
    "electrical-burauen-generator-008",
    "electrical-dla-transformer-013",
    "electrical-dla-power-supply-016",
]
TARGET_REASONING_EFFORT = "medium"
TARGET_TEMPERATURE = None
TARGET_REPEATS = 1
TARGET_MAX_ACTIONS = 50


def write_diagnostics(output_dir: Path) -> dict:
    totals = {
        "runs": 0,
        "frontier_decisions": 0,
        "validity_frontier_interventions": 0,
        "deterministic_frontier_actions": 0,
        "llm_frontier_calls": 0,
        "validity_invalidations": 0,
        "requirement_invalidations": 0,
        "quote_invalidations": 0,
        "withdrawal_invalidations": 0,
        "coverage_forced_rfqs": 0,
        "coverage_forced_followups": 0,
        "coverage_forced_answers": 0,
    }
    per_run = []

    for path in sorted(output_dir.rglob("run-*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        metrics = result.get("policy_metrics") or {}
        row = {
            "run_id": result.get("run_id"),
            "episode_id": result.get("episode_id"),
            "status": result.get("status"),
            "requirement_epoch": metrics.get("requirement_epoch"),
            "evaluation_current": metrics.get("evaluation_current"),
            "frontier_decisions": int(
                metrics.get("frontier_decisions") or 0
            ),
            "validity_frontier_interventions": int(
                metrics.get("validity_frontier_interventions") or 0
            ),
            "deterministic_frontier_actions": int(
                metrics.get("deterministic_frontier_actions") or 0
            ),
            "llm_frontier_calls": int(
                metrics.get("llm_frontier_calls") or 0
            ),
            "validity_invalidations": int(
                metrics.get("validity_invalidations") or 0
            ),
            "requirement_invalidations": int(
                metrics.get("requirement_invalidations") or 0
            ),
            "quote_invalidations": int(
                metrics.get("quote_invalidations") or 0
            ),
            "withdrawal_invalidations": int(
                metrics.get("withdrawal_invalidations") or 0
            ),
            "coverage_forced_rfqs": int(
                metrics.get("coverage_forced_rfqs") or 0
            ),
            "coverage_forced_followups": int(
                metrics.get("coverage_forced_followups") or 0
            ),
            "coverage_forced_answers": int(
                metrics.get("coverage_forced_answers") or 0
            ),
            "clarification_epochs_used": (
                metrics.get("clarification_epochs_used") or []
            ),
            "amendment_required_epochs": (
                metrics.get("amendment_required_epochs") or []
            ),
            "amended_epochs": metrics.get("amended_epochs") or [],
            "handled_repair_event_ids": (
                metrics.get("handled_repair_event_ids") or []
            ),
            "frontier_trace": metrics.get("frontier_trace") or [],
        }
        per_run.append(row)
        totals["runs"] += 1
        for key in totals:
            if key == "runs":
                continue
            totals[key] += int(row.get(key) or 0)

    payload = {
        "schema_version": "0.1.0",
        "method": "state-validity-frontier-v0.1",
        "protocol": {
            "model": TARGET_MODEL,
            "episodes": TARGETED_PILOT_EPISODES,
            "repeats": TARGET_REPEATS,
            "max_actions": TARGET_MAX_ACTIONS,
            "reasoning_effort": TARGET_REASONING_EFFORT,
            "temperature": TARGET_TEMPERATURE,
        },
        "totals": totals,
        "per_run": per_run,
    }
    (output_dir / "state-validity-frontier-diagnostics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default=TARGET_MODEL,
        help="Frozen Stage-1 model; other values are rejected.",
    )
    parser.add_argument(
        "--output-dir",
        default="results/state-validity-frontier-v0.1",
    )
    args = parser.parse_args()

    if args.model != TARGET_MODEL:
        parser.error(
            f"Stage-1 protocol requires --model {TARGET_MODEL}"
        )

    output_dir = Path(args.output_dir)
    run_pilot(
        [TARGET_MODEL],
        TARGETED_PILOT_EPISODES,
        TARGET_REPEATS,
        output_dir,
        TARGET_MAX_ACTIONS,
        policy_factory=StateValidityFrontierPolicy,
        policy_kwargs={
            "temperature": TARGET_TEMPERATURE,
            "reasoning_effort": TARGET_REASONING_EFFORT,
        },
        run_prefix="state-validity-frontier-v0.1",
        baseline_name="state-validity-frontier-v0.1",
    )
    diagnostics = write_diagnostics(output_dir)
    print(json.dumps(diagnostics["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
