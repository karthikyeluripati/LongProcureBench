"""Verify always-replan/verifier compact evidence against the source artifact."""
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

from frozen_always_replan_verifier_v01 import (
    EPISODES,
    EXPECTED_COMPACT_ROWS_SHA256,
)
from materialize_always_replan_verifier_evidence_v01 import (
    _canonical_line,
    _compact_record,
)

ARTIFACT_SHA256 = "8e08847b3fb9725703adb7d0d4046e88a92fdc6ead9f0f7226fe8ccdabf7f7df"
ARTIFACT_BYTES = 771853
RUN_PATH_RE = re.compile(
    r"/(?P<episode>electrical-[^/]+)/run-(?P<repeat>[0-9]{3})[.]json$"
)


def _root(lines: list[str]) -> str:
    return sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def verify_artifact(path: Path) -> dict[str, str]:
    payload = path.read_bytes()
    if len(payload) != ARTIFACT_BYTES:
        raise ValueError("Always-replan/verifier artifact size mismatch")
    if sha256(payload).hexdigest() != ARTIFACT_SHA256:
        raise ValueError("Always-replan/verifier artifact digest mismatch")

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
            raise ValueError("Always-replan/verifier artifact grid mismatch")

        compact_rows = []
        provenance_lines = []
        raw_lines = []
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            # The materializer freezes rows in sorted artifact-member-path
            # order, so reproduce that exact order for checksum comparison.
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
                row, provenance = _compact_record(target, artifact_root)
                if row[0] != episode_index or row[1] != repeat:
                    raise ValueError("Artifact compact key mismatch")
                compact_rows.append(row)
                provenance_lines.append(provenance.rstrip("\n"))
                raw_lines.append(
                    f"{episode_index}|{repeat}|{name}|"
                    f"{sha256(raw_bytes).hexdigest()}"
                )

    compact_payload = b"".join(_canonical_line(row) for row in compact_rows)
    compact_root = sha256(compact_payload).hexdigest()
    if compact_root != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError("Artifact-derived compact replay root mismatch")

    committed = (
        ROOT
        / "evidence"
        / "always-replan-verifier-v0.1"
        / "source-provenance.txt"
    ).read_text(encoding="utf-8").splitlines()
    if committed != provenance_lines:
        raise ValueError("Committed provenance is not source-artifact-derived")

    return {
        "compact_rows_sha256": compact_root,
        "raw_provenance_sha256": _root(raw_lines),
        "record_provenance_sha256": _root(provenance_lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", required=True)
    args = parser.parse_args()
    result = verify_artifact(Path(args.artifact_zip))
    print("Always-replan/verifier source artifact verified.")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
