"""Audit frozen Coverage + Repair confirmatory development evidence."""
from __future__ import annotations

from collections import Counter
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
from frozen_coverage_repair_confirmatory_v01 import (
    EPISODES,
    EXPECTED_COMPACT_ROWS_BYTES,
    EXPECTED_COMPACT_ROWS_SHA256,
    EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256,
    load_frozen_coverage_repair_source,
    reconstruct_actions as reconstruct_coverage_actions,
)
from frozen_react_comparator_v01 import (
    load_frozen_react_source,
    reconstruct_actions as reconstruct_react_actions,
)

EVIDENCE_DIR = ROOT / "evidence" / "coverage-repair-confirmatory-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
RESULTS_PATH = EVIDENCE_DIR / "results.json"


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
    terminal = obligation = strict = economic = 0
    actionable = resolved = unresolved_total = 0
    accepted = calls = prompt = completion = total_tokens = 0
    latency = cost = 0.0
    interventions = Counter()

    for record in records:
        evaluation = record["evaluation"]
        obligations = evaluation["obligations"]
        metrics = record["policy_metrics"]
        terminal += int(evaluation["terminal_outcome"]["correct"])
        obligation += int(evaluation["feasible_obligation_success"])
        strict += int(evaluation["episode_success_v02"])
        economic += int(evaluation["economic_objective"]["satisfied"])
        actionable += int(obligations["actionable"])
        resolved += int(obligations["resolved"])
        unresolved_total += int(obligations["unresolved"])

        accepted += len(record["decisions"])
        for decision in record["decisions"]:
            actions[decision["type"]] += 1
        for row in obligations.get("results") or []:
            if row.get("status") == "unresolved" and row.get("checkpoint"):
                unresolved[row["checkpoint"]] += 1

        calls += int(metrics["model_calls_attempted"])
        prompt += int(metrics["prompt_tokens"])
        completion += int(metrics["completion_tokens"])
        total_tokens += int(metrics["total_tokens"])
        latency += float(metrics["latency_ms"])
        cost += float(metrics["cost_usd"])
        for key in (
            "coverage_repair_interventions",
            "coverage_forced_rfqs",
            "coverage_forced_followups",
            "coverage_forced_answers",
        ):
            if key in metrics:
                interventions[key] += int(metrics[key])

    return {
        "runs": len(records),
        "terminal_feasible": terminal,
        "feasible_obligation_success": obligation,
        "strict_v02": strict,
        "economic_objective": economic,
        "accepted_actions": accepted,
        "model_calls": calls,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total_tokens,
        "latency_ms": latency,
        "known_cost_usd": cost,
        "actionable_obligations": actionable,
        "resolved_obligations": resolved,
        "unresolved_obligations": unresolved_total,
        "unresolved_obligation_counts": dict(sorted(unresolved.items())),
        "action_type_counts": dict(sorted(actions.items())),
        "interventions": dict(sorted(interventions.items())),
    }


def _close(actual: Any, expected: Any, path: str) -> None:
    if isinstance(expected, float):
        if not math.isclose(
            float(actual), expected, rel_tol=1e-12, abs_tol=1e-9
        ):
            raise ValueError(
                f"Numeric drift at {path}: expected={expected}, actual={actual}"
            )
        return
    if actual != expected:
        raise ValueError(
            f"Evidence drift at {path}: expected={expected!r}, actual={actual!r}"
        )


def _check_frozen_chunks(manifest: dict[str, Any]) -> None:
    storage = manifest.get("storage") or {}
    expected_replay_chunks = [
        {
            "path": "replay-source.b64.part00",
            "bytes": 2200,
            "sha256": "760149ed1a2f5081a6b0b1a966bdc0d1dc5941bb762f3e933323f84f8c184ba2",
        },
        {
            "path": "replay-source.b64.part01",
            "bytes": 2200,
            "sha256": "5d5ef0f2d853538c63c810e1abf78dc9bd48473a7aaf4e8ee6b19bc4ba04fdaf",
        },
        {
            "path": "replay-source.b64.part02",
            "bytes": 2200,
            "sha256": "703632f14cbd0b512b869cc6956069f6aa1fbcf7a8a1b40c89b6c7112807a9dc",
        },
    ]
    _close(
        storage.get("format"),
        "gzip(JSONL canonical compact replay records) encoded as base64 text and split into checksum-locked chunks",
        "manifest.storage.format",
    )
    _close(storage.get("chunks"), expected_replay_chunks, "manifest.storage.chunks")
    _close(storage.get("encoded_bytes"), 6600, "manifest.storage.encoded_bytes")
    for row in expected_replay_chunks:
        path = EVIDENCE_DIR / row["path"]
        if not path.is_file():
            raise ValueError(f"Missing Coverage + Repair replay chunk: {path}")
        payload = path.read_bytes()
        _close(len(payload), row["bytes"], f"{row['path']}.bytes")
        _close(
            sha256(payload).hexdigest(),
            row["sha256"],
            f"{row['path']}.sha256",
        )

    provenance = manifest.get("provenance") or {}
    expected_provenance_chunks = [
        {
            "path": "source-provenance.txt.part00",
            "bytes": 3156,
            "sha256": "7087beaf7a98c1747d301922fffeb11cf4902f5ceba898cdef5e59c661d5610b",
        },
        {
            "path": "source-provenance.txt.part01",
            "bytes": 3168,
            "sha256": "38b21672de5ed560b46b13b049e581eb6b3ef68648d96b28973a5588a5f177a8",
        },
        {
            "path": "source-provenance.txt.part02",
            "bytes": 3156,
            "sha256": "08c5a448dd5907e9504a0937cfe0903becd987045ac3c200a85359c611494d9b",
        },
        {
            "path": "source-provenance.txt.part03",
            "bytes": 3126,
            "sha256": "519bb470b4dcc1f011d624a2a8c2cb31a5e9ca99f8a88c19c453efe01a74e7f2",
        },
    ]
    _close(
        provenance.get("chunks"),
        expected_provenance_chunks,
        "manifest.provenance.chunks",
    )
    _close(provenance.get("bytes"), 12606, "manifest.provenance.bytes")
    _close(
        provenance.get("sha256"),
        "016fd2f237854356d34f85fae65096b28273c27301c52909f51d8470abd7d122",
        "manifest.provenance.sha256",
    )
    _close(
        provenance.get("raw_provenance_sha256"),
        "ba74befd2b64dd07e5ea08d2621941407fd11fa7a7f32c2fa76876318a80b97f",
        "manifest.provenance.raw_provenance_sha256",
    )
    joined = b""
    for row in expected_provenance_chunks:
        path = EVIDENCE_DIR / row["path"]
        if not path.is_file():
            raise ValueError(f"Missing Coverage + Repair provenance chunk: {path}")
        payload = path.read_bytes()
        _close(len(payload), row["bytes"], f"{row['path']}.bytes")
        _close(
            sha256(payload).hexdigest(),
            row["sha256"],
            f"{row['path']}.sha256",
        )
        joined += payload
    _close(
        sha256(joined).hexdigest(),
        provenance["sha256"],
        "joined provenance sha256",
    )


def check_provenance(records: list[dict[str, Any]]) -> None:
    parts = sorted(EVIDENCE_DIR.glob("source-provenance.txt.part*"))
    if len(parts) != 4:
        raise ValueError(
            f"Expected 4 Coverage + Repair provenance chunks; found {len(parts)}"
        )
    lines = "".join(
        part.read_text(encoding="utf-8") for part in parts
    ).splitlines()
    if len(lines) != 60:
        raise ValueError("Coverage + Repair provenance must contain 60 rows")
    entries = {}
    for line_number, line in enumerate(lines, start=1):
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError(
                f"Malformed provenance row on line {line_number}"
            )
        episode_text, repeat_text, member, raw_sha, compact_sha = fields
        episode_index = int(episode_text)
        repeat = int(repeat_text)
        if not 1 <= episode_index <= len(EPISODES) or repeat not in (1, 2, 3):
            raise ValueError("Out-of-range provenance key")
        expected_suffix = f"/{EPISODES[episode_index - 1]}/run-{repeat:03d}.json"
        if not ("/" + member.lstrip("/")).endswith(expected_suffix):
            raise ValueError("Provenance member path does not match key")
        for digest in (raw_sha, compact_sha):
            if len(digest) != 64:
                raise ValueError("Invalid provenance digest length")
            int(digest, 16)
        key = (episode_index, repeat)
        if key in entries:
            raise ValueError(f"Duplicate provenance key: {key}")
        entries[key] = compact_sha

    expected_keys = {
        (episode_index, repeat)
        for episode_index in range(1, 21)
        for repeat in (1, 2, 3)
    }
    if set(entries) != expected_keys:
        raise ValueError("Coverage + Repair provenance grid mismatch")

    from frozen_coverage_repair_confirmatory_v01 import (
        _canonical_line,
    )

    for record in records:
        episode_index = EPISODES.index(record["episode_id"]) + 1
        decisions = [
            [d["type"], d.get("supplier_id"), d.get("arguments") or {}]
            for d in record["decisions"]
        ]
        metrics = record["policy_metrics"]
        from frozen_coverage_repair_confirmatory_v01 import POLICY_METRIC_FIELDS
        row = [
            episode_index,
            record["repeat"],
            record["status"],
            decisions,
            [metrics.get(key) for key in POLICY_METRIC_FIELDS],
        ]
        digest = sha256(_canonical_line(row)).hexdigest()
        if entries[(episode_index, record["repeat"])] != digest:
            raise ValueError("Committed replay does not match provenance")


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))

    expected_manifest = {
        "source_workflow_run_id": 36345529581,
        "source_artifact_id": 10941001111,
        "source_artifact_digest": (
            "sha256:c8a0c85e6ec00af8199d0085a9bcbc64ea46826d92d0a20a0df00aad485474a5"
        ),
        "source_artifact_bytes": 206620,
        "model": "openai/gpt-5.6-sol",
        "records": 60,
        "episodes": 20,
        "repeats_per_episode": 3,
    }
    for key, value in expected_manifest.items():
        _close(manifest.get(key), value, f"manifest.{key}")

    storage = manifest.get("storage") or {}
    expected_storage = {
        "compact_rows_bytes": EXPECTED_COMPACT_ROWS_BYTES,
        "compact_rows_sha256": EXPECTED_COMPACT_ROWS_SHA256,
        "compressed_bytes": EXPECTED_COMPRESSED_BYTES,
        "compressed_sha256": EXPECTED_COMPRESSED_SHA256,
    }
    for key, value in expected_storage.items():
        _close(storage.get(key), value, f"manifest.storage.{key}")
    _check_frozen_chunks(manifest)

    evaluator = LongProcureBenchEvaluator(repo_root=ROOT)
    coverage_source = load_frozen_coverage_repair_source(ROOT)
    check_provenance(coverage_source)
    context_source = load_frozen_context_compiled_source(ROOT)
    react_source = load_frozen_react_source(ROOT)

    coverage = _summary(_evaluate(
        coverage_source, reconstruct_coverage_actions, evaluator
    ))
    context = _summary(_evaluate(
        context_source, reconstruct_context_actions, evaluator
    ))
    react = _summary(_evaluate(
        react_source, reconstruct_react_actions, evaluator
    ))

    for name, summary in (
        ("factual_context", context),
        ("react", react),
        ("coverage_repair", coverage),
    ):
        frozen = results["rows"][name]
        mapping = {
            "runs": summary["runs"],
            "terminal_feasible": [summary["terminal_feasible"], summary["runs"]],
            "feasible_obligation_success": [summary["feasible_obligation_success"], summary["runs"]],
            "strict_v02": [summary["strict_v02"], summary["runs"]],
            "economic_objective": [summary["economic_objective"], summary["runs"]],
            "accepted_actions": summary["accepted_actions"],
            "model_calls": summary["model_calls"],
            "total_tokens": summary["total_tokens"],
            "latency_ms": summary["latency_ms"],
            "known_cost_usd": summary["known_cost_usd"],
        }
        for key, value in mapping.items():
            _close(frozen[key], value, f"results.rows.{name}.{key}")

    diag = results["coverage_repair_diagnostics"]
    diag_actual = {
        "interventions": coverage["interventions"]["coverage_repair_interventions"],
        "forced_rfqs": coverage["interventions"]["coverage_forced_rfqs"],
        "forced_followups": coverage["interventions"]["coverage_forced_followups"],
        "forced_answers": coverage["interventions"]["coverage_forced_answers"],
    }
    _close(diag, diag_actual, "results.coverage_repair_diagnostics")

    unresolved = results["unresolved_obligations"]["coverage_repair"]
    unresolved_actual = {
        "actionable": coverage["actionable_obligations"],
        "resolved": coverage["resolved_obligations"],
        "unresolved": coverage["unresolved_obligations"],
        "by_class": coverage["unresolved_obligation_counts"],
    }
    _close(unresolved, unresolved_actual, "results.unresolved.coverage_repair")

    def rate(summary: dict[str, Any], key: str) -> float:
        return summary[key] / summary["runs"]

    strict_recovery = (
        rate(coverage, "strict_v02") - rate(context, "strict_v02")
    ) / (
        rate(react, "strict_v02") - rate(context, "strict_v02")
    )
    economic_recovery = (
        rate(coverage, "economic_objective")
        - rate(context, "economic_objective")
    ) / (
        rate(react, "economic_objective")
        - rate(context, "economic_objective")
    )
    _close(
        results["react_gain_recovery"]["strict_v02"],
        strict_recovery,
        "results.react_gain_recovery.strict_v02",
    )
    _close(
        results["react_gain_recovery"]["economic_objective"],
        economic_recovery,
        "results.react_gain_recovery.economic_objective",
    )

    substantial = (
        strict_recovery >= 0.5
        and economic_recovery >= 0.5
        and rate(coverage, "feasible_obligation_success")
        >= rate(context, "feasible_obligation_success") - 0.05
        and rate(coverage, "terminal_feasible")
        >= rate(context, "terminal_feasible") - 0.05
    )
    near_react = (
        rate(coverage, "strict_v02") >= rate(react, "strict_v02") - 0.05
        and rate(coverage, "economic_objective")
        >= rate(react, "economic_objective") - 0.05
        and coverage["known_cost_usd"] <= react["known_cost_usd"] * 0.75
    )
    _close(
        results["predeclared_verdict"],
        {
            "substantial_workflow_explanation": substantial,
            "near_react_workflow_explanation": near_react,
        },
        "results.predeclared_verdict",
    )

    print("Coverage + Repair confirmatory audit passed.")
    print(
        "coverage strict={}/60 economic={}/60 feasible_obligation={}/60 "
        "tokens={} cost=${:.6f}".format(
            coverage["strict_v02"],
            coverage["economic_objective"],
            coverage["feasible_obligation_success"],
            coverage["total_tokens"],
            coverage["known_cost_usd"],
        )
    )


if __name__ == "__main__":
    main()
