"""Validate the frozen ProcureHarness fresh package 031-050 v0.1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import FreshScriptedReferencePolicy
MANIFEST_PATH = (
    ROOT / "evidence" / "procureharness-fresh-package-v0.1" / "manifest.json"
)

EXPECTED_VALIDATION = [
    "electrical-imperial-ev-phase1-031",
    "electrical-imperial-ev-phase23-032",
    "electrical-lewiston-ev-chargers-033",
    "electrical-idaho-falls-ev-chargers-034",
    "electrical-union-township-ev-chargers-035",
    "electrical-methuen-stadium-led-036",
    "electrical-philadelphia-led-phase5-037",
    "electrical-hampton-fountain-led-038",
    "electrical-danville-pole-transformer-039",
    "electrical-danville-substation-transformers-040"
]
EXPECTED_FINAL = [
    "electrical-danvers-transformers-041",
    "electrical-rocky-mount-transformer-upgrade-042",
    "electrical-rocky-mount-breakers-043",
    "electrical-siloam-circuit-switchers-044",
    "electrical-eweb-mcc-vfd-plc-045",
    "electrical-odot-alkali-generator-046",
    "electrical-portland-tx-generator-047",
    "electrical-marshfield-generator-048",
    "electrical-dubuque-generator-049",
    "electrical-philadelphia-substation-switchgear-050"
]
EXPECTED_PACKAGES = [
    "us-imperial-ca-ev-phase1-2026-09",
    "us-imperial-ca-ev-phase23-2026-06",
    "us-lewiston-me-ev-chargers-2026-008",
    "us-idaho-falls-ev-build-ifp-26-07",
    "us-union-township-oh-ev-pid122828",
    "us-methuen-ma-mhs-led-lighting-2026",
    "us-philadelphia-led-6711r-b2626934",
    "us-hampton-va-fountain-led-rfp27-14tm",
    "us-danville-va-pole-transformer-qb25-26-075",
    "us-danville-va-substation-transformers-qb25-26-085",
    "us-danvers-ma-transformers-2026-31",
    "us-rocky-mount-nc-substation10-transformer-320-040226fd",
    "us-rocky-mount-nc-69kv-breakers-320-010926fd",
    "us-siloam-springs-ar-69kv-circuit-switchers-2026",
    "us-eweb-mcc-vfd-plc-rfp26-057-gs",
    "us-odot-alkali-lake-generator-00016455",
    "us-portland-tx-generator-rfb6631",
    "us-marshfield-mo-generator-10-15-2025",
    "us-dubuque-county-generator-08042025-it016",
    "us-philadelphia-substation-switchgear-b2625884"
]
EXPECTED_FREEZE_COMMIT = "c04697635bc4dc83a10af3fb9019c8c8b9cc5abe"
EXPECTED_SOURCE_POLICY = (
    "real public buyer notices for initial states; synthetic supplier/quote/event layer only"
)
EXPECTED_MODEL_STATUS = "no model/provider calls executed on episodes 031-050"
EXPECTED_VALIDATION_POLICY = (
    "may be used for bounded architecture-search validation only after this freeze"
)
EXPECTED_FINAL_POLICY = (
    "untouched by model-backed ProcureHarness architecture search until the winning architecture is frozen"
)


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_blob_at_commit(commit: str, path: str) -> str:
    """Resolve the immutable Git blob ID for path at the declared freeze commit."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{commit}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"Frozen path missing at freeze commit: {path}"
        ) from exc
    blob = result.stdout.strip()
    if len(blob) != 40:
        raise ValueError(f"Invalid frozen blob ID for {path}: {blob!r}")
    return blob


def validate_manifest(manifest=None) -> None:
    if manifest is None:
        manifest = _load(MANIFEST_PATH)

    if manifest.get("schema_version") != "0.1.0":
        raise ValueError("Fresh-package schema version changed")
    if manifest.get("package") != "procureharness-fresh-package-v0.1":
        raise ValueError("Fresh-package identity changed")
    if manifest.get("freeze_commit") != EXPECTED_FREEZE_COMMIT:
        raise ValueError("Fresh-package freeze commit changed")
    if manifest.get("source_policy") != EXPECTED_SOURCE_POLICY:
        raise ValueError("Fresh-package source policy changed")
    if manifest.get("model_execution_status_at_freeze") != EXPECTED_MODEL_STATUS:
        raise ValueError("Fresh-package pre-freeze model status changed")

    validation = manifest.get("validation_split") or {}
    final = manifest.get("final_split") or {}
    if validation.get("episode_ids") != EXPECTED_VALIDATION:
        raise ValueError("Validation split must remain exactly 031-040")
    if final.get("episode_ids") != EXPECTED_FINAL:
        raise ValueError("Final split must remain exactly 041-050")
    if validation.get("exposure_policy") != EXPECTED_VALIDATION_POLICY:
        raise ValueError("Validation exposure policy changed")
    if final.get("exposure_policy") != EXPECTED_FINAL_POLICY:
        raise ValueError("Final exposure policy changed")

    package_ids = manifest.get("package_ids")
    if package_ids != EXPECTED_PACKAGES:
        raise ValueError("Fresh package IDs changed")
    if len(set(package_ids)) != 20:
        raise ValueError("Fresh package IDs must be unique")

    frozen = manifest.get("frozen_files")
    if not isinstance(frozen, list) or manifest.get("frozen_file_count") != 60:
        raise ValueError("Fresh package must freeze exactly 60 data files")
    if len(frozen) != 60:
        raise ValueError("Fresh package frozen-file list must have 60 entries")

    paths = [row.get("path") for row in frozen]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate frozen path")
    if paths != sorted(paths):
        raise ValueError("Frozen file list must be sorted")

    expected_paths = sorted(
        [f"data/initial_states/electrical/{pkg}.json" for pkg in EXPECTED_PACKAGES]
        + [f"data/episodes/electrical/{eid}.json" for eid in EXPECTED_VALIDATION + EXPECTED_FINAL]
        + [f"data/evaluation/electrical/{eid}.json" for eid in EXPECTED_VALIDATION + EXPECTED_FINAL]
    )
    if paths != expected_paths:
        raise ValueError("Frozen path set changed")

    for row in frozen:
        relpath = row["path"]
        path = ROOT / relpath
        if not path.is_file():
            raise ValueError(f"Missing frozen file: {relpath}")

        immutable_blob = frozen_blob_at_commit(
            EXPECTED_FREEZE_COMMIT,
            relpath,
        )
        declared_blob = row.get("git_blob_sha1")
        if declared_blob != immutable_blob:
            raise ValueError(
                f"Manifest hash does not match freeze commit: {relpath}"
            )

        observed = git_blob_sha1(path.read_bytes())
        if observed != immutable_blob:
            raise ValueError(f"Frozen file drift: {relpath}")

    seen_packages = []
    for eid in EXPECTED_VALIDATION + EXPECTED_FINAL:
        episode_path = ROOT / "data" / "episodes" / "electrical" / f"{eid}.json"
        eval_path = ROOT / "data" / "evaluation" / "electrical" / f"{eid}.json"
        episode = _load(episode_path)
        config = _load(eval_path)

        if episode.get("episode_id") != eid or config.get("episode_id") != eid:
            raise ValueError(f"Episode/evaluation identity mismatch: {eid}")
        if episode.get("realism", {}).get("initial_state_data") != "real_public":
            raise ValueError(f"Fresh episode is not real-public grounded: {eid}")
        ref = episode.get("initial_state_ref") or {}
        if ref.get("grounding") != "real_public":
            raise ValueError(f"Fresh episode grounding changed: {eid}")
        seen_packages.append(ref.get("package_id"))

    if seen_packages != EXPECTED_PACKAGES:
        raise ValueError("Episode-to-package mapping changed")

    urls = []
    for pkg in EXPECTED_PACKAGES:
        state = _load(
            ROOT / "data" / "initial_states" / "electrical" / f"{pkg}.json"
        )
        if state.get("package_id") != pkg:
            raise ValueError(f"Initial-state package mismatch: {pkg}")
        docs = state.get("supporting_documents") or []
        if not docs:
            raise ValueError(f"Fresh state has no public source: {pkg}")
        urls.append(docs[0].get("url"))

    if len(set(urls)) != 20:
        raise ValueError("Fresh states must use 20 distinct public source URLs")

    reference_ids = FreshScriptedReferencePolicy.episode_ids()
    if reference_ids != EXPECTED_VALIDATION + EXPECTED_FINAL:
        raise ValueError(
            "Fresh reference control must cover exactly episodes 031-050"
        )


def main() -> None:
    validate_manifest()
    print("PASS ProcureHarness fresh package 031-050 v0.1")


if __name__ == "__main__":
    main()
