# ReAct comparator v0.1

## Purpose

This is a **recognizable external baseline/comparator**, not a new
ProcureHarness mechanism and not another architecture-search candidate.

The comparator asks whether the standard ReAct pattern — explicit
**Thought -> Action -> Observation** iteration — behaves differently from the
reactive and factual-context baselines on LongProcureBench.

## Frozen comparator definition

The comparator uses:

- the same 20 frozen development/calibration episodes 001-020;
- GPT-5.6 Sol;
- reasoning effort = medium;
- temperature omitted;
- the same deterministic runtime and Evaluator v0.2;
- the same semantic procurement action contract;
- the same 50 accepted-action cap;
- the retained factual context compiler (`factual_compiled_v0.1`).

At every environment step, exactly **one model call** returns:

1. `thought_summary`: a concise, externally represented decision rationale;
2. `action`: exactly one semantic LongProcureBench action.

After the action is accepted, the environment observation from that transition
is appended to an explicit ReAct transcript. The next model call receives the
current factual compiled state plus the accepted transcript of prior
Thought/Action/Observation steps.

The thought summary is bounded before persistence. It is an auditable external
working trace, not hidden provider chain-of-thought.

## Information boundary

ReAct receives no information beyond what is already agent-visible:

- no evaluator results/checkpoints/obligation labels;
- no oracle outcomes or hard constraints;
- no hidden suppliers;
- no future events;
- no held-out data;
- no episode-specific policy rules.

The comparator does not add planners, verifiers, ledgers, retrieval systems,
memory stores, deterministic repairs, or extra model calls.

## Measurement

The development measurement is one frozen grid:

**20 episodes x 3 repeats = 60 runs**

Report the same benchmark metrics used elsewhere:

- terminal feasibility;
- feasible-obligation success;
- strict v0.2 success;
- obligation resolution;
- accepted actions;
- model calls;
- prompt/completion/total tokens;
- aggregate model latency;
- known API cost;
- action-type and failure distributions.

Also report ReAct-specific descriptive diagnostics:

- number of accepted ReAct transcript steps;
- thought-summary character counts;
- transcript growth.

There is **no inclusion gate** because this is not a candidate architecture.
Its result is reported as a comparator whether it performs better, worse, or
the same.

## Execution discipline

1. merge the implementation only after offline tests/CI pass;
2. run one live smoke only for provider/schema/runtime compatibility;
3. if smoke is clean, run exactly one 60-run development measurement;
4. do not tune the comparator from the measurement outcome;
5. freeze the result before any held-out evaluation.

Held-out starting states and future held-out episodes remain untouched.
