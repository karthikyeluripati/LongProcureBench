# State Validity Frontier — development protocol v0.2

## Status

**Prospective development comparison. No new results in this protocol.**

Stage-1 remains frozen exactly as observed: **3/3 terminal-feasible, 3/3
feasible-obligation complete, 3/3 strict v0.2, 3/3 economic-objective
satisfied, 0 unresolved obligations**, with 30 accepted actions, 14 model calls,
33,661 tokens, and $0.185558 known API cost.

The original v0.1 strict mechanism gate remains recorded as **failed** because
episode 013 identified suppliers before the buyer clarification response. This
document does not rewrite that result.

## v0.2 semantic clarification

`identify_suppliers` is treated as **non-committing information discovery**.
It does not solicit a quote, create commercial exposure, or commit the buyer.

For prerequisite ordering, the first commercial sourcing boundary is
`send_rfq`.

Therefore, for the 013-style starting-prerequisite mechanism:

- supplier identification may occur before clarification;
- the **first RFQ must occur after the visible buyer-clarification response**;
- clarification remains bounded to one request per unchanged requirement epoch;
- terminal actions still require a current evaluation.

All other State Validity Frontier v0.1 mechanics remain unchanged.

### Explicit prerequisite sequence gate

This ordering is checked directly from the accepted trajectory; it is **not**
inferred from `strict_v02`.

For each of the three development repeats of episode 013:

1. locate the first visible `buyer_clarification` response;
2. locate the first accepted `send_rfq`;
3. require `first_send_rfq_step > buyer_clarification_step`.

The development runner writes `prerequisite-sequence-gate.json` and fails the
protocol execution if any of the three repeats violates this ordering. Thus a
run cannot count as a passing development result merely because its evaluator
quality metrics are favorable.

## Development experiment

Run the already-merged controller unchanged on the frozen development suite:

- episodes: **001-020**
- repeats: **3**
- total State Validity Frontier runs: **60**
- model: `openai/gpt-5.6-sol`
- reasoning effort: `medium`
- temperature: omitted
- max actions: 50
- context: `factual_compiled_v0.1`
- no access to 021-030

Do **not** rerun the baselines. Compare against their already-frozen 20x3
evidence.

### Frozen execution procedure

Use only:

```bash
python scripts/run_state_validity_frontier_development_v02.py \
  --output-dir <fresh-output-directory>
```

The development runner itself hard-codes episodes 001-020, three repeats,
`openai/gpt-5.6-sol`, medium reasoning, omitted temperature, and max-actions
50. It exposes no CLI override for those experimental settings and validates
the exact 60 episode/repeat pairs after execution.

The earlier `run_state_validity_frontier.py` remains the historical **three-run
Stage-1 runner** and is not the development execution procedure.

| Method | Feasible-obligation | Strict v0.2 | Economic objective | Tokens | Cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Factual context | 40/60 (66.7%) | 14/60 (23.3%) | 14/60 (23.3%) | 974,208 | $4.609 |
| ReAct | 41/60 (68.3%) | 27/60 (45.0%) | 28/60 (46.7%) | 1,454,192 | $7.984 |
| **Coverage+Repair** | **50/60 (83.3%)** | **30/60 (50.0%)** | **30/60 (50.0%)** | **687,462** | **$2.978** |
| **State Validity Frontier** | **next run** | **next run** | **next run** | **next run** | **next run** |

## Metrics

Primary quality metric: **feasible-obligation success**.

Always report:

- terminal feasibility;
- feasible-obligation success;
- strict Evaluator v0.2 success;
- obligation-resolution rate;
- economic-objective satisfaction;
- accepted actions;
- model calls;
- prompt/completion/total tokens;
- model latency;
- known API cost;
- deterministic versus LLM frontier actions;
- invalidation diagnostics and unresolved-obligation taxonomy.

There is no weighted composite score.

### Economic metric

Evaluator v0.2 currently freezes **economic-objective satisfaction**: whether a
feasible terminal decision matches an episode's preferred economic outcome.

It does **not** currently expose a continuous dollar-regret number. We will not
add a State-Validity-Frontier-only regret metric mid-comparison. If numeric
procurement regret is added later, it must be separately frozen and recomputed
uniformly from durable trajectories for every compared method.

## Matched inference

Use the existing paired episode-cluster bootstrap contract:

- 20,000 resamples
- seed 20260926
- `sha256-index-v1`
- episode as cluster

Compare State Validity Frontier against Coverage+Repair, ReAct, and factual
context.

## Frozen development gate

Execution must be clean and use the exact frozen grid/settings/code.
Additionally, **all three episode-013 repeats must pass the explicit
buyer-clarification-before-first-RFQ sequence gate**.

Quality requirements:

- feasible-obligation success **>= 47/60 (78.3%)**;
- strict v0.2 **>= 30/60 (50.0%)**;
- economic-objective satisfaction **>= 30/60 (50.0%)**.

Then at least one contribution branch must pass:

1. **Quality branch:** strict or economic success improves by at least **3/60
   (5 pp)** over Coverage+Repair, while total known API cost stays at or below
   frozen ReAct ($7.9842).
2. **Efficiency branch:** feasible-obligation, strict, and economic success all
   stay within **3/60 (5 pp)** of Coverage+Repair while known API cost improves
   by at least **20%** versus Coverage+Repair.

Only then do we proceed to component ablations.

If the gate fails, freeze the result. Do not tune the controller on episodes
001-020 until it passes.

## Ablations if the gate passes

1. remove dependency invalidation while retaining frontier gating;
2. retain validity annotations but remove frontier gating;
3. retain the frontier but call the LLM at every step instead of executing
   singleton frontiers deterministically.

These isolate whether gains come from invalidation, action-space restriction,
or selective model allocation.

## Held-out hygiene

Episodes 021-030 remain diagnostic-only for this new method.

A new untouched **031+** test set is authored and frozen only after development
and retained ablations are complete. No held-out trajectory may alter the
controller, prompt, metrics, or gate.
