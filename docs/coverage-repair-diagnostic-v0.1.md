# Coverage + Repair diagnostic v0.1

## Research question

The frozen ReAct comparison improved strict and economic outcomes, but trajectory
inspection shows that many wins coincide with obtaining supplier evidence that
the factual context-reactive policy never observed.

This diagnostic asks:

> How much of ReAct's gain is explained by a simple procurement workflow rule:
> finish visible supplier coverage and discharge obvious event-triggered repair
> work, without buying a Thought -> Action -> Observation model call for every
> step?

This is a **baseline diagnostic**, not a ProcureHarness method proposal.

## Matched information boundary

The policy inherits `ContextCompiledReactiveLLMPolicy` and therefore keeps:

- the same factual compiled state;
- the same semantic action space;
- the same runtime and Evaluator v0.2;
- the same model and sampling configuration;
- no oracle/evaluator fields;
- no hidden suppliers or future events;
- no episode-specific heuristics.

## Deterministic controller

The controller does **not** decide when sourcing should begin. The LLM must send
the first RFQ itself.

After the first accepted RFQ, the controller may take only these visible-state
actions without an additional model call:

1. `supplier_non_response` -> one `send_follow_up` for that supplier;
2. `supplier_question` -> one `answer_supplier_question` for that supplier;
3. `requirement_change` or `quantity_change` -> one `issue_amendment`
   after that visible event;
4. send one RFQ to each currently visible supplier that has not yet received an
   RFQ.

Visible event repair takes priority over opening another supplier branch.

The controller does **not** deterministically:

- request the initial buyer clarification;
- request quote revisions;
- judge feasibility/compliance/eligibility;
- evaluate quotes;
- choose an award;
- choose no-award;
- inspect the benchmark oracle or evaluator.

Those remain model decisions.

## Why this baseline is necessary

If this simple workflow recovers most of ReAct's strict/economic improvement at
substantially lower model-call cost, then the ReAct gain is largely attributable
to procurement workflow coverage rather than the reasoning pattern itself.

If it does not, the residual gap is evidence that iterative reasoning contributes
something beyond deterministic coverage/repair. That residual is what later
Plan-and-Execute, Reflexion, and a proposed new agent pattern should explain.

## Cost-control protocol

Do not start with a 60-run paid experiment.

### Stage 1: live protocol smoke

Exactly three development episodes, one repeat each:

- `electrical-bongabon-generator-001`
- `electrical-dla-power-supply-016`
- `electrical-vre-generator-020`

Model/settings:

- `openai/gpt-5.6-sol`
- reasoning effort `medium`
- temperature omitted
- maximum 20 accepted actions

The smoke is only a protocol check. Continue only if:

- all three runs have valid execution/evaluation;
- at least one deterministic intervention fires;
- no run hits the action cap;
- no deterministic action is rejected by the environment.

### Stage 2: development diagnostic

Only after the smoke passes, run the 20 development episodes once. Compare
paired episode outcomes and resource use against the existing factual-context
and ReAct evidence. Do not run 20 x 3 unless the one-repeat diagnostic reveals
a scientifically meaningful distinction worth confirming.

## Data-use boundary

Episodes 021-030 were already inspected through the frozen PR38 evaluation and
are now diagnostic evidence, not an untouched test set for a newly designed
method. This baseline should be developed on episodes 001-020. Any eventual
ProcureHarness method requires a fresh held-out slice.
