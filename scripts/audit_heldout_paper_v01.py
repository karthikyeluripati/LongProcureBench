"""Audit and freeze the completed held-out paper evaluation evidence."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from hashlib import sha1, sha256
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]

from aggregate_heldout_matrix_results_v01 import aggregate_matrix
from longprocurebench.context_compiled_reactive import compact_visible_event
from run_heldout_paper_row import (
    EXPECTED_HELDOUT_EPISODES,
    EXPECTED_ROW_IDS,
    load_execution_plan,
)
from run_reactive_pilot import model_slug
from validate_heldout_row_results_v01 import validate_row_results

EVIDENCE_DIR = (
    ROOT / "evidence" / "heldout-paper-evaluation-v0.1"
)
SOURCE_DIR = EVIDENCE_DIR / "source-artifacts"
RESULTS_PATH = EVIDENCE_DIR / "results.json"
TAXONOMY_PATH = EVIDENCE_DIR / "failure-taxonomy.json"
MANIFEST_PATH = EVIDENCE_DIR / "results-manifest.json"

SOURCE_WORKFLOW_RUN_ID = 36329287113
SOURCE_HEAD_SHA = "cf725f239fcc76cba1f0e2e51fee9d726fbca590"
SOURCE_RUN_ATTEMPT = 1
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SAMPLER = "sha256-index-v1"

ROW_ORDER = [
    "raw-reactive-openai",
    "raw-reactive-anthropic",
    "raw-reactive-gemini",
    "context-compiled-openai",
    "react-openai",
]
MATCHED_ROWS = [
    "raw-reactive-openai",
    "context-compiled-openai",
    "react-openai",
]
CONTEXT_ROW = "context-compiled-openai"

SOURCE_ARTIFACTS = {
    "reference-control": {
        "artifact_id": 10934782476,
        "artifact_name": "heldout-reference-control-36329287113",
        "path": "source-artifacts/heldout-reference-control-36329287113.zip",
        "bytes": 30675,
        "sha256": "13baa4585a098347fe418ce28732082e198ff6d1b4508df6a1e97fd7a257a2b4",
        "git_blob_sha": "48a1328f7d49e8877ad5d39d70e455b1ad7d2da6",
    },
    "raw-reactive-openai": {
        "artifact_id": 10935062553,
        "artifact_name": "heldout-raw-reactive-openai-36329287113",
        "path": "source-artifacts/heldout-raw-reactive-openai-36329287113.zip",
        "bytes": 103221,
        "sha256": "7aca3f5ff235b391ea79b2d2e877837382365f929f29fda7ba309ca64cf81ddd",
        "git_blob_sha": "43adf1aa586688563945aa5e2c7ef6b424a5035c",
    },
    "raw-reactive-anthropic": {
        "artifact_id": 10935671154,
        "artifact_name": "heldout-raw-reactive-anthropic-36329287113",
        "path": "source-artifacts/heldout-raw-reactive-anthropic-36329287113.zip",
        "bytes": 101808,
        "sha256": "63825363ec04321de0c8b75596e932e394605a97999f5d35d5f3def667019a68",
        "git_blob_sha": "1764c3047255b075450a6715ddac0685fcb351b8",
    },
    "raw-reactive-gemini": {
        "artifact_id": 10935288077,
        "artifact_name": "heldout-raw-reactive-gemini-36329287113",
        "path": "source-artifacts/heldout-raw-reactive-gemini-36329287113.zip",
        "bytes": 100872,
        "sha256": "107a696e1b744e877c6dd5170f8558a96e04da2aae604317792ced72227c4313",
        "git_blob_sha": "85c32853001ed2cb02e54cc8288242b48b7aee8e",
    },
    "context-compiled-openai": {
        "artifact_id": 10935671643,
        "artifact_name": "heldout-context-compiled-openai-36329287113",
        "path": "source-artifacts/heldout-context-compiled-openai-36329287113.zip",
        "bytes": 103738,
        "sha256": "1533556c1f59b338a53fd81dce7eb43e0d64dcdea19977b7e3c4e5f90aba6e20",
        "git_blob_sha": "50144e3a84a0371b94973c70aa783f3f2fa009a3",
    },
    "react-openai": {
        "artifact_id": 10935443329,
        "artifact_name": "heldout-react-openai-36329287113",
        "path": "source-artifacts/heldout-react-openai-36329287113.zip",
        "bytes": 142047,
        "sha256": "9c1448ad33b0db4a237cf62e6983d44de9f30fddf7aaff567503d0125db3fc11",
        "git_blob_sha": "0e93f32c8e4f3fc0e12173c68540ff681b085a74",
    },
    "aggregate": {
        "artifact_id": 10935910728,
        "artifact_name": "heldout-paper-matrix-36329287113",
        "path": "source-artifacts/heldout-paper-matrix-36329287113.zip",
        "bytes": 9323,
        "sha256": "805ff7e625f564e263d772995df8d4407538f01401af1b91356f2cc565ea6e53",
        "git_blob_sha": "e63673701a4307f7ec7b92fbde932ca87052a8ed",
    },
}


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    return sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload
    ).hexdigest()


def _verify_source_artifact(
    source_dir: Path,
    key: str,
) -> Path:
    spec = SOURCE_ARTIFACTS[key]
    path = source_dir / Path(spec["path"]).name
    if not path.is_file():
        raise ValueError(f"Missing held-out source artifact: {path}")
    payload = path.read_bytes()
    if len(payload) != spec["bytes"]:
        raise ValueError(
            f"Held-out source artifact byte drift for {key}: "
            f"expected={spec['bytes']}, actual={len(payload)}"
        )
    actual_sha = sha256(payload).hexdigest()
    if actual_sha != spec["sha256"]:
        raise ValueError(
            f"Held-out source artifact digest drift for {key}: "
            f"expected={spec['sha256']}, actual={actual_sha}"
        )
    actual_blob = _git_blob_sha(path)
    if actual_blob != spec["git_blob_sha"]:
        raise ValueError(
            f"Held-out source artifact git-blob drift for {key}: "
            f"expected={spec['git_blob_sha']}, actual={actual_blob}"
        )
    return path


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(
                    f"Unsafe held-out artifact member: {name!r}"
                )
            target = (destination / name).resolve()
            if target != root and root not in target.parents:
                raise ValueError(
                    f"Held-out artifact member escapes root: {name!r}"
                )
        handle.extractall(destination)


def _expected_row_archive_members(
    row_id: str,
    spec: dict[str, Any],
) -> set[str]:
    root = (
        "reference-control"
        if row_id == "reference-control"
        else model_slug(spec["model"])
    )
    members = {
        (
            f"{root}/{episode_id}/"
            f"run-{repeat:03d}.json"
        )
        for episode_id in EXPECTED_HELDOUT_EPISODES
        for repeat in range(1, spec["repeats"] + 1)
    }
    members.update({
        "runs.csv",
        "summary.json",
        "validated-row.json",
    })
    return members


def _validate_archive_members(
    archive: Path,
    key: str,
    plan: dict[str, dict[str, Any]],
) -> None:
    with zipfile.ZipFile(archive) as handle:
        names = [
            info.filename
            for info in handle.infolist()
            if not info.is_dir()
        ]

    if len(names) != len(set(names)):
        duplicates = sorted(
            name
            for name, count in Counter(names).items()
            if count > 1
        )
        raise ValueError(
            f"Duplicate members in held-out source artifact {key}: "
            f"{duplicates}"
        )

    expected = (
        {
            "heldout-runs.csv",
            "heldout-matrix-manifest.json",
        }
        if key == "aggregate"
        else _expected_row_archive_members(key, plan[key])
    )
    actual = set(names)
    if actual != expected:
        raise ValueError(
            f"Held-out source artifact member drift for {key}: "
            f"missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _validate_react_transcripts(
    row_dir: Path,
    spec: dict[str, Any],
) -> None:
    root = row_dir / model_slug(spec["model"])
    checked = 0

    for episode_id in EXPECTED_HELDOUT_EPISODES:
        for repeat in range(1, spec["repeats"] + 1):
            path = (
                root
                / episode_id
                / f"run-{repeat:03d}.json"
            )
            result = json.loads(path.read_text(encoding="utf-8"))
            metrics = result.get("policy_metrics") or {}
            transcript = metrics.get("react_transcript")
            trajectory = result.get("trajectory") or []

            if not isinstance(transcript, list):
                raise ValueError(
                    f"Missing ReAct transcript: "
                    f"{episode_id} r{repeat}"
                )
            if len(transcript) != len(trajectory):
                raise ValueError(
                    f"ReAct transcript/trajectory length drift: "
                    f"{episode_id} r{repeat} "
                    f"transcript={len(transcript)} "
                    f"trajectory={len(trajectory)}"
                )
            if metrics.get("react_steps_accepted") != len(trajectory):
                raise ValueError(
                    f"ReAct accepted-step count drift: "
                    f"{episode_id} r{repeat}"
                )

            thought_lengths = []
            for index, (entry, step) in enumerate(
                zip(transcript, trajectory),
                start=1,
            ):
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"Malformed ReAct transcript entry: "
                        f"{episode_id} r{repeat} step {index}"
                    )
                if entry.get("step") != step.get("step"):
                    raise ValueError(
                        f"ReAct transcript step drift: "
                        f"{episode_id} r{repeat} step {index}"
                    )

                thought = entry.get("thought_summary")
                if not isinstance(thought, str) or not thought.strip():
                    raise ValueError(
                        f"Missing ReAct thought summary: "
                        f"{episode_id} r{repeat} step {index}"
                    )
                thought_lengths.append(len(thought))

                semantic_action = {
                    key: value
                    for key, value in (step.get("action") or {}).items()
                    if key not in {"action_id", "episode_id"}
                }
                if entry.get("action") != semantic_action:
                    raise ValueError(
                        f"ReAct transcript action drift: "
                        f"{episode_id} r{repeat} step {index}"
                    )

                compact_observations = [
                    compact
                    for compact in (
                        compact_visible_event(observation)
                        for observation in (
                            step.get("observations") or []
                        )
                    )
                    if compact is not None
                ]
                if entry.get("observation") != compact_observations:
                    raise ValueError(
                        f"ReAct transcript observation drift: "
                        f"{episode_id} r{repeat} step {index}"
                    )

            total_chars = sum(thought_lengths)
            max_chars = max(thought_lengths, default=0)
            mean_chars = (
                total_chars / len(thought_lengths)
                if thought_lengths
                else None
            )
            if metrics.get("react_thought_chars_total") != total_chars:
                raise ValueError(
                    f"ReAct thought total drift: "
                    f"{episode_id} r{repeat}"
                )
            if metrics.get("react_thought_chars_max") != max_chars:
                raise ValueError(
                    f"ReAct thought max drift: "
                    f"{episode_id} r{repeat}"
                )
            actual_mean = metrics.get("react_thought_chars_mean")
            if mean_chars is None:
                if actual_mean is not None:
                    raise ValueError(
                        f"ReAct thought mean drift: "
                        f"{episode_id} r{repeat}"
                    )
            elif not isinstance(actual_mean, (int, float)) or not math.isclose(
                float(actual_mean),
                mean_chars,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"ReAct thought mean drift: "
                    f"{episode_id} r{repeat}"
                )

            checked += 1

    if checked != spec["expected_runs"]:
        raise ValueError(
            f"ReAct transcript coverage drift: "
            f"expected={spec['expected_runs']}, actual={checked}"
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _as_bool(value: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"Unexpected boolean CSV value: {value!r}")


def _as_int(value: str | None) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def _as_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _typed_rows(
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    typed = []
    for row in rows:
        typed.append({
            **row,
            "repeat": int(row["repeat"]),
            "terminal_feasible": _as_bool(row["terminal_feasible"]),
            "feasible_obligation_success": _as_bool(
                row["feasible_obligation_success"]
            ),
            "episode_success_v02": _as_bool(row["episode_success_v02"]),
            "economic_objective_satisfied": _as_bool(
                row["economic_objective_satisfied"]
            ),
            "obligations_actionable": _as_int(
                row["obligations_actionable"]
            ),
            "obligations_resolved": _as_int(
                row["obligations_resolved"]
            ),
            "obligations_unresolved": _as_int(
                row["obligations_unresolved"]
            ),
            "accepted_actions": _as_int(row["accepted_actions"]),
            "model_calls": _as_int(row["model_calls"]),
            "total_tokens": _as_int(row["total_tokens"]),
            "latency_ms": _as_float(row["latency_ms"]),
            "cost_usd": _as_float(row["cost_usd"]),
        })
    return typed


def _raw_results(row_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(row_dir.rglob("run-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        records.append(record)
    return records


def _raw_metrics(
    row_dir: Path,
) -> dict[str, Any]:
    prompt = completion = calls = failed = 0
    actions = Counter()
    for result in _raw_results(row_dir):
        metrics = result.get("policy_metrics") or {}
        prompt += int(metrics.get("prompt_tokens") or 0)
        completion += int(metrics.get("completion_tokens") or 0)
        calls += int(metrics.get("model_calls_attempted") or 0)
        failed += int(metrics.get("model_calls_failed") or 0)
        for step in result.get("trajectory") or []:
            action_type = (step.get("action") or {}).get("type")
            if action_type:
                actions[action_type] += 1
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "model_calls_attempted": calls,
        "model_calls_failed": failed,
        "action_type_counts": dict(sorted(actions.items())),
    }


def _summarize(
    rows: list[dict[str, Any]],
    row_id: str,
    row_dir: Path,
) -> dict[str, Any]:
    subset = [row for row in rows if row["row_id"] == row_id]
    runs = len(subset)
    actionable = sum(row["obligations_actionable"] for row in subset)
    resolved = sum(row["obligations_resolved"] for row in subset)
    raw = _raw_metrics(row_dir)
    return {
        "runs": runs,
        "terminal_feasible": [
            sum(row["terminal_feasible"] for row in subset),
            runs,
        ],
        "feasible_obligation_success": [
            sum(
                row["feasible_obligation_success"]
                for row in subset
            ),
            runs,
        ],
        "episode_success_v02": [
            sum(row["episode_success_v02"] for row in subset),
            runs,
        ],
        "obligation_resolution": [resolved, actionable],
        "economic_objective_satisfied": [
            sum(
                row["economic_objective_satisfied"]
                for row in subset
            ),
            runs,
        ],
        "accepted_actions": sum(
            row["accepted_actions"] for row in subset
        ),
        "mean_accepted_actions": (
            sum(row["accepted_actions"] for row in subset) / runs
            if runs else None
        ),
        "model_calls": sum(row["model_calls"] for row in subset),
        "prompt_tokens": raw["prompt_tokens"],
        "completion_tokens": raw["completion_tokens"],
        "total_tokens": sum(row["total_tokens"] for row in subset),
        "latency_ms": sum(row["latency_ms"] for row in subset),
        "known_cost_usd": sum(row["cost_usd"] for row in subset),
        "status_counts": dict(sorted(Counter(
            row["status"] for row in subset
        ).items())),
        "model_calls_failed": raw["model_calls_failed"],
        "action_type_counts": raw["action_type_counts"],
    }


def _per_episode(
    rows: list[dict[str, Any]],
    row_id: str,
) -> dict[str, dict[str, Any]]:
    subset = [row for row in rows if row["row_id"] == row_id]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in subset:
        grouped[row["episode_id"]].append(row)

    expected_repeats = 1 if row_id == "reference-control" else 3
    out = {}
    for episode_id in EXPECTED_HELDOUT_EPISODES:
        episode_rows = grouped[episode_id]
        if len(episode_rows) != expected_repeats:
            raise ValueError(
                f"{row_id} expected {expected_repeats} rows for "
                f"{episode_id}; found {len(episode_rows)}"
            )
        out[episode_id] = {
            "terminal": (
                sum(row["terminal_feasible"] for row in episode_rows)
                / expected_repeats
            ),
            "obligation_success": (
                sum(
                    row["feasible_obligation_success"]
                    for row in episode_rows
                )
                / expected_repeats
            ),
            "strict": (
                sum(
                    row["episode_success_v02"]
                    for row in episode_rows
                )
                / expected_repeats
            ),
            "economic": (
                sum(
                    row["economic_objective_satisfied"]
                    for row in episode_rows
                )
                / expected_repeats
            ),
            "resolved": sum(
                row["obligations_resolved"]
                for row in episode_rows
            ),
            "actionable": sum(
                row["obligations_actionable"]
                for row in episode_rows
            ),
            "actions": sum(
                row["accepted_actions"] for row in episode_rows
            ),
            "calls": sum(
                row["model_calls"] for row in episode_rows
            ),
            "tokens": sum(
                row["total_tokens"] for row in episode_rows
            ),
            "cost": sum(
                row["cost_usd"] for row in episode_rows
            ),
            "latency": sum(
                row["latency_ms"] for row in episode_rows
            ),
        }
    return out


def _delta(
    base: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, float]:
    def rate(pair):
        return pair[0] / pair[1]

    return {
        "terminal_feasible_pp": 100 * (
            rate(treatment["terminal_feasible"])
            - rate(base["terminal_feasible"])
        ),
        "feasible_obligation_success_pp": 100 * (
            rate(treatment["feasible_obligation_success"])
            - rate(base["feasible_obligation_success"])
        ),
        "episode_success_v02_pp": 100 * (
            rate(treatment["episode_success_v02"])
            - rate(base["episode_success_v02"])
        ),
        "economic_objective_pp": 100 * (
            rate(treatment["economic_objective_satisfied"])
            - rate(base["economic_objective_satisfied"])
        ),
        "obligation_resolution_pp": 100 * (
            rate(treatment["obligation_resolution"])
            - rate(base["obligation_resolution"])
        ),
        "accepted_actions_pct": 100 * (
            treatment["accepted_actions"] / base["accepted_actions"] - 1
        ),
        "model_calls_pct": 100 * (
            treatment["model_calls"] / base["model_calls"] - 1
        ),
        "total_tokens_pct": 100 * (
            treatment["total_tokens"] / base["total_tokens"] - 1
        ),
        "cost_pct": 100 * (
            treatment["known_cost_usd"] / base["known_cost_usd"] - 1
        ),
        "latency_pct": 100 * (
            treatment["latency_ms"] / base["latency_ms"] - 1
        ),
    }


def _bootstrap_index(resample: int, draw: int) -> int:
    payload = (
        "longprocurebench-bootstrap-v1:"
        f"{BOOTSTRAP_SEED}:{resample}:{draw}"
    ).encode("utf-8")
    return int.from_bytes(
        sha256(payload).digest(),
        "big",
    ) % len(EXPECTED_HELDOUT_EPISODES)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (position - low) * (
        ordered[high] - ordered[low]
    )


def _bootstrap(
    base: dict[str, dict[str, Any]],
    treatment: dict[str, dict[str, Any]],
) -> dict[str, list[float]]:
    names = (
        "terminal_feasible_pp",
        "feasible_obligation_success_pp",
        "episode_success_v02_pp",
        "economic_objective_pp",
        "obligation_resolution_pp",
        "accepted_actions_pct",
        "model_calls_pct",
        "total_tokens_pct",
        "cost_pct",
        "latency_pct",
    )
    values = {name: [] for name in names}

    for resample in range(BOOTSTRAP_RESAMPLES):
        sample = [
            EXPECTED_HELDOUT_EPISODES[
                _bootstrap_index(resample, draw)
            ]
            for draw in range(len(EXPECTED_HELDOUT_EPISODES))
        ]

        for field, output in (
            ("terminal", "terminal_feasible_pp"),
            ("obligation_success", "feasible_obligation_success_pp"),
            ("strict", "episode_success_v02_pp"),
            ("economic", "economic_objective_pp"),
        ):
            base_mean = sum(
                base[episode_id][field]
                for episode_id in sample
            ) / len(EXPECTED_HELDOUT_EPISODES)
            treatment_mean = sum(
                treatment[episode_id][field]
                for episode_id in sample
            ) / len(EXPECTED_HELDOUT_EPISODES)
            values[output].append(
                100 * (treatment_mean - base_mean)
            )

        base_resolved = sum(
            base[episode_id]["resolved"]
            for episode_id in sample
        )
        base_actionable = sum(
            base[episode_id]["actionable"]
            for episode_id in sample
        )
        treatment_resolved = sum(
            treatment[episode_id]["resolved"]
            for episode_id in sample
        )
        treatment_actionable = sum(
            treatment[episode_id]["actionable"]
            for episode_id in sample
        )
        values["obligation_resolution_pp"].append(
            100 * (
                treatment_resolved / treatment_actionable
                - base_resolved / base_actionable
            )
        )

        for field, output in (
            ("actions", "accepted_actions_pct"),
            ("calls", "model_calls_pct"),
            ("tokens", "total_tokens_pct"),
            ("cost", "cost_pct"),
            ("latency", "latency_pct"),
        ):
            base_total = sum(
                base[episode_id][field]
                for episode_id in sample
            )
            treatment_total = sum(
                treatment[episode_id][field]
                for episode_id in sample
            )
            values[output].append(
                100 * (treatment_total / base_total - 1)
            )

    return {
        name: [
            _quantile(samples, 0.025),
            _quantile(samples, 0.975),
        ]
        for name, samples in values.items()
    }


def _effect_counts(
    base: dict[str, dict[str, Any]],
    treatment: dict[str, dict[str, Any]],
    field: str,
) -> dict[str, int]:
    result = {"improved": 0, "tied": 0, "worsened": 0}
    for episode_id in EXPECTED_HELDOUT_EPISODES:
        delta = (
            treatment[episode_id][field]
            - base[episode_id][field]
        )
        if delta > 0:
            result["improved"] += 1
        elif delta < 0:
            result["worsened"] += 1
        else:
            result["tied"] += 1
    return result


def _failure_taxonomy(
    rows: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, Counter] = defaultdict(Counter)
    classes = set()
    for row in rows:
        row_id = row["row_id"]
        if row_id == "reference-control":
            continue
        for checkpoint in (
            row.get("unresolved_obligations") or ""
        ).split(";"):
            if checkpoint:
                counts[row_id][checkpoint] += 1
                classes.add(checkpoint)

    output = []
    for row_id in ROW_ORDER:
        summary = summaries[row_id]
        resolved, actionable = summary["obligation_resolution"]
        rate = resolved / actionable
        for checkpoint in sorted(classes):
            output.append({
                "method": row_id,
                "unresolved_obligation_class": checkpoint,
                "unresolved_count": counts[row_id][checkpoint],
                "actionable_count": actionable,
                "resolved_count": resolved,
                "resolution_rate": rate,
            })
    return output


def _per_episode_quality(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, int]]]:
    output = {}
    for row_id in ROW_ORDER:
        by_episode = defaultdict(list)
        for row in rows:
            if row["row_id"] == row_id:
                by_episode[row["episode_id"]].append(row)
        output[row_id] = {}
        for episode_id in EXPECTED_HELDOUT_EPISODES:
            episode_rows = by_episode[episode_id]
            output[row_id][episode_id] = {
                "terminal_feasible": sum(
                    row["terminal_feasible"]
                    for row in episode_rows
                ),
                "feasible_obligation_success": sum(
                    row["feasible_obligation_success"]
                    for row in episode_rows
                ),
                "episode_success_v02": sum(
                    row["episode_success_v02"]
                    for row in episode_rows
                ),
                "economic_objective_satisfied": sum(
                    row["economic_objective_satisfied"]
                    for row in episode_rows
                ),
                "runs": len(episode_rows),
            }
    return output


def compute_results(
    aggregate_dir: Path,
    row_dirs: dict[str, Path],
) -> dict[str, Any]:
    rows = _typed_rows(_read_csv(aggregate_dir / "heldout-runs.csv"))
    if len(rows) != 160:
        raise ValueError(
            f"Held-out aggregate must contain 160 rows; found {len(rows)}"
        )

    summaries = {
        row_id: _summarize(rows, row_id, row_dirs[row_id])
        for row_id in [
            "reference-control",
            *ROW_ORDER,
        ]
    }
    for row_id, summary in summaries.items():
        expected_runs = 10 if row_id == "reference-control" else 30
        if summary["runs"] != expected_runs:
            raise ValueError(
                f"Held-out summary run count drift for {row_id}"
            )
        if summary["status_counts"] != {"completed": expected_runs}:
            raise ValueError(
                f"Held-out status drift for {row_id}: "
                f"{summary['status_counts']}"
            )
        if summary["model_calls_failed"] != 0:
            raise ValueError(
                f"Held-out failed model calls present for {row_id}"
            )
        if (
            summary["prompt_tokens"]
            + summary["completion_tokens"]
            != summary["total_tokens"]
        ):
            raise ValueError(
                f"Held-out token accounting drift for {row_id}"
            )

    per_episode = {
        row_id: _per_episode(rows, row_id)
        for row_id in [
            "reference-control",
            *ROW_ORDER,
        ]
    }

    base = summaries[CONTEXT_ROW]
    deltas = {
        row_id: _delta(base, summaries[row_id])
        for row_id in (
            "raw-reactive-openai",
            "react-openai",
        )
    }
    bootstraps = {
        row_id: _bootstrap(
            per_episode[CONTEXT_ROW],
            per_episode[row_id],
        )
        for row_id in (
            "raw-reactive-openai",
            "react-openai",
        )
    }

    effects = {}
    for row_id in (
        "raw-reactive-openai",
        "react-openai",
    ):
        effects[row_id] = {
            "terminal_feasible": _effect_counts(
                per_episode[CONTEXT_ROW],
                per_episode[row_id],
                "terminal",
            ),
            "feasible_obligation_success": _effect_counts(
                per_episode[CONTEXT_ROW],
                per_episode[row_id],
                "obligation_success",
            ),
            "episode_success_v02": _effect_counts(
                per_episode[CONTEXT_ROW],
                per_episode[row_id],
                "strict",
            ),
            "economic_objective": _effect_counts(
                per_episode[CONTEXT_ROW],
                per_episode[row_id],
                "economic",
            ),
        }

    model_rows = [row for row in rows if row["row_id"] != "reference-control"]
    model_backed_totals = {
        "runs": len(model_rows),
        "accepted_actions": sum(
            row["accepted_actions"] for row in model_rows
        ),
        "model_calls": sum(
            row["model_calls"] for row in model_rows
        ),
        "prompt_tokens": sum(
            summaries[row_id]["prompt_tokens"]
            for row_id in ROW_ORDER
        ),
        "completion_tokens": sum(
            summaries[row_id]["completion_tokens"]
            for row_id in ROW_ORDER
        ),
        "total_tokens": sum(
            row["total_tokens"] for row in model_rows
        ),
        "latency_ms": sum(
            row["latency_ms"] for row in model_rows
        ),
        "known_cost_usd": sum(
            row["cost_usd"] for row in model_rows
        ),
    }

    return {
        "schema_version": "0.1.0",
        "experiment": "heldout-paper-evaluation-v0.1",
        "source_workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "source_head_sha": SOURCE_HEAD_SHA,
        "run_attempt": SOURCE_RUN_ATTEMPT,
        "total_runs": 160,
        "model_backed_runs": 150,
        "reference_control_runs": 10,
        "model_backed_totals": model_backed_totals,
        "reference_control": summaries["reference-control"],
        "provider_diverse_raw_reactive": {
            row_id: summaries[row_id]
            for row_id in (
                "raw-reactive-openai",
                "raw-reactive-anthropic",
                "raw-reactive-gemini",
            )
        },
        "matched_openai": {
            row_id: summaries[row_id]
            for row_id in MATCHED_ROWS
        },
        "matched_deltas_vs_context": deltas,
        "paired_episode_cluster_bootstrap_vs_context": {
            "cluster": "episode_id",
            "episodes": 10,
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
            "sampler": BOOTSTRAP_SAMPLER,
            **bootstraps,
        },
        "episode_effect_counts_vs_context": effects,
        "failure_taxonomy": _failure_taxonomy(rows, summaries),
        "per_episode_quality": _per_episode_quality(rows),
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _build_manifest(
    results_bytes: bytes,
    taxonomy_bytes: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "experiment": "heldout-paper-evaluation-v0.1",
        "status": "heldout_results_frozen",
        "source_workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "source_workflow_run_attempt": SOURCE_RUN_ATTEMPT,
        "source_head_sha": SOURCE_HEAD_SHA,
        "source_workflow_conclusion": "success",
        "source_artifacts": SOURCE_ARTIFACTS,
        "validated_grid": {
            "reference_control_runs": 10,
            "model_backed_runs": 150,
            "total_runs": 160,
            "episodes": 10,
            "model_backed_rows": 5,
        },
        "paper_contract": {
            "primary_quality_metric": "feasible_obligation_success",
            "matched_baseline": CONTEXT_ROW,
            "bootstrap_cluster": "episode_id",
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_sampler": BOOTSTRAP_SAMPLER,
            "no_weighted_composite": True,
        },
        "durability": (
            "The exact seven workflow artifact ZIPs are committed in the "
            "repository, including all 160 raw result JSON files, row CSV/"
            "summary validation products, full ReAct transcripts, and the "
            "aggregate artifact. Evidence no longer depends on Actions "
            "artifact retention."
        ),
        "outputs": {
            "results.json": {
                "bytes": len(results_bytes),
                "sha256": sha256(results_bytes).hexdigest(),
            },
            "failure-taxonomy.json": {
                "bytes": len(taxonomy_bytes),
                "sha256": sha256(taxonomy_bytes).hexdigest(),
            },
        },
        "interpretation_rule": (
            "Freeze and report the measured held-out matrix without using "
            "these outcomes to modify methods, prompts, episodes, evaluator "
            "semantics, model settings, or reporting tables."
        ),
        "next_step": (
            "Finalize manuscript tables/figures and claims from the frozen "
            "development and held-out evidence; do not reopen architecture "
            "search."
        ),
    }


def compute_from_sources(
    source_dir: Path = SOURCE_DIR,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan = load_execution_plan()
    if set(plan) != EXPECTED_ROW_IDS:
        raise ValueError("Frozen held-out execution-plan row set drift")

    for key in SOURCE_ARTIFACTS:
        archive = _verify_source_artifact(source_dir, key)
        _validate_archive_members(archive, key, plan)

    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        row_root = temp / "rows"
        row_dirs = {}
        for row_id in sorted(EXPECTED_ROW_IDS):
            row_dir = row_root / row_id
            _safe_extract(
                _verify_source_artifact(source_dir, row_id),
                row_dir,
            )
            validate_row_results(
                row_id,
                row_dir,
                write_manifest=False,
            )
            if row_id == "react-openai":
                _validate_react_transcripts(
                    row_dir,
                    plan[row_id],
                )
            row_dirs[row_id] = row_dir

        source_aggregate = temp / "source-aggregate"
        _safe_extract(
            _verify_source_artifact(source_dir, "aggregate"),
            source_aggregate,
        )

        recomputed = temp / "recomputed-aggregate"
        aggregate_matrix(row_root, recomputed)

        source_csv = source_aggregate / "heldout-runs.csv"
        recomputed_csv = recomputed / "heldout-runs.csv"
        if source_csv.read_bytes() != recomputed_csv.read_bytes():
            raise ValueError(
                "Source aggregate heldout-runs.csv does not reproduce "
                "from exact row artifacts"
            )

        source_manifest = json.loads(
            (
                source_aggregate
                / "heldout-matrix-manifest.json"
            ).read_text(encoding="utf-8")
        )
        recomputed_manifest = json.loads(
            (
                recomputed
                / "heldout-matrix-manifest.json"
            ).read_text(encoding="utf-8")
        )
        if source_manifest != recomputed_manifest:
            raise ValueError(
                "Source aggregate manifest does not reproduce from exact "
                "row artifacts"
            )

        results = compute_results(
            source_aggregate,
            row_dirs,
        )
        taxonomy = results["failure_taxonomy"]
        return results, taxonomy


def write_frozen_outputs() -> None:
    results, taxonomy = compute_from_sources()
    results_bytes = _canonical_json_bytes(results)
    taxonomy_bytes = _canonical_json_bytes({
        "schema_version": "0.1.0",
        "experiment": "heldout-paper-evaluation-v0.1",
        "rows": taxonomy,
    })
    RESULTS_PATH.write_bytes(results_bytes)
    TAXONOMY_PATH.write_bytes(taxonomy_bytes)
    manifest = _build_manifest(results_bytes, taxonomy_bytes)
    MANIFEST_PATH.write_bytes(_canonical_json_bytes(manifest))


def audit_committed_outputs() -> dict[str, Any]:
    results, taxonomy = compute_from_sources()
    expected_results = json.loads(
        RESULTS_PATH.read_text(encoding="utf-8")
    )
    if results != expected_results:
        raise ValueError(
            "Committed held-out results.json does not match source evidence"
        )

    expected_taxonomy = json.loads(
        TAXONOMY_PATH.read_text(encoding="utf-8")
    )
    actual_taxonomy = {
        "schema_version": "0.1.0",
        "experiment": "heldout-paper-evaluation-v0.1",
        "rows": taxonomy,
    }
    if expected_taxonomy != actual_taxonomy:
        raise ValueError(
            "Committed held-out failure taxonomy does not match source "
            "evidence"
        )

    results_bytes = RESULTS_PATH.read_bytes()
    taxonomy_bytes = TAXONOMY_PATH.read_bytes()
    expected_manifest = _build_manifest(
        results_bytes,
        taxonomy_bytes,
    )
    actual_manifest = json.loads(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )
    if actual_manifest != expected_manifest:
        raise ValueError(
            "Committed held-out results manifest does not match source "
            "evidence and outputs"
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write frozen results/taxonomy/manifest from exact source ZIPs.",
    )
    args = parser.parse_args()

    if args.write:
        write_frozen_outputs()

    results = audit_committed_outputs()
    context = results["matched_openai"]["context-compiled-openai"]
    react = results["matched_openai"]["react-openai"]
    print(
        "Held-out paper evidence audit passed: "
        "160/160 validated runs; "
        f"context obligation={context['feasible_obligation_success'][0]}/30; "
        f"ReAct obligation={react['feasible_obligation_success'][0]}/30; "
        f"ReAct strict={react['episode_success_v02'][0]}/30."
    )


if __name__ == "__main__":
    main()
