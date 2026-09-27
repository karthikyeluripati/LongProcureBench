"""Regenerate durable ReAct comparator replay evidence from a raw artifact."""
from __future__ import annotations

import argparse
import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench.context_compiled_reactive import compact_visible_event
EVIDENCE_DIR = ROOT / "evidence" / "react-comparator-v0.1"

EXPECTED_COMPRESSED_BYTES = 12554
EXPECTED_COMPRESSED_SHA256 = (
    "8f725cbc46b933d466dab481dde03ce2313acac7fce14193481a6af9e58c19e2"
)
EXPECTED_COMPACT_ROWS_BYTES = 90934
EXPECTED_COMPACT_ROWS_SHA256 = (
    "b93c810ce585807a7a822953bb890ee1d6161291c523d0d2de4a96b60f0a1c1c"
)
EXPECTED_PROVENANCE_BYTES = 12606
EXPECTED_PROVENANCE_SHA256 = (
    "b161fccfb83b1db3b739b1a0af74bb1ef157562c7c4201efed4fddf68bb924ee"
)
EXPECTED_TRANSCRIPT_ROWS_BYTES = 262900
EXPECTED_TRANSCRIPT_ROWS_SHA256 = (
    "dc073660375b68febef010da284cc867b24f11beb2e52c846957bf726c3a5ba8"
)
EXPECTED_TRANSCRIPT_COMPRESSED_BYTES = 30180
EXPECTED_TRANSCRIPT_COMPRESSED_SHA256 = (
    "a7cbe4277c70abe62d157df683efa34a58bb29cc39eeb951e0d253353b7e7456"
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
    if metrics.get("model") != "openai/gpt-5.6-sol":
        raise ValueError("Raw run model mismatch")
    if metrics.get("usage_incomplete") is not False:
        raise ValueError("Raw run usage is incomplete")
    if metrics.get("cost_usd") is None:
        raise ValueError("Raw run cost is missing")
    if metrics.get("model_calls_failed") != 0:
        raise ValueError("Raw run contains failed model calls")
    if metrics.get("context_strategy") != "factual_compiled_v0.1":
        raise ValueError("Raw run context strategy mismatch")
    if metrics.get("agent_pattern") != "react_v0.1":
        raise ValueError("Raw run agent pattern mismatch")
    if metrics.get("temperature") is not None:
        raise ValueError("Raw run temperature must be omitted")
    if metrics.get("reasoning_effort") != "medium":
        raise ValueError("Raw run reasoning effort mismatch")

    trajectory = run.get("trajectory")
    transcript = metrics.get("react_transcript")
    if not isinstance(trajectory, list) or not isinstance(transcript, list):
        raise ValueError("Raw run is missing trajectory/ReAct transcript")
    if len(trajectory) != len(transcript):
        raise ValueError("ReAct transcript length does not match trajectory")
    if metrics.get("react_steps_proposed") != len(trajectory):
        raise ValueError("ReAct proposed-step count mismatch")
    if metrics.get("react_steps_accepted") != len(trajectory):
        raise ValueError("ReAct accepted-step count mismatch")
    if metrics.get("model_calls_attempted") != len(trajectory):
        raise ValueError("ReAct must use one model call per accepted action")

    thought_lengths = []
    for trajectory_row, react_row in zip(trajectory, transcript):
        action = trajectory_row.get("action") or {}
        react_action = react_row.get("action") or {}
        semantic = {
            "type": action.get("type"),
            "supplier_id": action.get("supplier_id"),
            "arguments": action.get("arguments") or {},
        }
        if react_action != semantic:
            raise ValueError(
                "ReAct transcript action does not match accepted trajectory"
            )

        if react_row.get("step") != trajectory_row.get("step"):
            raise ValueError(
                "ReAct transcript step does not match accepted trajectory"
            )

        expected_observation = [
            compact
            for compact in (
                compact_visible_event(event)
                for event in (trajectory_row.get("observations") or [])
            )
            if compact is not None
        ]
        if react_row.get("observation") != expected_observation:
            raise ValueError(
                "ReAct transcript observation does not match executed "
                "factual-visible observation"
            )

        thought = react_row.get("thought_summary")
        if not isinstance(thought, str) or not thought.strip():
            raise ValueError("ReAct transcript contains empty thought summary")
        thought_lengths.append(len(thought))

    thought_total = sum(thought_lengths)
    thought_mean = (
        thought_total / len(thought_lengths)
        if thought_lengths
        else 0.0
    )
    thought_max = max(thought_lengths, default=0)
    if metrics.get("react_thought_chars_total") != thought_total:
        raise ValueError("ReAct thought-character total mismatch")
    if not isinstance(metrics.get("react_thought_chars_mean"), (int, float)):
        raise ValueError("ReAct thought-character mean is missing")
    if abs(
        float(metrics["react_thought_chars_mean"]) - thought_mean
    ) > 1e-9:
        raise ValueError("ReAct thought-character mean mismatch")
    if metrics.get("react_thought_chars_max") != thought_max:
        raise ValueError("ReAct thought-character max mismatch")


def _compact_transcript_row(run: dict, repeat: int) -> list:
    episode_id = run["episode_id"]
    transcript = []
    for react_row in run["policy_metrics"]["react_transcript"]:
        action = react_row["action"]
        transcript.append([
            react_row["step"],
            react_row["thought_summary"],
            [
                action["type"],
                action.get("supplier_id"),
                action.get("arguments") or {},
            ],
            react_row.get("observation") or [],
        ])
    return [
        EPISODE_INDEX[episode_id],
        repeat,
        transcript,
    ]


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
        metrics.get("agent_pattern"),
        metrics.get("react_steps_proposed"),
        metrics.get("react_steps_accepted"),
        metrics.get("react_thought_chars_total"),
        metrics.get("react_thought_chars_mean"),
        metrics.get("react_thought_chars_max"),
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
    transcript_row = _compact_transcript_row(run, repeat)
    return row, provenance, transcript_row


def materialize(artifact_root: Path) -> None:
    files = sorted(artifact_root.glob("**/run-*.json"))
    if len(files) != 60:
        raise ValueError(
            f"Expected 60 raw run JSON files; found {len(files)}"
        )

    rows = []
    transcript_rows = []
    provenance_lines = []
    keys = set()
    for path in files:
        row, provenance, transcript_row = _compact_record(
            path, artifact_root
        )
        key = (row[0], row[1])
        if key in keys:
            raise ValueError(f"Duplicate compact run key: {key}")
        keys.add(key)
        rows.append(row)
        transcript_rows.append(transcript_row)
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
    if len(payload) != EXPECTED_COMPACT_ROWS_BYTES:
        raise ValueError("Compact-row byte count mismatch")
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

    transcript_payload = b"".join(
        _canonical_line(row) for row in transcript_rows
    )
    transcript_compressed = bytearray(
        gzip.compress(transcript_payload, compresslevel=9, mtime=0)
    )
    transcript_compressed[9] = 255
    transcript_compressed = bytes(transcript_compressed)
    transcript_digest = sha256(transcript_compressed).hexdigest()
    transcript_rows_digest = sha256(transcript_payload).hexdigest()
    if (
        len(transcript_payload) != EXPECTED_TRANSCRIPT_ROWS_BYTES
        or transcript_rows_digest != EXPECTED_TRANSCRIPT_ROWS_SHA256
    ):
        raise ValueError(
            "Durable transcript row mismatch: "
            f"bytes={len(transcript_payload)} "
            f"sha256={transcript_rows_digest}"
        )
    if (
        len(transcript_compressed)
        != EXPECTED_TRANSCRIPT_COMPRESSED_BYTES
        or transcript_digest != EXPECTED_TRANSCRIPT_COMPRESSED_SHA256
    ):
        raise ValueError(
            "Durable transcript compressed mismatch: "
            f"bytes={len(transcript_compressed)} "
            f"sha256={transcript_digest}"
        )

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "replay-source.b64").write_text(
        base64.b64encode(compressed).decode("ascii") + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "transcript-source.b64").write_text(
        base64.b64encode(transcript_compressed).decode("ascii") + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "source-provenance.txt").write_bytes(provenance)
    print(
        "Materialized ReAct comparator evidence: "
        f"rows={len(rows)} compressed={len(compressed)} "
        f"sha256={compressed_digest}"
    )
    print(
        "Materialized durable ReAct transcript: "
        f"rows={len(transcript_rows)} "
        f"jsonl_bytes={len(transcript_payload)} "
        f"jsonl_sha256={transcript_rows_digest} "
        f"compressed_bytes={len(transcript_compressed)} "
        f"compressed_sha256={transcript_digest}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.artifact_dir.resolve())


if __name__ == "__main__":
    main()
