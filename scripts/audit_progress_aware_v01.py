"""Audit frozen progress-aware reactive evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
from frozen_context_compiled_v01 import (
    load_frozen_context_compiled_source,
    reconstruct_actions as reconstruct_context_actions,
)
from frozen_progress_aware_v01 import (
    EPISODES,
    MODEL,
    load_frozen_progress_aware_source,
    reconstruct_actions as reconstruct_progress_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "progress-aware-reactive-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
COMPARISON_PATH = EVIDENCE_DIR / "comparison.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SAMPLER = "sha256-index-v1"


def _canonical_compact_line(row: Any) -> bytes:
    return (
        json.dumps(
            row,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def _compact_row_from_record(record: dict[str, Any]) -> list[Any]:
    episode_index = EPISODES.index(record["episode_id"]) + 1
    decisions = [
        [
            decision["type"],
            decision.get("supplier_id"),
            decision.get("arguments") or {},
        ]
        for decision in record["decisions"]
    ]
    metrics = record["policy_metrics"]
    compact_metrics = [
        metrics.get("model_calls_attempted"),
        metrics.get("prompt_tokens"),
        metrics.get("completion_tokens"),
        metrics.get("total_tokens"),
        metrics.get("latency_ms"),
        metrics.get("cost_usd"),
        metrics.get("usage_incomplete"),
        metrics.get("temperature"),
        metrics.get("reasoning_effort"),
        metrics.get("context_strategy"),
        metrics.get("state_strategy"),
        metrics.get("no_progress_marks"),
        metrics.get("progress_events"),
        metrics.get("evidence_epoch"),
        metrics.get("guard_interventions"),
        metrics.get("guard_retry_calls"),
        metrics.get("guard_retry_noncompliance"),
        metrics.get("model_calls_failed"),
    ]
    return [
        episode_index,
        record["repeat"],
        record["status"],
        decisions,
        compact_metrics,
    ]


def check_provenance_entries(
    records: list[dict[str, Any]],
    provenance_path: Path = PROVENANCE_PATH,
) -> None:
    entries: dict[tuple[int, int], tuple[str, str, str]] = {}
    for line_number, line in enumerate(
        provenance_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError(
                f"Malformed provenance entry on line {line_number}"
            )
        episode_text, repeat_text, member_path, raw_sha, compact_sha = fields
        try:
            episode_index = int(episode_text)
            repeat = int(repeat_text)
        except ValueError as exc:
            raise ValueError(
                f"Invalid provenance key on line {line_number}"
            ) from exc
        if not 1 <= episode_index <= len(EPISODES) or not 1 <= repeat <= 3:
            raise ValueError(
                f"Out-of-range provenance key on line {line_number}"
            )
        expected_suffix = (
            f"/{EPISODES[episode_index - 1]}/run-{repeat:03d}.json"
        )
        if not ("/" + member_path.lstrip("/")).endswith(expected_suffix):
            raise ValueError(
                f"Provenance member path does not match key on line {line_number}"
            )
        for label, digest in (("raw", raw_sha), ("compact", compact_sha)):
            if len(digest) != 64:
                raise ValueError(
                    f"Invalid {label} provenance digest on line {line_number}"
                )
            try:
                int(digest, 16)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid {label} provenance digest on line {line_number}"
                ) from exc
        key = (episode_index, repeat)
        if key in entries:
            raise ValueError(f"Duplicate provenance entry for {key}")
        entries[key] = (member_path, raw_sha, compact_sha)

    expected_keys = {
        (episode_index, repeat)
        for episode_index in range(1, len(EPISODES) + 1)
        for repeat in (1, 2, 3)
    }
    if set(entries) != expected_keys:
        raise ValueError("Provenance grid does not match frozen 20x3 replay")

    for record in records:
        row = _compact_row_from_record(record)
        key = (row[0], row[1])
        actual = sha256(_canonical_compact_line(row)).hexdigest()
        if entries[key][2] != actual:
            raise ValueError(
                "Provenance compact digest does not match frozen replay "
                f"for {key}"
            )


def _evaluate(records, reconstruct: Callable, evaluator):
    out = []
    for record in records:
        evaluation = evaluator.evaluate_actions(
            record["episode_id"], reconstruct(record)
        )
        out.append({**record, "evaluation": evaluation})
    return out


def _summary(records):
    actions = Counter()
    statuses = Counter()
    terminal = obligation_success = strict = 0
    actionable = resolved = unresolved = 0
    prompt = completion = total_tokens = calls = accepted = 0
    latency = cost = 0.0

    for record in records:
        ev = record["evaluation"]
        ob = ev["obligations"]
        metrics = record["policy_metrics"]
        statuses[record.get("status", "completed")] += 1
        terminal += int(ev["terminal_outcome"]["correct"])
        obligation_success += int(ev["feasible_obligation_success"])
        strict += int(ev["episode_success_v02"])
        actionable += int(ob["actionable"])
        resolved += int(ob["resolved"])
        unresolved += int(ob["unresolved"])
        accepted += len(record["decisions"])
        for decision in record["decisions"]:
            actions[decision["type"]] += 1
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
        "accepted_actions": accepted,
        "latency_ms": latency,
        "cost_usd": cost,
        "status_counts": dict(sorted(statuses.items())),
        "action_type_counts": dict(sorted(actions.items())),
    }


def _per_episode(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record["episode_id"]].append(record)
    result = {}
    for episode_id in EPISODES:
        rows = grouped[episode_id]
        if len(rows) != 3:
            raise ValueError(f"Expected 3 runs for {episode_id}")
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
            "actions": sum(len(r["decisions"]) for r in rows),
            "calls": sum(
                int(r["policy_metrics"]["model_calls_attempted"])
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


def _quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (position - low) * (
        ordered[high] - ordered[low]
    )


def _bootstrap_index(resample, draw):
    payload = (
        f"longprocurebench-bootstrap-v1:"
        f"{BOOTSTRAP_SEED}:{resample}:{draw}"
    ).encode("utf-8")
    return int.from_bytes(sha256(payload).digest(), "big") % len(EPISODES)


def _bootstrap(base, treatment):
    names = (
        "terminal_feasible_pp",
        "feasible_obligation_success_pp",
        "episode_success_v02_pp",
        "obligation_resolution_pp",
        "accepted_actions_pct",
        "model_calls_pct",
        "total_tokens_pct",
        "cost_pct",
        "latency_pct",
    )
    values = {name: [] for name in names}
    for resample in range(BOOTSTRAP_RESAMPLES):
        sample = [
            EPISODES[_bootstrap_index(resample, draw)]
            for draw in range(len(EPISODES))
        ]
        for field, output in (
            ("terminal", "terminal_feasible_pp"),
            ("obligation_success", "feasible_obligation_success_pp"),
            ("strict", "episode_success_v02_pp"),
        ):
            base_mean = sum(base[e][field] for e in sample) / len(EPISODES)
            treatment_mean = (
                sum(treatment[e][field] for e in sample) / len(EPISODES)
            )
            values[output].append(100 * (treatment_mean - base_mean))

        base_resolved = sum(base[e]["resolved"] for e in sample)
        base_actionable = sum(base[e]["actionable"] for e in sample)
        treatment_resolved = sum(treatment[e]["resolved"] for e in sample)
        treatment_actionable = sum(
            treatment[e]["actionable"] for e in sample
        )
        values["obligation_resolution_pp"].append(
            100 * (
                treatment_resolved / treatment_actionable
                - base_resolved / base_actionable
            )
        )

        for field, output in (
            ("actions", "accepted_actions_pct"),
            ("calls", "model_calls_pct"),
            ("tokens", "total_tokens_pct"),
            ("cost", "cost_pct"),
            ("latency", "latency_pct"),
        ):
            base_total = sum(base[e][field] for e in sample)
            treatment_total = sum(treatment[e][field] for e in sample)
            values[output].append(
                100 * (treatment_total / base_total - 1)
            )

    return {
        name: [_quantile(samples, .025), _quantile(samples, .975)]
        for name, samples in values.items()
    }


def _gate(delta):
    tolerance = 1e-9
    branch1 = (
        delta["feasible_obligation_success_pp"] >= 5 - tolerance
        and delta["terminal_feasible_pp"] >= -5 - tolerance
        and delta["total_tokens_pct"] <= 15 + tolerance
    )
    branch2 = (
        delta["episode_success_v02_pp"] >= 5 - tolerance
        and delta["feasible_obligation_success_pp"] >= -2 - tolerance
        and delta["terminal_feasible_pp"] >= -5 - tolerance
        and delta["total_tokens_pct"] <= 15 + tolerance
    )
    return {
        "passed": branch1 or branch2,
        "matched_condition": (
            "branch1" if branch1 else ("branch2" if branch2 else None)
        ),
        "branch1": {
            "passed": branch1,
            "rule": (
                "feasible-obligation success improves by >=5 pp, "
                "terminal feasibility falls by <=5 pp, and total tokens "
                "increase by <=15%"
            ),
        },
        "branch2": {
            "passed": branch2,
            "rule": (
                "strict v0.2 success improves by >=5 pp, feasible-obligation "
                "success falls by <=2 pp, terminal feasibility falls by <=5 "
                "pp, and total tokens increase by <=15%"
            ),
        },
    }


def _mechanism(records, base_records):
    no_progress = sum(
        int(r["policy_metrics"]["no_progress_marks"]) for r in records
    )
    runs_with_marks = sum(
        int(r["policy_metrics"]["no_progress_marks"]) > 0 for r in records
    )
    progress_events = sum(
        int(r["policy_metrics"]["progress_events"]) for r in records
    )
    max_epoch = max(
        int(r["policy_metrics"]["evidence_epoch"]) for r in records
    )
    interventions = sum(
        int(r["policy_metrics"]["guard_interventions"]) for r in records
    )
    retries = sum(
        int(r["policy_metrics"]["guard_retry_calls"]) for r in records
    )
    noncompliance = sum(
        int(r["policy_metrics"]["guard_retry_noncompliance"])
        for r in records
    )

    base_ep = _per_episode(base_records)
    treatment_ep = _per_episode(records)
    improved = worsened = tied = 0
    for episode_id in EPISODES:
        delta = (
            treatment_ep[episode_id]["obligation_success"]
            - base_ep[episode_id]["obligation_success"]
        )
        if delta > 0:
            improved += 1
        elif delta < 0:
            worsened += 1
        else:
            tied += 1

    return {
        "no_progress_marks": no_progress,
        "runs_with_no_progress_marks": runs_with_marks,
        "progress_events": progress_events,
        "max_evidence_epoch": max_epoch,
        "guard_interventions": interventions,
        "guard_retry_calls": retries,
        "guard_retry_noncompliance": noncompliance,
        "episode_obligation_success_effect_counts": {
            "improved": improved,
            "worsened": worsened,
            "tied": tied,
        },
        "action_type_counts_context": _summary(base_records)[
            "action_type_counts"
        ],
        "action_type_counts_progress_aware": _summary(records)[
            "action_type_counts"
        ],
    }


def build_comparison():
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    base = _evaluate(
        load_frozen_context_compiled_source(ROOT),
        reconstruct_context_actions,
        evaluator,
    )
    treatment = _evaluate(
        load_frozen_progress_aware_source(ROOT),
        reconstruct_progress_actions,
        evaluator,
    )
    base_summary = _summary(base)
    treatment_summary = _summary(treatment)

    delta = {
        "terminal_feasible_pp": 100 * (
            treatment_summary["terminal_feasible"] / 60
            - base_summary["terminal_feasible"] / 60
        ),
        "feasible_obligation_success_pp": 100 * (
            treatment_summary["feasible_obligation_success"] / 60
            - base_summary["feasible_obligation_success"] / 60
        ),
        "episode_success_v02_pp": 100 * (
            treatment_summary["episode_success_v02"] / 60
            - base_summary["episode_success_v02"] / 60
        ),
        "obligation_resolution_pp": 100 * (
            treatment_summary["resolved_obligations"]
            / treatment_summary["actionable_obligations"]
            - base_summary["resolved_obligations"]
            / base_summary["actionable_obligations"]
        ),
        "prompt_tokens_pct": 100 * (
            treatment_summary["prompt_tokens"]
            / base_summary["prompt_tokens"]
            - 1
        ),
        "completion_tokens_pct": 100 * (
            treatment_summary["completion_tokens"]
            / base_summary["completion_tokens"]
            - 1
        ),
        "total_tokens_pct": 100 * (
            treatment_summary["total_tokens"]
            / base_summary["total_tokens"]
            - 1
        ),
        "model_calls_pct": 100 * (
            treatment_summary["model_calls"]
            / base_summary["model_calls"]
            - 1
        ),
        "accepted_actions_pct": 100 * (
            treatment_summary["accepted_actions"]
            / base_summary["accepted_actions"]
            - 1
        ),
        "latency_pct": 100 * (
            treatment_summary["latency_ms"]
            / base_summary["latency_ms"]
            - 1
        ),
        "cost_pct": 100 * (
            treatment_summary["cost_usd"]
            / base_summary["cost_usd"]
            - 1
        ),
    }

    return {
        "schema_version": "0.1.0",
        "experiment": "progress-aware-reactive-v0.1",
        "source_workflow_run_id": 36312020696,
        "model": MODEL,
        "runs_per_condition": 60,
        "episodes": 20,
        "repeats": 3,
        "context_compiled": base_summary,
        "progress_aware": treatment_summary,
        "delta": delta,
        "cluster_bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "sampler": BOOTSTRAP_SAMPLER,
            "cluster": "episode_id",
            "95pct_ci": _bootstrap(
                _per_episode(base), _per_episode(treatment)
            ),
        },
        "predeclared_gate": _gate(delta),
        "mechanism_diagnostic": _mechanism(treatment, base),
    }


def _close(actual: Any, expected: Any, path="root"):
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
            float(actual), expected, rel_tol=1e-12, abs_tol=1e-9
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


def check_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        "source_workflow_run_id": 36312020696,
        "source_workflow_run_attempt": 1,
        "source_artifact_id": 10929711515,
        "source_artifact_name": "progress-aware-reactive-36312020696-1",
        "source_artifact_digest": (
            "sha256:063cc839f2338116a3a4776ce68a17bdbd5293bcde551b"
            "cd4dbc203909238688"
        ),
        "benchmark_code_sha": (
            "aa0560a43c81c14931e22e2f6ac2bd142820b834"
        ),
        "execution_head_sha": (
            "e615af9ca23806e3dcd14e0cca83aea6297c38be"
        ),
        "records": 60,
        "episodes": 20,
        "repeats_per_episode": 3,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Manifest mismatch for {key}")

    source = manifest["source_verification"]
    provenance = PROVENANCE_PATH.read_bytes()
    if (
        len(provenance) != source["record_provenance_bytes"]
        or sha256(provenance).hexdigest()
        != source["record_provenance_sha256"]
    ):
        raise ValueError("Source provenance mismatch")
    if (
        source.get("verifier_script")
        != "scripts/verify_progress_aware_source_artifact_v01.py"
    ):
        raise ValueError("Source artifact verifier is not declared")
    records = load_frozen_progress_aware_source(ROOT)
    check_provenance_entries(records)

    comparison = manifest["comparison"]
    payload = COMPARISON_PATH.read_bytes()
    if (
        len(payload) != comparison["bytes"]
        or sha256(payload).hexdigest() != comparison["sha256"]
    ):
        raise ValueError("Comparison manifest mismatch")


def main():
    check_manifest()
    expected = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
    actual = build_comparison()
    _close(actual, expected)
    delta = actual["delta"]
    print("Progress-aware matched audit passed.")
    print(
        "terminal={:+.1f}pp obligation_success={:+.1f}pp "
        "strict={:+.1f}pp tokens={:+.1f}% cost={:+.1f}%".format(
            delta["terminal_feasible_pp"],
            delta["feasible_obligation_success_pp"],
            delta["episode_success_v02_pp"],
            delta["total_tokens_pct"],
            delta["cost_pct"],
        )
    )


if __name__ == "__main__":
    main()
