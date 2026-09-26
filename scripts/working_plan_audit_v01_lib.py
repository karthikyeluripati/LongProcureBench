"""Audit helpers for the frozen maintained-working-plan experiment."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import base64
import gzip
import json
import math
from pathlib import Path
import re
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
from frozen_working_plan_v01 import (
    EPISODES,
    EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256,
    EXPECTED_PARTS,
    EXPECTED_PROVENANCE_BYTES,
    EXPECTED_PROVENANCE_SHA256,
    EXPECTED_REPEATS,
    EXPECTED_RUNS,
    EXPECTED_SELECTED_COMPACTION_SHA256,
    EXPECTED_SELECTED_RAW_PROVENANCE_SHA256,
    MODEL,
    load_frozen_working_plan_source,
    reconstruct_actions as reconstruct_working_plan_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "working-plan-reactive-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
COMPARISON_PATH = EVIDENCE_DIR / "comparison.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SAMPLER = "sha256-index-v1"
MEMBER_RE = re.compile(
    r"(?:^|/)(?P<episode>electrical-[^/]+)/run-(?P<repeat>[0-9]{3})[.]json$"
)


def _evaluate_records(
    records: list[dict[str, Any]],
    reconstruct: Callable[[dict[str, Any]], list[dict[str, Any]]],
    evaluator: LongProcureBenchEvaluator,
) -> list[dict[str, Any]]:
    out = []
    for record in records:
        evaluation = evaluator.evaluate_actions(
            record["episode_id"], reconstruct(record)
        )
        out.append({**record, "evaluation": evaluation})
    return out


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    actions: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    terminal = obligation_success = strict = 0
    actionable = resolved = unresolved = 0
    prompt = completion = total_tokens = calls = 0
    latency = cost = 0.0

    for record in records:
        evaluation = record["evaluation"]
        obligations = evaluation["obligations"]
        statuses[record.get("status", "completed")] += 1
        terminal += int(evaluation["terminal_outcome"]["correct"])
        obligation_success += int(evaluation["feasible_obligation_success"])
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
        "status_counts": dict(sorted(statuses.items())),
        "action_type_counts": dict(sorted(actions.items())),
    }


def _unresolved_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        for item in record["evaluation"]["obligations"]["results"]:
            if item.get("actionable") and not item.get("resolved"):
                counts[item["checkpoint"]] += 1
    return dict(sorted(counts.items()))


def _per_episode(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["episode_id"]].append(record)

    result: dict[str, dict[str, float]] = {}
    for episode_id in EPISODES:
        rows = grouped[episode_id]
        if len(rows) != EXPECTED_REPEATS:
            raise ValueError(
                f"Expected {EXPECTED_REPEATS} runs for {episode_id}; found {len(rows)}"
            )
        result[episode_id] = {
            "terminal": sum(
                int(r["evaluation"]["terminal_outcome"]["correct"])
                for r in rows
            ) / EXPECTED_REPEATS,
            "obligation_success": sum(
                int(r["evaluation"]["feasible_obligation_success"])
                for r in rows
            ) / EXPECTED_REPEATS,
            "strict": sum(
                int(r["evaluation"]["episode_success_v02"])
                for r in rows
            ) / EXPECTED_REPEATS,
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
            "calls": sum(
                int(r["policy_metrics"]["model_calls_attempted"])
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
    payload = (
        f"longprocurebench-bootstrap-v1:"
        f"{BOOTSTRAP_SEED}:{resample}:{draw}"
    ).encode("utf-8")
    return int.from_bytes(sha256(payload).digest(), "big") % len(EPISODES)


def _bootstrap(
    baseline: dict[str, dict[str, float]],
    treatment: dict[str, dict[str, float]],
) -> dict[str, list[float]]:
    values = {
        name: []
        for name in (
            "terminal_feasible_pp",
            "feasible_obligation_success_pp",
            "episode_success_v02_pp",
            "obligation_resolution_pp",
            "total_tokens_pct",
            "model_calls_pct",
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
            baseline_mean = sum(
                baseline[EPISODES[index]][field] for index in sampled
            ) / len(EPISODES)
            treatment_mean = sum(
                treatment[EPISODES[index]][field] for index in sampled
            ) / len(EPISODES)
            values[output_name].append(
                100 * (treatment_mean - baseline_mean)
            )

        baseline_resolved = sum(
            baseline[EPISODES[index]]["resolved"] for index in sampled
        )
        baseline_actionable = sum(
            baseline[EPISODES[index]]["actionable"] for index in sampled
        )
        treatment_resolved = sum(
            treatment[EPISODES[index]]["resolved"] for index in sampled
        )
        treatment_actionable = sum(
            treatment[EPISODES[index]]["actionable"] for index in sampled
        )
        values["obligation_resolution_pp"].append(
            100 * (
                treatment_resolved / treatment_actionable
                - baseline_resolved / baseline_actionable
            )
        )

        for field, output_name in (
            ("tokens", "total_tokens_pct"),
            ("calls", "model_calls_pct"),
            ("cost", "cost_pct"),
            ("latency", "latency_pct"),
        ):
            baseline_total = sum(
                baseline[EPISODES[index]][field] for index in sampled
            )
            treatment_total = sum(
                treatment[EPISODES[index]][field] for index in sampled
            )
            values[output_name].append(
                100 * (treatment_total / baseline_total - 1)
            )

    return {
        name: [_quantile(samples, 0.025), _quantile(samples, 0.975)]
        for name, samples in values.items()
    }


def evaluate_predeclared_gate(delta: dict[str, float]) -> dict[str, Any]:
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
                "2 pp AND terminal feasibility does not fall by more than 5 pp"
            ),
        },
    }


def _plan_diagnostics(records: list[dict[str, Any]]) -> dict[str, Any]:
    length_counts: Counter[int] = Counter()
    rejection_messages: Counter[str] = Counter()
    total_updates = total_rejections = runs_with_rejections = 0
    first_step_opportunities = action_type_matches = full_matches = 0
    empty_before_later_action = 0
    adjacent_updates = objective_changes = stop_changes = 0

    for record in records:
        decisions = record["decisions"]
        trace = record["plan_trace"]
        rejections = record["plan_rejection_trace"]
        total_updates += len(trace)
        total_rejections += len(rejections)
        runs_with_rejections += int(bool(rejections))
        for rejection in rejections:
            rejection_messages[rejection.get("message", "?")] += 1

        for row in trace:
            step = int(row["accepted_state_step"])
            steps = row["next_plan"]["next_steps"]
            length_counts[len(steps)] += 1
            if step < len(decisions) and not steps:
                empty_before_later_action += 1
            if step < len(decisions) and steps:
                first_step_opportunities += 1
                planned = steps[0]
                actual = decisions[step]
                action_match = planned["action_type"] == actual["type"]
                supplier_match = (
                    planned.get("supplier_id") == actual.get("supplier_id")
                )
                action_type_matches += int(action_match)
                full_matches += int(action_match and supplier_match)

        ordered = sorted(trace, key=lambda row: int(row["accepted_state_step"]))
        for previous, current in zip(ordered, ordered[1:]):
            adjacent_updates += 1
            objective_changes += int(
                previous["next_plan"]["objective"]
                != current["next_plan"]["objective"]
            )
            stop_changes += int(
                previous["next_plan"]["stop_condition"]
                != current["next_plan"]["stop_condition"]
            )

    total_plan_steps = sum(length * count for length, count in length_counts.items())
    return {
        "total_plan_updates": total_updates,
        "total_plan_rejections": total_rejections,
        "runs_with_plan_rejections": runs_with_rejections,
        "plan_length_counts": {
            str(length): count for length, count in sorted(length_counts.items())
        },
        "mean_plan_steps_per_update": total_plan_steps / total_updates,
        "max_plan_steps": max(length_counts, default=0),
        "accepted_plan_first_step_opportunities": first_step_opportunities,
        "accepted_plan_first_step_action_type_matches": action_type_matches,
        "accepted_plan_first_step_action_type_match_rate": (
            action_type_matches / first_step_opportunities
        ),
        "accepted_plan_first_step_action_and_supplier_matches": full_matches,
        "accepted_plan_first_step_action_and_supplier_match_rate": (
            full_matches / first_step_opportunities
        ),
        "accepted_empty_plan_before_later_action": empty_before_later_action,
        "adjacent_accepted_plan_updates": adjacent_updates,
        "objective_change_rate": objective_changes / adjacent_updates,
        "stop_condition_change_rate": stop_changes / adjacent_updates,
        "plan_rejection_message_counts": dict(sorted(rejection_messages.items())),
    }


def _paired_episode_delta(
    baseline: dict[str, dict[str, float]],
    treatment: dict[str, dict[str, float]],
) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, int]]]:
    paired: dict[str, dict[str, float | None]] = {}
    directions = {
        "terminal_feasible": {"improved": 0, "worsened": 0, "tied": 0},
        "feasible_obligation_success": {"improved": 0, "worsened": 0, "tied": 0},
        "episode_success_v02": {"improved": 0, "worsened": 0, "tied": 0},
    }
    for episode_id in EPISODES:
        base = baseline[episode_id]
        treat = treatment[episode_id]
        deltas = {
            "terminal_feasible_pp": 100 * (treat["terminal"] - base["terminal"]),
            "feasible_obligation_success_pp": 100 * (
                treat["obligation_success"] - base["obligation_success"]
            ),
            "episode_success_v02_pp": 100 * (treat["strict"] - base["strict"]),
            "obligation_resolution_pp": (
                100 * (
                    treat["resolved"] / treat["actionable"]
                    - base["resolved"] / base["actionable"]
                )
                if treat["actionable"] and base["actionable"]
                else None
            ),
            "total_tokens_pct": 100 * (treat["tokens"] / base["tokens"] - 1),
            "model_calls_pct": 100 * (treat["calls"] / base["calls"] - 1),
        }
        paired[episode_id] = deltas
        for key, field in (
            ("terminal_feasible", "terminal_feasible_pp"),
            ("feasible_obligation_success", "feasible_obligation_success_pp"),
            ("episode_success_v02", "episode_success_v02_pp"),
        ):
            value = float(deltas[field])
            bucket = "improved" if value > 0 else ("worsened" if value < 0 else "tied")
            directions[key][bucket] += 1
    return paired, directions


def build_comparison() -> dict[str, Any]:
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    context_source = load_frozen_context_compiled_source(ROOT)
    working_source = load_frozen_working_plan_source(ROOT)
    context_records = _evaluate_records(
        context_source, reconstruct_context_actions, evaluator
    )
    working_records = _evaluate_records(
        working_source, reconstruct_working_plan_actions, evaluator
    )
    context = _summarize(context_records)
    working = _summarize(working_records)
    delta = {
        "terminal_feasible_pp": 100 * (
            working["terminal_feasible"] / EXPECTED_RUNS
            - context["terminal_feasible"] / EXPECTED_RUNS
        ),
        "feasible_obligation_success_pp": 100 * (
            working["feasible_obligation_success"] / EXPECTED_RUNS
            - context["feasible_obligation_success"] / EXPECTED_RUNS
        ),
        "episode_success_v02_pp": 100 * (
            working["episode_success_v02"] / EXPECTED_RUNS
            - context["episode_success_v02"] / EXPECTED_RUNS
        ),
        "obligation_resolution_pp": 100 * (
            working["resolved_obligations"] / working["actionable_obligations"]
            - context["resolved_obligations"] / context["actionable_obligations"]
        ),
        "prompt_tokens_pct": 100 * (
            working["prompt_tokens"] / context["prompt_tokens"] - 1
        ),
        "completion_tokens_pct": 100 * (
            working["completion_tokens"] / context["completion_tokens"] - 1
        ),
        "total_tokens_pct": 100 * (
            working["total_tokens"] / context["total_tokens"] - 1
        ),
        "model_calls_pct": 100 * (
            working["model_calls"] / context["model_calls"] - 1
        ),
        "latency_pct": 100 * (
            working["latency_ms"] / context["latency_ms"] - 1
        ),
        "cost_pct": 100 * (working["cost_usd"] / context["cost_usd"] - 1),
    }
    context_by_episode = _per_episode(context_records)
    working_by_episode = _per_episode(working_records)
    paired, directions = _paired_episode_delta(
        context_by_episode, working_by_episode
    )
    return {
        "schema_version": "0.1.0",
        "experiment": "working-plan-reactive-v0.1",
        "source_workflow_run_id": 36243953648,
        "model": MODEL,
        "runs_per_condition": EXPECTED_RUNS,
        "episodes": len(EPISODES),
        "repeats": EXPECTED_REPEATS,
        "context_compiled": context,
        "working_plan": working,
        "delta": delta,
        "paired_episode_delta": paired,
        "paired_episode_direction_counts": directions,
        "cluster_bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "sampler": BOOTSTRAP_SAMPLER,
            "cluster": "episode_id",
            "95pct_ci": _bootstrap(context_by_episode, working_by_episode),
        },
        "predeclared_gate": evaluate_predeclared_gate(delta),
        "unresolved_obligation_counts": {
            "context_compiled": _unresolved_counts(context_records),
            "working_plan": _unresolved_counts(working_records),
        },
        "plan_diagnostics": _plan_diagnostics(working_records),
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
        if not math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError(
                f"Comparison numeric drift at {path}: expected={expected}, actual={actual}"
            )
        return
    if actual != expected:
        raise ValueError(
            f"Comparison drift at {path}: expected={expected!r}, actual={actual!r}"
        )


def _check_declared_replay_files(directory: Path, expected_parts: tuple[str, ...]) -> None:
    actual = {
        path.name
        for path in directory.glob("replay-source*.b64")
        if path.is_file()
    }
    expected = set(expected_parts)
    if actual != expected:
        raise ValueError(
            "Frozen working-plan replay file set mismatch: "
            f"expected={sorted(expected)}, actual={sorted(actual)}"
        )


def _canonical_compact_line(row: Any) -> bytes:
    return (
        json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        .encode("utf-8")
        + b"\n"
    )


def _provenance_root(lines: list[str]) -> str:
    return sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def check_source_provenance() -> None:
    payload = PROVENANCE_PATH.read_bytes()
    if len(payload) != EXPECTED_PROVENANCE_BYTES:
        raise ValueError("Working-plan source provenance size mismatch")
    if sha256(payload).hexdigest() != EXPECTED_PROVENANCE_SHA256:
        raise ValueError("Working-plan source provenance digest mismatch")

    lines = [line for line in payload.decode("utf-8").splitlines() if line]
    if len(lines) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} provenance rows; found {len(lines)}"
        )
    entries: dict[tuple[int, int], tuple[str, str, str]] = {}
    raw_lines: list[str] = []
    hexdigits = set("0123456789abcdef")
    for line in lines:
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError("Malformed working-plan source provenance row")
        episode_text, repeat_text, member, raw_sha, compact_sha = fields
        episode_index = int(episode_text)
        repeat = int(repeat_text)
        if not 1 <= episode_index <= len(EPISODES):
            raise ValueError("Invalid provenance episode index")
        if not 1 <= repeat <= EXPECTED_REPEATS:
            raise ValueError("Invalid provenance repeat")
        match = MEMBER_RE.search(member)
        if (
            match is None
            or match.group("episode") != EPISODES[episode_index - 1]
            or int(match.group("repeat")) != repeat
        ):
            raise ValueError("Working-plan provenance member/key mismatch")
        for digest in (raw_sha, compact_sha):
            if len(digest) != 64 or any(ch not in hexdigits for ch in digest):
                raise ValueError("Malformed working-plan provenance SHA-256")
        key = (episode_index, repeat)
        if key in entries:
            raise ValueError("Duplicate working-plan provenance key")
        entries[key] = (member, raw_sha, compact_sha)
        raw_lines.append(f"{episode_index}|{repeat}|{member}|{raw_sha}")

    expected_keys = {
        (episode_index, repeat)
        for episode_index in range(1, len(EPISODES) + 1)
        for repeat in range(1, EXPECTED_REPEATS + 1)
    }
    if set(entries) != expected_keys:
        raise ValueError("Working-plan provenance grid mismatch")
    if _provenance_root(raw_lines) != EXPECTED_SELECTED_RAW_PROVENANCE_SHA256:
        raise ValueError("Working-plan raw source provenance root mismatch")

    encoded = "".join(
        (EVIDENCE_DIR / name).read_text(encoding="utf-8").strip()
        for name in EXPECTED_PARTS
    )
    compressed = base64.b64decode(encoded, validate=True)
    rows = [
        json.loads(line)
        for line in gzip.decompress(compressed).decode("utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        episode_index, repeat = row[:2]
        expected = entries.get((episode_index, repeat))
        if expected is None:
            raise ValueError("Compact working-plan row missing provenance entry")
        compact_sha = sha256(_canonical_compact_line(row)).hexdigest()
        if compact_sha != expected[2]:
            raise ValueError(
                "Compact working-plan row differs from artifact-derived compaction"
            )


def check_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        "source_workflow_run_id": 36243953648,
        "source_workflow_run_attempt": 1,
        "source_artifact_id": 10907187177,
        "source_artifact_name": "working-plan-reactive-36243953648-1",
        "source_artifact_digest": (
            "sha256:924443c9bde20b687a2a3b9fe0c8058f8a224604d8532d6c325c6a9c89fd6c9b"
        ),
        "source_artifact_bytes": 280188,
        "benchmark_code_sha": "aee79caf71dc3301f7ddc7db99f9d96289878403",
        "execution_head_sha": "e43b5a90685d1da5409637fe220df21f4ff61e8e",
        "execution_head_delta": "workflow trigger only",
        "model": MODEL,
        "records": EXPECTED_RUNS,
        "episodes": len(EPISODES),
        "repeats_per_episode": EXPECTED_REPEATS,
        "status_counts": {"completed": EXPECTED_RUNS},
        "usage_complete_runs": EXPECTED_RUNS,
        "known_cost_runs": EXPECTED_RUNS,
        "evaluation_version": "0.2.0",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Working-plan manifest mismatch for {key}")

    expected_episode_index = {
        str(index): episode_id
        for index, episode_id in enumerate(EPISODES, start=1)
    }
    if manifest.get("episode_index") != expected_episode_index:
        raise ValueError("Working-plan manifest episode index mismatch")

    storage = manifest.get("storage") or {}
    expected_storage = {
        "parts": list(EXPECTED_PARTS),
        "compressed_bytes": EXPECTED_COMPRESSED_BYTES,
        "compressed_sha256": EXPECTED_COMPRESSED_SHA256,
    }
    for key, value in expected_storage.items():
        if storage.get(key) != value:
            raise ValueError(f"Working-plan manifest replay mismatch for {key}")
    _check_declared_replay_files(EVIDENCE_DIR, EXPECTED_PARTS)

    source = manifest.get("source_verification") or {}
    expected_source = {
        "verifier_script": "scripts/verify_working_plan_source_artifact_v01.py",
        "selected_compaction_sha256": EXPECTED_SELECTED_COMPACTION_SHA256,
        "selected_raw_provenance_sha256": EXPECTED_SELECTED_RAW_PROVENANCE_SHA256,
        "record_provenance_path": "source-provenance.txt",
        "record_provenance_bytes": EXPECTED_PROVENANCE_BYTES,
        "record_provenance_sha256": EXPECTED_PROVENANCE_SHA256,
        "provenance_line_format": (
            "episode_index|repeat|artifact_member_path|"
            "sha256(exact raw run JSON bytes)|"
            "sha256(canonical compact record line)"
        ),
    }
    for key, value in expected_source.items():
        if source.get(key) != value:
            raise ValueError(f"Working-plan source verification mismatch for {key}")
    if not (ROOT / source["verifier_script"]).is_file():
        raise ValueError("Working-plan source-artifact verifier is missing")

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
            raise ValueError(f"Working-plan comparison manifest mismatch for {key}")
    payload = COMPARISON_PATH.read_bytes()
    if len(payload) != comparison.get("bytes"):
        raise ValueError("Frozen working-plan comparison size mismatch")
    if sha256(payload).hexdigest() != comparison.get("sha256"):
        raise ValueError("Frozen working-plan comparison digest mismatch")


def check_frozen_comparison() -> dict[str, Any]:
    expected = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
    actual = build_comparison()
    _close(actual, expected)
    return actual


def run_audit() -> None:
    check_manifest()
    check_source_provenance()
    comparison = check_frozen_comparison()
    delta = comparison["delta"]
    gate = comparison["predeclared_gate"]
    print("Working-plan matched audit passed.")
    print(
        "terminal={:+.1f}pp obligation_success={:+.1f}pp strict={:+.1f}pp "
        "tokens={:+.1f}% cost={:+.1f}% gate={}".format(
            delta["terminal_feasible_pp"],
            delta["feasible_obligation_success_pp"],
            delta["episode_success_v02_pp"],
            delta["total_tokens_pct"],
            delta["cost_pct"],
            gate["passed"],
        )
    )
