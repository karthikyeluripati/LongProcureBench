"""Run the scripted reference control across all frozen episodes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import BenchmarkRunner, ScriptedReferencePolicy


def run_all_reference(output_dir, runner=None):
    runner = runner or BenchmarkRunner()
    failures = 0

    for episode_id in ScriptedReferencePolicy.episode_ids():
        result = runner.run(
            ScriptedReferencePolicy(),
            episode_id,
            result_path=Path(output_dir) / f"{episode_id}.json",
        )
        evaluation = result.get("evaluation")
        success = bool(
            evaluation and evaluation.get("episode_success")
        )
        actions = (
            evaluation["efficiency"]["accepted_actions"]
            if evaluation
            else len(result.get("trajectory", []))
        )
        failures += 0 if success else 1
        print(
            f"{episode_id}: status={result['status']} "
            f"success={success} actions={actions}"
        )

    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="results/reference-control-v0.1",
        help="Directory for standardized result JSON files.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    failures = run_all_reference(output_dir)

    if failures:
        raise SystemExit(
            f"{failures} reference-control episode(s) failed."
        )


if __name__ == "__main__":
    main()
