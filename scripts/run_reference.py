"""Run the scripted reference control across all frozen episodes."""
import argparse
from pathlib import Path

from longprocurebench import BenchmarkRunner, ScriptedReferencePolicy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="results/reference-control-v0.1",
        help="Directory for standardized result JSON files.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    runner = BenchmarkRunner()
    failures = 0

    for episode_id in ScriptedReferencePolicy.episode_ids():
        result = runner.run(
            ScriptedReferencePolicy(),
            episode_id,
            result_path=output_dir / f"{episode_id}.json",
        )
        success = result["evaluation"]["episode_success"]
        failures += 0 if success else 1
        print(
            f"{episode_id}: status={result['status']} "
            f"success={success} "
            f"actions={result['evaluation']['efficiency']['accepted_actions']}"
        )

    if failures:
        raise SystemExit(
            f"{failures} reference-control episode(s) failed."
        )


if __name__ == "__main__":
    main()
