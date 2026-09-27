"""Regenerate durable always-replan/verifier replay evidence from a raw artifact."""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evidence" / "always-replan-verifier-v0.1"
EXPECTED_COMPRESSED_BYTES = 51107
EXPECTED_COMPRESSED_SHA256 = "494a9cf48d868589b39e75a034f3e314c0c1f52be3636959a81981cd6085a4ab"
EXPECTED_COMPACT_ROWS_SHA256 = "e8e854bf0ba45176641a1d888fc8a4733f3b122c1fb031eb135d29f09054d380"
EXPECTED_PROVENANCE_BYTES = 12606
EXPECTED_PROVENANCE_SHA256 = "0888f100312820eb5fc287012cf734301f1b9bbbf86e4088592db1e21e624d3c"
PART_CHARS = 9000

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
EPISODE_INDEX = {episode_id: index for index, episode_id in enumerate(EPISODES, start=1)}


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


def _compact_record(path: Path, artifact_root: Path):
    raw = path.read_bytes()
    run = json.loads(raw)
    episode_id = run["episode_id"]
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
        metrics.get("planner_calls"),
        metrics.get("action_calls"),
        metrics.get("verifier_calls"),
        metrics.get("verifier_rejections"),
        metrics.get("repair_calls"),
        metrics.get("model_calls_failed"),
    ]

    terminal_proposals = Counter()
    rejected_recommendations = Counter()
    approved_recommendations = Counter()
    bounded_issue_traces = 0
    for trace in metrics.get("verification_trace") or []:
        proposed = trace.get("proposed_action") or {}
        verdict = trace.get("verdict") or {}
        proposal_type = proposed.get("type")
        recommendation = verdict.get("recommended_action_type")
        if proposal_type:
            terminal_proposals[proposal_type] += 1
        bounded_issue_traces += int(bool(verdict.get("issues_were_bounded")))
        if recommendation:
            if verdict.get("approve"):
                approved_recommendations[recommendation] += 1
            else:
                rejected_recommendations[recommendation] += 1

    diagnostics = [
        dict(sorted(terminal_proposals.items())),
        dict(sorted(rejected_recommendations.items())),
        dict(sorted(approved_recommendations.items())),
        bounded_issue_traces,
    ]
    row = [
        EPISODE_INDEX[episode_id],
        repeat,
        run["status"],
        decisions,
        compact_metrics,
        diagnostics,
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
        raise ValueError(f"Expected 60 raw run JSON files; found {len(files)}")

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

    expected = {(index, repeat) for index in range(1, 21) for repeat in range(1, 4)}
    if keys != expected:
        raise ValueError("Raw artifact does not contain the exact 20x3 development grid")

    payload = b"".join(_canonical_line(row) for row in rows)
    rows_digest = sha256(payload).hexdigest()
    if rows_digest != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError(
            f"Compact-row digest mismatch: expected={EXPECTED_COMPACT_ROWS_SHA256}, actual={rows_digest}"
        )

    compressed = bytearray(gzip.compress(payload, compresslevel=9, mtime=0))
    # Python 3.11/3.12 may inherit zlib's platform OS byte when mtime=0,
    # while newer Python versions guarantee 255. Normalize it so the durable
    # replay bytes are version- and runner-independent.
    compressed[9] = 255
    compressed = bytes(compressed)
    compressed_digest = sha256(compressed).hexdigest()
    if len(compressed) != EXPECTED_COMPRESSED_BYTES or compressed_digest != EXPECTED_COMPRESSED_SHA256:
        raise ValueError(
            "Compressed replay mismatch: "
            f"bytes={len(compressed)} sha256={compressed_digest}"
        )

    provenance = "".join(provenance_lines).encode("utf-8")
    provenance_digest = sha256(provenance).hexdigest()
    if len(provenance) != EXPECTED_PROVENANCE_BYTES or provenance_digest != EXPECTED_PROVENANCE_SHA256:
        raise ValueError(
            "Provenance mismatch: "
            f"bytes={len(provenance)} sha256={provenance_digest}"
        )

    encoded = base64.b64encode(compressed).decode("ascii")
    parts = [
        encoded[offset : offset + PART_CHARS]
        for offset in range(0, len(encoded), PART_CHARS)
    ]
    if len(parts) != 8:
        raise ValueError(f"Expected 8 replay parts; found {len(parts)}")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for index, part in enumerate(parts, start=1):
        (EVIDENCE_DIR / f"replay-source.part-{index:02d}.b64").write_text(
            part + "\n",
            encoding="utf-8",
        )
    (EVIDENCE_DIR / "source-provenance.txt").write_bytes(provenance)

    print(
        "Materialized always-replan/verifier replay evidence: "
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
