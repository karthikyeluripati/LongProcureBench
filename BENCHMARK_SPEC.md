# LongProcureBench benchmark contract v0.1

This document freezes the data and observability contract used by the current
electrical LongProcureBench suite before architecture experiments begin.

## Scientific role of the current 20 episodes

Episodes 001–020 are **development/calibration episodes**, not the final held-out
paper test set. They have already been used to build the runtime, diagnose
checkpoint fairness, design Evaluator v0.2, and inspect Luna trajectories.
Reporting them remains useful for development and ablations, but architecture or
metric choices must not be justified as if these episodes were untouched test
data.

The next benchmark-scale target is approximately 30 episodes. The next ten
distinct real public starting states are reserved for a held-out paper evaluation
slice. Once those held-out episodes are frozen, evaluator semantics and agent
architecture choices must not be tuned on their results.

The machine-readable split policy is in
`data/splits/electrical-v0.3-plan.json`.

## Reality boundary

LongProcureBench is semi-synthetic by design.

| Layer | Grounding | Policy visibility |
| --- | --- | --- |
| Initial procurement state | Real buyer-authored public procurement data | Visible at reset |
| Raw source documents | Real public evidence used by curators | Not runtime input |
| Supplier directory identities | Synthetic | Hidden until `identify_suppliers` |
| Supplier eligibility/compliance profile fields | Synthetic | Never exposed directly |
| Quotes, supplier messages, withdrawals, substitutions, revisions | Synthetic controlled scenario facts | Hidden until their event trigger fires |
| Future event schedule and pending events | Synthetic | Never exposed before trigger |
| Oracle, acceptable outcomes, failure conditions | Curator-authored benchmark ground truth | Never exposed to the policy |
| Evaluation configuration and scores | Deterministic benchmark machinery | Post-run only |

The rule is:

> Preserve reality where it is observable; synthesize only the private
> interaction layer or controlled interventions required for evaluation.

Synthetic suppliers and events are benchmark constructs. They must never be
described as historical behavior by real organizations or vendors.

## Temporal observability

### Reset

The policy receives the referenced initial-state JSON. It does not receive raw
source documents, future events, supplier profiles, episode oracle data, or
evaluation configuration.

### Supplier discovery

Before `identify_suppliers` is accepted, the supplier directory is hidden.
Afterward, runtime-visible supplier entries expose only synthetic identifier,
display name, and the synthetic marker. Hidden profile fields such as configured
eligibility or compliance state are not directly revealed.

### Step execution

Accepted agent actions define benchmark time. For accepted action step `n`:

1. validate and apply the action;
2. emit matching `after_action` events;
3. emit `at_step` events scheduled for step `n`;
4. return only those newly revealed observations plus accumulated visible state;
5. accept the next action.

Pending future events remain hidden. Rejected actions do not advance time.

### Terminal evaluation

Only after execution does the evaluator use oracle outcomes, hard-constraint
configuration, and trigger-aware obligation semantics. A competitive policy must
never access those objects.

## Ground truth

Ground truth has two distinct sources and they must remain distinguishable.

1. **Real starting-state constraints.** Buyer-authored quantities, schedules,
   budgets, eligibility requirements, technical requirements, and other facts
   are reconstructed from cited public sources. Unknown values stay null.
2. **Controlled scenario ground truth.** Synthetic quote values, messages,
   withdrawals, amendments, clarifications, and other private interactions are
   authored solely to create controlled long-horizon tasks.

Evaluator v0.2 may combine both layers when deciding whether an observed terminal
decision is feasible. That does not make a synthetic scenario fact historical
data.

## Leakage rules

The benchmark must reject or review any change that:

- puts supplier responses, offered prices, negotiations, awards, or later
  outcomes into the initial state;
- exposes future events, event triggers, the oracle, evaluation configuration, or
  hidden supplier profile fields to a policy;
- uses a real supplier name to represent synthetic behavior;
- silently converts a missing public field into a known value;
- treats a controlled clarification or amendment as a real source fact;
- tunes evaluator semantics or the final agent design against the future held-out
  test slice.

## Episode-level audit

`OBSERVABILITY_MATRIX.csv` is the frozen episode-level audit for the current
suite. Every episode records:

- distinct real public package ID and source family;
- development-vs-held-out role;
- grounding of initial state, suppliers, and interaction layer;
- visibility timing for source documents, supplier directory, hidden profiles,
  future events, oracle, and evaluation;
- controlled synthetic requirement-changing event types;
- primary failure mechanisms exercised by the episode.

`scripts/validate_benchmark_contract.py` cross-checks the matrix against the
committed episodes and initial states in CI.

## Expansion gate

Before adding episodes 021–030:

- collect a distinct real public procurement starting state for every episode;
- preserve field-level provenance and missingness;
- construct the episode without using outcomes from a model under evaluation;
- update the observability matrix;
- keep the held-out slice sealed from evaluator and architecture tuning once
  frozen.

LangGraph, ReAct, planner/executor systems, persistent-memory agents, and
ProcureHarness are downstream experimental implementations. They do not change
this benchmark contract.
