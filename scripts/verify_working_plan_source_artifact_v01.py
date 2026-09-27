"""Verify working-plan compact records directly against the Actions artifact."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frozen_working_plan_v01 import (
    EPISODES,
    EXPECTED_PROVENANCE_BYTES,
    EXPECTED_PROVENANCE_SHA256,
    EXPECTED_SELECTED_COMPACTION_SHA256,
    EXPECTED_SELECTED_RAW_PROVENANCE_SHA256,
    compact_rows_sha256,
)

ARTIFACT_SHA256 = "924443c9bde20b687a2a3b9fe0c8058f8a224604d8532d6c325c6a9c89fd6c9b"
ARTIFACT_BYTES = 280188
RUN_PATH_RE = re.compile(
    r"/(?P<episode>electrical-[^/]+)/run-(?P<repeat>[0-9]{3})[.]json$"
)


def _canonical_line(row: list) -> bytes:
    return (
        json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _root(lines: list[str]) -> str:
    return sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def _compact(raw: dict, episode_index: int, repeat: int) -> list:
    decisions = []
    for trajectory_row in raw.get("trajectory") or []:
        action = trajectory_row["action"]
        decisions.append([
            action["type"],
            action.get("supplier_id"),
            action.get("arguments") or {},
        ])
    metrics = raw.get("policy_metrics") or {}
    return [
        episode_index,
        repeat,
        raw.get("status"),
        decisions,
        [
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
            metrics.get("plan_updates"),
            metrics.get("plan_rejections"),
            metrics.get("mean_plan_steps"),
            metrics.get("max_plan_steps"),
            metrics.get("model_calls_failed"),
        ],
        metrics.get("final_plan"),
        metrics.get("plan_trace"),
        metrics.get("plan_rejection_trace"),
    ]


def verify_artifact(path: Path) -> dict[str, str]:
    payload = path.read_bytes()
    if len(payload) != ARTIFACT_BYTES:
        raise ValueError("Working-plan artifact size mismatch")
    if sha256(payload).hexdigest() != ARTIFACT_SHA256:
        raise ValueError("Working-plan artifact digest mismatch")

    with zipfile.ZipFile(path) as archive:
        members: dict[tuple[str, int], str] = {}
        for name in archive.namelist():
            match = RUN_PATH_RE.search("/" + name.lstrip("/"))
            if match:
                key = (match.group("episode"), int(match.group("repeat")))
                if key in members:
                    raise ValueError(f"Duplicate run member for {key}")
                members[key] = name

        expected_keys = {
            (episode_id, repeat)
            for episode_id in EPISODES
            for repeat in (1, 2, 3)
        }
        if set(members) != expected_keys:
            raise ValueError("Working-plan artifact grid mismatch")

        compact_rows = []
        raw_lines = []
        provenance_lines = []
        for episode_index, episode_id in enumerate(EPISODES, start=1):
            for repeat in (1, 2, 3):
                name = members[(episode_id, repeat)]
                raw_bytes = archive.read(name)
                raw = json.loads(raw_bytes)
                if raw.get("episode_id") != episode_id:
                    raise ValueError("Artifact episode identity mismatch")
                if raw.get("status") != "completed":
                    raise ValueError("Artifact contains non-completed run")
                if raw.get("error") is not None or raw.get("evaluation_error") is not None:
                    raise ValueError("Artifact contains execution/evaluation error")
                if (raw.get("evaluation") or {}).get("evaluation_version") != "0.2.0":
                    raise ValueError("Artifact evaluator coverage mismatch")
                metrics = raw.get("policy_metrics") or {}
                if metrics.get("usage_incomplete") is not False or metrics.get("cost_usd") is None:
                    raise ValueError("Artifact usage/cost is incomplete")
                if metrics.get("model_calls_failed") != 0:
                    raise ValueError("Artifact contains failed model calls")
                if metrics.get("context_strategy") != "factual_compiled_v0.1":
                    raise ValueError("Artifact context strategy mismatch")
                if metrics.get("state_strategy") != "maintained_working_plan_v0.1":
                    raise ValueError("Artifact state strategy mismatch")

                row = _compact(raw, episode_index, repeat)
                compact_rows.append(row)
                raw_sha = sha256(raw_bytes).hexdigest()
                compact_sha = sha256(_canonical_line(row)).hexdigest()
                raw_line = f"{episode_index}|{repeat}|{name}|{raw_sha}"
                raw_lines.append(raw_line)
                provenance_lines.append(f"{raw_line}|{compact_sha}")

    actual = {
        "selected_compaction_sha256": compact_rows_sha256(compact_rows),
        "selected_raw_provenance_sha256": _root(raw_lines),
    }
    expected = {
        "selected_compaction_sha256": EXPECTED_SELECTED_COMPACTION_SHA256,
        "selected_raw_provenance_sha256": EXPECTED_SELECTED_RAW_PROVENANCE_SHA256,
    }
    if actual != expected:
        raise ValueError("Artifact-derived compact/provenance root mismatch")

    committed = (
        ROOT / "evidence" / "working-plan-reactive-v0.1" / "source-provenance.txt"
    ).read_bytes()
    generated = ("\n".join(provenance_lines) + "\n").encode("utf-8")
    if len(committed) != EXPECTED_PROVENANCE_BYTES:
        raise ValueError("Committed provenance size mismatch")
    if sha256(committed).hexdigest() != EXPECTED_PROVENANCE_SHA256:
        raise ValueError("Committed provenance digest mismatch")
    if committed != generated:
        raise ValueError("Committed provenance is not artifact-derived")
    return actual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", required=True)
    args = parser.parse_args()
    result = verify_artifact(Path(args.artifact_zip))
    print("Working-plan source artifact verified.")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
