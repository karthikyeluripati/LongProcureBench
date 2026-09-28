"""Verify frozen Plan-and-Execute replay against the source artifact ZIP."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frozen_plan_execute_targeted_v01 import (
    EPISODES,
    _canonical_line,
    compact_record_from_raw,
    load_frozen_plan_execute_targeted_source,
)


EVIDENCE_DIR = ROOT / "evidence" / "plan-execute-targeted-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"


def verify_artifact(path: Path) -> dict[str, str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload = path.read_bytes()

    if len(payload) != manifest["source_artifact_bytes"]:
        raise ValueError("Plan-and-Execute artifact size mismatch")
    expected_digest = manifest["source_artifact_digest"].removeprefix(
        "sha256:"
    )
    if sha256(payload).hexdigest() != expected_digest:
        raise ValueError("Plan-and-Execute artifact digest mismatch")

    expected_members = {
        row["path"]: row
        for row in manifest["source_members"]
    }
    provenance = {}
    for line in PROVENANCE_PATH.read_text(encoding="utf-8").splitlines():
        episode_id, member, raw_bytes, raw_sha, compact_sha = line.split("|")
        provenance[episode_id] = {
            "member": member,
            "raw_bytes": int(raw_bytes),
            "raw_sha256": raw_sha,
            "compact_sha256": compact_sha,
        }

    artifact_records = {}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if names != set(expected_members):
            missing = sorted(set(expected_members) - names)
            extra = sorted(names - set(expected_members))
            raise ValueError(
                "Plan-and-Execute artifact member mismatch: "
                f"missing={missing}, extra={extra}"
            )

        for name in sorted(names):
            raw = archive.read(name)
            expected = expected_members[name]
            if len(raw) != expected["bytes"]:
                raise ValueError(f"Artifact member size mismatch: {name}")
            if sha256(raw).hexdigest() != expected["sha256"]:
                raise ValueError(f"Artifact member digest mismatch: {name}")

            if not name.endswith("/run-001.json"):
                continue
            source = json.loads(raw)
            compact = compact_record_from_raw(source)
            episode_id = compact["episode_id"]
            if episode_id not in EPISODES:
                raise ValueError("Unexpected episode in source artifact")
            if episode_id in artifact_records:
                raise ValueError("Duplicate source artifact episode")
            prov = provenance.get(episode_id)
            if prov is None or prov["member"] != name:
                raise ValueError("Artifact run is not linked by provenance")
            if prov["raw_bytes"] != len(raw):
                raise ValueError("Provenance raw byte count mismatch")
            if prov["raw_sha256"] != sha256(raw).hexdigest():
                raise ValueError("Provenance raw digest mismatch")
            if prov["compact_sha256"] != sha256(
                _canonical_line(compact)
            ).hexdigest():
                raise ValueError("Provenance compact digest mismatch")
            artifact_records[episode_id] = compact

    if set(artifact_records) != set(EPISODES):
        raise ValueError("Source artifact targeted episode set drift")

    committed = {
        record["episode_id"]: record
        for record in load_frozen_plan_execute_targeted_source(ROOT)
    }
    for episode_id in EPISODES:
        if _canonical_line(artifact_records[episode_id]) != _canonical_line(
            committed[episode_id]
        ):
            raise ValueError(
                f"Committed replay differs from source artifact: {episode_id}"
            )

    return {
        "source_artifact_sha256": expected_digest,
        "committed_compact_rows_sha256": sha256(
            b"".join(_canonical_line(committed[e]) for e in EPISODES)
        ).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", required=True)
    args = parser.parse_args()
    result = verify_artifact(Path(args.artifact_zip))
    print("Plan-and-Execute source artifact verified.")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
