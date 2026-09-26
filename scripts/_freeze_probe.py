"""Build committed working-plan replay/provenance from the frozen Actions artifact."""
from __future__ import annotations

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frozen_working_plan_v01 import (
    EPISODES,
    EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256,
    EXPECTED_PROVENANCE_BYTES,
    EXPECTED_PROVENANCE_SHA256,
    EXPECTED_SELECTED_COMPACTION_SHA256,
    EXPECTED_SELECTED_RAW_PROVENANCE_SHA256,
    compact_rows_sha256,
)
from verify_operational_ledger_source_artifacts_v01 import _deterministic_gzip
from verify_working_plan_source_artifact_v01 import (
    ARTIFACT_BYTES,
    ARTIFACT_SHA256,
    RUN_PATH_RE,
    _canonical_line,
    _compact,
)


def _root(lines: list[str]) -> str:
    return sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", required=True)
    args = parser.parse_args()
    artifact = Path(args.artifact_zip)
    raw_zip = artifact.read_bytes()
    if len(raw_zip) != ARTIFACT_BYTES or sha256(raw_zip).hexdigest() != ARTIFACT_SHA256:
        raise ValueError("Actions artifact identity mismatch")

    rows = []
    raw_lines = []
    provenance = []
    with zipfile.ZipFile(artifact) as archive:
        members = {}
        for name in archive.namelist():
            match = RUN_PATH_RE.search("/" + name.lstrip("/"))
            if match:
                members[(match.group("episode"), int(match.group("repeat")))] = name
        expected = {(episode, repeat) for episode in EPISODES for repeat in (1, 2, 3)}
        if set(members) != expected:
            raise ValueError("Actions artifact grid mismatch")
        for episode_index, episode in enumerate(EPISODES, start=1):
            for repeat in (1, 2, 3):
                member = members[(episode, repeat)]
                raw = archive.read(member)
                record = json.loads(raw)
                row = _compact(record, episode_index, repeat)
                rows.append(row)
                raw_sha = sha256(raw).hexdigest()
                compact_sha = sha256(_canonical_line(row)).hexdigest()
                raw_line = f"{episode_index}|{repeat}|{member}|{raw_sha}"
                raw_lines.append(raw_line)
                provenance.append(f"{raw_line}|{compact_sha}")

    if compact_rows_sha256(rows) != EXPECTED_SELECTED_COMPACTION_SHA256:
        raise ValueError("Compact root mismatch")
    if _root(raw_lines) != EXPECTED_SELECTED_RAW_PROVENANCE_SHA256:
        raise ValueError("Raw provenance root mismatch")

    evidence = ROOT / "evidence" / "working-plan-reactive-v0.1"
    evidence.mkdir(parents=True, exist_ok=True)
    replay = b"".join(_canonical_line(row) for row in rows)
    compressed = _deterministic_gzip(replay)
    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError("Replay size mismatch")
    if sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256:
        raise ValueError("Replay digest mismatch")
    (evidence / "replay-source.b64").write_text(
        base64.b64encode(compressed).decode() + "\n", encoding="utf-8"
    )

    provenance_bytes = ("\n".join(provenance) + "\n").encode()
    if len(provenance_bytes) != EXPECTED_PROVENANCE_BYTES:
        raise ValueError("Provenance size mismatch")
    if sha256(provenance_bytes).hexdigest() != EXPECTED_PROVENANCE_SHA256:
        raise ValueError("Provenance digest mismatch")
    (evidence / "source-provenance.txt").write_bytes(provenance_bytes)


if __name__ == "__main__":
    main()
