# Evaluator v0.1

Evaluator v0.1 turns a completed LongProcureBench trajectory into a deterministic,
auditable report. It does not use an LLM judge.

## Dimensions

The evaluator deliberately does **not** collapse everything into one weighted
magic score. It reports:

- terminal feasibility / acceptable-outcome match;
- economic objective satisfaction;
- hard constraints passed / total;
- required checkpoints completed / total;
- constraint violation IDs;
- accepted action count.

`feasible_process_success` requires a feasible terminal outcome, all hard constraints, and all required checkpoints. `episode_success` additionally requires the episode economic objective to be satisfied.

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

Some checkpoints have direct trajectory evidence. Amendment handling requires the amendment to occur after the revealed requirement change and the ultimately awarded quote(s) to be observed only after that amendment. Withdrawal recovery requires a fresh quote/revision from a non-withdrawn supplier after the withdrawal, followed by a new quote-evaluation action. Follow-up after non-response, buyer clarification, supplier-question handling, quote-revision requests, and terminal decision are also checked directly.

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

## Feasibility versus economic optimality

Pilot audit v0.1 separates terminal feasibility from economic preference.

- Terminal feasibility means the terminal award/no-award decision matches any explicitly acceptable feasible outcome.
- Economic objective means the matched feasible outcome belongs to the preferred outcome set. The current pilot objective is minimum feasible total price.

A higher-price compliant award is therefore reported as feasible but economically suboptimal, rather than as an incorrect terminal decision.

The episode oracle stores economic_objective.preferred_outcome_ids, which must reference a subset of acceptable_terminal_outcomes.
