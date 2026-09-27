"""Execute exactly one frozen held-out paper-evaluation row.

This script intentionally exposes no research-setting overrides. The only
selectable research dimension is the already-frozen row ID from the development
comparator matrix. Model identity, episodes, repeats, max actions, sampling,
context strategy, and agent pattern are loaded from committed freeze artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import (
    BenchmarkRunner,
    ContextCompiledReactiveLLMPolicy,
    ReActLLMPolicy,
    ReactiveLLMPolicy,
    ScriptedReferencePolicy,
)
from run_reactive_pilot import (
    ensure_fresh_output_dir,
    flatten_result,
    run_pilot,
    summarize,
    write_csv,
)

MATRIX_PATH = (
    ROOT
    / "evidence"
    / "development-comparator-matrix-v0.1"
    / "matrix.json"
)
HELDOUT_MANIFEST_PATH = (
    ROOT
    / "evidence"
    / "heldout-episode-package-v0.1"
    / "manifest.json"
)

EXPECTED_HELDOUT_EPISODES = (
    "electrical-columbus-switchgear-021",
    "electrical-eweb-transformer-022",
    "electrical-lompoc-transformer-023",
    "electrical-njang-generator-024",
    "electrical-port-angeles-transformers-025",
    "electrical-greenport-transformers-026",
    "electrical-san-bruno-ev-chargers-027",
    "electrical-shelter-island-solar-bess-028",
    "electrical-philadelphia-switchgear-mcc-029",
    "electrical-detroit-generator-ats-030",
)

EXPECTED_ROW_IDS = {
    "reference-control",
    "raw-reactive-openai",
    "raw-reactive-anthropic",
    "raw-reactive-gemini",
    "context-compiled-openai",
    "react-openai",
}

EXPECTED_ROW_CONTRACT = {
    "reference-control": {
        "model": None,
        "runs_if_10_episodes": 10,
        "competitive": False,
        "execution_settings": {
            "provider": None,
            "model": None,
            "temperature": None,
            "reasoning_effort": None,
            "max_actions": 50,
            "policy_kind": "reference_control",
            "context_strategy": None,
            "agent_pattern": None,
            "temperature_mode": "not_applicable",
        },
    },
    "raw-reactive-openai": {
        "model": "openai/gpt-5.6-sol",
        "runs_if_10_episodes": 30,
        "competitive": True,
        "execution_settings": {
            "provider": "openai",
            "model": "openai/gpt-5.6-sol",
            "temperature": None,
            "reasoning_effort": "medium",
            "max_actions": 50,
            "policy_kind": "llm_reactive_baseline",
            "context_strategy": None,
            "agent_pattern": None,
            "temperature_mode": "omitted",
        },
    },
    "raw-reactive-anthropic": {
        "model": "anthropic/claude-opus-5-5",
        "runs_if_10_episodes": 30,
        "competitive": True,
        "execution_settings": {
            "provider": "anthropic",
            "model": "anthropic/claude-opus-5-5",
            "temperature": None,
            "reasoning_effort": None,
            "max_actions": 50,
            "policy_kind": "llm_reactive_baseline",
            "context_strategy": None,
            "agent_pattern": None,
            "temperature_mode": "omitted",
        },
    },
    "raw-reactive-gemini": {
        "model": "gemini/gemini-3.8-flash",
        "runs_if_10_episodes": 30,
        "competitive": True,
        "execution_settings": {
            "provider": "gemini",
            "model": "gemini/gemini-3.8-flash",
            "temperature": None,
            "reasoning_effort": None,
            "max_actions": 50,
            "policy_kind": "llm_reactive_baseline",
            "context_strategy": None,
            "agent_pattern": None,
            "temperature_mode": "omitted",
        },
    },
    "context-compiled-openai": {
        "model": "openai/gpt-5.6-sol",
        "runs_if_10_episodes": 30,
        "competitive": True,
        "execution_settings": {
            "provider": "openai",
            "model": "openai/gpt-5.6-sol",
            "temperature": None,
            "reasoning_effort": "medium",
            "max_actions": 50,
            "policy_kind": "llm_context_compiled_reactive",
            "context_strategy": "factual_compiled_v0.1",
            "agent_pattern": None,
            "temperature_mode": "omitted",
        },
    },
    "react-openai": {
        "model": "openai/gpt-5.6-sol",
        "runs_if_10_episodes": 30,
        "competitive": True,
        "execution_settings": {
            "provider": "openai",
            "model": "openai/gpt-5.6-sol",
            "temperature": None,
            "reasoning_effort": "medium",
            "max_actions": 50,
            "policy_kind": "llm_react_comparator",
            "context_strategy": "factual_compiled_v0.1",
            "agent_pattern": "react_v0.1",
            "temperature_mode": "omitted",
        },
    },
}

POLICY_FACTORY_BY_ROW = {
    "raw-reactive-openai": ReactiveLLMPolicy,
    "raw-reactive-anthropic": ReactiveLLMPolicy,
    "raw-reactive-gemini": ReactiveLLMPolicy,
    "context-compiled-openai": ContextCompiledReactiveLLMPolicy,
    "react-openai": ReActLLMPolicy,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_execution_plan() -> dict[str, dict[str, Any]]:
    matrix = _load_json(MATRIX_PATH)
    if matrix.get("status") != "development_comparator_set_frozen":
        raise ValueError("Development comparator matrix is not frozen")

    heldout = _load_json(HELDOUT_MANIFEST_PATH)
    if heldout.get("status") != "heldout_episode_package_frozen":
        raise ValueError("Held-out episode package is not frozen")
    if heldout.get("model_evaluations_run") is not False:
        raise ValueError(
            "Held-out package must be frozen before model evaluation"
        )

    manifest_episodes = tuple(
        row["episode_id"] for row in heldout.get("episodes") or []
    )
    if manifest_episodes != EXPECTED_HELDOUT_EPISODES:
        raise ValueError("Frozen held-out episode order changed")

    protocol = matrix.get("heldout_protocol") or {}
    if protocol.get("heldout_episode_count") != 10:
        raise ValueError("Held-out episode count changed")
    if protocol.get("model_backed_repeats") != 3:
        raise ValueError("Held-out model-backed repeat count changed")
    if protocol.get("reference_control_repeats") != 1:
        raise ValueError("Held-out reference repeat count changed")
    if protocol.get("expected_model_backed_runs") != 150:
        raise ValueError("Frozen model-backed held-out run count changed")
    if protocol.get("expected_reference_control_runs") != 10:
        raise ValueError("Frozen reference-control run count changed")

    rows = protocol.get("eligible_rows") or []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            raise ValueError("Held-out row is missing id")
        if row_id in by_id:
            raise ValueError(f"Duplicate held-out row id: {row_id}")
        by_id[row_id] = row

    if set(by_id) != EXPECTED_ROW_IDS:
        raise ValueError(
            "Frozen held-out row set changed: "
            f"expected={sorted(EXPECTED_ROW_IDS)}, "
            f"actual={sorted(by_id)}"
        )

    plan: dict[str, dict[str, Any]] = {}
    for row_id, expected in EXPECTED_ROW_CONTRACT.items():
        actual = by_id[row_id]
        expected_row = {"id": row_id, **expected}
        if actual != expected_row:
            raise ValueError(
                f"Frozen held-out row contract changed for {row_id}: "
                f"expected={expected_row!r}, actual={actual!r}"
            )

        settings = actual["execution_settings"]
        repeats = 1 if row_id == "reference-control" else 3
        plan[row_id] = {
            "row_id": row_id,
            "model": actual["model"],
            "episodes": list(EXPECTED_HELDOUT_EPISODES),
            "repeats": repeats,
            "expected_runs": actual["runs_if_10_episodes"],
            "competitive": actual["competitive"],
            "provider": settings["provider"],
            "temperature": settings["temperature"],
            "temperature_mode": settings["temperature_mode"],
            "reasoning_effort": settings["reasoning_effort"],
            "max_actions": settings["max_actions"],
            "policy_kind": settings["policy_kind"],
            "context_strategy": settings["context_strategy"],
            "agent_pattern": settings["agent_pattern"],
        }

    model_runs = sum(
        spec["expected_runs"]
        for row_id, spec in plan.items()
        if row_id != "reference-control"
    )
    if model_runs != 150:
        raise ValueError(
            f"Frozen execution plan must contain 150 model runs; "
            f"found {model_runs}"
        )
    if plan["reference-control"]["expected_runs"] != 10:
        raise ValueError("Frozen execution plan must contain 10 reference runs")

    return plan


def _run_reference_row(
    spec: dict[str, Any],
    output_dir: Path,
    runner=None,
):
    output_dir = Path(output_dir)
    ensure_fresh_output_dir(output_dir)
    runner = runner or BenchmarkRunner()
    rows = []

    for episode_id in spec["episodes"]:
        repeat = 1
        run_id = (
            "heldout-reference-control-v0.1"
            f"--{episode_id}--r{repeat:03d}"
        )
        result_path = (
            output_dir
            / "reference-control"
            / episode_id
            / f"run-{repeat:03d}.json"
        )
        result = runner.run(
            ScriptedReferencePolicy(),
            episode_id,
            max_actions=spec["max_actions"],
            run_id=run_id,
            result_path=result_path,
        )
        row = flatten_result(
            result,
            "reference-control",
            repeat,
        )
        rows.append(row)
        print(
            f"reference-control | {episode_id} | r1: "
            f"status={row['status']} "
            f"success={row['episode_success_v02']} "
            f"actions={row['accepted_actions']}"
        )

    summary = summarize(
        rows,
        baseline_name="heldout-reference-control-v0.1",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(rows, output_dir / "runs.csv")
    return rows, summary


def run_row(
    row_id: str,
    output_dir: Path,
    *,
    runner=None,
):
    plan = load_execution_plan()
    if row_id not in plan:
        raise ValueError(
            f"Held-out row {row_id!r} is not frozen for paper evaluation"
        )
    spec = plan[row_id]

    if row_id == "reference-control":
        return _run_reference_row(
            spec,
            Path(output_dir),
            runner=runner,
        )

    policy_factory = POLICY_FACTORY_BY_ROW[row_id]
    return run_pilot(
        [spec["model"]],
        spec["episodes"],
        spec["repeats"],
        Path(output_dir),
        spec["max_actions"],
        runner=runner,
        policy_factory=policy_factory,
        policy_kwargs={
            "temperature": spec["temperature"],
            "reasoning_effort": spec["reasoning_effort"],
        },
        run_prefix=f"heldout-paper-v0.1--{row_id}",
        baseline_name=f"heldout-paper-v0.1--{row_id}",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute one immutable held-out paper-evaluation row. "
            "Research settings are loaded from committed freeze artifacts."
        )
    )
    parser.add_argument(
        "--row",
        required=True,
        choices=sorted(EXPECTED_ROW_IDS),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Fresh directory for raw row evidence.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_row(args.row, Path(args.output_dir))


if __name__ == "__main__":
    main()
