"""Run the reactive LLM baseline on LongProcureBench episodes."""
import argparse
from hashlib import sha256
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import BenchmarkRunner, ReactiveLLMPolicy

MODEL_SLUG_MAX_BYTES = 120
HASH_SUFFIX_BYTES = 12  # "--" + 10 hex chars

def model_slug(model):
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-") or "model"
    digest = sha256(model.encode("utf-8")).hexdigest()[:10]
    max_readable = MODEL_SLUG_MAX_BYTES - HASH_SUFFIX_BYTES
    readable = readable[:max_readable].rstrip("._-") or "model"
    return f"{readable}--{digest}"


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
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--omit-temperature", action="store_true")
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument(
        "--output-dir",
        default="results/reactive-llm-v0.1",
        help="Root result directory; a model-specific subdirectory is added.",
    )
    args = parser.parse_args()

    runner = BenchmarkRunner()
    episodes = args.episodes or DEFAULT_EPISODES
    output_dir = Path(args.output_dir) / model_slug(args.model)
    execution_failures = 0
    temperature = None if args.omit_temperature else args.temperature

    for episode_id in episodes:
        policy = ReactiveLLMPolicy(
            args.model,
            temperature=temperature,
            reasoning_effort=args.reasoning_effort,
        )
        result = runner.run(
            policy,
            episode_id,
            max_actions=args.max_actions,
            result_path=output_dir / f"{episode_id}.json",
        )
        evaluation = result.get("evaluation")
        success = bool(evaluation and evaluation.get("episode_success"))
        if result["status"] not in {"completed", "max_actions"}:
            execution_failures += 1
        metrics = result.get("policy_metrics") or {}
        print(
            f"{episode_id}: status={result['status']} "
            f"success={success} calls={metrics.get('model_calls', 0)} "
            f"tokens={metrics.get('total_tokens', 0)} "
            f"cost_usd={metrics.get('cost_usd')}"
        )

    if execution_failures:
        raise SystemExit(
            f"{execution_failures} episode(s) had execution errors."
        )


if __name__ == "__main__":
    main()
