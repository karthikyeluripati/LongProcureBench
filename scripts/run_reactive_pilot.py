"""Run and summarize repeated reactive-LLM pilot experiments."""
import argparse
import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
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


def model_slug(model):
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-") or "model"
    digest = sha256(model.encode("utf-8")).hexdigest()[:10]
    readable = readable[:108].rstrip("._-") or "model"
    return f"{readable}--{digest}"


def flatten_result(result, model, repeat):
    evaluation = result.get("evaluation") or {}
    hard = evaluation.get("hard_constraints") or {}
    checkpoints = evaluation.get("required_checkpoints") or {}
    metrics = result.get("policy_metrics") or {}
    return {
        "model": model,
        "episode_id": result["episode_id"],
        "repeat": repeat,
        "run_id": result["run_id"],
        "status": result["status"],
        "episode_success": bool(evaluation.get("episode_success", False)),
        "terminal_correct": bool((evaluation.get("terminal_outcome") or {}).get("correct", False)),
        "hard_constraints_passed": hard.get("passed"),
        "hard_constraints_total": hard.get("total"),
        "checkpoints_completed": checkpoints.get("completed"),
        "checkpoints_total": checkpoints.get("total"),
        "constraint_violations": list(evaluation.get("constraint_violations") or []),
        "incomplete_checkpoints": [x["checkpoint"] for x in checkpoints.get("results", []) if not x.get("complete", False)],
        "accepted_actions": (evaluation.get("efficiency") or {}).get("accepted_actions", len(result.get("trajectory", []))),
        "model_calls": metrics.get("model_calls_attempted", metrics.get("model_calls")),
        "total_tokens": metrics.get("total_tokens"),
        "latency_ms": metrics.get("latency_ms"),
        "cost_usd": metrics.get("cost_usd"),
        "usage_incomplete": metrics.get("usage_incomplete"),
        "error_type": (result.get("error") or {}).get("type"),
    }


def _mean(values):
    known = [float(x) for x in values if x is not None]
    return sum(known) / len(known) if known else None


def summarize(rows):
    by_model = {}
    for model in sorted({r["model"] for r in rows}):
        subset = [r for r in rows if r["model"] == model]
        constraints = Counter(x for r in subset for x in r["constraint_violations"])
        checkpoints = Counter(x for r in subset for x in r["incomplete_checkpoints"])
        statuses = Counter(r["status"] for r in subset)
        successes = sum(r["episode_success"] for r in subset)
        terminal = sum(r["terminal_correct"] for r in subset)
        by_model[model] = {
            "runs": len(subset),
            "episode_successes": successes,
            "episode_success_rate": successes / len(subset),
            "terminal_correct_rate": terminal / len(subset),
            "status_counts": dict(sorted(statuses.items())),
            "constraint_failure_counts": dict(sorted(constraints.items())),
            "checkpoint_failure_counts": dict(sorted(checkpoints.items())),
            "mean_accepted_actions": _mean([r["accepted_actions"] for r in subset]),
            "mean_total_tokens": _mean([r["total_tokens"] for r in subset]),
            "mean_latency_ms": _mean([r["latency_ms"] for r in subset]),
            "total_cost_usd": sum(float(r["cost_usd"]) for r in subset) if subset and all(r["cost_usd"] is not None for r in subset) else None,
            "runs_with_incomplete_usage": sum(bool(r["usage_incomplete"]) for r in subset),
        }
    return {"schema_version": "0.1.0", "benchmark": "LongProcureBench", "baseline": "reactive-llm-v0.1", "runs": len(rows), "by_model": by_model}


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["model","episode_id","repeat","run_id","status","episode_success","terminal_correct","hard_constraints_passed","hard_constraints_total","checkpoints_completed","checkpoints_total","constraint_violations","incomplete_checkpoints","accepted_actions","model_calls","total_tokens","latency_ms","cost_usd","usage_incomplete","error_type"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            x = dict(row)
            x["constraint_violations"] = ";".join(row["constraint_violations"])
            x["incomplete_checkpoints"] = ";".join(row["incomplete_checkpoints"])
            w.writerow(x)


def run_pilot(models, episodes, repeats, output_dir, max_actions=50, runner=None, policy_factory=ReactiveLLMPolicy):
    if not models:
        raise ValueError("At least one model is required")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    runner = runner or BenchmarkRunner()
    rows = []
    for model in models:
        for episode_id in episodes:
            for repeat in range(1, repeats + 1):
                policy = policy_factory(model)
                rid = f"reactive-v0.1--{model_slug(model)}--{episode_id}--r{repeat:03d}"
                path = output_dir / model_slug(model) / episode_id / f"run-{repeat:03d}.json"
                result = runner.run(policy, episode_id, max_actions=max_actions, run_id=rid, result_path=path)
                row = flatten_result(result, model, repeat)
                rows.append(row)
                print(f"{model} | {episode_id} | r{repeat}: status={row['status']} success={row['episode_success']} actions={row['accepted_actions']} tokens={row['total_tokens']}")
    summary = summarize(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(rows, output_dir / "runs.csv")
    return rows, summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", action="append", dest="models", required=True)
    p.add_argument("--episode", action="append", dest="episodes")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--max-actions", type=int, default=50)
    p.add_argument("--output-dir", default="results/reactive-pilot-v0.1")
    a = p.parse_args()
    run_pilot(a.models, a.episodes or DEFAULT_EPISODES, a.repeats, Path(a.output_dir), a.max_actions)


if __name__ == "__main__":
    main()
