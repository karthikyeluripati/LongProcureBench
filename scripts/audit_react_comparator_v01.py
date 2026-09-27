"""Audit frozen ReAct comparator evidence."""
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
from frozen_react_comparator_v01 import (
    EPISODES,
    MODEL,
    _compact_row_from_record,
    _canonical_line,
    load_frozen_react_source,
    load_frozen_react_transcripts,
    reconstruct_actions as reconstruct_react_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "react-comparator-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
COMPARISON_PATH = EVIDENCE_DIR / "comparison.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"

BOOTSTRAP_SEED = 20260926
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SAMPLER = "sha256-index-v1"


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
                "Provenance member path does not match key on "
                f"line {line_number}"
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
        raise ValueError("Provenance grid does not match frozen ReAct replay")

    for record in records:
        row = _compact_row_from_record(record)
        key = (row[0], row[1])
        actual = sha256(_canonical_line(row)).hexdigest()
        if entries[key][2] != actual:
            raise ValueError(
                "Provenance compact digest does not match frozen replay "
                f"for {key}"
            )


def _evaluate(
    records: list[dict[str, Any]],
    reconstruct: Callable,
    evaluator: LongProcureBenchEvaluator,
) -> list[dict[str, Any]]:
    out = []
    for record in records:
        evaluation = evaluator.evaluate_actions(
            record["episode_id"],
            reconstruct(record),
        )
        out.append({**record, "evaluation": evaluation})
    return out


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    actions = Counter()
    unresolved = Counter()
    statuses = Counter()
    terminal = obligation_success = strict = 0
    legacy_success = process = economic = 0
    actionable = resolved = unresolved_total = 0
    prompt = completion = total_tokens = calls = accepted = 0
    latency = cost = 0.0

    for record in records:
        evaluation = record["evaluation"]
        obligations = evaluation["obligations"]
        metrics = record["policy_metrics"]

        statuses[record.get("status", "completed")] += 1
        terminal += int(evaluation["terminal_outcome"]["correct"])
        obligation_success += int(
            evaluation["feasible_obligation_success"]
        )
        strict += int(evaluation["episode_success_v02"])
        legacy_success += int(evaluation["episode_success"])
        process += int(evaluation["feasible_process_success"])
        economic += int(evaluation["economic_objective"]["satisfied"])

        actionable += int(obligations["actionable"])
        resolved += int(obligations["resolved"])
        unresolved_total += int(obligations["unresolved"])

        accepted += len(record["decisions"])
        for decision in record["decisions"]:
            actions[decision["type"]] += 1

        for row in obligations.get("results") or []:
            if row.get("status") == "unresolved":
                checkpoint = row.get("checkpoint")
                if checkpoint:
                    unresolved[checkpoint] += 1

        calls += int(metrics["model_calls_attempted"])
        prompt += int(metrics["prompt_tokens"])
        completion += int(metrics["completion_tokens"])
        total_tokens += int(metrics["total_tokens"])
        latency += float(metrics["latency_ms"])
        cost += float(metrics["cost_usd"])

    return {
        "accepted_actions": accepted,
        "action_type_counts": dict(sorted(actions.items())),
        "actionable_obligations": actionable,
        "completion_tokens": completion,
        "cost_usd": cost,
        "economic_objective_satisfied": economic,
        "episode_success": legacy_success,
        "episode_success_v02": strict,
        "feasible_obligation_success": obligation_success,
        "feasible_process_success": process,
        "latency_ms": latency,
        "model_calls": calls,
        "prompt_tokens": prompt,
        "resolved_obligations": resolved,
        "status_counts": dict(sorted(statuses.items())),
        "terminal_feasible": terminal,
        "total_tokens": total_tokens,
        "unresolved_obligation_counts": dict(sorted(unresolved.items())),
        "unresolved_obligations": unresolved_total,
    }


def _per_episode(records: list[dict[str, Any]]) -> dict[str, Any]:
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
                int(row["evaluation"]["terminal_outcome"]["correct"])
                for row in rows
            ) / 3,
            "obligation_success": sum(
                int(row["evaluation"]["feasible_obligation_success"])
                for row in rows
            ) / 3,
            "strict": sum(
                int(row["evaluation"]["episode_success_v02"])
                for row in rows
            ) / 3,
            "resolved": sum(
                int(row["evaluation"]["obligations"]["resolved"])
                for row in rows
            ),
            "actionable": sum(
                int(row["evaluation"]["obligations"]["actionable"])
                for row in rows
            ),
            "actions": sum(len(row["decisions"]) for row in rows),
            "calls": sum(
                int(row["policy_metrics"]["model_calls_attempted"])
                for row in rows
            ),
            "tokens": sum(
                int(row["policy_metrics"]["total_tokens"])
                for row in rows
            ),
            "cost": sum(
                float(row["policy_metrics"]["cost_usd"])
                for row in rows
            ),
            "latency": sum(
                float(row["policy_metrics"]["latency_ms"])
                for row in rows
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
    return ordered[low] + (position - low) * (
        ordered[high] - ordered[low]
    )


def _bootstrap_index(resample: int, draw: int) -> int:
    payload = (
        f"longprocurebench-bootstrap-v1:"
        f"{BOOTSTRAP_SEED}:{resample}:{draw}"
    ).encode("utf-8")
    return int.from_bytes(sha256(payload).digest(), "big") % len(EPISODES)


def _bootstrap(
    base: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, list[float]]:
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
    values: dict[str, list[float]] = {name: [] for name in names}

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
            base_mean = sum(
                base[episode_id][field] for episode_id in sample
            ) / len(EPISODES)
            treatment_mean = sum(
                treatment[episode_id][field] for episode_id in sample
            ) / len(EPISODES)
            values[output].append(100 * (treatment_mean - base_mean))

        base_resolved = sum(
            base[episode_id]["resolved"] for episode_id in sample
        )
        base_actionable = sum(
            base[episode_id]["actionable"] for episode_id in sample
        )
        treatment_resolved = sum(
            treatment[episode_id]["resolved"] for episode_id in sample
        )
        treatment_actionable = sum(
            treatment[episode_id]["actionable"] for episode_id in sample
        )
        values["obligation_resolution_pp"].append(
            100
            * (
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
            base_total = sum(
                base[episode_id][field] for episode_id in sample
            )
            treatment_total = sum(
                treatment[episode_id][field] for episode_id in sample
            )
            values[output].append(
                100 * (treatment_total / base_total - 1)
            )

    return {
        name: [_quantile(samples, 0.025), _quantile(samples, 0.975)]
        for name, samples in values.items()
    }


def _effect_counts(
    base: dict[str, Any],
    treatment: dict[str, Any],
    field: str,
) -> dict[str, int]:
    improved = worsened = tied = 0
    for episode_id in EPISODES:
        delta = treatment[episode_id][field] - base[episode_id][field]
        if delta > 0:
            improved += 1
        elif delta < 0:
            worsened += 1
        else:
            tied += 1
    return {
        "improved": improved,
        "tied": tied,
        "worsened": worsened,
    }


def build_comparison() -> dict[str, Any]:
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)

    base = _evaluate(
        load_frozen_context_compiled_source(ROOT),
        reconstruct_context_actions,
        evaluator,
    )
    treatment = _evaluate(
        load_frozen_react_source(ROOT),
        reconstruct_react_actions,
        evaluator,
    )
    transcript_records = load_frozen_react_transcripts(ROOT)
    transcript_by_key = {
        (record["episode_id"], record["repeat"]): record
        for record in transcript_records
    }
    for record in treatment:
        key = (record["episode_id"], record["repeat"])
        transcript_record = transcript_by_key.get(key)
        if transcript_record is None:
            raise ValueError(f"Missing durable ReAct transcript for {key}")
        transcript = transcript_record["react_transcript"]
        decisions = record["decisions"]
        if len(transcript) != len(decisions):
            raise ValueError(
                f"Durable ReAct transcript length mismatch for {key}"
            )
        for step, decision in zip(transcript, decisions):
            if step["action"] != decision:
                raise ValueError(
                    f"Durable ReAct transcript action mismatch for {key}"
                )
        thought_lengths = [
            len(step["thought_summary"]) for step in transcript
        ]
        metrics = record["policy_metrics"]
        if sum(thought_lengths) != metrics["react_thought_chars_total"]:
            raise ValueError(
                f"Durable ReAct thought total mismatch for {key}"
            )
        if max(thought_lengths, default=0) != metrics["react_thought_chars_max"]:
            raise ValueError(
                f"Durable ReAct thought max mismatch for {key}"
            )

    base_summary = _summary(base)
    treatment_summary = _summary(treatment)
    base_episode = _per_episode(base)
    treatment_episode = _per_episode(treatment)

    delta = {
        "accepted_actions_pct": 100
        * (
            treatment_summary["accepted_actions"]
            / base_summary["accepted_actions"]
            - 1
        ),
        "completion_tokens_pct": 100
        * (
            treatment_summary["completion_tokens"]
            / base_summary["completion_tokens"]
            - 1
        ),
        "cost_pct": 100
        * (
            treatment_summary["cost_usd"]
            / base_summary["cost_usd"]
            - 1
        ),
        "episode_success_v02_pp": 100
        * (
            treatment_summary["episode_success_v02"] / 60
            - base_summary["episode_success_v02"] / 60
        ),
        "feasible_obligation_success_pp": 100
        * (
            treatment_summary["feasible_obligation_success"] / 60
            - base_summary["feasible_obligation_success"] / 60
        ),
        "latency_pct": 100
        * (
            treatment_summary["latency_ms"]
            / base_summary["latency_ms"]
            - 1
        ),
        "model_calls_pct": 100
        * (
            treatment_summary["model_calls"]
            / base_summary["model_calls"]
            - 1
        ),
        "obligation_resolution_pp": 100
        * (
            treatment_summary["resolved_obligations"]
            / treatment_summary["actionable_obligations"]
            - base_summary["resolved_obligations"]
            / base_summary["actionable_obligations"]
        ),
        "prompt_tokens_pct": 100
        * (
            treatment_summary["prompt_tokens"]
            / base_summary["prompt_tokens"]
            - 1
        ),
        "terminal_feasible_pp": 100
        * (
            treatment_summary["terminal_feasible"] / 60
            - base_summary["terminal_feasible"] / 60
        ),
        "total_tokens_pct": 100
        * (
            treatment_summary["total_tokens"]
            / base_summary["total_tokens"]
            - 1
        ),
    }

    react_metrics = [record["policy_metrics"] for record in treatment]
    durable_steps = [
        step
        for record in transcript_records
        for step in record["react_transcript"]
    ]
    react_steps = len(durable_steps)
    thought_chars = sum(
        len(step["thought_summary"]) for step in durable_steps
    )

    return {
        "cluster_bootstrap": {
            "95pct_ci": _bootstrap(base_episode, treatment_episode),
            "cluster": "episode_id",
            "resamples": BOOTSTRAP_RESAMPLES,
            "sampler": BOOTSTRAP_SAMPLER,
            "seed": BOOTSTRAP_SEED,
        },
        "context_compiled": base_summary,
        "decision": {
            "inclusion_gate": None,
            "interpretation": (
                "Report as an external comparator; do not promote into "
                "ProcureHarness solely from development performance."
            ),
            "next_step": (
                "Freeze the development comparator set before any held-out "
                "evaluation."
            ),
        },
        "delta": delta,
        "episodes": 20,
        "experiment": "react-comparator-v0.1",
        "model": MODEL,
        "react": treatment_summary,
        "react_diagnostic": {
            "action_type_counts_context": base_summary[
                "action_type_counts"
            ],
            "action_type_counts_react": treatment_summary[
                "action_type_counts"
            ],
            "episode_effect_counts": {
                "episode_success_v02": _effect_counts(
                    base_episode, treatment_episode, "strict"
                ),
                "feasible_obligation_success": _effect_counts(
                    base_episode, treatment_episode, "obligation_success"
                ),
                "terminal_feasible": _effect_counts(
                    base_episode, treatment_episode, "terminal"
                ),
            },
            "react_steps_accepted": react_steps,
            "react_steps_proposed": sum(
                int(metrics["react_steps_proposed"])
                for metrics in react_metrics
            ),
            "runs_with_complete_react_steps": sum(
                int(metrics["react_steps_proposed"])
                == int(metrics["react_steps_accepted"])
                for metrics in react_metrics
            ),
            "thought_chars_max": max(
                (len(step["thought_summary"]) for step in durable_steps),
                default=0,
            ),
            "thought_chars_mean": thought_chars / react_steps,
            "thought_chars_total": thought_chars,
        },
        "repeats": 3,
        "role": "external_comparator",
        "runs_per_condition": 60,
        "schema_version": "0.1.0",
        "source_workflow_run_id": 36316652236,
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
        "source_workflow_run_id": 36316652236,
        "source_workflow_run_attempt": 1,
        "source_artifact_id": 10931387170,
        "source_artifact_name": "react-comparator-36316652236-1",
        "source_artifact_digest": (
            "sha256:d767d296d077a5e693bfc18e7429b35627bf5f5939283f"
            "98208372cc5f63e373"
        ),
        "benchmark_code_sha": (
            "9e0da4df909f271ac797898ea6daa9b6f9781a57"
        ),
        "execution_head_sha": (
            "8e3721d6f067613b9750f1b6aa7f954fd947a7db"
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
        raise ValueError("ReAct source provenance mismatch")

    if (
        source.get("verifier_script")
        != "scripts/verify_react_source_artifact_v01.py"
    ):
        raise ValueError("ReAct source artifact verifier is not declared")

    records = load_frozen_react_source(ROOT)
    check_provenance_entries(records)
    transcripts = load_frozen_react_transcripts(ROOT)
    if len(transcripts) != 60:
        raise ValueError("Durable ReAct transcript count mismatch")

    transcript_storage = manifest.get("transcript_storage") or {}
    if transcript_storage.get("path") != "transcript-source.b64":
        raise ValueError("Durable ReAct transcript path mismatch")
    if transcript_storage.get("compressed_bytes") != 30180:
        raise ValueError("Durable ReAct transcript byte count mismatch")
    if transcript_storage.get("compressed_sha256") != (
        "a7cbe4277c70abe62d157df683efa34a58bb29cc39eeb951e0d253353b7e7456"
    ):
        raise ValueError("Durable ReAct transcript digest mismatch")

    comparison = manifest["comparison"]
    payload = COMPARISON_PATH.read_bytes()
    if (
        len(payload) != comparison["bytes"]
        or sha256(payload).hexdigest() != comparison["sha256"]
    ):
        raise ValueError("ReAct comparison manifest mismatch")


def main() -> None:
    check_manifest()
    expected = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
    actual = build_comparison()
    _close(actual, expected)
    delta = actual["delta"]
    print("ReAct matched comparator audit passed.")
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
