"""Run the persistent operational-ledger reactive baseline."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import OperationalLedgerReactiveLLMPolicy
from run_reactive_pilot import (
    DEFAULT_EPISODES,
    DEVELOPMENT_EPISODES,
    resolve_sampling_options,
    run_pilot,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--episode", action="append", dest="episodes")
    parser.add_argument(
        "--development-suite",
        action="store_true",
        help="Run all 20 frozen development/calibration episodes.",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-actions", type=int, default=50)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--omit-temperature", action="store_true")
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument(
        "--output-dir",
        default="results/operational-ledger-reactive-v0.1",
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
    run_pilot(
        [args.model],
        episodes,
        args.repeats,
        Path(args.output_dir),
        args.max_actions,
        policy_factory=OperationalLedgerReactiveLLMPolicy,
        policy_kwargs={
            "temperature": temperature,
            "reasoning_effort": args.reasoning_effort,
        },
        run_prefix="operational-ledger-reactive-v0.1",
        baseline_name="operational-ledger-reactive-v0.1",
    )


if __name__ == "__main__":
    main()
