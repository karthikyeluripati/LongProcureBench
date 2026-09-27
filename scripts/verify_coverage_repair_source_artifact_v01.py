"""Verify Coverage + Repair compact evidence against the source artifact."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]

from frozen_coverage_repair_v01 import (
    EPISODES,
    EXPECTED_COMPACT_ROWS_SHA256,
    _canonical_line,
    _compact_row_from_record,
)

ARTIFACT_SHA256 = (
    "c8a0c85e6ec00af8199d0085a9bcbc64ea46826d92d0a20a0df00aad485474a5"
)
ARTIFACT_BYTES = 206620
RUN_PATH_RE = re.compile(
    r"/(?P<episode>electrical-[^/]+)/run-(?P<repeat>[0-9]{3})[.]json$"
)


def _root(lines: list[str]) -> str:
    return sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def verify_artifact(path: Path) -> dict[str, str]:
    payload = path.read_bytes()
    if len(payload) != ARTIFACT_BYTES:
        raise ValueError("Coverage+Repair artifact size mismatch")
    if sha256(payload).hexdigest() != ARTIFACT_SHA256:
        raise ValueError("Coverage+Repair artifact digest mismatch")

    with zipfile.ZipFile(path) as archive:
        members: dict[tuple[str, int], str] = {}
        for name in archive.namelist():
            match = RUN_PATH_RE.search("/" + name.lstrip("/"))
            if not match:
                continue
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
            missing = sorted(expected_keys - set(members))
            extra = sorted(set(members) - expected_keys)
            raise ValueError(
                "Coverage+Repair artifact grid mismatch: "
                f"missing={missing}, extra={extra}"
            )

        compact_rows = []
        provenance_lines = []
        for episode_id in EPISODES:
            for repeat in (1, 2, 3):
                name = members[(episode_id, repeat)]
                raw_bytes = archive.read(name)
                record = json.loads(raw_bytes)
                row = _compact_row_from_record(record)
                episode_index = EPISODES.index(episode_id) + 1
                if row[0] != episode_index or row[1] != repeat:
                    raise ValueError("Coverage+Repair artifact compact key mismatch")
                compact_rows.append(row)
                provenance_lines.append(
                    f"{episode_index}|{repeat}|{name}|"
                    f"{sha256(raw_bytes).hexdigest()}|"
                    f"{sha256(_canonical_line(row)).hexdigest()}"
                )

    compact_payload = b"".join(
        _canonical_line(row) for row in compact_rows
    )
    compact_root = sha256(compact_payload).hexdigest()
    if compact_root != EXPECTED_COMPACT_ROWS_SHA256:
        raise ValueError(
            "Artifact-derived Coverage+Repair compact replay root mismatch"
        )

    committed = (
        ROOT
        / "evidence"
        / "coverage-repair-confirmatory-v0.1"
        / "source-provenance.txt"
    ).read_text(encoding="utf-8").splitlines()
    if committed != provenance_lines:
        raise ValueError(
            "Committed Coverage+Repair provenance is not source-artifact-derived"
        )

    return {
        "compact_rows_sha256": compact_root,
        "raw_provenance_sha256": _root([
            "|".join(line.split("|")[:4])
            for line in provenance_lines
        ]),
        "record_provenance_sha256": _root(provenance_lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", required=True)
    args = parser.parse_args()
    result = verify_artifact(Path(args.artifact_zip))
    print("Coverage+Repair source artifact verified.")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
