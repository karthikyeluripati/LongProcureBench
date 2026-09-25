# Evaluator v0.1

Evaluator v0.1 turns a completed LongProcureBench trajectory into a deterministic,
auditable report. It does not use an LLM judge.

## Dimensions

The evaluator deliberately does **not** collapse everything into one weighted
magic score. It reports:

- terminal outcome correctness;
- hard constraints passed / total;
- required checkpoints completed / total;
- constraint violation IDs;
- accepted action count.

`episode_success` requires a correct terminal outcome, all hard constraints, and
all required checkpoints.

## Replay-first

Evaluation takes an accepted action history and replays it through a fresh
`LongProcureBenchEnv`. The evaluator therefore inherits the same event ordering,
hidden-state rules, one-shot emission, action validation, and terminal semantics
as the benchmark runtime rather than trusting a fabricated final state.

## Machine hard constraints

Each episode has a versioned config in
`data/evaluation/electrical/<episode_id>.json` mapping every human-readable
oracle constraint to machine checks.

Evaluator v0.1 supports price/lead-time bounds, exact quote attributes,
supplier eligibility fields, latest-revision checks, supplier withdrawal checks,
required event-before-action ordering, and complete award scope.

## Required checkpoints

Some checkpoints have direct trajectory evidence, including follow-up after
non-response, buyer clarification, amendment handling, supplier-question handling,
quote-revision requests, withdrawal recovery, quote evaluation, and terminal
decision.

The current action contract does not include explicit `normalize_quotes`,
`validate_eligibility`, or `validate_compliance` actions. Those report
`evidence_mode: "proxy"` and use conservative observable proxies. This is
intentional and visible in the report.

## Example report shape

```text
Episode success:          true
Terminal outcome:         correct
Hard constraints:         4/4
Required checkpoints:     7/7
Constraint violations:    []
Accepted actions:         8
```

No weighted score is introduced in v0.1.

## Not included yet

- LLM judge;
- model/agent baseline;
- token/latency/cost metrics;
- OpenTelemetry / Arize trace export;
- leaderboard.
