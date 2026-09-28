"""Verify frozen SVF development replay against its source Actions artifact."""
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

from frozen_state_validity_frontier_development_v02 import (
    EPISODES,
    EXPECTED_ROWS_SHA256,
    canonical_line,
    compact_record_from_raw,
    load_frozen_state_validity_frontier_development_v02,
)


EVIDENCE_DIR = (
    ROOT / "evidence" / "state-validity-frontier-development-v0.2"
)
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
PROVENANCE_PATH = EVIDENCE_DIR / "source-provenance.txt"


def _load_provenance() -> dict[tuple[str, int], dict[str, object]]:
    entries = {}
    for line in PROVENANCE_PATH.read_text(encoding="utf-8").splitlines():
        fields = line.split("|")
        if len(fields) != 6:
            raise ValueError("Malformed SVF development provenance row")
        episode_id, repeat, member, raw_bytes, raw_sha, compact_sha = fields
        key = (episode_id, int(repeat))
        if key in entries:
            raise ValueError("Duplicate SVF development provenance key")
        entries[key] = {
            "member": member,
            "raw_bytes": int(raw_bytes),
            "raw_sha256": raw_sha,
            "compact_record_sha256": compact_sha,
        }
    expected = {
        (episode_id, repeat)
        for episode_id in EPISODES
        for repeat in (1, 2, 3)
    }
    if set(entries) != expected:
        raise ValueError("SVF development provenance grid drift")
    return entries


def verify_artifact(path: Path) -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload = path.read_bytes()
    expected_artifact_sha = manifest["source_artifact_digest"].removeprefix(
        "sha256:"
    )
    if len(payload) != manifest["source_artifact_bytes"]:
        raise ValueError("SVF development source artifact byte-size mismatch")
    if sha256(payload).hexdigest() != expected_artifact_sha:
        raise ValueError("SVF development source artifact digest mismatch")

    expected_members = {
        row["path"]: row
        for row in manifest.get("source_members") or []
    }
    if not expected_members:
        raise ValueError("SVF development manifest is missing source_members")

    provenance = _load_provenance()
    committed = {
        (row["episode_id"], row["repeat"]): row
        for row in load_frozen_state_validity_frontier_development_v02(ROOT)
    }

    with zipfile.ZipFile(path) as archive:
        names = [
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
        ]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate source artifact members")
        if set(names) != set(expected_members):
            raise ValueError(
                "SVF development artifact member mismatch: "
                f"missing={sorted(set(expected_members) - set(names))}, "
                f"extra={sorted(set(names) - set(expected_members))}"
            )

        for name in sorted(names):
            raw = archive.read(name)
            expected = expected_members[name]
            if len(raw) != expected["bytes"]:
                raise ValueError(f"Artifact member byte drift: {name}")
            if sha256(raw).hexdigest() != expected["sha256"]:
                raise ValueError(f"Artifact member digest drift: {name}")

        for key in sorted(provenance):
            episode_id, repeat = key
            entry = provenance[key]
            member = str(entry["member"])
            raw = archive.read(member)
            if len(raw) != entry["raw_bytes"]:
                raise ValueError(f"Raw run byte drift for {key}")
            raw_sha = sha256(raw).hexdigest()
            if raw_sha != entry["raw_sha256"]:
                raise ValueError(f"Raw run digest drift for {key}")

            compact = compact_record_from_raw(json.loads(raw), repeat)
            compact_sha = sha256(canonical_line(compact)).hexdigest()
            if compact_sha != entry["compact_record_sha256"]:
                raise ValueError(f"Artifact-derived compact digest drift for {key}")
            if canonical_line(compact) != canonical_line(committed[key]):
                raise ValueError(
                    f"Committed compact replay is not artifact-derived: {key}"
                )

    source_members = manifest["source_members"]
    source_members_payload = (
        json.dumps(source_members, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    provenance_payload = PROVENANCE_PATH.read_bytes()

    return {
        "schema_version": "0.2.0",
        "experiment": "state-validity-frontier-development-v0.2",
        "verification_kind": "source_artifact_to_committed_replay",
        "source_workflow_run_id": manifest["source_workflow_run_id"],
        "source_artifact_id": manifest["source_artifact_id"],
        "source_artifact_name": manifest["source_artifact_name"],
        "source_artifact_bytes": manifest["source_artifact_bytes"],
        "source_artifact_sha256": expected_artifact_sha,
        "source_artifact_expires_at": manifest["source_artifact_expires_at"],
        "source_members_count": len(source_members),
        "source_members_sha256": sha256(source_members_payload).hexdigest(),
        "provenance_sha256": sha256(provenance_payload).hexdigest(),
        "committed_compact_rows_sha256": EXPECTED_ROWS_SHA256,
        "verifier": (
            "scripts/"
            "verify_state_validity_frontier_development_source_artifact_v02.py"
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
        Path(args.write_verification).write_text(payload, encoding="utf-8")
    print("SVF development source artifact verified.")
    print(payload)


if __name__ == "__main__":
    main()
