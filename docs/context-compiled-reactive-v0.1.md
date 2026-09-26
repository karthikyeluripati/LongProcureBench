# Context-compiled reactive baseline v0.1

This experiment tests one narrow causal hypothesis:

> The reactive agent already has the necessary visible facts, but raw benchmark
> serialization presents them with unnecessary provenance, duplication, and weak
> salience. A deterministic factual context compiler may improve long-horizon
> reliability without adding planning calls or memory.

This is **not** an obligation-memory baseline and it is not ProcureHarness.

## Matched conditions

The experiment is matched to the frozen GPT-5.6 Sol raw-history baseline:

- model: `openai/gpt-5.6-sol`
- reasoning effort: `medium`
- temperature: omitted
- episodes: frozen development/calibration 001–020 only
- repeats: 3
- maximum accepted actions: 50
- same `BenchmarkRunner`
- same runtime/evaluator
- same action schema
- same system prompt
- one fresh model call per action
- no hidden conversation memory
- no planner, reflection, verifier, or retry loop

Only the model-facing state representation changes.

## Factual compiler contract

The compiler may reorganize or remove redundant information that is already
agent-visible. It must never infer what the agent *should* do.

It retains:

- project/package identity and operational scope;
- line items, quantities, technical summaries, alternates, known buyer costs;
- schedule, eligibility, and compliance requirements;
- operationally relevant missing-information facts;
- currently visible supplier identities;
- all revealed event facts in compact form;
- the latest revealed **awardable quote/revision** per supplier and scope;
- revealed buyer requirement/quantity clarifications and changes;
- compact accepted action history.

It strips:

- source URLs and document catalog metadata;
- field-level provenance/locators;
- snapshot/checksum bookkeeping;
- event trigger/emission metadata that the runtime has already consumed;
- duplicated current-observation serialization.

It must not add:

- `obligation`, `required_checkpoint`, or evaluator fields;
- stale/feasible/infeasible labels;
- preferred suppliers or award recommendations;
- "needs follow-up", "must replan", or next-action hints;
- hidden suppliers, future events, oracle outcomes, or episode-specific rules.

`latest_offers` means only the last revealed runtime-awardable
`quote_received` or `quote_revision` event for a supplier/scope. A
`substitution_proposed` event remains visible in `event_history` because it
can justify a later revision request, but it is not presented as an awardable
offer. The recency view still does not claim that a quote remains valid after
later requirement changes or withdrawal.

## Why this is first

The 180-run cross-family baseline showed that raw-history agents can reach
feasible terminal decisions while leaving 107/241 actionable obligations
unresolved. But the runtime already exposes complete accepted action history and
all revealed events. Before introducing persistent memory or planning, the
cheapest clean test is therefore whether **better context representation alone**
changes the result.

## Primary comparison

The frozen GPT-5.6 Sol raw-history reference is:

- 60 runs
- terminal feasible: 49/60 (**81.7%**)
- feasible-obligation success: 41/60 (**68.3%**)
- strict v0.2 success: 19/60 (**31.7%**)
- obligation resolution: 73/94 (**77.7%**)
- total tokens: **1,640,350**
- known API cost: **$6.35**

The context-compiled experiment will produce the same 20 × 3 grid.

Primary reliability metrics:

1. feasible-obligation success;
2. obligation-resolution rate;
3. terminal feasibility as a guardrail.

Efficiency metrics:

- total and mean tokens;
- accepted actions/model calls;
- latency;
- known API cost.

Failure-type counts remain diagnostic.

## Development inclusion gate

This is an engineering/research selection rule on development episodes, not a
claim of statistical significance.

Keep context compilation as a component candidate if either:

1. feasible-obligation success or obligation-resolution rate improves by at
   least **5 percentage points** while terminal feasibility does not fall by
   more than **5 points**; or
2. both reliability metrics remain within **2 points** of the raw baseline
   while total tokens fall by at least **15%**.

Otherwise, do not carry the compiler forward merely because "context
engineering" is fashionable.

For analysis, report episode-level paired differences across the same 20
development episodes and a cluster bootstrap over episode IDs. The thresholds
above remain the predeclared component-selection rule.

## Next gate

If this experiment earns inclusion, the next distinct hypothesis is an
**explicit structured obligation/state ledger**. That experiment may infer and
persist open/resolved work from visible events. The context compiler in this PR
deliberately may not.
