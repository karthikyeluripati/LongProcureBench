"""Run the reactive LLM baseline on LongProcureBench episodes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import BenchmarkRunner, ReactiveLLMPolicy


DEFAULT_EPISODES = [
    "electrical-bongabon-generator-001",
    "electrical-national-museum-lighting-002",
    "electrical-neust-cable-003",
    "electrical-dla-breaker-004",
    "electrical-barrie-transformer-005",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--episode",
        action="append",
        dest="episodes",
        help="Episode ID; repeat flag to run multiple. Defaults to all five.",
    )
    parser.add_argument("--max-actions", type=int, default=50)
    parser.add_argument(
        "--output-dir",
        default="results/reactive-llm-v0.1",
    )
    args = parser.parse_args()

    runner = BenchmarkRunner()
    episodes = args.episodes or DEFAULT_EPISODES
    output_dir = Path(args.output_dir)
    failures = 0

    for episode_id in episodes:
        policy = ReactiveLLMPolicy(args.model)
        result = runner.run(
            policy,
            episode_id,
            max_actions=args.max_actions,
            result_path=output_dir / f"{episode_id}.json",
        )
        evaluation = result.get("evaluation")
        success = bool(evaluation and evaluation.get("episode_success"))
        failures += 0 if success else 1
        metrics = result.get("policy_metrics") or {}
        print(
            f"{episode_id}: status={result['status']} "
            f"success={success} calls={metrics.get('model_calls', 0)} "
            f"tokens={metrics.get('total_tokens', 0)} "
            f"cost_usd={metrics.get('cost_usd')}"
        )

    if failures:
        raise SystemExit(f"{failures} episode(s) did not succeed.")


if __name__ == "__main__":
    main()
