# Maintained working-plan reactive baseline v0.1

This experiment tests the next causal hypothesis after the operational-ledger
negative result:

> Long-horizon reliability may depend less on accumulating persistent
> commitments and more on maintaining a small prospective plan that tells the
> agent what to do next, when to revise course, and when to stop.

The treatment adds a **bounded, replaceable working plan** on top of the frozen
factual context compiler. It does not add a second planner call, verifier,
knowledge graph, evaluator-derived state, or hidden memory.

## Matched comparison

The comparison condition is the frozen factual context-compiled GPT-5.6 Sol
baseline.

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

The treatment differences are only:

1. each model response also returns a structured `next_plan`;
2. the most recently accepted plan is included in the next model-facing state;
3. the system instruction defines how the plan should be replaced when stale or
   unproductive.

This is therefore a test of **externally represented prospective working
state**, not of additional inference-time compute.

## Working-plan contract

The model-facing plan has exactly three fields:

- `objective` — the current procurement objective;
- `next_steps` — at most **four** prospective future actions, each with an
  action type, optional currently-visible supplier, and short purpose;
- `stop_condition` — an observable condition for making a terminal
  award/no-award decision or otherwise ending the current plan.

The plan uses **full replacement semantics**. It is not an append-only memory:
after every accepted action, the newly proposed plan replaces the previous one.

The current action and next plan are produced by the **same model call**. The
new plan is interpreted as the remaining plan *after* that action. As with the
operational ledger fix, the plan commits only after the runtime accepts the
semantic action. A rejected action cannot mutate persistent plan state.

The plan is deliberately constrained so it cannot contain:

- evaluator checkpoints or obligation labels;
- oracle constraints/outcomes;
- hidden suppliers or future events;
- chain-of-thought;
- arbitrary long histories;
- more than four prospective steps.

A planned supplier may be named only if that supplier is already visible in the
state used for the call.

The semantic action and the auxiliary plan have separate validity consequences.
If the action is valid but the proposed plan violates the bounded-plan contract
(for example, more than four steps or a non-visible supplier), the harness
records a **plan rejection**, keeps the previously accepted plan unchanged, and
still sends the semantic action to the runtime. An invalid auxiliary plan must
not truncate an otherwise valid episode. Any remaining `WorkingPlanError`
indicates a policy lifecycle/internal consistency failure and fails live-run
validation.

## Why this is distinct from the failed ledger

Operational-ledger v0.1 accumulated open commitments and produced a strong
fixation failure: 652 buyer-clarification actions and 11 max-action runs.

This treatment does **not** preserve unresolved work as an append-only set.
Instead, the model sees one small plan that can be replaced wholesale whenever
visible facts make it stale or unproductive. The prompt explicitly treats the
plan as guidance rather than an obligation.

No episode-specific anti-loop rule is added. The treatment is testing whether
bounded prospective structure itself changes behavior.

## Frozen comparison reference

The factual context-compiled baseline on the same 20 × 3 development grid is:

- terminal feasible: **46/60 (76.7%)**
- feasible-obligation success: **40/60 (66.7%)**
- strict v0.2 success: **14/60 (23.3%)**
- obligation resolution: **72/86 (83.7%)**
- total tokens: **974,208**
- known API cost: **$4.61**
- model calls: **464**
- max-action runs: **0**

## Development protocol freeze

The offline regression suite passed on Python 3.10 and 3.12 before live use.

A single provider-compatibility smoke was then run on development episode 004:

- workflow run: `36242197100`
- execution head: `84cb5d4adfc9d343aea8f7251c64ead3c988f750`
- artifact: `10906856017`
- GPT-5.6 Sol call path, structured schema, runtime execution, evaluator coverage,
  and artifact upload all completed successfully.

The smoke is **not part of the experiment result**. Its episode outcome was not
used to change the prompt, schema, plan semantics, inclusion gate, or evaluation
protocol.

Before the 20 × 3 run, code review identified two observability/correctness
issues without using additional episode outcomes: locally invalid auxiliary plan
updates could terminate an otherwise valid action, and plan-length/update
diagnostics were missing from aggregate outputs. Those issues were fixed by
rejecting only the invalid plan update while allowing the action to proceed, and
by carrying plan diagnostics into `runs.csv` and `summary.json`. The
working-plan treatment is re-frozen after these review fixes.

## Primary metrics

Primary reliability metric:

1. **feasible-obligation success**

Also report:

- terminal feasibility;
- strict v0.2 success;
- aggregate obligation resolution, with its policy-path-dependent denominator;
- unresolved-obligation categories;
- max-action runs and action-type distribution;
- tokens, calls, latency, and known API cost;
- plan update and plan-rejection counts;
- mean/max plan length and plan replacement trace diagnostics.

## Predeclared development inclusion gate

This is a development component-selection rule, not a significance claim.

Retain the maintained working plan as a candidate if **either**:

1. feasible-obligation success improves by at least **5 percentage points**
   while terminal feasibility does not fall by more than **5 points**; **or**
2. strict v0.2 success improves by at least **5 percentage points**, while
   feasible-obligation success does not fall by more than **2 points** and
   terminal feasibility does not fall by more than **5 points**.

Efficiency is reported but is not a pass condition for this mechanism test,
because the plan adds structured output while preserving the same one-call
cadence.

Report paired episode-level deltas and a 20-episode cluster bootstrap with the
same deterministic bootstrap protocol used for prior architecture comparisons.

## Interpretation discipline

A positive result would support the claim that **bounded prospective working
state** helps beyond factual context compilation.

It would not establish that:

- a separate planner model call is necessary;
- ReAct-style hidden reasoning traces are necessary;
- always-replanning is necessary;
- a verifier is necessary;
- selective event-triggered replanning is necessary.

If this treatment passes, the next experiment should test whether dedicated
replanning/verification adds anything beyond the maintained plan.

If it fails, do not keep plan state merely because plan-and-execute is a common
agent pattern. Move to the next distinct computation hypothesis instead.

Held-out starting states remain untouched, and no held-out episodes may be
authored or evaluated during this development experiment.
