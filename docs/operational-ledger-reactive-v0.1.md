# Operational-ledger reactive baseline v0.1

This experiment tests the next causal hypothesis after factual context
compilation:

> Long-horizon failures persist because useful facts are visible, but commitments
> created by those facts are not maintained as explicit persistent task state.

The experiment adds a **model-maintained operational ledger** on top of the
factual context compiler. It does not add ReAct, a planner, a verifier, a
knowledge graph, extra model calls, or evaluator-derived obligations.

## Matched comparison

The comparison condition is the frozen context-compiled GPT-5.6 Sol baseline.

Matched settings:

- model: `openai/gpt-5.6-sol`
- reasoning effort: `medium`
- temperature: omitted
- frozen development episodes: 001–020 only
- repeats: 3
- maximum accepted actions: 50
- same `BenchmarkRunner`, runtime, evaluator, and semantic action contract
- same factual context compiler
- one model call per action

The necessary treatment differences are:

1. the response schema also contains a structured `ledger_update`;
2. the prompt includes persistent **open** commitments accumulated from prior
   accepted actions plus only a compact resolved-item count;
3. the system instruction defines the narrow ledger-update contract.

## Ledger contract

The policy persists two explicit collections:

- **open items** — visible-fact-grounded procurement work the model believes
  remains to be discharged;
- **resolved items** — previously open items the model explicitly closed.

The model does not choose persistent IDs. The harness assigns monotonic IDs
(`l001`, `l002`, ...) to newly created items so later turns can resolve them
without free-form identity drift.

A new item contains only:

- a broad category: `requirement`, `supplier`, `offer`, `decision`, or
  `other`;
- optional currently-visible `supplier_id`;
- zero or more already-revealed `source_event_ids`;
- a short operational-task description.

The harness rejects references to unrevealed events, non-visible suppliers, and
unknown ledger IDs.

The ledger deliberately does **not** contain:

- evaluator checkpoints or obligation labels;
- oracle constraints/outcomes;
- hidden suppliers or future events;
- chain-of-thought or free-form reasoning traces;
- a hand-coded mapping from benchmark event types to required actions.

The model itself decides whether a visible fact creates an open commitment and
when that commitment is resolved. That is the mechanism under test.

Ledger updates use two-phase commit semantics. A model call may **propose** a
ledger update together with its semantic action, but the harness commits that
update only after the runtime accepts the action. A runtime-rejected action
therefore cannot change the persistent ledger, trace, or ledger counts.

Only open items are repeated in the model-facing prompt. Completed-item details
are omitted from later prompts because accepted action history already carries
the observable execution history; the prompt includes only `resolved_count`.
The full resolved-item history remains in result metadata for auditing.

## Why this is narrower than a full state harness

The factual compiler already carries current requirements, visible suppliers,
revealed events, latest awardable quotes/revisions, and compact action history.
Adding another hand-built copy of those facts would confound the experiment.

This treatment therefore adds only the missing **persistent commitment state**.
If that helps, later experiments can test whether richer typed dependency state
or an operational graph adds further value.

## Frozen comparison reference

The context-compiled baseline on the same 20 × 3 development grid achieved:

- terminal feasible: **46/60 (76.7%)**
- feasible-obligation success: **40/60 (66.7%)**
- strict v0.2 success: **14/60 (23.3%)**
- obligation resolution: **72/86 (83.7%)**
- total tokens: **974,208**
- known API cost: **$4.61**
- model calls: **464**

## Development protocol freeze

The live provider path was smoke-tested on development episode 016 before the
full experiment. The first provider smoke exposed an unsupported JSON-schema
keyword and made no model inference. A successful provider smoke then exposed a
general concurrency weakness: when multiple visible facts created independent
future work, the ledger could retain only one. The instruction was refined once
to require separate open items for concurrent commitments.

The final protocol smoke (workflow run `36230552854`) completed normally. It
is **not included in the experiment result**. Subsequent code review identified
two treatment-correctness issues before the 20 × 3 run: ledger updates were
being committed before runtime action acceptance, and resolved-item details
were being replayed unnecessarily in every prompt. Those issues were fixed
without using additional episode outcomes. The treatment is re-frozen after
these review fixes; no further outcome-driven tuning is allowed before the
development run.

## Primary metrics

The primary reliability metric is **feasible-obligation success** because it is
run-level and directly tests whether long-horizon commitments were discharged
without giving up terminal feasibility.

Also report:

- strict v0.2 success;
- terminal feasibility;
- aggregate obligation resolution, with the caveat that the actionable
  denominator is policy-path dependent;
- failure-category counts;
- tokens, calls, cost, and latency;
- ledger open/resolved counts and ledger growth.

## Predeclared development inclusion gate

This is a component-selection rule on development episodes, not a significance
claim.

Retain the ledger as a reliability-component candidate if **either**:

1. feasible-obligation success improves by at least **5 percentage points**
   while terminal feasibility does not fall by more than **5 points**; **or**
2. strict v0.2 success improves by at least **5 percentage points**, while
   feasible-obligation success does not fall by more than **2 points** and
   terminal feasibility does not fall by more than **5 points**.

Otherwise, do not carry the ledger forward merely because persistent memory or
state is a fashionable agent-system concept.

Report paired episode-level deltas and an episode-cluster bootstrap for
descriptive uncertainty. Efficiency is reported but is not a pass condition for
this experiment because the ledger intentionally adds structured output and
persistent state.

## Attribution discipline

This treatment necessarily changes two coupled things relative to factual
context compilation: it asks the model to emit structured commitment state, and
it carries that state forward across steps. Therefore a positive result is
evidence for the **structured commitment-state treatment**, but is not yet
sufficient to attribute the gain specifically to persistence.

If this treatment passes the inclusion gate, run a follow-up persistence
ablation before making that narrower claim: use the same structured commitment
output discipline and one-call budget, but recompute the commitment view from
visible history rather than carrying prior ledger items forward. Only a further
gain from the persistent version supports a persistence-specific conclusion.

## Interpretation discipline

A positive result would support the claim that **explicit structured commitment
state** matters beyond factual context engineering.

It would not by itself establish that:

- ReAct is necessary;
- a planner is necessary;
- a knowledge graph is necessary;
- long-term vector memory is necessary;
- continual learning or self-improvement is necessary.

A negative result would be equally informative: it would push the next causal
test toward explicit planning/replanning rather than adding more memory
infrastructure.

Held-out states remain untouched.
