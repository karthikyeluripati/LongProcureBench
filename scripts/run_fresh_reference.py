"""Run the oracle-aware reference control for fresh episodes 031-050."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import BenchmarkRunner, FreshScriptedReferencePolicy


def run_all_fresh_reference(output_dir, runner=None):
    runner = runner or BenchmarkRunner()
    failures = 0

    for episode_id in FreshScriptedReferencePolicy.episode_ids():
        result = runner.run(
            FreshScriptedReferencePolicy(),
            episode_id,
            result_path=Path(output_dir) / f"{episode_id}.json",
        )
        evaluation = result.get("evaluation")
        success = bool(
            evaluation
            and evaluation.get("episode_success")
            and evaluation.get("feasible_obligation_success")
            and evaluation.get("episode_success_v02")
            and evaluation.get("hard_constraints", {}).get("all_passed")
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
        default="results/fresh-reference-control-v0.1",
    )
    args = parser.parse_args()
    failures = run_all_fresh_reference(Path(args.output_dir))
    if failures:
        raise SystemExit(
            f"{failures} fresh reference-control episode(s) failed."
        )


if __name__ == "__main__":
    main()
