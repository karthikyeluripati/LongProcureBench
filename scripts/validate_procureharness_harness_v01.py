"""Validate ProcureHarness architecture harness v0.1 against protocol #50."""
from __future__ import annotations

import json
from pathlib import Path
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


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _suffixes(episode_ids):
    return [int(e.rsplit("-", 1)[1]) for e in episode_ids]


def validate_harness() -> dict[str, int]:
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
