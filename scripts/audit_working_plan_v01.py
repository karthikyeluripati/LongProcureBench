"""Audit the frozen maintained-working-plan experiment against context compilation."""
from __future__ import annotations

import base64
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import LongProcureBenchEvaluator
from frozen_context_compiled_v01 import load_frozen_context_compiled_source, reconstruct_actions as reconstruct_context_actions
from frozen_working_plan_v01 import (
    EPISODES, EXPECTED_COMPACTION_SHA256, EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256, EXPECTED_PARTS, EXPECTED_PROVENANCE_BYTES,
    EXPECTED_PROVENANCE_SHA256, EXPECTED_RAW_PROVENANCE_SHA256, EXPECTED_RUNS, MODEL,
    load_frozen_working_plan_source, reconstruct_actions as reconstruct_working_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "working-plan-reactive-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
COMPARISON_PATH = EVIDENCE_DIR / "comparison.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SAMPLER = "sha256-index-v1"


def _evaluate(records, reconstruct, evaluator):
    return [{**r, "evaluation": evaluator.evaluate_actions(r["episode_id"], reconstruct(r))} for r in records]


def _summary(records, *, plan=False):
    actions = Counter(); unresolved = Counter(); statuses = Counter()
    total = Counter(); run_means = []; plan_lengths = []; rejection_reasons = Counter()
    head_match = head_eligible = objective_changes = stop_changes = change_den = final_empty = 0
    for record in records:
        ev = record["evaluation"]; ob = ev["obligations"]; pm = record["policy_metrics"]
        statuses[record.get("status", "completed")] += 1
        total["terminal_feasible"] += int(ev["terminal_outcome"]["correct"])
        total["feasible_obligation_success"] += int(ev["feasible_obligation_success"])
        total["episode_success_v02"] += int(ev["episode_success_v02"])
        total["actionable_obligations"] += int(ob["actionable"]); total["resolved_obligations"] += int(ob["resolved"]); total["unresolved_obligations"] += int(ob["unresolved"])
        total["prompt_tokens"] += int(pm["prompt_tokens"]); total["completion_tokens"] += int(pm["completion_tokens"]); total["total_tokens"] += int(pm["total_tokens"]); total["model_calls"] += int(pm["model_calls_attempted"])
        total["latency_ms"] += float(pm["latency_ms"]); total["cost_usd"] += float(pm["cost_usd"])
        for d in record["decisions"]: actions[d["type"]] += 1
        for o in ob["results"]:
            if o.get("status") == "unresolved" and o.get("checkpoint"): unresolved[o["checkpoint"]] += 1
        if plan:
            total["plan_updates"] += int(pm["plan_updates"]); total["plan_rejections"] += int(pm["plan_rejections"]); total["runs_with_plan_rejections"] += int(pm["plan_rejections"] > 0)
            if pm.get("mean_plan_steps") is not None: run_means.append(float(pm["mean_plan_steps"]))
            trace = record["plan_trace"]; by_step = {t["accepted_state_step"]: t["next_plan"] for t in trace}; prev = None
            for t in trace:
                current_plan = t["next_plan"]; plan_lengths.append(len(current_plan["next_steps"]))
                if prev is not None:
                    change_den += 1; objective_changes += int(current_plan["objective"] != prev["objective"]); stop_changes += int(current_plan["stop_condition"] != prev["stop_condition"])
                prev = current_plan
            for index in range(1, len(record["decisions"])):
                p = by_step.get(index)
                if p and p["next_steps"]:
                    head_eligible += 1; head_match += int(p["next_steps"][0]["action_type"] == record["decisions"][index]["type"])
            for rejection in record["plan_rejection_trace"]: rejection_reasons[rejection["message"]] += 1
            final_empty += int(bool(record["final_plan"]) and record["final_plan"].get("next_steps") == [])
    out = dict(total); out["status_counts"] = dict(sorted(statuses.items())); out["action_type_counts"] = dict(sorted(actions.items())); out["unresolved_obligation_counts"] = dict(sorted(unresolved.items()))
    if plan:
        out.update({
            "mean_plan_steps": sum(run_means) / len(run_means),
            "update_weighted_mean_plan_steps": sum(plan_lengths) / len(plan_lengths),
            "max_plan_steps": max(plan_lengths),
            "plan_length_counts": {str(k): v for k, v in sorted(Counter(plan_lengths).items())},
            "next_action_head_match": {"matched": head_match, "eligible": head_eligible, "rate": head_match / head_eligible},
            "objective_change_rate": objective_changes / change_den,
            "stop_condition_change_rate": stop_changes / change_den,
            "final_empty_plan_runs": final_empty,
            "plan_rejection_reasons": dict(rejection_reasons),
        })
    return out


def _per_episode(records):
    grouped = defaultdict(list)
    for r in records: grouped[r["episode_id"]].append(r)
    result = {}
    for episode_id in EPISODES:
        rows = grouped[episode_id]
        if len(rows) != 3: raise ValueError(f"Expected 3 runs for {episode_id}; found {len(rows)}")
        result[episode_id] = {
            "terminal": sum(int(r["evaluation"]["terminal_outcome"]["correct"]) for r in rows) / 3,
            "obligation_success": sum(int(r["evaluation"]["feasible_obligation_success"]) for r in rows) / 3,
            "strict": sum(int(r["evaluation"]["episode_success_v02"]) for r in rows) / 3,
            "resolved": sum(int(r["evaluation"]["obligations"]["resolved"]) for r in rows),
            "actionable": sum(int(r["evaluation"]["obligations"]["actionable"]) for r in rows),
            "tokens": sum(int(r["policy_metrics"]["total_tokens"]) for r in rows),
            "cost": sum(float(r["policy_metrics"]["cost_usd"]) for r in rows),
            "latency": sum(float(r["policy_metrics"]["latency_ms"]) for r in rows),
            "calls": sum(int(r["policy_metrics"]["model_calls_attempted"]) for r in rows),
        }
    return result


def _quantile(values, probability):
    ordered = sorted(values); position = (len(ordered) - 1) * probability; low = math.floor(position); high = math.ceil(position)
    if low == high: return ordered[low]
    weight = position - low; return ordered[low] + weight * (ordered[high] - ordered[low])


def _bootstrap_index(resample, draw):
    payload = f"longprocurebench-bootstrap-v1:{BOOTSTRAP_SEED}:{resample}:{draw}".encode("utf-8")
    return int.from_bytes(sha256(payload).digest(), "big") % len(EPISODES)


def _bootstrap(context, working):
    values = {name: [] for name in ("terminal_feasible_pp", "feasible_obligation_success_pp", "episode_success_v02_pp", "obligation_resolution_pp", "total_tokens_pct", "cost_pct", "latency_pct", "model_calls_pct")}
    for resample in range(BOOTSTRAP_RESAMPLES):
        sampled = [_bootstrap_index(resample, draw) for draw in range(len(EPISODES))]
        for field, output in (("terminal", "terminal_feasible_pp"), ("obligation_success", "feasible_obligation_success_pp"), ("strict", "episode_success_v02_pp")):
            cm = sum(context[EPISODES[i]][field] for i in sampled) / len(EPISODES); wm = sum(working[EPISODES[i]][field] for i in sampled) / len(EPISODES)
            values[output].append(100 * (wm - cm))
        cr = sum(context[EPISODES[i]]["resolved"] for i in sampled); ca = sum(context[EPISODES[i]]["actionable"] for i in sampled); wr = sum(working[EPISODES[i]]["resolved"] for i in sampled); wa = sum(working[EPISODES[i]]["actionable"] for i in sampled)
        values["obligation_resolution_pp"].append(100 * (wr / wa - cr / ca))
        for field, output in (("tokens", "total_tokens_pct"), ("cost", "cost_pct"), ("latency", "latency_pct"), ("calls", "model_calls_pct")):
            ct = sum(context[EPISODES[i]][field] for i in sampled); wt = sum(working[EPISODES[i]][field] for i in sampled)
            values[output].append(100 * (wt / ct - 1))
    return {name: [_quantile(samples, 0.025), _quantile(samples, 0.975)] for name, samples in values.items()}


def evaluate_predeclared_gate(delta):
    tolerance = 1e-9
    obligation = delta["feasible_obligation_success_pp"] >= 5.0 - tolerance and delta["terminal_feasible_pp"] >= -5.0 - tolerance
    strict = delta["episode_success_v02_pp"] >= 5.0 - tolerance and delta["feasible_obligation_success_pp"] >= -2.0 - tolerance and delta["terminal_feasible_pp"] >= -5.0 - tolerance
    return {
        "passed": obligation or strict,
        "matched_condition": "feasible_obligation_gain" if obligation else "strict_gain_guardrailed" if strict else None,
        "feasible_obligation_gain": {"passed": obligation, "rule": "feasible-obligation success improves by >=5 pp AND terminal feasibility does not fall by more than 5 pp"},
        "strict_gain_guardrailed": {"passed": strict, "rule": "strict v0.2 success improves by >=5 pp AND feasible-obligation success does not fall by more than 2 pp AND terminal feasibility does not fall by more than 5 pp"},
    }


def build_comparison():
    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    context_records = _evaluate(load_frozen_context_compiled_source(ROOT), reconstruct_context_actions, evaluator)
    working_records = _evaluate(load_frozen_working_plan_source(ROOT), reconstruct_working_actions, evaluator)
    context = _summary(context_records); working = _summary(working_records, plan=True)
    delta = {
        "terminal_feasible_pp": 100 * (working["terminal_feasible"] / 60 - context["terminal_feasible"] / 60),
        "feasible_obligation_success_pp": 100 * (working["feasible_obligation_success"] / 60 - context["feasible_obligation_success"] / 60),
        "episode_success_v02_pp": 100 * (working["episode_success_v02"] / 60 - context["episode_success_v02"] / 60),
        "obligation_resolution_pp": 100 * (working["resolved_obligations"] / working["actionable_obligations"] - context["resolved_obligations"] / context["actionable_obligations"]),
        "prompt_tokens_pct": 100 * (working["prompt_tokens"] / context["prompt_tokens"] - 1),
        "completion_tokens_pct": 100 * (working["completion_tokens"] / context["completion_tokens"] - 1),
        "total_tokens_pct": 100 * (working["total_tokens"] / context["total_tokens"] - 1),
        "model_calls_pct": 100 * (working["model_calls"] / context["model_calls"] - 1),
        "latency_pct": 100 * (working["latency_ms"] / context["latency_ms"] - 1),
        "cost_pct": 100 * (working["cost_usd"] / context["cost_usd"] - 1),
    }
    ce = _per_episode(context_records); we = _per_episode(working_records)
    paired = {
        e: {
            "terminal_feasible_pp": 100 * (we[e]["terminal"] - ce[e]["terminal"]),
            "feasible_obligation_success_pp": 100 * (we[e]["obligation_success"] - ce[e]["obligation_success"]),
            "episode_success_v02_pp": 100 * (we[e]["strict"] - ce[e]["strict"]),
            "context_resolved_over_actionable": [ce[e]["resolved"], ce[e]["actionable"]],
            "working_plan_resolved_over_actionable": [we[e]["resolved"], we[e]["actionable"]],
            "total_tokens_pct": 100 * (we[e]["tokens"] / ce[e]["tokens"] - 1),
            "model_calls_pct": 100 * (we[e]["calls"] / ce[e]["calls"] - 1),
        }
        for e in EPISODES
    }
    return {
        "schema_version": "0.1.0", "experiment": "working-plan-reactive-v0.1", "model": MODEL,
        "runs_per_condition": 60, "episodes": 20, "repeats": 3, "source_workflow_run_id": 36243953648,
        "context_compiled": context, "working_plan": working, "delta": delta,
        "paired_episode_deltas": paired,
        "cluster_bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES, "sampler": BOOTSTRAP_SAMPLER, "cluster": "episode_id", "95pct_ci": _bootstrap(ce, we)},
        "predeclared_gate": evaluate_predeclared_gate(delta),
    }


def _canonical_line(row):
    return json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def _root(lines):
    return sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def _check_declared_replay_files(directory, expected_parts):
    actual = {p.name for p in directory.glob("replay-source*.b64") if p.is_file()}; expected = set(expected_parts)
    if actual != expected: raise ValueError(f"Frozen working-plan replay file set mismatch: expected={sorted(expected)}, actual={sorted(actual)}")


def check_source_provenance():
    payload = PROVENANCE_PATH.read_bytes()
    if len(payload) != EXPECTED_PROVENANCE_BYTES or sha256(payload).hexdigest() != EXPECTED_PROVENANCE_SHA256: raise ValueError("Working-plan source provenance digest mismatch")
    lines = [line for line in payload.decode("utf-8").splitlines() if line]
    if len(lines) != EXPECTED_RUNS: raise ValueError("Working-plan provenance row count mismatch")
    entries = {}; raw_lines = []
    for line in lines:
        fields = line.split("|")
        if len(fields) != 4: raise ValueError("Malformed working-plan provenance row")
        ei, rep, raw_sha, compact_sha = fields; key = (int(ei), int(rep))
        if key in entries: raise ValueError("Duplicate working-plan provenance key")
        entries[key] = (raw_sha, compact_sha); raw_lines.append(f"{ei}|{rep}|{raw_sha}")
    expected_keys = {(i, r) for i in range(1, 21) for r in range(1, 4)}
    if set(entries) != expected_keys: raise ValueError("Working-plan provenance grid mismatch")
    if _root(raw_lines) != EXPECTED_RAW_PROVENANCE_SHA256: raise ValueError("Working-plan raw source provenance root mismatch")
    encoded = "".join((EVIDENCE_DIR / name).read_text(encoding="utf-8").strip() for name in EXPECTED_PARTS)
    rows = [json.loads(line) for line in gzip.decompress(base64.b64decode(encoded, validate=True)).decode("utf-8").splitlines() if line.strip()]
    for row in rows:
        key = (row[0], row[1]); expected = entries.get(key)
        if expected is None or sha256(_canonical_line(row)).hexdigest() != expected[1]: raise ValueError("Compact working-plan row differs from artifact-derived compaction")


def check_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {"benchmark_code_sha": "aee79caf71dc3301f7ddc7db99f9d96289878403", "execution_head_sha": "e43b5a90685d1da5409637fe220df21f4ff61e8e", "model": MODEL, "records": 60, "episodes": 20, "repeats_per_episode": 3}
    for k, v in expected.items():
        if manifest.get(k) != v: raise ValueError(f"Working-plan manifest mismatch for {k}")
    artifact = manifest.get("source_artifact") or {}
    expected_artifact = {"workflow_run_id": 36243953648, "workflow_run_attempt": 1, "artifact_id": 10907187177, "artifact_name": "working-plan-reactive-36243953648-1", "artifact_digest": "sha256:924443c9bde20b687a2a3b9fe0c8058f8a224604d8532d6c325c6a9c89fd6c9b", "artifact_bytes": 280188}
    for k, v in expected_artifact.items():
        if artifact.get(k) != v: raise ValueError(f"Working-plan manifest artifact mismatch for {k}")
    storage = manifest.get("storage") or {}
    if storage.get("parts") != list(EXPECTED_PARTS) or storage.get("compressed_bytes") != EXPECTED_COMPRESSED_BYTES or storage.get("compressed_sha256") != EXPECTED_COMPRESSED_SHA256: raise ValueError("Working-plan replay storage mismatch")
    _check_declared_replay_files(EVIDENCE_DIR, EXPECTED_PARTS)
    sv = manifest.get("source_verification") or {}
    expected_sv = {"verifier_script": "scripts/verify_working_plan_source_artifact_v01.py", "selected_compaction_sha256": EXPECTED_COMPACTION_SHA256, "raw_provenance_sha256": EXPECTED_RAW_PROVENANCE_SHA256, "record_provenance_path": "source-provenance.txt", "record_provenance_bytes": EXPECTED_PROVENANCE_BYTES, "record_provenance_sha256": EXPECTED_PROVENANCE_SHA256, "provenance_line_format": "episode_index|repeat|sha256(exact raw run JSON bytes)|sha256(canonical compact record line)"}
    for k, v in expected_sv.items():
        if sv.get(k) != v: raise ValueError(f"Working-plan source verification mismatch for {k}")
    comp = manifest.get("comparison") or {}; payload = COMPARISON_PATH.read_bytes()
    for k, v in {"path":"comparison.json","bootstrap_seed":BOOTSTRAP_SEED,"bootstrap_resamples":BOOTSTRAP_RESAMPLES,"bootstrap_cluster":"episode_id","bootstrap_sampler":BOOTSTRAP_SAMPLER}.items():
        if comp.get(k) != v: raise ValueError(f"Working-plan comparison manifest mismatch for {k}")
    if len(payload) != comp.get("bytes") or sha256(payload).hexdigest() != comp.get("sha256"): raise ValueError("Working-plan comparison digest mismatch")


def _close(actual, expected, path="root"):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected): raise ValueError(f"Comparison shape mismatch at {path}")
        for k in expected: _close(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected): raise ValueError(f"Comparison list mismatch at {path}")
        for i, v in enumerate(expected): _close(actual[i], v, f"{path}[{i}]")
    elif isinstance(expected, float):
        if not math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-9): raise ValueError(f"Comparison numeric drift at {path}: expected={expected}, actual={actual}")
    elif actual != expected: raise ValueError(f"Comparison drift at {path}: expected={expected!r}, actual={actual!r}")


def check_frozen_comparison():
    expected = json.loads(COMPARISON_PATH.read_text(encoding="utf-8")); actual = build_comparison(); _close(actual, expected); return actual


def main():
    check_manifest(); check_source_provenance(); comparison = check_frozen_comparison(); d = comparison["delta"]
    print("Maintained working-plan matched audit passed.")
    print("terminal={:+.1f}pp obligation_success={:+.1f}pp strict={:+.1f}pp tokens={:+.1f}% calls={:+.1f}% gate={}".format(d["terminal_feasible_pp"], d["feasible_obligation_success_pp"], d["episode_success_v02_pp"], d["total_tokens_pct"], d["model_calls_pct"], comparison["predeclared_gate"]["passed"]))

if __name__ == "__main__": main()
