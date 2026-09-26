"""Audit the frozen operational-ledger experiment against context compilation."""
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
    load_frozen_context_compiled_source,
    reconstruct_actions as reconstruct_context_actions,
)
from frozen_operational_ledger_v01 import (
    EPISODES,
    EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256,
    EXPECTED_EPISODES,
    EXPECTED_ORIGINAL_RUNS,
    EXPECTED_RECOVERY_RUNS,
    EXPECTED_REPEATS,
    EXPECTED_PARTS,
    EXPECTED_RUNS,
    MODEL,
    load_frozen_operational_ledger_source,
    reconstruct_actions as reconstruct_ledger_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "operational-ledger-reactive-v0.1"
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
    statuses = Counter()
    terminal = obligation_success = strict = 0
    actionable = resolved = unresolved = 0
    prompt = completion = total_tokens = calls = 0
    latency = cost = 0.0
    ledger_created = []
    ledger_max_open = []
    ledger_final_open = []
    ledger_final_resolved = []

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
        statuses[record.get("status", "completed")] += 1

        metrics = record["policy_metrics"]
        prompt += int(metrics["prompt_tokens"])
        completion += int(metrics["completion_tokens"])
        total_tokens += int(metrics["total_tokens"])
        calls += int(metrics["model_calls_attempted"])
        latency += float(metrics["latency_ms"])
        cost += float(metrics["cost_usd"])

        if metrics.get("ledger_items_created") is not None:
            ledger_created.append(int(metrics["ledger_items_created"]))
            ledger_max_open.append(int(metrics["ledger_max_open_items"]))
            ledger_final_open.append(int(metrics["ledger_open_items"]))
            ledger_final_resolved.append(
                int(metrics["ledger_resolved_items"])
            )

    summary = {
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
        "status_counts": dict(sorted(statuses.items())),
        "action_type_counts": dict(sorted(actions.items())),
    }

    if ledger_created:
        count = len(ledger_created)
        summary.update({
            "ledger_items_created": sum(ledger_created),
            "mean_ledger_items_created": sum(ledger_created) / count,
            "mean_ledger_max_open_items": sum(ledger_max_open) / count,
            "mean_final_open_items": sum(ledger_final_open) / count,
            "mean_final_resolved_items": (
                sum(ledger_final_resolved) / count
            ),
        })
    return summary


def _unresolved_counts(
    records: list[dict[str, Any]],
) -> dict[str, int]:
    counts = Counter()
    for record in records:
        for obligation in record["evaluation"]["obligations"]["results"]:
            if (
                obligation.get("status") == "unresolved"
                and obligation.get("checkpoint")
            ):
                counts[obligation["checkpoint"]] += 1
    return dict(sorted(counts.items()))


def _per_episode(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
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
            "calls": sum(
                int(r["policy_metrics"]["model_calls_attempted"])
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
    payload = (
        f"longprocurebench-bootstrap-v1:"
        f"{BOOTSTRAP_SEED}:{resample}:{draw}"
    ).encode("utf-8")
    return int.from_bytes(sha256(payload).digest(), "big") % len(EPISODES)


def _bootstrap(
    context: dict[str, dict[str, float]],
    ledger: dict[str, dict[str, float]],
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
            "model_calls_pct",
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
            context_mean = sum(
                context[EPISODES[index]][field] for index in sampled
            ) / len(EPISODES)
            ledger_mean = sum(
                ledger[EPISODES[index]][field] for index in sampled
            ) / len(EPISODES)
            values[output_name].append(
                100 * (ledger_mean - context_mean)
            )

        context_resolved = sum(
            context[EPISODES[index]]["resolved"] for index in sampled
        )
        context_actionable = sum(
            context[EPISODES[index]]["actionable"] for index in sampled
        )
        ledger_resolved = sum(
            ledger[EPISODES[index]]["resolved"] for index in sampled
        )
        ledger_actionable = sum(
            ledger[EPISODES[index]]["actionable"] for index in sampled
        )
        values["obligation_resolution_pp"].append(
            100 * (
                ledger_resolved / ledger_actionable
                - context_resolved / context_actionable
            )
        )

        for field, output_name in (
            ("tokens", "total_tokens_pct"),
            ("cost", "cost_pct"),
            ("latency", "latency_pct"),
            ("calls", "model_calls_pct"),
        ):
            context_total = sum(
                context[EPISODES[index]][field] for index in sampled
            )
            ledger_total = sum(
                ledger[EPISODES[index]][field] for index in sampled
            )
            values[output_name].append(
                100 * (ledger_total / context_total - 1)
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
    tolerance = 1e-9
    obligation_gain = (
        delta["feasible_obligation_success_pp"] >= 5.0 - tolerance
        and delta["terminal_feasible_pp"] >= -5.0 - tolerance
    )
    strict_gain_guardrailed = (
        delta["episode_success_v02_pp"] >= 5.0 - tolerance
        and delta["feasible_obligation_success_pp"] >= -2.0 - tolerance
        and delta["terminal_feasible_pp"] >= -5.0 - tolerance
    )
    if obligation_gain:
        matched = "feasible_obligation_gain"
    elif strict_gain_guardrailed:
        matched = "strict_gain_guardrailed"
    else:
        matched = None

    return {
        "passed": obligation_gain or strict_gain_guardrailed,
        "matched_condition": matched,
        "feasible_obligation_gain": {
            "passed": obligation_gain,
            "rule": (
                "feasible-obligation success improves by >=5 pp AND "
                "terminal feasibility does not fall by more than 5 pp"
            ),
        },
        "strict_gain_guardrailed": {
            "passed": strict_gain_guardrailed,
            "rule": (
                "strict v0.2 success improves by >=5 pp AND "
                "feasible-obligation success does not fall by more than "
                "2 pp AND terminal feasibility does not fall by more "
                "than 5 pp"
            ),
        },
    }


def build_comparison() -> dict[str, Any]:
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    context_source = load_frozen_context_compiled_source(ROOT)
    ledger_source = load_frozen_operational_ledger_source(ROOT)

    context_records = _evaluate_records(
        context_source,
        reconstruct_context_actions,
        evaluator,
    )
    ledger_records = _evaluate_records(
        ledger_source,
        reconstruct_ledger_actions,
        evaluator,
    )
    context = _summarize(context_records)
    ledger = _summarize(ledger_records)

    delta = {
        "terminal_feasible_pp": 100 * (
            ledger["terminal_feasible"] / 60
            - context["terminal_feasible"] / 60
        ),
        "feasible_obligation_success_pp": 100 * (
            ledger["feasible_obligation_success"] / 60
            - context["feasible_obligation_success"] / 60
        ),
        "episode_success_v02_pp": 100 * (
            ledger["episode_success_v02"] / 60
            - context["episode_success_v02"] / 60
        ),
        "obligation_resolution_pp": 100 * (
            ledger["resolved_obligations"]
            / ledger["actionable_obligations"]
            - context["resolved_obligations"]
            / context["actionable_obligations"]
        ),
        "prompt_tokens_pct": 100 * (
            ledger["prompt_tokens"] / context["prompt_tokens"] - 1
        ),
        "completion_tokens_pct": 100 * (
            ledger["completion_tokens"]
            / context["completion_tokens"]
            - 1
        ),
        "total_tokens_pct": 100 * (
            ledger["total_tokens"] / context["total_tokens"] - 1
        ),
        "model_calls_pct": 100 * (
            ledger["model_calls"] / context["model_calls"] - 1
        ),
        "latency_pct": 100 * (
            ledger["latency_ms"] / context["latency_ms"] - 1
        ),
        "cost_pct": 100 * (
            ledger["cost_usd"] / context["cost_usd"] - 1
        ),
    }

    return {
        "schema_version": "0.1.0",
        "experiment": "operational-ledger-reactive-v0.1",
        "model": MODEL,
        "runs_per_condition": 60,
        "episodes": 20,
        "repeats": 3,
        "source_workflow_runs": [36231717716, 36235841640],
        "recovery_selection": {
            "original_artifact_id": 10902813768,
            "original_retained_runs": 43,
            "recovery_artifact_id": 10904540560,
            "recovery_retained_runs": 17,
            "discarded_recovery_key": (
                "electrical-dla-battery-charger-015/r1"
            ),
            "discard_rule": (
                "discard recovery 015/r1 before outcome inspection; "
                "retain original valid 015/r1"
            ),
        },
        "context_compiled": context,
        "operational_ledger": ledger,
        "delta": delta,
        "cluster_bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "sampler": BOOTSTRAP_SAMPLER,
            "cluster": "episode_id",
            "95pct_ci": _bootstrap(
                _per_episode(context_records),
                _per_episode(ledger_records),
            ),
        },
        "predeclared_gate": evaluate_predeclared_gate(delta),
        "unresolved_obligation_counts": _unresolved_counts(
            ledger_records
        ),
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

    expected_top = {
        "benchmark_code_sha": (
            "4a3ef65b40f37b14816926e1e2d48110705c78f5"
        ),
        "model": MODEL,
        "records": EXPECTED_RUNS,
        "episodes": EXPECTED_EPISODES,
        "repeats_per_episode": EXPECTED_REPEATS,
    }
    for key, value in expected_top.items():
        if manifest.get(key) != value:
            raise ValueError(
                f"Ledger manifest experiment mismatch for {key}"
            )

    expected_artifacts = {
        "original": {
            "workflow_run_id": 36231717716,
            "workflow_run_attempt": 1,
            "artifact_id": 10902813768,
            "artifact_name": (
                "operational-ledger-reactive-36231717716-1"
            ),
            "artifact_digest": (
                "sha256:801decf63bc6e24f6bba2a20d6326dd"
                "482065aedd5bab266e8d9ff66c895e950"
            ),
            "execution_head_sha": (
                "da3e0236b862b36f0eb607e9af5b72ecbdbe71c3"
            ),
            "retained_runs": EXPECTED_ORIGINAL_RUNS,
        },
        "recovery": {
            "workflow_run_id": 36235841640,
            "workflow_run_attempt": 1,
            "artifact_id": 10904540560,
            "artifact_name": (
                "operational-ledger-reactive-36235841640-1"
            ),
            "artifact_digest": (
                "sha256:53c4de34d9f8ce85935e7dd783d05b2"
                "e122b5dcc7d80b74d432ea87189f0be9b"
            ),
            "execution_head_sha": (
                "55f5cba2c6349723bc46753b6025d37edd0640d3"
            ),
            "retained_runs": EXPECTED_RECOVERY_RUNS,
        },
    }
    artifacts = manifest.get("source_artifacts") or {}
    for source, expected in expected_artifacts.items():
        actual = artifacts.get(source) or {}
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ValueError(
                    f"Ledger manifest provenance mismatch: "
                    f"{source}.{key}"
                )

    selection = manifest.get("recovery_selection") or {}
    if selection.get("discarded_recovery_key") != (
        "electrical-dla-battery-charger-015/r1"
    ):
        raise ValueError("Ledger recovery discard key mismatch")

    expected_episode_index = {
        str(index): episode_id
        for index, episode_id in enumerate(EPISODES, start=1)
    }
    if manifest.get("episode_index") != expected_episode_index:
        raise ValueError("Ledger manifest episode index mismatch")

    storage = manifest.get("storage") or {}
    expected_storage = {
        "parts": list(EXPECTED_PARTS),
        "compressed_bytes": EXPECTED_COMPRESSED_BYTES,
        "compressed_sha256": EXPECTED_COMPRESSED_SHA256,
    }
    for key, value in expected_storage.items():
        if storage.get(key) != value:
            raise ValueError(
                f"Ledger manifest replay storage mismatch for {key}"
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
                f"Frozen ledger comparison manifest mismatch for {key}"
            )

    payload = COMPARISON_PATH.read_bytes()
    if len(payload) != comparison.get("bytes"):
        raise ValueError("Frozen ledger comparison size mismatch")
    if sha256(payload).hexdigest() != comparison.get("sha256"):
        raise ValueError("Frozen ledger comparison digest mismatch")


def check_frozen_comparison() -> dict[str, Any]:
    expected = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
    actual = build_comparison()
    try:
        _close(actual, expected)
    except ValueError:
        print(
            "Replay-derived operational-ledger comparison:",
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
    gate = comparison["predeclared_gate"]
    print("Operational-ledger matched audit passed.")
    print(
        "terminal={:+.1f}pp obligation_success={:+.1f}pp "
        "strict={:+.1f}pp tokens={:+.1f}% calls={:+.1f}% gate={}"
        .format(
            delta["terminal_feasible_pp"],
            delta["feasible_obligation_success_pp"],
            delta["episode_success_v02_pp"],
            delta["total_tokens_pct"],
            delta["model_calls_pct"],
            gate["passed"],
        )
    )


if __name__ == "__main__":
    main()
