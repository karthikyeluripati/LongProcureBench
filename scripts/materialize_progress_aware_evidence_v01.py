"""Regenerate durable progress-aware replay evidence from a raw artifact."""
from __future__ import annotations

import argparse
import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evidence" / "progress-aware-reactive-v0.1"
EXPECTED_COMPRESSED_BYTES = 4361
EXPECTED_COMPRESSED_SHA256 = (
    "1bd89a732721e513cb64591752693f3a02977f42ebee5c30ce37acb816bb9f6e"
)
EXPECTED_COMPACT_ROWS_SHA256 = (
    "3317c8d61477a7d22d077b1f9f829ede74f49431b8ae16c2274ff08af71ebee5"
)
EXPECTED_PROVENANCE_BYTES = 12606
EXPECTED_PROVENANCE_SHA256 = (
    "64e6958b0e2e0ec7c641205e2bc9818c4caf94377dad4de9e9420819d687e772"
)

EPISODES = [
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
EPISODE_INDEX = {
    episode_id: index
    for index, episode_id in enumerate(EPISODES, start=1)
}


def _canonical_line(row):
    return (
        json.dumps(
            row,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def _validate_raw_run(run: dict, episode_id: str) -> None:
    if run.get("episode_id") != episode_id:
        raise ValueError("Raw run episode identity mismatch")
    if run.get("status") != "completed":
        raise ValueError(
            f"Raw run has unexpected status: {run.get('status')!r}"
        )
    if "error" not in run or run["error"] is not None:
        raise ValueError("Raw run contains or omits execution error state")
    if (
        "evaluation_error" not in run
        or run["evaluation_error"] is not None
    ):
        raise ValueError(
            "Raw run contains or omits evaluation error state"
        )
    evaluation = run.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ValueError("Raw run is missing evaluation output")
    if evaluation.get("evaluation_version") != "0.2.0":
        raise ValueError("Raw run does not contain Evaluator v0.2 output")
    if evaluation.get("episode_id") != episode_id:
        raise ValueError("Raw run evaluation episode identity mismatch")

    metrics = run.get("policy_metrics") or {}
    if metrics.get("usage_incomplete") is not False:
        raise ValueError("Raw run usage is incomplete")
    if metrics.get("cost_usd") is None:
        raise ValueError("Raw run cost is missing")
    if metrics.get("model_calls_failed") != 0:
        raise ValueError("Raw run contains failed model calls")
    if metrics.get("context_strategy") != "factual_compiled_v0.1":
        raise ValueError("Raw run context strategy mismatch")
    if (
        metrics.get("state_strategy")
        != "progress_aware_no_progress_guard_v0.1"
    ):
        raise ValueError("Raw run state strategy mismatch")


def _compact_record(path: Path, artifact_root: Path):
    raw = path.read_bytes()
    run = json.loads(raw)
    episode_id = run.get("episode_id")
    if episode_id not in EPISODE_INDEX:
        raise ValueError(f"Unexpected raw run episode_id: {episode_id!r}")
    _validate_raw_run(run, episode_id)
    repeat = int(path.stem.rsplit("-", 1)[1])

    decisions = []
    for trajectory_row in run["trajectory"]:
        action = trajectory_row["action"]
        decisions.append([
            action["type"],
            action.get("supplier_id"),
            action.get("arguments") or {},
        ])

    metrics = run["policy_metrics"]
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

    row = [
        EPISODE_INDEX[episode_id],
        repeat,
        run["status"],
        decisions,
        compact_metrics,
    ]
    line = _canonical_line(row)
    provenance = (
        f"{EPISODE_INDEX[episode_id]}|{repeat}|"
        f"{path.relative_to(artifact_root).as_posix()}|"
        f"{sha256(raw).hexdigest()}|{sha256(line).hexdigest()}\n"
    )
    return row, provenance


def materialize(artifact_root: Path) -> None:
    files = sorted(artifact_root.glob("**/run-*.json"))
    if len(files) != 60:
        raise ValueError(
            f"Expected 60 raw run JSON files; found {len(files)}"
        )

    rows = []
    provenance_lines = []
    keys = set()
    for path in files:
        row, provenance = _compact_record(path, artifact_root)
        key = (row[0], row[1])
        if key in keys:
            raise ValueError(f"Duplicate compact run key: {key}")
        keys.add(key)
        rows.append(row)
        provenance_lines.append(provenance)

    expected = {
        (index, repeat)
        for index in range(1, 21)
        for repeat in range(1, 4)
    }
    if keys != expected:
        raise ValueError(
            "Raw artifact does not contain the exact 20x3 development grid"
        )

    payload = b"".join(_canonical_line(row) for row in rows)
    rows_digest = sha256(payload).hexdigest()
    if rows_digest != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError(
            "Compact-row digest mismatch: "
            f"expected={EXPECTED_COMPACT_ROWS_SHA256}, actual={rows_digest}"
        )

    compressed = bytearray(gzip.compress(payload, compresslevel=9, mtime=0))
    compressed[9] = 255
    compressed = bytes(compressed)
    compressed_digest = sha256(compressed).hexdigest()
    if (
        len(compressed) != EXPECTED_COMPRESSED_BYTES
        or compressed_digest != EXPECTED_COMPRESSED_SHA256
    ):
        raise ValueError(
            "Compressed replay mismatch: "
            f"bytes={len(compressed)} sha256={compressed_digest}"
        )

    provenance = "".join(provenance_lines).encode("utf-8")
    provenance_digest = sha256(provenance).hexdigest()
    if (
        len(provenance) != EXPECTED_PROVENANCE_BYTES
        or provenance_digest != EXPECTED_PROVENANCE_SHA256
    ):
        raise ValueError(
            "Provenance mismatch: "
            f"bytes={len(provenance)} sha256={provenance_digest}"
        )

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "replay-source.b64").write_text(
        base64.b64encode(compressed).decode("ascii") + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "source-provenance.txt").write_bytes(provenance)

    print(
        "Materialized progress-aware replay evidence: "
        f"rows={len(rows)} compressed={len(compressed)} "
        f"sha256={compressed_digest}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.artifact_dir.resolve())


if __name__ == "__main__":
    main()
