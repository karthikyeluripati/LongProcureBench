"""Validate ProcureHarness architecture harness v0.1 against protocol #50."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench.procureharness import (
    CANDIDATE_CONFIGS,
    MAX_LOCAL_PLAN_STEPS,
    MAX_MODEL_CALLS_BETWEEN_ACCEPTED_ACTIONS,
    MAX_REACT_FALLBACK_ACTIONS,
    ROUTING_CHOICES,
    PLANNING_CHOICES,
    REASONING_CHOICES,
    VERIFICATION_CHOICES,
    FALLBACK_CHOICES,
    candidate_registry,
    validate_candidate_registry,
)
from run_procureharness_search_v01 import (
    DEVELOPMENT_EPISODES,
    MAX_ACTIONS,
    MODEL,
    PHASES,
    REASONING_EFFORT,
    TEMPERATURE,
    VALIDATION_EPISODES,
)

PROTOCOL_PATH = ROOT / "docs" / "procureharness-architecture-search-v0.1-protocol.json"
REGISTRY_PATH = ROOT / "docs" / "procureharness-candidate-registry-v0.1.json"
IMPLEMENTATION_MANIFEST_PATH = (
    ROOT
    / "evidence"
    / "procureharness-architecture-harness-v0.1"
    / "manifest.json"
)
EXPECTED_IMPLEMENTATION_FREEZE_COMMIT = (
    "16357d8a8393043e2457d60c03fa0a2f3bcd8dd4"
)
EXPECTED_IMPLEMENTATION_BLOBS = {
    "docs/procureharness-architecture-harness-v0.1.md": "5791a6d11ca6fe39bc6472f0ec03cf75d9fd9697",
    "docs/procureharness-candidate-registry-v0.1.json": "3c0485825224daff9b6cb064241488233fc89f0d",
    "longprocurebench/context_compiled_reactive.py": "82b102d60c077247672d3d9ba1377243233672a9",
    "longprocurebench/evaluator.py": "ef0204f605027bafde6839cce2f14a03d15425bd",
    "longprocurebench/litellm_client.py": "3726f763e9e88bbfcf9073ee79db86e98e58e0d1",
    "longprocurebench/procureharness.py": "b71f91e1191b3f54ae371c9b3844d41ad6f84c98",
    "longprocurebench/reactive_llm.py": "d237f262b0377ae78608fb28833adfa6f2ff5853",
    "longprocurebench/runner.py": "a5108b71b0d7e67d91ffa0492e298508a26ff573",
    "longprocurebench/runtime.py": "3f283ed874db363d849ff759a108f4d650336760",
    "longprocurebench/validation.py": "98f27230d28144b063cb910b5b99886d920d966b",
    "requirements.txt": "698ec65e21cd73df53c948ed5e7770746c804bc4",
    "schema/action.schema.json": "b47589fd82f97b5d49415d48cc8fd29cbfa17b22",
    "schema/episode.schema.json": "3bf03a9d3b3c8b8d4b7a0ebea6856c95f9998939",
    "schema/evaluation.schema.json": "031a8a72e68a904ba51054ff7db68ef4a513991c",
    "schema/initial-state.schema.json": "0b8269964b5d7c5d1a09e1fdf4091c4e7f8d9926",
    "schema/result.schema.json": "1c16655142c02eada9c045010b414bae207e1e1b",
    "scripts/run_procureharness_search_v01.py": "4fbd50327981452c2557b1872d23c7cf7039b558",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _suffixes(episode_ids):
    return [int(e.rsplit("-", 1)[1]) for e in episode_ids]


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def frozen_blob_at_commit(commit: str, path: str) -> str:
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
            f"Frozen implementation path missing at snapshot commit: {path}"
        ) from exc
    blob = result.stdout.strip()
    if len(blob) != 40:
        raise ValueError(
            f"Invalid frozen implementation blob for {path}: {blob!r}"
        )
    return blob


def validate_implementation_freeze(manifest=None) -> None:
    manifest = (
        _load(IMPLEMENTATION_MANIFEST_PATH)
        if manifest is None
        else manifest
    )
    if manifest.get("schema_version") != "0.1.0":
        raise ValueError("implementation manifest schema version changed")
    if manifest.get("package") != "procureharness-architecture-harness-v0.1":
        raise ValueError("implementation manifest package identity changed")
    if manifest.get("protocol_id") != "procureharness-architecture-search-v0.1":
        raise ValueError("implementation manifest protocol identity changed")
    if manifest.get("freeze_commit") != EXPECTED_IMPLEMENTATION_FREEZE_COMMIT:
        raise ValueError("implementation freeze commit changed")
    if manifest.get("freeze_status") != "implementation_frozen_no_model_runs":
        raise ValueError("implementation freeze status changed")
    if manifest.get("model_execution_status_at_freeze") != (
        "no ProcureHarness model/provider search runs executed"
    ):
        raise ValueError("implementation pre-run status changed")

    rows = manifest.get("frozen_files")
    if not isinstance(rows, list):
        raise ValueError("implementation frozen_files must be a list")
    observed_map = {
        row.get("path"): row.get("git_blob_sha1")
        for row in rows
        if isinstance(row, dict)
    }
    if observed_map != EXPECTED_IMPLEMENTATION_BLOBS:
        raise ValueError("implementation manifest blob map changed")

    for path, expected_blob in EXPECTED_IMPLEMENTATION_BLOBS.items():
        immutable = frozen_blob_at_commit(
            EXPECTED_IMPLEMENTATION_FREEZE_COMMIT,
            path,
        )
        if immutable != expected_blob:
            raise ValueError(
                f"hard-coded implementation blob disagrees with snapshot: {path}"
            )
        current_path = ROOT / path
        if not current_path.is_file():
            raise ValueError(f"missing frozen implementation file: {path}")
        current = git_blob_sha1(current_path.read_bytes())
        if current != expected_blob:
            raise ValueError(f"frozen implementation drift: {path}")


def validate_harness() -> dict[str, int]:
    validate_implementation_freeze()
    validate_candidate_registry()
    protocol = _load(PROTOCOL_PATH)
    registry = _load(REGISTRY_PATH)

    if protocol.get("protocol_id") != "procureharness-architecture-search-v0.1":
        raise ValueError("architecture-search protocol identity changed")
    if registry.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("candidate registry protocol mismatch")
    if registry.get("status") != "implementation_frozen_no_model_runs":
        raise ValueError("candidate registry status changed")

    budget = registry.get("search_budget")
    if budget != {
        "max_rounds": 3,
        "max_new_candidates_per_round": 6,
        "max_unique_candidates": 18,
    }:
        raise ValueError("candidate registry search budget changed")
    procedure = protocol["search_procedure"]
    if budget != {
        "max_rounds": procedure["max_rounds"],
        "max_new_candidates_per_round": procedure["max_new_candidates_per_round"],
        "max_unique_candidates": procedure["max_unique_candidates"],
    }:
        raise ValueError("candidate registry budget disagrees with protocol")

    code_rows = candidate_registry()
    json_rows = [
        {
            key: row[key]
            for key in (
                "candidate_id",
                "round",
                "obligation_routing",
                "local_planning",
                "skill_reasoning",
                "verification",
                "fallback",
            )
        }
        for row in registry["candidates"]
    ]
    if json_rows != code_rows:
        raise ValueError("candidate registry JSON/code drift")

    axis_names = (
        "obligation_routing",
        "local_planning",
        "skill_reasoning",
        "verification",
        "fallback",
    )
    seen_candidates = {}
    for row in registry["candidates"]:
        candidate_id = row["candidate_id"]
        parents = row.get("parent_candidates")
        deltas = row.get("module_deltas")
        if not isinstance(parents, list) or not isinstance(deltas, list):
            raise ValueError(
                f"candidate lineage metadata missing: {candidate_id}"
            )

        for parent_id in parents:
            parent = seen_candidates.get(parent_id)
            if parent is None:
                raise ValueError(
                    f"candidate parent must precede child: "
                    f"{candidate_id} -> {parent_id}"
                )
            if parent["round"] > row["round"]:
                raise ValueError(
                    f"candidate parent cannot come from a later round: "
                    f"{candidate_id} -> {parent_id}"
                )

        if not parents:
            if candidate_id != "ph-r1-c01":
                raise ValueError(
                    "only ph-r1-c01 may be the lineage seed"
                )
            if {delta.get("axis") for delta in deltas} != set(axis_names):
                raise ValueError(
                    "seed candidate must declare all five architecture axes"
                )
            for delta in deltas:
                if (
                    delta.get("relative_to") is not None
                    or delta.get("from") is not None
                    or delta.get("to") != row[delta["axis"]]
                ):
                    raise ValueError("seed candidate lineage delta changed")
        else:
            primary_id = parents[0]
            reconstructed = {
                axis: seen_candidates[primary_id][axis]
                for axis in axis_names
            }
            for delta in deltas:
                axis = delta.get("axis")
                if axis not in axis_names:
                    raise ValueError(
                        f"unknown lineage axis for {candidate_id}: {axis!r}"
                    )
                if delta.get("relative_to") != primary_id:
                    raise ValueError(
                        f"lineage delta relative_to mismatch for {candidate_id}"
                    )
                if delta.get("from") != reconstructed[axis]:
                    raise ValueError(
                        f"lineage delta from-value mismatch for {candidate_id}"
                    )
                reconstructed[axis] = delta.get("to")

            if reconstructed != {
                axis: row[axis]
                for axis in axis_names
            }:
                raise ValueError(
                    f"candidate module deltas do not reproduce config: "
                    f"{candidate_id}"
                )

        seen_candidates[candidate_id] = row

    axes = {
        row["name"]: set(row["choices"])
        for row in protocol["architecture_grammar"]["searchable_axes"]
    }
    expected_axes = {
        "obligation_routing": set(ROUTING_CHOICES),
        "local_planning": set(PLANNING_CHOICES),
        "skill_reasoning": set(REASONING_CHOICES),
        "verification": set(VERIFICATION_CHOICES),
        "fallback": set(FALLBACK_CHOICES),
    }
    if axes != expected_axes:
        raise ValueError("controller search axes disagree with protocol")

    protocol_limits = protocol["architecture_grammar"]["hard_complexity_limits"]
    code_limits = {
        "max_model_calls_between_accepted_actions": MAX_MODEL_CALLS_BETWEEN_ACCEPTED_ACTIONS,
        "max_local_plan_steps": MAX_LOCAL_PLAN_STEPS,
        "max_react_fallback_actions": MAX_REACT_FALLBACK_ACTIONS,
        "multi_agent": False,
        "persistent_cross_episode_memory": False,
    }
    if code_limits != protocol_limits:
        raise ValueError("controller complexity limits disagree with protocol")
    if registry["hard_complexity_limits"] != protocol_limits:
        raise ValueError("registry complexity limits disagree with protocol")

    if registry["deferred_axes"] != protocol["architecture_grammar"]["deferred_harness_axes"]:
        raise ValueError("deferred architecture axes changed")

    defaults = protocol["execution_defaults"]
    expected_defaults = {
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "temperature": TEMPERATURE,
        "max_actions": MAX_ACTIONS,
    }
    observed_defaults = {
        "model": defaults["model"],
        "reasoning_effort": defaults["reasoning_effort"],
        "temperature": defaults["temperature"],
        "max_actions": defaults["max_actions"],
    }
    if expected_defaults != observed_defaults:
        raise ValueError("search runner execution defaults disagree with protocol")

    if _suffixes(DEVELOPMENT_EPISODES) != list(range(1, 21)):
        raise ValueError("development search episodes must remain exactly 001-020")
    if _suffixes(VALIDATION_EPISODES) != list(range(31, 41)):
        raise ValueError("validation episodes must remain exactly 031-040")
    if set(PHASES) != {
        "screening",
        "development_confirmation",
        "validation",
    }:
        raise ValueError("search runner executable phases changed")
    if any(
        41 <= suffix <= 50
        for spec in PHASES.values()
        for suffix in _suffixes(spec["episodes"])
    ):
        raise ValueError("search runner must never expose 041-050")

    if PHASES["screening"]["repeats"] != 1:
        raise ValueError("screening repeat count changed")
    if PHASES["development_confirmation"]["repeats"] != 3:
        raise ValueError("development confirmation repeat count changed")
    if PHASES["validation"]["repeats"] != 3:
        raise ValueError("validation repeat count changed")

    fresh_manifest = _load(
        ROOT / "evidence" / "procureharness-fresh-package-v0.1" / "manifest.json"
    )
    if fresh_manifest["validation_split"]["episode_ids"] != VALIDATION_EPISODES:
        raise ValueError("search validation IDs disagree with frozen fresh package")
    final_ids = fresh_manifest["final_split"]["episode_ids"]
    if _suffixes(final_ids) != list(range(41, 51)):
        raise ValueError("fresh final split must remain exactly 041-050")

    return {
        "candidates": len(CANDIDATE_CONFIGS),
        "rounds": 3,
        "development_episodes": len(DEVELOPMENT_EPISODES),
        "validation_episodes": len(VALIDATION_EPISODES),
        "final_episodes_exposed": 0,
    }


def main():
    summary = validate_harness()
    print(
        "PASS ProcureHarness architecture harness v0.1: "
        f"{summary['candidates']} candidates, "
        f"{summary['rounds']} rounds, "
        f"{summary['development_episodes']} development episodes, "
        f"{summary['validation_episodes']} validation episodes, "
        "0 final episodes exposed"
    )


if __name__ == "__main__":
    main()
