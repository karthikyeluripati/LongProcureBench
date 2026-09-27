"""Verify ReAct compact evidence against the source artifact."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]

from frozen_react_comparator_v01 import (
    EPISODES,
    EXPECTED_COMPACT_ROWS_SHA256,
    EXPECTED_TRANSCRIPT_ROWS_SHA256,
    load_frozen_react_transcripts,
)
from materialize_react_comparator_evidence_v01 import (
    _canonical_line,
    _compact_record,
)

ARTIFACT_SHA256 = (
    "d767d296d077a5e693bfc18e7429b35627bf5f5939283f98208372cc5f63e373"
)
ARTIFACT_BYTES = 274100
RUN_PATH_RE = re.compile(
    r"/(?P<episode>electrical-[^/]+)/run-(?P<repeat>[0-9]{3})[.]json$"
)


def _root(lines: list[str]) -> str:
    return sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def verify_artifact(path: Path) -> dict[str, str]:
    payload = path.read_bytes()
    if len(payload) != ARTIFACT_BYTES:
        raise ValueError("ReAct artifact size mismatch")
    if sha256(payload).hexdigest() != ARTIFACT_SHA256:
        raise ValueError("ReAct artifact digest mismatch")

    with zipfile.ZipFile(path) as archive:
        members: dict[tuple[str, int], str] = {}
        for name in archive.namelist():
            match = RUN_PATH_RE.search("/" + name.lstrip("/"))
            if match:
                key = (
                    match.group("episode"),
                    int(match.group("repeat")),
                )
                if key in members:
                    raise ValueError(f"Duplicate run member for {key}")
                members[key] = name

        expected_keys = {
            (episode_id, repeat)
            for episode_id in EPISODES
            for repeat in (1, 2, 3)
        }
        if set(members) != expected_keys:
            raise ValueError("ReAct artifact grid mismatch")

        compact_rows = []
        transcript_rows = []
        provenance_lines = []
        raw_lines = []
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            for name in sorted(members.values()):
                match = RUN_PATH_RE.search("/" + name.lstrip("/"))
                if match is None:
                    raise ValueError("Unexpected artifact run member path")

                episode_id = match.group("episode")
                repeat = int(match.group("repeat"))
                episode_index = EPISODES.index(episode_id) + 1
                raw_bytes = archive.read(name)

                target = artifact_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw_bytes)

                row, provenance, transcript_row = _compact_record(
                    target, artifact_root
                )
                if row[0] != episode_index or row[1] != repeat:
                    raise ValueError("Artifact compact key mismatch")
                if (
                    transcript_row[0] != episode_index
                    or transcript_row[1] != repeat
                ):
                    raise ValueError("Artifact transcript key mismatch")

                compact_rows.append(row)
                transcript_rows.append(transcript_row)
                provenance_lines.append(provenance.rstrip("\n"))
                raw_lines.append(
                    f"{episode_index}|{repeat}|{name}|"
                    f"{sha256(raw_bytes).hexdigest()}"
                )

    compact_payload = b"".join(
        _canonical_line(row) for row in compact_rows
    )
    compact_root = sha256(compact_payload).hexdigest()
    if compact_root != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError("Artifact-derived compact replay root mismatch")

    transcript_payload = b"".join(
        _canonical_line(row) for row in transcript_rows
    )
    transcript_root = sha256(transcript_payload).hexdigest()
    if transcript_root != EXPECTED_TRANSCRIPT_ROWS_SHA256:
        raise ValueError("Artifact-derived ReAct transcript root mismatch")

    committed_transcript = (
        ROOT
        / "evidence"
        / "react-comparator-v0.1"
        / "transcript-source.b64"
    )
    if not committed_transcript.is_file():
        raise ValueError("Committed durable ReAct transcript is missing")
    durable_transcripts = load_frozen_react_transcripts(ROOT)
    if len(durable_transcripts) != 60:
        raise ValueError("Durable ReAct transcript grid mismatch")

    committed = (
        ROOT
        / "evidence"
        / "react-comparator-v0.1"
        / "source-provenance.txt"
    ).read_text(encoding="utf-8").splitlines()
    if committed != provenance_lines:
        raise ValueError(
            "Committed ReAct provenance is not source-artifact-derived"
        )

    return {
        "compact_rows_sha256": compact_root,
        "transcript_rows_sha256": transcript_root,
        "raw_provenance_sha256": _root(raw_lines),
        "record_provenance_sha256": _root(provenance_lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", required=True)
    args = parser.parse_args()
    result = verify_artifact(Path(args.artifact_zip))
    print("ReAct source artifact verified.")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
