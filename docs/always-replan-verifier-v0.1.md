# Always-replan + pre-terminal verifier v0.1

## Research question

Does explicit **additional computation** improve long-horizon procurement
reliability beyond factual context compilation, after the persistent
operational-ledger and maintained-working-plan treatments failed?

This is deliberately a quality-heavy comparator, not yet the efficient
ProcureHarness mechanism.

## Frozen treatment

Matched to the factual context-compiled GPT-5.6 Sol baseline:

- same frozen development episodes 001-020;
- same model: GPT-5.6 Sol;
- reasoning effort: medium;
- temperature omitted;
- same runtime, evaluator, semantic action contract, and 50 accepted-action cap;
- same factual context compiler.

Each decision performs:

1. a fresh structured **planner** call from current visible state;
2. an **action-selection** call conditioned on that fresh plan;
3. only when the proposed action is terminal (award/no-award), a separate
   **pre-terminal verifier** call;
4. if the verifier rejects the terminal action, exactly one bounded
   **non-terminal repair-action** call.

The repair schema forbids award/no-award so a rejected terminal decision cannot
bypass verification in the same step.

## Information boundary

Planner, action selector, verifier, and repair pass may use only the same
agent-visible facts already available through the factual compiled context.

They may not receive or infer from harness-provided labels:

- evaluator checkpoints or obligation labels;
- terminal-correctness labels;
- oracle constraints/outcomes;
- hidden suppliers;
- future events;
- unrevealed quotes;
- held-out data.

The structured planner/verifier records are external compact artifacts, not
private chain-of-thought.

## Predeclared development gate

Compare the 60-run treatment grid against the frozen 60-run context-compiled
GPT-5.6 Sol grid.

Retain the quality mechanism for the next efficiency experiment if either:

1. feasible-obligation success improves by **>=5 percentage points** while
   terminal feasibility falls by **<=5 points**; or
2. strict v0.2 success improves by **>=5 points**, while
   feasible-obligation success falls by **<=2 points** and terminal feasibility
   falls by **<=5 points**.

Tokens, model calls, latency, and API cost are diagnostics rather than pass
conditions for this experiment because the treatment intentionally purchases
extra inference. They become primary targets in the conditional selective
replanning experiment.

## Conditional next step

- **Pass:** test selective event-triggered replanning + pre-terminal verifier to
  retain quality with fewer calls/tokens/latency/cost.
- **Fail:** do not optimize this mechanism for efficiency; reassess the failure
  axis before adding more architecture.

No held-out episode is authored, inspected, or evaluated by this experiment.
