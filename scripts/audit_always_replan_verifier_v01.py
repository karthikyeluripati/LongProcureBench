"""Audit frozen always-replan + pre-terminal-verifier evidence."""
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
from frozen_always_replan_verifier_v01 import (
    EPISODES,
    MODEL,
    load_frozen_always_replan_verifier_source,
    reconstruct_actions as reconstruct_treatment_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "always-replan-verifier-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
COMPARISON_PATH = EVIDENCE_DIR / "comparison.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SAMPLER = "sha256-index-v1"


def _evaluate(records, reconstruct: Callable, evaluator):
    out = []
    for record in records:
        evaluation = evaluator.evaluate_actions(record["episode_id"], reconstruct(record))
        out.append({**record, "evaluation": evaluation})
    return out


def _summary(records):
    actions = Counter(); statuses = Counter()
    terminal = obligation_success = strict = actionable = resolved = unresolved = 0
    prompt = completion = total_tokens = calls = accepted = 0
    latency = cost = 0.0
    for record in records:
        ev = record["evaluation"]; ob = ev["obligations"]
        statuses[record.get("status", "completed")] += 1
        terminal += int(ev["terminal_outcome"]["correct"])
        obligation_success += int(ev["feasible_obligation_success"])
        strict += int(ev["episode_success_v02"])
        actionable += int(ob["actionable"]); resolved += int(ob["resolved"]); unresolved += int(ob["unresolved"])
        for decision in record["decisions"]: actions[decision["type"]] += 1
        accepted += len(record["decisions"])
        m = record["policy_metrics"]
        prompt += int(m["prompt_tokens"]); completion += int(m["completion_tokens"]); total_tokens += int(m["total_tokens"])
        calls += int(m["model_calls_attempted"]); latency += float(m["latency_ms"]); cost += float(m["cost_usd"])
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
        "accepted_actions": accepted,
        "status_counts": dict(sorted(statuses.items())),
        "action_type_counts": dict(sorted(actions.items())),
    }


def _unresolved_counts(records):
    counts = Counter()
    for record in records:
        for item in record["evaluation"]["obligations"]["results"]:
            if item.get("actionable") and not item.get("resolved"):
                counts[item["checkpoint"]] += 1
    return dict(sorted(counts.items()))


def _per_episode(records):
    grouped = defaultdict(list)
    for record in records: grouped[record["episode_id"]].append(record)
    result = {}
    for episode_id in EPISODES:
        rows = grouped[episode_id]
        if len(rows) != 3: raise ValueError(f"Expected 3 runs for {episode_id}")
        result[episode_id] = {
            "terminal": sum(int(r["evaluation"]["terminal_outcome"]["correct"]) for r in rows) / 3,
            "obligation_success": sum(int(r["evaluation"]["feasible_obligation_success"]) for r in rows) / 3,
            "strict": sum(int(r["evaluation"]["episode_success_v02"]) for r in rows) / 3,
            "resolved": sum(int(r["evaluation"]["obligations"]["resolved"]) for r in rows),
            "actionable": sum(int(r["evaluation"]["obligations"]["actionable"]) for r in rows),
            "actions": sum(len(r["decisions"]) for r in rows),
            "calls": sum(int(r["policy_metrics"]["model_calls_attempted"]) for r in rows),
            "tokens": sum(int(r["policy_metrics"]["total_tokens"]) for r in rows),
            "cost": sum(float(r["policy_metrics"]["cost_usd"]) for r in rows),
            "latency": sum(float(r["policy_metrics"]["latency_ms"]) for r in rows),
        }
    return result


def _quantile(values, p):
    values = sorted(values); pos = (len(values) - 1) * p; lo = math.floor(pos); hi = math.ceil(pos)
    if lo == hi: return values[lo]
    return values[lo] + (pos - lo) * (values[hi] - values[lo])


def _index(resample, draw):
    payload = f"longprocurebench-bootstrap-v1:{BOOTSTRAP_SEED}:{resample}:{draw}".encode()
    return int.from_bytes(sha256(payload).digest(), "big") % len(EPISODES)


def _bootstrap(base, treatment):
    names = (
        "terminal_feasible_pp", "feasible_obligation_success_pp", "episode_success_v02_pp",
        "obligation_resolution_pp", "accepted_actions_pct", "model_calls_pct", "total_tokens_pct", "cost_pct", "latency_pct",
    )
    values = {name: [] for name in names}
    for resample in range(BOOTSTRAP_RESAMPLES):
        sample = [EPISODES[_index(resample, draw)] for draw in range(len(EPISODES))]
        for field, out in (("terminal", "terminal_feasible_pp"), ("obligation_success", "feasible_obligation_success_pp"), ("strict", "episode_success_v02_pp")):
            bm = sum(base[e][field] for e in sample) / len(EPISODES)
            tm = sum(treatment[e][field] for e in sample) / len(EPISODES)
            values[out].append(100 * (tm - bm))
        br = sum(base[e]["resolved"] for e in sample); ba = sum(base[e]["actionable"] for e in sample)
        tr = sum(treatment[e]["resolved"] for e in sample); ta = sum(treatment[e]["actionable"] for e in sample)
        values["obligation_resolution_pp"].append(100 * (tr / ta - br / ba))
        for field, out in (("actions", "accepted_actions_pct"), ("calls", "model_calls_pct"), ("tokens", "total_tokens_pct"), ("cost", "cost_pct"), ("latency", "latency_pct")):
            b = sum(base[e][field] for e in sample); t = sum(treatment[e][field] for e in sample)
            values[out].append(100 * (t / b - 1))
    return {name: [_quantile(samples, .025), _quantile(samples, .975)] for name, samples in values.items()}


def _mechanism(records, base_records):
    proposals = Counter(); rejected = Counter(); approved = Counter(); bounded = 0
    for record in records:
        d = record["diagnostics"]
        proposals.update(d["terminal_proposal_type_counts"])
        rejected.update(d["rejected_verifier_recommendation_counts"])
        approved.update(d["approved_verifier_recommendation_counts"])
        bounded += int(d["verification_traces_with_bounded_issues"])
    base_ep = _per_episode(base_records); tr_ep = _per_episode(records)
    improved = worsened = tied = 0
    for ep in EPISODES:
        delta = tr_ep[ep]["obligation_success"] - base_ep[ep]["obligation_success"]
        if delta > 0: improved += 1
        elif delta < 0: worsened += 1
        else: tied += 1
    verifier_calls = sum(proposals.values()); rejections = sum(rejected.values())
    return {
        "verifier_terminal_proposals": verifier_calls,
        "verifier_approvals": sum(approved.values()),
        "verifier_rejections": rejections,
        "verifier_rejection_rate": rejections / verifier_calls,
        "terminal_proposal_type_counts": dict(sorted(proposals.items())),
        "rejected_verifier_recommendation_counts": dict(sorted(rejected.items())),
        "approved_verifier_recommendation_counts": dict(sorted(approved.items())),
        "call_role_counts": {
            "action": sum(r["policy_metrics"]["action_calls"] for r in records),
            "planner": sum(r["policy_metrics"]["planner_calls"] for r in records),
            "repair_action": sum(r["policy_metrics"]["repair_calls"] for r in records),
            "verifier": sum(r["policy_metrics"]["verifier_calls"] for r in records),
        },
        "verification_traces_with_bounded_issues": bounded,
        "unresolved_obligation_counts_context": _unresolved_counts(base_records),
        "unresolved_obligation_counts_treatment": _unresolved_counts(records),
        "episode_obligation_success_effect_counts": {"improved": improved, "worsened": worsened, "tied": tied},
    }


def _gate(delta):
    tolerance = 1e-9
    b1 = delta["feasible_obligation_success_pp"] >= 5 - tolerance and delta["terminal_feasible_pp"] >= -5 - tolerance
    b2 = delta["episode_success_v02_pp"] >= 5 - tolerance and delta["feasible_obligation_success_pp"] >= -2 - tolerance and delta["terminal_feasible_pp"] >= -5 - tolerance
    return {
        "passed": b1 or b2,
        "matched_condition": "branch1" if b1 else ("branch2" if b2 else None),
        "branch1": {"passed": b1, "rule": "feasible-obligation success improves by >=5 pp while terminal feasibility does not fall by more than 5 pp"},
        "branch2": {"passed": b2, "rule": "strict v0.2 success improves by >=5 pp while feasible-obligation success does not fall by more than 2 pp and terminal feasibility does not fall by more than 5 pp"},
    }


def build_comparison():
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    base = _evaluate(load_frozen_context_compiled_source(ROOT), reconstruct_context_actions, evaluator)
    treatment = _evaluate(load_frozen_always_replan_verifier_source(ROOT), reconstruct_treatment_actions, evaluator)
    b = _summary(base); t = _summary(treatment)
    delta = {
        "terminal_feasible_pp": 100 * (t["terminal_feasible"] / 60 - b["terminal_feasible"] / 60),
        "feasible_obligation_success_pp": 100 * (t["feasible_obligation_success"] / 60 - b["feasible_obligation_success"] / 60),
        "episode_success_v02_pp": 100 * (t["episode_success_v02"] / 60 - b["episode_success_v02"] / 60),
        "obligation_resolution_pp": 100 * (t["resolved_obligations"] / t["actionable_obligations"] - b["resolved_obligations"] / b["actionable_obligations"]),
        "prompt_tokens_pct": 100 * (t["prompt_tokens"] / b["prompt_tokens"] - 1),
        "completion_tokens_pct": 100 * (t["completion_tokens"] / b["completion_tokens"] - 1),
        "total_tokens_pct": 100 * (t["total_tokens"] / b["total_tokens"] - 1),
        "model_calls_pct": 100 * (t["model_calls"] / b["model_calls"] - 1),
        "accepted_actions_pct": 100 * (t["accepted_actions"] / b["accepted_actions"] - 1),
        "latency_pct": 100 * (t["latency_ms"] / b["latency_ms"] - 1),
        "cost_pct": 100 * (t["cost_usd"] / b["cost_usd"] - 1),
    }
    return {
        "schema_version": "0.1.0",
        "experiment": "always-replan-verifier-v0.1",
        "source_workflow_run_id": 36286064411,
        "model": MODEL,
        "runs_per_condition": 60,
        "episodes": 20,
        "repeats": 3,
        "context_compiled": b,
        "always_replan_verifier": t,
        "delta": delta,
        "cluster_bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES, "sampler": BOOTSTRAP_SAMPLER, "cluster": "episode_id", "95pct_ci": _bootstrap(_per_episode(base), _per_episode(treatment))},
        "predeclared_gate": _gate(delta),
        "mechanism_diagnostic": _mechanism(treatment, base),
    }


def _close(actual: Any, expected: Any, path="root"):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected): raise ValueError(f"Comparison shape mismatch at {path}")
        for k in expected: _close(actual[k], expected[k], f"{path}.{k}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected): raise ValueError(f"Comparison list mismatch at {path}")
        for i, v in enumerate(expected): _close(actual[i], v, f"{path}[{i}]")
        return
    if isinstance(expected, float):
        if not math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-9): raise ValueError(f"Comparison numeric drift at {path}: expected={expected}, actual={actual}")
        return
    if actual != expected: raise ValueError(f"Comparison drift at {path}: expected={expected!r}, actual={actual!r}")


def check_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        "source_workflow_run_id": 36286064411,
        "source_workflow_run_attempt": 1,
        "source_artifact_id": 10924959171,
        "source_artifact_name": "always-replan-verifier-36286064411-1",
        "source_artifact_digest": "sha256:8e08847b3fb9725703adb7d0d4046e88a92fdc6ead9f0f7226fe8ccdabf7f7df",
        "benchmark_code_sha": "6fa855bf33698aa0380c794dcba4a3ab15b07e89",
        "execution_head_sha": "2c66dd7f79a04a99d0d29afee46dd14095b7a7a6",
        "records": 60,
        "episodes": 20,
        "repeats_per_episode": 3,
    }
    for key, value in expected.items():
        if manifest.get(key) != value: raise ValueError(f"Manifest mismatch for {key}")
    storage = manifest["storage"]
    if storage.get("compressed_bytes") != 51107 or storage.get("compressed_sha256") != "494a9cf48d868589b39e75a034f3e314c0c1f52be3636959a81981cd6085a4ab" or storage.get("compact_rows_sha256") != "e8e854bf0ba45176641a1d888fc8a4733f3b122c1fb031eb135d29f09054d380":
        raise ValueError("Replay storage manifest mismatch")
    provenance = PROVENANCE_PATH.read_bytes()
    source = manifest["source_verification"]
    if len(provenance) != source["record_provenance_bytes"] or sha256(provenance).hexdigest() != source["record_provenance_sha256"]:
        raise ValueError("Source provenance mismatch")
    payload = COMPARISON_PATH.read_bytes(); comp = manifest["comparison"]
    if len(payload) != comp["bytes"] or sha256(payload).hexdigest() != comp["sha256"]:
        raise ValueError("Comparison manifest mismatch")


def main():
    check_manifest()
    expected = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
    actual = build_comparison()
    _close(actual, expected)
    d = actual["delta"]
    print("Always-replan + verifier matched audit passed.")
    print("terminal={:+.1f}pp obligation_success={:+.1f}pp strict={:+.1f}pp tokens={:+.1f}% cost={:+.1f}%".format(d["terminal_feasible_pp"], d["feasible_obligation_success_pp"], d["episode_success_v02_pp"], d["total_tokens_pct"], d["cost_pct"]))


if __name__ == "__main__":
    main()
