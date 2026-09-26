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

EPISODE_ID_RE = re.compile(r"^[a-z0-9-]+$")


def resolve_sampling_options(
    temperature,
    omit_temperature,
    reasoning_effort,
):
    if omit_temperature and temperature is not None:
        raise ValueError(
            "--temperature and --omit-temperature cannot be used together"
        )
    if reasoning_effort is not None and temperature is not None:
        raise ValueError(
            "--reasoning-effort cannot be combined with --temperature; "
            "temperature is omitted automatically for reasoning runs"
        )
    if reasoning_effort is not None or omit_temperature:
        return None
    return 0.0 if temperature is None else temperature

DEFAULT_EPISODES = [
    "electrical-bongabon-generator-001",
    "electrical-national-museum-lighting-002",
    "electrical-neust-cable-003",
    "electrical-dla-breaker-004",
    "electrical-barrie-transformer-005",
]

DEVELOPMENT_EPISODES = [
    "electrical-bongabon-generator-001",
    "electrical-national-museum-lighting-002",
    "electrical-neust-cable-003",
    "electrical-dla-breaker-004",
    "electrical-barrie-transformer-005",
    "electrical-bfar-generator-006",
    "electrical-negros-wire-007",
    "electrical-burauen-generator-008",
    "electrical-highpoint-transformer-009",
    "electrical-painesville-switchgear-010",
    "electrical-sagada-generator-011",
    "electrical-dla-relay-012",
    "electrical-dla-transformer-013",
    "electrical-dla-battery-supply-014",
    "electrical-dla-battery-charger-015",
    "electrical-dla-power-supply-016",
    "electrical-dla-qpl-breaker-017",
    "electrical-highpoint-cable-018",
    "electrical-usaf-ups-019",
    "electrical-vre-generator-020",
]


def model_slug(model):
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-") or "model"
    digest = sha256(model.encode("utf-8")).hexdigest()[:10]
    readable = readable[:108].rstrip("._-") or "model"
    return f"{readable}--{digest}"


def validate_episode_id(episode_id):
    if not isinstance(episode_id, str) or not EPISODE_ID_RE.fullmatch(episode_id):
        raise ValueError(
            f"Invalid episode ID for pilot output path: {episode_id!r}"
        )
    return episode_id


def ensure_fresh_output_dir(output_dir):
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Pilot output directory is not empty: {output_dir}. "
            "Use a new --output-dir so raw replicates are never overwritten."
        )


def flatten_result(result, model, repeat):
    evaluation = result.get("evaluation") or {}
    hard = evaluation.get("hard_constraints") or {}
    checkpoints = evaluation.get("required_checkpoints") or {}
    obligations = evaluation.get("obligations") or {}
    metrics = result.get("policy_metrics") or {}
    return {
        "model": model,
        "episode_id": result["episode_id"],
        "repeat": repeat,
        "run_id": result["run_id"],
        "status": result["status"],
        "episode_success": bool(evaluation.get("episode_success", False)),
        "episode_success_v02": bool(evaluation.get("episode_success_v02", False)),
        "feasible_process_success": bool(evaluation.get("feasible_process_success", False)),
        "feasible_obligation_success": bool(evaluation.get("feasible_obligation_success", False)),
        "terminal_feasible": bool((evaluation.get("terminal_outcome") or {}).get("correct", False)),
        "economic_objective_satisfied": bool((evaluation.get("economic_objective") or {}).get("satisfied", False)),
        "hard_constraints_passed": hard.get("passed"),
        "hard_constraints_total": hard.get("total"),
        "checkpoints_completed": checkpoints.get("completed"),
        "checkpoints_total": checkpoints.get("total"),
        "constraint_violations": list(evaluation.get("constraint_violations") or []),
        "incomplete_checkpoints": [x["checkpoint"] for x in checkpoints.get("results", []) if not x.get("complete", False)],
        "obligations_actionable": obligations.get("actionable"),
        "obligations_resolved": obligations.get("resolved"),
        "obligations_unresolved": obligations.get("unresolved"),
        "obligations_no_opportunity": obligations.get("no_opportunity"),
        "obligations_not_applicable": obligations.get("not_applicable"),
        "obligation_resolution_rate": obligations.get("resolution_rate"),
        "unresolved_obligations": [
            x.get("checkpoint")
            for x in obligations.get("results", [])
            if x.get("status") == "unresolved"
            and x.get("checkpoint")
        ],
        "accepted_actions": (evaluation.get("efficiency") or {}).get("accepted_actions", len(result.get("trajectory", []))),
        "model_calls": metrics.get("model_calls_attempted", metrics.get("model_calls")),
        "total_tokens": metrics.get("total_tokens"),
        "latency_ms": metrics.get("latency_ms"),
        "cost_usd": metrics.get("cost_usd"),
        "usage_incomplete": metrics.get("usage_incomplete"),
        "error_type": (result.get("error") or {}).get("type"),
        "evaluation_error_type": (
            result.get("evaluation_error") or {}
        ).get("type"),
    }


def _mean(values):
    known = [float(x) for x in values if x is not None]
    return sum(known) / len(known) if known else None


def summarize(rows, baseline_name="reactive-llm-v0.1"):
    by_model = {}
    for model in sorted({r["model"] for r in rows}):
        subset = [r for r in rows if r["model"] == model]
        constraints = Counter(x for r in subset for x in r["constraint_violations"])
        checkpoints = Counter(x for r in subset for x in r["incomplete_checkpoints"])
        statuses = Counter(r["status"] for r in subset)
        successes = sum(r["episode_success"] for r in subset)
        successes_v02 = sum(r.get("episode_success_v02", False) for r in subset)
        terminal = sum(r["terminal_feasible"] for r in subset)
        process = sum(r["feasible_process_success"] for r in subset)
        obligation_success = sum(
            r.get("feasible_obligation_success", False) for r in subset
        )
        economic = sum(r["economic_objective_satisfied"] for r in subset)
        unresolved_obligations = Counter(
            x
            for r in subset
            for x in (r.get("unresolved_obligations") or [])
            if x
        )
        by_model[model] = {
            "runs": len(subset),
            "episode_successes": successes,
            "episode_success_rate": successes / len(subset),
            "episode_successes_v02": successes_v02,
            "episode_success_rate_v02": successes_v02 / len(subset),
            "terminal_feasible_rate": terminal / len(subset),
            "feasible_process_success_rate": process / len(subset),
            "feasible_obligation_success_rate": obligation_success / len(subset),
            "economic_objective_rate": economic / len(subset),
            "actionable_obligations": sum(
                int(r.get("obligations_actionable") or 0) for r in subset
            ),
            "resolved_obligations": sum(
                int(r.get("obligations_resolved") or 0) for r in subset
            ),
            "unresolved_obligations": sum(
                int(r.get("obligations_unresolved") or 0) for r in subset
            ),
            "unresolved_obligation_counts": dict(
                sorted(unresolved_obligations.items())
            ),
            "status_counts": dict(sorted(statuses.items())),
            "constraint_failure_counts": dict(sorted(constraints.items())),
            "checkpoint_failure_counts": dict(sorted(checkpoints.items())),
            "mean_accepted_actions": _mean([r["accepted_actions"] for r in subset]),
            "mean_total_tokens": _mean([r["total_tokens"] for r in subset]),
            "mean_latency_ms": _mean([r["latency_ms"] for r in subset]),
            "total_known_cost_usd": sum(
                float(r["cost_usd"])
                for r in subset
                if r["cost_usd"] is not None
            ),
            "runs_with_unknown_cost_usd": sum(
                r["cost_usd"] is None for r in subset
            ),
            "runs_with_incomplete_usage": sum(bool(r["usage_incomplete"]) for r in subset),
        }
    return {"schema_version": "0.1.0", "benchmark": "LongProcureBench", "baseline": baseline_name, "runs": len(rows), "by_model": by_model}


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["model","episode_id","repeat","run_id","status","episode_success","episode_success_v02","feasible_process_success","feasible_obligation_success","terminal_feasible","economic_objective_satisfied","hard_constraints_passed","hard_constraints_total","checkpoints_completed","checkpoints_total","constraint_violations","incomplete_checkpoints","obligations_actionable","obligations_resolved","obligations_unresolved","obligations_no_opportunity","obligations_not_applicable","obligation_resolution_rate","unresolved_obligations","accepted_actions","model_calls","total_tokens","latency_ms","cost_usd","usage_incomplete","error_type","evaluation_error_type"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            x = dict(row)
            x["constraint_violations"] = ";".join(row["constraint_violations"])
            x["incomplete_checkpoints"] = ";".join(row["incomplete_checkpoints"])
            x["unresolved_obligations"] = ";".join(
                row.get("unresolved_obligations") or []
            )
            w.writerow(x)


def run_pilot(
    models,
    episodes,
    repeats,
    output_dir,
    max_actions=50,
    runner=None,
    policy_factory=ReactiveLLMPolicy,
    policy_kwargs=None,
    run_prefix="reactive-v0.1",
    baseline_name="reactive-llm-v0.1",
):
    if not models:
        raise ValueError("At least one model is required")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")

    output_dir = Path(output_dir)
    ensure_fresh_output_dir(output_dir)
    validated_episodes = [validate_episode_id(x) for x in episodes]

    runner = runner or BenchmarkRunner()
    policy_kwargs = dict(policy_kwargs or {})
    rows = []
    for model in models:
        for episode_id in validated_episodes:
            for repeat in range(1, repeats + 1):
                policy = policy_factory(model, **policy_kwargs)
                rid = f"{run_prefix}--{model_slug(model)}--{episode_id}--r{repeat:03d}"
                path = output_dir / model_slug(model) / episode_id / f"run-{repeat:03d}.json"
                result = runner.run(policy, episode_id, max_actions=max_actions, run_id=rid, result_path=path)
                row = flatten_result(result, model, repeat)
                rows.append(row)
                print(f"{model} | {episode_id} | r{repeat}: status={row['status']} success={row['episode_success']} actions={row['accepted_actions']} tokens={row['total_tokens']}")
    summary = summarize(rows, baseline_name=baseline_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(rows, output_dir / "runs.csv")
    return rows, summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", action="append", dest="models", required=True)
    p.add_argument("--episode", action="append", dest="episodes")
    p.add_argument(
        "--development-suite",
        action="store_true",
        help="Run all 20 frozen development/calibration episodes.",
    )
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--max-actions", type=int, default=50)
    p.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature. Defaults to 0.0 when reasoning is off.",
    )
    p.add_argument(
        "--omit-temperature",
        action="store_true",
        help="Omit temperature from the provider request.",
    )
    p.add_argument(
        "--reasoning-effort",
        default=None,
        help=(
            "Provider reasoning effort. Supplying this automatically omits "
            "temperature; do not combine it with --temperature."
        ),
    )
    p.add_argument("--output-dir", default="results/reactive-pilot-v0.1")
    a = p.parse_args()
    try:
        temperature = resolve_sampling_options(
            a.temperature,
            a.omit_temperature,
            a.reasoning_effort,
        )
    except ValueError as exc:
        p.error(str(exc))
    if a.development_suite and a.episodes:
        p.error("--development-suite cannot be combined with --episode")
    episodes = (
        DEVELOPMENT_EPISODES
        if a.development_suite
        else (a.episodes or DEFAULT_EPISODES)
    )
    run_pilot(
        a.models,
        episodes,
        a.repeats,
        Path(a.output_dir),
        a.max_actions,
        policy_kwargs={
            "temperature": temperature,
            "reasoning_effort": a.reasoning_effort,
        },
    )


if __name__ == "__main__":
    main()
