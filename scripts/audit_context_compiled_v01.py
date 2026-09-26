"""Audit the frozen context-compiled experiment and matched raw baseline."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
from frozen_context_compiled_v01 import (
    EPISODES,
    EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256,
    EXPECTED_EPISODES,
    EXPECTED_REPEATS,
    EXPECTED_RUNS,
    MODEL,
    load_frozen_context_compiled_source,
    reconstruct_actions as reconstruct_context_actions,
)
from frozen_cross_family_reactive_v01 import (
    load_frozen_cross_family_source,
    reconstruct_actions as reconstruct_raw_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "context-compiled-reactive-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
COMPARISON_PATH = EVIDENCE_DIR / "comparison.json"
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SAMPLER = "sha256-index-v1"


def _evaluate_records(
    records: list[dict[str, Any]],
    reconstruct,
    evaluator: LongProcureBenchEvaluator,
) -> list[dict[str, Any]]:
    out = []
    for record in records:
        evaluation = evaluator.evaluate_actions(
            record["episode_id"],
            reconstruct(record),
        )
        out.append({
            **record,
            "evaluation": evaluation,
        })
    return out


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    actions = Counter()
    terminal = obligation_success = strict = 0
    actionable = resolved = unresolved = 0
    prompt = completion = total_tokens = calls = 0
    latency = cost = 0.0

    for record in records:
        evaluation = record["evaluation"]
        obligations = evaluation["obligations"]
        terminal += int(evaluation["terminal_outcome"]["correct"])
        obligation_success += int(
            evaluation["feasible_obligation_success"]
        )
        strict += int(evaluation["episode_success_v02"])
        actionable += int(obligations["actionable"])
        resolved += int(obligations["resolved"])
        unresolved += int(obligations["unresolved"])

        for decision in record["decisions"]:
            actions[decision["type"]] += 1

        metrics = record["policy_metrics"]
        prompt += int(metrics["prompt_tokens"])
        completion += int(metrics["completion_tokens"])
        total_tokens += int(metrics["total_tokens"])
        calls += int(metrics["model_calls_attempted"])
        latency += float(metrics["latency_ms"])
        cost += float(metrics["cost_usd"])

    return {
        "terminal_feasible": terminal,
        "feasible_obligation_success": obligation_success,
        "episode_success_v02": strict,
        "actionable_obligations": actionable,
        "resolved_obligations": resolved,
        "unresolved_obligations": unresolved,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total_tokens,
        "model_calls": calls,
        "latency_ms": latency,
        "cost_usd": cost,
        "action_type_counts": dict(sorted(actions.items())),
    }


def _per_episode(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["episode_id"]].append(record)

    result = {}
    for episode_id in EPISODES:
        rows = grouped[episode_id]
        if len(rows) != 3:
            raise ValueError(
                f"Expected 3 runs for {episode_id}; found {len(rows)}"
            )
        result[episode_id] = {
            "terminal": sum(
                int(r["evaluation"]["terminal_outcome"]["correct"])
                for r in rows
            ) / 3,
            "obligation_success": sum(
                int(r["evaluation"]["feasible_obligation_success"])
                for r in rows
            ) / 3,
            "strict": sum(
                int(r["evaluation"]["episode_success_v02"])
                for r in rows
            ) / 3,
            "resolved": sum(
                int(r["evaluation"]["obligations"]["resolved"])
                for r in rows
            ),
            "actionable": sum(
                int(r["evaluation"]["obligations"]["actionable"])
                for r in rows
            ),
            "tokens": sum(
                int(r["policy_metrics"]["total_tokens"])
                for r in rows
            ),
            "cost": sum(
                float(r["policy_metrics"]["cost_usd"])
                for r in rows
            ),
            "latency": sum(
                float(r["policy_metrics"]["latency_ms"])
                for r in rows
            ),
        }
    return result


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] + weight * (ordered[high] - ordered[low])


def _bootstrap_index(resample: int, draw: int) -> int:
    """Return a version-independent deterministic episode index."""
    payload = (
        f"longprocurebench-bootstrap-v1:"
        f"{BOOTSTRAP_SEED}:{resample}:{draw}"
    ).encode("utf-8")
    return int.from_bytes(sha256(payload).digest(), "big") % len(EPISODES)


def _bootstrap(
    raw: dict[str, dict[str, float]],
    compiled: dict[str, dict[str, float]],
) -> dict[str, list[float]]:
    values = {
        name: []
        for name in (
            "terminal_feasible_pp",
            "feasible_obligation_success_pp",
            "episode_success_v02_pp",
            "obligation_resolution_pp",
            "total_tokens_pct",
            "cost_pct",
            "latency_pct",
        )
    }

    for resample in range(BOOTSTRAP_RESAMPLES):
        sampled = [
            _bootstrap_index(resample, draw)
            for draw in range(len(EPISODES))
        ]

        for field, output_name in (
            ("terminal", "terminal_feasible_pp"),
            ("obligation_success", "feasible_obligation_success_pp"),
            ("strict", "episode_success_v02_pp"),
        ):
            raw_mean = sum(
                raw[EPISODES[index]][field] for index in sampled
            ) / len(EPISODES)
            compiled_mean = sum(
                compiled[EPISODES[index]][field] for index in sampled
            ) / len(EPISODES)
            values[output_name].append(
                100 * (compiled_mean - raw_mean)
            )

        raw_resolved = sum(
            raw[EPISODES[index]]["resolved"] for index in sampled
        )
        raw_actionable = sum(
            raw[EPISODES[index]]["actionable"] for index in sampled
        )
        compiled_resolved = sum(
            compiled[EPISODES[index]]["resolved"] for index in sampled
        )
        compiled_actionable = sum(
            compiled[EPISODES[index]]["actionable"] for index in sampled
        )
        values["obligation_resolution_pp"].append(
            100 * (
                compiled_resolved / compiled_actionable
                - raw_resolved / raw_actionable
            )
        )

        for field, output_name in (
            ("tokens", "total_tokens_pct"),
            ("cost", "cost_pct"),
            ("latency", "latency_pct"),
        ):
            raw_total = sum(
                raw[EPISODES[index]][field] for index in sampled
            )
            compiled_total = sum(
                compiled[EPISODES[index]][field] for index in sampled
            )
            values[output_name].append(
                100 * (compiled_total / raw_total - 1)
            )

    return {
        name: [
            _quantile(samples, 0.025),
            _quantile(samples, 0.975),
        ]
        for name, samples in values.items()
    }


def evaluate_predeclared_gate(
    delta: dict[str, float],
) -> dict[str, Any]:
    """Evaluate the two frozen development inclusion branches."""
    terminal = float(delta["terminal_feasible_pp"])
    obligation_success = float(
        delta["feasible_obligation_success_pp"]
    )
    obligation_resolution = float(
        delta["obligation_resolution_pp"]
    )
    total_tokens = float(delta["total_tokens_pct"])
    tolerance = 1e-9

    quality_gain = (
        (
            obligation_success >= 5.0 - tolerance
            or obligation_resolution >= 5.0 - tolerance
        )
        and terminal >= -5.0 - tolerance
    )
    efficiency_noninferiority = (
        abs(obligation_success) <= 2.0 + tolerance
        and abs(obligation_resolution) <= 2.0 + tolerance
        and total_tokens <= -15.0 + tolerance
    )

    if quality_gain:
        matched_condition = "quality_gain"
    elif efficiency_noninferiority:
        matched_condition = "efficiency_noninferiority"
    else:
        matched_condition = None

    return {
        "passed": quality_gain or efficiency_noninferiority,
        "matched_condition": matched_condition,
        "quality_gain": {
            "passed": quality_gain,
            "rule": (
                "feasible-obligation success OR obligation-resolution "
                "rate improves by >=5 pp, AND terminal feasibility "
                "does not fall by more than 5 pp"
            ),
        },
        "efficiency_noninferiority": {
            "passed": efficiency_noninferiority,
            "rule": (
                "both reliability metrics remain within +/-2 pp of "
                "raw history, AND total tokens fall by >=15%"
            ),
        },
    }


def build_comparison() -> dict[str, Any]:
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    raw_source = [
        record
        for record in load_frozen_cross_family_source(ROOT)
        if record["model"] == MODEL
    ]
    compiled_source = load_frozen_context_compiled_source(ROOT)

    raw_records = _evaluate_records(
        raw_source,
        reconstruct_raw_actions,
        evaluator,
    )
    compiled_records = _evaluate_records(
        compiled_source,
        reconstruct_context_actions,
        evaluator,
    )
    raw = _summarize(raw_records)
    compiled = _summarize(compiled_records)

    delta = {
        "terminal_feasible_pp": 100 * (
            compiled["terminal_feasible"] / 60
            - raw["terminal_feasible"] / 60
        ),
        "feasible_obligation_success_pp": 100 * (
            compiled["feasible_obligation_success"] / 60
            - raw["feasible_obligation_success"] / 60
        ),
        "episode_success_v02_pp": 100 * (
            compiled["episode_success_v02"] / 60
            - raw["episode_success_v02"] / 60
        ),
        "obligation_resolution_pp": 100 * (
            compiled["resolved_obligations"]
            / compiled["actionable_obligations"]
            - raw["resolved_obligations"]
            / raw["actionable_obligations"]
        ),
        "prompt_tokens_pct": 100 * (
            compiled["prompt_tokens"] / raw["prompt_tokens"] - 1
        ),
        "completion_tokens_pct": 100 * (
            compiled["completion_tokens"] / raw["completion_tokens"] - 1
        ),
        "total_tokens_pct": 100 * (
            compiled["total_tokens"] / raw["total_tokens"] - 1
        ),
        "model_calls_pct": 100 * (
            compiled["model_calls"] / raw["model_calls"] - 1
        ),
        "latency_pct": 100 * (
            compiled["latency_ms"] / raw["latency_ms"] - 1
        ),
        "cost_pct": 100 * (
            compiled["cost_usd"] / raw["cost_usd"] - 1
        ),
    }

    return {
        "schema_version": "0.1.0",
        "experiment": "context-compiled-reactive-v0.1",
        "source_workflow_run_id": 36226304814,
        "model": MODEL,
        "runs_per_condition": 60,
        "episodes": 20,
        "repeats": 3,
        "raw_history": raw,
        "context_compiled": compiled,
        "delta": delta,
        "cluster_bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "sampler": BOOTSTRAP_SAMPLER,
            "cluster": "episode_id",
            "95pct_ci": _bootstrap(
                _per_episode(raw_records),
                _per_episode(compiled_records),
            ),
        },
        "predeclared_gate": evaluate_predeclared_gate(delta),
    }


def _close(actual: Any, expected: Any, path: str = "root") -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(f"Comparison shape mismatch at {path}")
        for key in expected:
            _close(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"Comparison list mismatch at {path}")
        for index, value in enumerate(expected):
            _close(actual[index], value, f"{path}[{index}]")
        return
    if isinstance(expected, float):
        if not math.isclose(
            float(actual),
            expected,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Comparison numeric drift at {path}: "
                f"expected={expected}, actual={actual}"
            )
        return
    if actual != expected:
        raise ValueError(
            f"Comparison drift at {path}: expected={expected!r}, "
            f"actual={actual!r}"
        )


def check_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        "source_workflow_run_id": 36226304814,
        "source_workflow_run_attempt": 1,
        "source_artifact_id": 10901395062,
        "source_artifact_name": (
            "context-compiled-reactive-36226304814-1"
        ),
        "source_artifact_digest": (
            "sha256:7c73f651715e2e22dfcdc0b696739d850a9c5201"
            "441e6b0f2e25e028adca7ef0"
        ),
        "benchmark_code_sha": (
            "98a698654ef454a7b48af6f701e41cf49fea6638"
        ),
        "execution_head_sha": (
            "0673a425685b75a4317f89eed138d28a3436a769"
        ),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(
                f"Context manifest provenance mismatch for {key}"
            )

    dimensions = {
        "model": MODEL,
        "records": EXPECTED_RUNS,
        "episodes": EXPECTED_EPISODES,
        "repeats_per_episode": EXPECTED_REPEATS,
    }
    for key, value in dimensions.items():
        if manifest.get(key) != value:
            raise ValueError(
                f"Context manifest experiment mismatch for {key}"
            )

    expected_episode_index = {
        str(index): episode_id
        for index, episode_id in enumerate(EPISODES, start=1)
    }
    if manifest.get("episode_index") != expected_episode_index:
        raise ValueError("Context manifest episode index mismatch")

    storage = manifest.get("storage") or {}
    expected_storage = {
        "path": "replay-source.b64",
        "compressed_bytes": EXPECTED_COMPRESSED_BYTES,
        "compressed_sha256": EXPECTED_COMPRESSED_SHA256,
    }
    for key, value in expected_storage.items():
        if storage.get(key) != value:
            raise ValueError(
                f"Context manifest replay storage mismatch for {key}"
            )

    comparison = manifest.get("comparison") or {}
    expected_comparison = {
        "path": "comparison.json",
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_cluster": "episode_id",
        "bootstrap_sampler": BOOTSTRAP_SAMPLER,
    }
    for key, value in expected_comparison.items():
        if comparison.get(key) != value:
            raise ValueError(
                f"Frozen context comparison manifest mismatch for {key}"
            )

    payload = COMPARISON_PATH.read_bytes()
    if len(payload) != comparison.get("bytes"):
        raise ValueError("Frozen context comparison size mismatch")
    if sha256(payload).hexdigest() != comparison.get("sha256"):
        raise ValueError("Frozen context comparison digest mismatch")


def check_frozen_comparison() -> dict[str, Any]:
    expected = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
    actual = build_comparison()
    try:
        _close(actual, expected)
    except ValueError:
        print(
            "Replay-derived comparison that failed the frozen check:",
            file=sys.stderr,
        )
        print(
            json.dumps(actual, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        raise
    return actual


def main() -> None:
    check_manifest()
    comparison = check_frozen_comparison()
    delta = comparison["delta"]
    print("Context-compiled matched audit passed.")
    print(
        "terminal={:+.1f}pp obligation_success={:+.1f}pp "
        "obligation_resolution={:+.1f}pp tokens={:+.1f}% cost={:+.1f}%"
        .format(
            delta["terminal_feasible_pp"],
            delta["feasible_obligation_success_pp"],
            delta["obligation_resolution_pp"],
            delta["total_tokens_pct"],
            delta["cost_pct"],
        )
    )


if __name__ == "__main__":
    main()
