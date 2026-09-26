"""Verify frozen operational-ledger compaction directly from Actions artifacts."""
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

from frozen_operational_ledger_v01 import (
    EPISODES,
    EXPECTED_ORIGINAL_RAW_PROVENANCE_SHA256,
    EXPECTED_PROVENANCE_BYTES,
    EXPECTED_PROVENANCE_SHA256,
    EXPECTED_RECOVERY_RAW_PROVENANCE_SHA256,
    EXPECTED_SELECTED_COMPACTION_SHA256,
    EXPECTED_SELECTED_RAW_PROVENANCE_SHA256,
    compact_rows_sha256,
)

ORIGINAL_ARTIFACT_SHA256 = (
    "801decf63bc6e24f6bba2a20d6326dd482065aedd5bab266e8d9ff66c895e950"
)
RECOVERY_ARTIFACT_SHA256 = (
    "53c4de34d9f8ce85935e7dd783d05b2e122b5dcc7d80b74d432ea87189f0be9b"
)
RUN_PATH_RE = re.compile(
    r"/(?P<episode>electrical-[^/]+)/run-(?P<repeat>[0-9]{3})\.json$"
)


def _expected_source_code(episode_index: int, repeat: int) -> int:
    if episode_index <= 14:
        return 0
    if episode_index == 15 and repeat == 1:
        return 0
    return 1


def _artifact_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _run_paths(path: Path) -> dict[tuple[str, int], str]:
    rows = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            match = RUN_PATH_RE.search("/" + name.lstrip("/"))
            if not match:
                continue
            key = (
                match.group("episode"),
                int(match.group("repeat")),
            )
            if key in rows:
                raise ValueError(f"Duplicate artifact run path for {key}")
            rows[key] = name
    return rows


def _compact_record(
    raw: dict,
    *,
    episode_index: int,
    repeat: int,
    source_code: int,
) -> list:
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
        source_code,
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
            metrics.get("ledger_open_items"),
            metrics.get("ledger_resolved_items"),
            metrics.get("ledger_items_created"),
            metrics.get("ledger_max_open_items"),
        ],
        metrics.get("final_ledger"),
        metrics.get("ledger_trace"),
    ]


def _canonical_compact_line(row: list) -> bytes:
    return (
        json.dumps(
            row,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def _provenance_root(lines: list[str]) -> str:
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    return sha256(payload).hexdigest()


def verify_artifacts(original_zip: Path, recovery_zip: Path) -> dict:
    if _artifact_digest(original_zip) != ORIGINAL_ARTIFACT_SHA256:
        raise ValueError("Original artifact ZIP digest mismatch")
    if _artifact_digest(recovery_zip) != RECOVERY_ARTIFACT_SHA256:
        raise ValueError("Recovery artifact ZIP digest mismatch")

    paths = {
        0: _run_paths(original_zip),
        1: _run_paths(recovery_zip),
    }
    zips = {
        0: original_zip,
        1: recovery_zip,
    }

    compact_rows = []
    provenance = []
    provenance_by_source = {0: [], 1: []}
    record_provenance = []

    archives = {
        source_code: zipfile.ZipFile(path)
        for source_code, path in zips.items()
    }
    try:
        for episode_index, episode_id in enumerate(EPISODES, start=1):
            for repeat in (1, 2, 3):
                source_code = _expected_source_code(
                    episode_index,
                    repeat,
                )
                key = (episode_id, repeat)
                name = paths[source_code].get(key)
                if name is None:
                    raise ValueError(
                        f"Selected source artifact is missing {key}"
                    )

                raw_bytes = archives[source_code].read(name)
                raw_sha = sha256(raw_bytes).hexdigest()
                line = (
                    f"{source_code}|{episode_index}|{repeat}|{raw_sha}"
                )
                provenance.append(line)
                provenance_by_source[source_code].append(line)

                raw = json.loads(raw_bytes)
                if raw.get("status") not in {"completed", "max_actions"}:
                    raise ValueError(
                        f"Selected run is not execution-valid: {key}"
                    )
                compact = _compact_record(
                    raw,
                    episode_index=episode_index,
                    repeat=repeat,
                    source_code=source_code,
                )
                compact_rows.append(compact)
                compact_sha = sha256(
                    _canonical_compact_line(compact)
                ).hexdigest()
                record_provenance.append(
                    f"{line}|{compact_sha}"
                )
    finally:
        for archive in archives.values():
            archive.close()

    compact_root = compact_rows_sha256(compact_rows)
    raw_root = _provenance_root(provenance)
    original_root = _provenance_root(provenance_by_source[0])
    recovery_root = _provenance_root(provenance_by_source[1])

    expected = {
        "selected_compaction_sha256": EXPECTED_SELECTED_COMPACTION_SHA256,
        "selected_raw_provenance_sha256": (
            EXPECTED_SELECTED_RAW_PROVENANCE_SHA256
        ),
        "original_raw_provenance_sha256": (
            EXPECTED_ORIGINAL_RAW_PROVENANCE_SHA256
        ),
        "recovery_raw_provenance_sha256": (
            EXPECTED_RECOVERY_RAW_PROVENANCE_SHA256
        ),
    }
    actual = {
        "selected_compaction_sha256": compact_root,
        "selected_raw_provenance_sha256": raw_root,
        "original_raw_provenance_sha256": original_root,
        "recovery_raw_provenance_sha256": recovery_root,
    }
    if actual != expected:
        raise ValueError(
            "Artifact-derived source verification mismatch: "
            + json.dumps({"expected": expected, "actual": actual})
        )

    provenance_payload = (
        "\n".join(record_provenance) + "\n"
    ).encode("utf-8")
    provenance_path = (
        ROOT
        / "evidence"
        / "operational-ledger-reactive-v0.1"
        / "source-provenance.txt"
    )
    committed = provenance_path.read_bytes()
    if len(committed) != EXPECTED_PROVENANCE_BYTES:
        raise ValueError("Committed source provenance size mismatch")
    if sha256(committed).hexdigest() != EXPECTED_PROVENANCE_SHA256:
        raise ValueError("Committed source provenance digest mismatch")
    if committed != provenance_payload:
        raise ValueError(
            "Committed source provenance does not match artifact-derived records"
        )
    return actual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-zip", required=True)
    parser.add_argument("--recovery-zip", required=True)
    args = parser.parse_args()

    result = verify_artifacts(
        Path(args.original_zip),
        Path(args.recovery_zip),
    )
    print("Operational-ledger source artifacts verified.")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
