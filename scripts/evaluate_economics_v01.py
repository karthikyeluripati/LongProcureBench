"""Offline CLI for deterministic procurement economics v0.1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from longprocurebench import (
    EconomicRegretEvaluator,
    compare_candidate_on_reference_cohort,
    freeze_reference_cohort,
)


def _load(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_many(paths):
    return [_load(path) for path in paths]


def _write(payload, output):
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def main():
    parser = argparse.ArgumentParser(
        description="Score LongProcureBench procurement economics offline."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    score = sub.add_parser("score")
    score.add_argument("--result", required=True)
    score.add_argument("--repeat", type=int, required=True)
    score.add_argument("--output")

    cohort = sub.add_parser("cohort")
    cohort.add_argument("--coverage", nargs="+", required=True)
    cohort.add_argument("--react", nargs="+", required=True)
    cohort.add_argument("--output")

    compare = sub.add_parser("compare")
    compare.add_argument("--candidate", nargs="+", required=True)
    compare.add_argument("--coverage", nargs="+", required=True)
    compare.add_argument("--react", nargs="+", required=True)
    compare.add_argument("--cohort")
    compare.add_argument("--output")

    args = parser.parse_args()

    if args.command == "score":
        evaluator = EconomicRegretEvaluator()
        payload = evaluator.score_result(
            _load(args.result),
            repeat=args.repeat,
        )
    elif args.command == "cohort":
        payload = freeze_reference_cohort(
            _load_many(args.coverage),
            _load_many(args.react),
        )
    else:
        frozen = _load(args.cohort) if args.cohort else None
        payload = compare_candidate_on_reference_cohort(
            _load_many(args.candidate),
            coverage_repair_reports=_load_many(args.coverage),
            react_reports=_load_many(args.react),
            reference_cohort=frozen,
        )

    _write(payload, args.output)


if __name__ == "__main__":
    main()
