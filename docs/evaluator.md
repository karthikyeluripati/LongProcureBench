# Evaluator v0.2

Evaluator v0.2 turns a completed LongProcureBench trajectory into a deterministic, auditable report. It does not use an LLM judge. Legacy v0.1 checkpoint/process fields remain in the output so older evidence can still be reproduced.

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

Evaluator v0.2 supports price/lead-time bounds, exact quote attributes,
supplier eligibility fields, latest-revision checks, supplier withdrawal checks,
required event-before-action ordering, and complete award scope.

## Required checkpoints

Some checkpoints have direct trajectory evidence. Amendment handling requires the amendment to occur after the revealed requirement change and the ultimately awarded quote(s) to be observed only after that amendment. Withdrawal recovery requires a fresh quote/revision from a non-withdrawn supplier after the withdrawal, followed by a new quote-evaluation action. Follow-up after non-response, buyer clarification, supplier-question handling, quote-revision requests, and terminal decision are also checked directly.

The current action contract does not include explicit `normalize_quotes`,
`validate_eligibility`, or `validate_compliance` actions. Those report
`evidence_mode: "proxy"` and use conservative observable proxies. This is
intentional and visible in the report.

## Trigger-aware obligations

Evaluator v0.2 adds a separate `obligations` section. It does **not** treat every
episode-declared checkpoint as a mandatory action on every trajectory.

Obligation states are:

- `resolved` — the obligation became applicable, the agent had an action
  opportunity, and the required state transition/recovery occurred;
- `unresolved` — applicable and actionable, but not discharged;
- `no_opportunity` — the trigger became visible only when there was no later
  accepted action opportunity;
- `not_applicable` — the relevant event/branch never occurred.

The primary process quantity is
`obligations.resolution_rate = resolved / actionable`. `no_opportunity` and
`not_applicable` records are excluded from that denominator.

Current obligation classes:

- non-response → follow up that supplier;
- supplier question → answer that supplier;
- requirement/quantity change → issue an amendment and avoid stale awarded quotes;
- supplier withdrawal → restore a feasible, hard-constraint-satisfying terminal
  path without awarding the withdrawn supplier;
- visible initial requirement gap → clarify before sourcing;
- quote revision → conditional on the selected path actually requiring a
  revision or using a revised offer.

`feasible_obligation_success` requires terminal feasibility, all hard
constraints, and all actionable obligations resolved. `episode_success_v02`
additionally requires the economic objective.

## Diagnostics versus obligations

`normalize_quotes`, `validate_eligibility`, and `validate_compliance` remain
proxy diagnostics because the action contract does not expose them as explicit
agent actions. `solicit_competition`, `evaluate_quotes`, and
`award_or_recommend` are retained as procedural diagnostics. They remain in
legacy `required_checkpoints`, but they do not determine the v0.2 obligation
metric.

## Backward compatibility

The following v0.1 fields remain unchanged:

- `required_checkpoints`;
- `feasible_process_success`;
- `episode_success`.

New v0.2 fields are additive:

- `evaluation_version`;
- `obligations`;
- `checkpoint_diagnostics`;
- `feasible_obligation_success`;
- `episode_success_v02`.

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
