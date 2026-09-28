"""Verify frozen State Validity Frontier Stage-1 replay against its source artifact."""
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

from frozen_state_validity_frontier_stage1_v01 import (
    EPISODES,
    EXPECTED_ROWS_SHA256,
    canonical_line,
    compact_record_from_raw,
    load_frozen_state_validity_frontier_stage1,
)


EVIDENCE_DIR = ROOT / "evidence" / "state-validity-frontier-stage1-v0.1"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"


def _load_provenance() -> dict[str, dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    for line in PROVENANCE_PATH.read_text(encoding="utf-8").splitlines():
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError("Malformed Stage-1 provenance row")
        episode_id, member, raw_bytes, raw_sha, compact_sha = fields
        if episode_id in entries:
            raise ValueError("Duplicate Stage-1 provenance episode")
        entries[episode_id] = {
            "member": member,
            "raw_bytes": int(raw_bytes),
            "raw_sha256": raw_sha,
            "compact_record_sha256": compact_sha,
        }

    if set(entries) != set(EPISODES):
        raise ValueError("Stage-1 provenance episode set drift")
    return entries


def verify_artifact(path: Path) -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload = path.read_bytes()
    expected_artifact_sha = manifest["source_artifact_digest"].removeprefix(
        "sha256:"
    )
    if len(payload) != manifest["source_artifact_bytes"]:
        raise ValueError("Stage-1 source artifact byte-size mismatch")
    if sha256(payload).hexdigest() != expected_artifact_sha:
        raise ValueError("Stage-1 source artifact digest mismatch")

    expected_members = {
        row["path"]: row
        for row in manifest.get("source_members") or []
    }
    if not expected_members:
        raise ValueError("Stage-1 manifest is missing source_members")

    provenance = _load_provenance()
    committed = {
        row["episode_id"]: row
        for row in load_frozen_state_validity_frontier_stage1(ROOT)
    }
    verified_runs = []

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if names != set(expected_members):
            missing = sorted(set(expected_members) - names)
            extra = sorted(names - set(expected_members))
            raise ValueError(
                "Stage-1 artifact member mismatch: "
                f"missing={missing}, extra={extra}"
            )

        for name in sorted(names):
            raw = archive.read(name)
            expected = expected_members[name]
            if len(raw) != expected["bytes"]:
                raise ValueError(f"Artifact member byte drift: {name}")
            if sha256(raw).hexdigest() != expected["sha256"]:
                raise ValueError(f"Artifact member digest drift: {name}")

        for episode_id in sorted(EPISODES):
            entry = provenance[episode_id]
            member = str(entry["member"])
            raw = archive.read(member)
            if len(raw) != entry["raw_bytes"]:
                raise ValueError(
                    f"Raw run byte drift for {episode_id}"
                )
            raw_sha = sha256(raw).hexdigest()
            if raw_sha != entry["raw_sha256"]:
                raise ValueError(
                    f"Raw run digest drift for {episode_id}"
                )

            compact = compact_record_from_raw(json.loads(raw))
            compact_sha = sha256(canonical_line(compact)).hexdigest()
            if compact_sha != entry["compact_record_sha256"]:
                raise ValueError(
                    f"Artifact-derived compact digest drift for {episode_id}"
                )
            if canonical_line(compact) != canonical_line(
                committed[episode_id]
            ):
                raise ValueError(
                    f"Committed compact replay is not artifact-derived: "
                    f"{episode_id}"
                )

            verified_runs.append({
                "episode_id": episode_id,
                "artifact_member": member,
                "raw_bytes": len(raw),
                "raw_sha256": raw_sha,
                "compact_record_sha256": compact_sha,
            })

    archive_members = [
        {
            "path": path,
            "bytes": int(expected_members[path]["bytes"]),
            "sha256": expected_members[path]["sha256"],
        }
        for path in sorted(expected_members)
    ]

    return {
        "schema_version": "0.1.0",
        "experiment": "state-validity-frontier-stage1-v0.1",
        "verification_kind": "source_artifact_to_committed_replay",
        "source_workflow_run_id": manifest["source_workflow_run_id"],
        "source_artifact_id": manifest["source_artifact_id"],
        "source_artifact_name": manifest["source_artifact_name"],
        "source_artifact_bytes": manifest["source_artifact_bytes"],
        "source_artifact_sha256": expected_artifact_sha,
        "source_artifact_expires_at": manifest[
            "source_artifact_expires_at"
        ],
        "verified_run_members": verified_runs,
        "archive_members": archive_members,
        "committed_compact_rows_sha256": EXPECTED_ROWS_SHA256,
        "verifier": (
            "scripts/"
            "verify_state_validity_frontier_stage1_source_artifact_v01.py"
        ),
        "result": "verified",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", required=True)
    parser.add_argument("--write-verification")
    args = parser.parse_args()

    result = verify_artifact(Path(args.artifact_zip))
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"

    if args.write_verification:
        Path(args.write_verification).write_text(
            payload,
            encoding="utf-8",
        )

    print("State Validity Frontier Stage-1 source artifact verified.")
    print(payload)


if __name__ == "__main__":
    main()
