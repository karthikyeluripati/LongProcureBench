# Maintained working-plan reactive v0.1 — matched result

This is a development/calibration experiment on the same frozen 20 episodes as
the factual context-compiled GPT-5.6 Sol baseline. The treatment keeps the same
model, reasoning setting, factual compiler, runtime, evaluator, semantic action
space, and one-model-call-per-action cadence. It adds one bounded replaceable
prospective plan containing an objective, at most four future steps, and a stop
condition.

The result **fails the predeclared inclusion gate**. Maintained working-plan
state is dropped as a component candidate in this form.

## Source

- Live workflow run: `36243953648`
- Source artifact: `10907187177`
- Artifact digest:
  `sha256:924443c9bde20b687a2a3b9fe0c8058f8a224604d8532d6c325c6a9c89fd6c9b`
- Benchmark code:
  `aee79caf71dc3301f7ddc7db99f9d96289878403`
- Execution head:
  `e43b5a90685d1da5409637fe220df21f4ff61e8e`
- Execution-head delta: workflow trigger only
- Grid: GPT-5.6 Sol × 20 development episodes × 3 repeats = **60 runs**
- All 60 runs completed; there were no model/provider, runtime, or evaluator
  failures and no run hit the action cap.

The committed replay source is linked to the raw Actions artifact by per-record
raw-byte and compact-record SHA-256 provenance. The standalone verifier
`scripts/verify_working_plan_source_artifact_v01.py` can rederive those roots
from a downloaded artifact.

## Matched comparison

| Metric | Context compiled | Working plan | Delta |
| --- | ---: | ---: | ---: |
| Terminal feasible | 46/60 (**76.7%**) | 41/60 (**68.3%**) | **-8.3 pp** |
| Feasible-obligation success | 40/60 (**66.7%**) | 27/60 (**45.0%**) | **-21.7 pp** |
| Strict v0.2 success | 14/60 (**23.3%**) | 17/60 (**28.3%**) | **+5.0 pp** |
| Obligation resolution | 72/86 (**83.7%**) | 63/86 (**73.3%**) | **-10.5 pp** |
| Prompt tokens | 931,985 | 1,209,938 | **+29.8%** |
| Completion tokens | 42,223 | 106,087 | **+151.3%** |
| Total tokens | 974,208 | 1,316,025 | **+35.1%** |
| Model calls | 464 | 481 | **+3.7%** |
| Known API cost | $4.61 | $7.85 | **+70.3%** |
| Aggregate model latency | 869,561 ms | 1,520,406 ms | **+74.8%** |

The strict-success increase does not rescue the treatment: the run-level
feasible-obligation metric and terminal-feasibility guardrail both regress
materially.

## Predeclared gate

The protocol was frozen before the full experiment. Retain the component if
either:

1. feasible-obligation success improves by at least **5 percentage points**
   while terminal feasibility does not fall by more than **5 points**; or
2. strict v0.2 success improves by at least **5 points**, while
   feasible-obligation success does not fall by more than **2 points** and
   terminal feasibility does not fall by more than **5 points**.

Observed:

- feasible-obligation success: **-21.7 pp**
- terminal feasibility: **-8.3 pp**
- strict v0.2: **+5.0 pp**

Therefore **neither branch passes**.

## Episode-cluster bootstrap

A paired cluster bootstrap over the 20 episode IDs (20,000 resamples, seed
`20260926`, sampler `sha256-index-v1`) gives descriptive 95% intervals:

| Delta | 95% interval |
| --- | ---: |
| Terminal feasible | **[-23.3, +5.0] pp** |
| Feasible-obligation success | **[-41.7, -1.7] pp** |
| Strict v0.2 success | **[-13.3, +21.7] pp** |
| Obligation resolution | **[-26.1, +2.5] pp** |
| Total tokens | **[+23.7%, +47.9%]** |
| Model calls | **[-4.1%, +11.6%]** |
| Cost | **[+49.3%, +98.5%]** |
| Aggregate model latency | **[+59.4%, +94.3%]** |

The feasible-obligation interval remains below zero, while token, cost, and
latency increases remain above zero across the episode-cluster resamples.

## The plan was active, but not reliably useful

The negative result is not explained by the model simply ignoring the plan.

Across the 60 runs:

- **473** plan updates were accepted and **8** were rejected;
- **7** runs contained at least one rejected auxiliary plan;
- mean accepted plan length was **1.80** steps; maximum was the frozen limit of
  four;
- where a next planned step existed, its action type matched the following
  accepted action **85.3%** of the time;
- action type plus supplier matched **78.1%** of the time;
- across adjacent accepted plan updates, the objective changed **78.0%** of the
  time and the stop condition changed **79.9%** of the time.

So the prospective state was being generated, revised, and followed. The
evidence instead says that **adding this one-call maintained plan did not
produce a better long-horizon policy**.

## Failure pattern

Unresolved actionable obligations changed from **14** under factual context
compilation to **23** under the working plan:

| Obligation class | Context compiled | Working plan |
| --- | ---: | ---: |
| Supplier non-response follow-up | 4 | 13 |
| Withdrawal recovery | 3 | 5 |
| Quote revision | 3 | 2 |
| Requirement-gap resolution | 1 | 3 |
| Amendment handling | 3 | 0 |

The treatment also sent more RFQs (**149 → 177**), while model calls changed
only modestly (**464 → 481**). This is consistent with a planning treatment that
changed action selection but did not preserve the right downstream
commitments.

Episode-level effects were heterogeneous. Episode 016 improved strongly
(feasible-obligation and strict success both +66.7 pp), and episodes 002, 003,
and 018 also improved. Those gains were outweighed by regressions including
episodes 001, 006, 010, 013, and 019. Across 20 episode clusters,
feasible-obligation success improved on 4, worsened on 10, and tied on 6.

## Decision

**Drop maintained working-plan reactive v0.1.**

Three controlled results now point in the same direction:

- better factual serialization substantially improves efficiency but does not
  solve reliability;
- persistent commitment-ledger state worsened end-to-end behavior;
- a bounded prospective plan under the same one-call cadence also worsened
  feasible-obligation reliability.

The next experiment should therefore isolate **additional computation and
verification**, not add another representation. The quality-heavy comparator is
an **always-replan + pre-award verifier** treatment: explicitly deliberate after
state changes and perform a separate generic visible-state check before a
terminal award/no-award decision. If that earns a reliability gain, a later
selective event-triggered version can test whether most of the quality can be
retained at lower inference cost.

Held-out states and future held-out episodes remain untouched.
