"""Load the durable frozen 60-run Luna diagnostic evidence."""
from __future__ import annotations

import base64
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

EXPECTED_COMPRESSED_SHA256 = (
    "e67bf0a7408e239cfb677d1f3143e7f09a485f72c714ede4e385115eda577707"
)
EXPECTED_COMPRESSED_BYTES = 18140
EXPECTED_RUNS = 60
EXPECTED_EPISODES = 20
EXPECTED_REPEATS = 3


def source_dir(repo_root: Path) -> Path:
    return (
        Path(repo_root)
        / "evidence"
        / "luna20-diagnostic-v0.1"
    )


def load_frozen_luna20_source(
    repo_root: Path,
) -> list[dict[str, Any]]:
    root = source_dir(repo_root)
    parts = sorted(root.glob("fairness-source.b64.part*"))
    if len(parts) != 6:
        raise ValueError(
            f"Expected 6 frozen source chunks; found {len(parts)}"
        )

    encoded = "".join(
        path.read_text(encoding="utf-8").strip()
        for path in parts
    )
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Frozen source base64 is invalid") from exc

    if len(compressed) != EXPECTED_COMPRESSED_BYTES:
        raise ValueError(
            "Frozen source compressed size mismatch: "
            f"expected={EXPECTED_COMPRESSED_BYTES}, "
            f"actual={len(compressed)}"
        )

    digest = sha256(compressed).hexdigest()
    if digest != EXPECTED_COMPRESSED_SHA256:
        raise ValueError(
            "Frozen source digest mismatch: "
            f"expected={EXPECTED_COMPRESSED_SHA256}, actual={digest}"
        )

    try:
        payload = gzip.decompress(compressed).decode("utf-8")
    except Exception as exc:
        raise ValueError(
            "Frozen source gzip could not be decompressed"
        ) from exc

    runs = [
        json.loads(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    if len(runs) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} frozen runs; found {len(runs)}"
        )

    run_ids = [run.get("run_id") for run in runs]
    if any(not isinstance(run_id, str) for run_id in run_ids):
        raise ValueError("Frozen source contains a missing run_id")
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("Frozen source contains duplicate run_id values")

    counts = Counter(run.get("episode_id") for run in runs)
    if (
        len(counts) != EXPECTED_EPISODES
        or any(count != EXPECTED_REPEATS for count in counts.values())
    ):
        raise ValueError(
            "Expected 20 episodes x 3 repeats; found "
            f"{dict(sorted(counts.items(), key=lambda x: str(x[0])))}"
        )

    return runs
