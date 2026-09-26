# Context-compiled reactive v0.1 — matched result

This is a development/calibration experiment on the same frozen 20 episodes as
the raw-history GPT-5.6 Sol baseline. It changes only the model-facing factual
state representation; model, reasoning setting, action schema, runtime,
evaluator, and one-call-per-step reactive policy are matched.

The result is a **mixed, narrow pass** of the predeclared component gate. Context
compilation is retained as an **efficiency-layer candidate**, not as the
long-horizon reliability mechanism.

## Source

- Live workflow run: `36226304814`
- Source artifact: `10901395062`
- Benchmark code: `98a698654ef454a7b48af6f701e41cf49fea6638`
- Execution head: `0673a425685b75a4317f89eed138d28a3436a769`
- Execution-head delta: workflow trigger only
- Grid: GPT-5.6 Sol × 20 development episodes × 3 repeats = **60 runs**
- All 60 runs completed and passed live execution/evaluator validation.

## Matched comparison

| Metric | Raw history | Context compiled | Delta |
| --- | ---: | ---: | ---: |
| Terminal feasible | 49/60 (**81.7%**) | 46/60 (**76.7%**) | **-5.0 pp** |
| Feasible-obligation success | 41/60 (**68.3%**) | 40/60 (**66.7%**) | **-1.7 pp** |
| Strict v0.2 success | 19/60 (**31.7%**) | 14/60 (**23.3%**) | **-8.3 pp** |
| Obligation resolution | 73/94 (**77.7%**) | 72/86 (**83.7%**) | **+6.1 pp** |
| Prompt tokens | 1,602,951 | 931,985 | **-41.9%** |
| Total tokens | 1,640,350 | 974,208 | **-40.6%** |
| Model calls | 441 | 464 | **+5.2%** |
| Known API cost | $6.35 | $4.61 | **-27.5%** |
| Aggregate model latency | 706,902 ms | 869,561 ms | **+23.0%** |

The compiler therefore made each decision context substantially cheaper in
tokens, but the agent took slightly more actions/calls and aggregate model
latency increased.

## Predeclared gate

The development inclusion gate was frozen before the experiment. Keep the
component if **either**:

1. feasible-obligation success **or** obligation-resolution rate improves by at
   least **5 percentage points**, while terminal feasibility does not fall by
   more than **5 points**; **or**
2. both reliability metrics remain within **2 points** of the raw baseline,
   while total tokens fall by at least **15%**.

This result passes through **condition 1**, at the boundary of its terminal
guardrail:

- obligation resolution: **+6.1 pp**
- terminal feasibility: **-5.0 pp exactly**

Condition 2 is not the basis for this result because obligation resolution moved
by more than 2 points.

This must not be interpreted as an overall quality win. Feasible-obligation
success fell 1.7 pp and strict v0.2 success fell 8.3 pp.

## Cluster bootstrap

A paired cluster bootstrap over the 20 episode IDs (20,000 resamples,
seed `20260926`, version-independent sampler `sha256-index-v1`) gives
descriptive 95% intervals:

| Delta | 95% interval |
| --- | ---: |
| Terminal feasible | **[-16.7, +5.0] pp** |
| Feasible-obligation success | **[-18.3, +15.0] pp** |
| Strict v0.2 success | **[-20.0, +1.7] pp** |
| Obligation resolution | **[-5.5, +19.5] pp** |
| Total tokens | **[-47.3%, -33.1%]** |
| Cost | **[-38.9%, -12.4%]** |
| Aggregate model latency | **[+11.4%, +34.7%]** |

The reliability intervals are wide and cross zero. The efficiency signal is much
clearer: token and cost reduction are consistent across episode-cluster
resamples.

## Behavior changed, not just serialization size

Compared with raw history, the compiled policy produced:

- buyer clarifications: **22 → 47**
- supplier follow-ups: **2 → 12**
- RFQs: **165 → 149**
- quote evaluations: **64 → 74**

This is consistent with factual salience changing the policy's action
distribution. Unresolved actionable obligation instances changed from
**21/94** to **14/86**. Because the number and type of triggered obligations also
changed with the policy's actions, that absolute reduction is descriptive rather
than a like-for-like reliability improvement. Terminal/economic regressions were
large enough that end-to-end success did not improve.

## The central failure remains

On `electrical-dla-power-supply-016`, the strongest earlier
terminal-vs-obligation diagnostic, context compilation did **not** solve the
problem:

- raw history: terminal feasible **3/3**, obligation success **0/3**,
  obligations resolved **4/7**
- context compiled: terminal feasible **3/3**, obligation success **0/3**,
  obligations resolved **3/6**

So better factual context alone is not the missing reliability mechanism.

## Decision

**Keep factual context compilation as an efficiency layer candidate. Do not
claim it improves long-horizon reliability.**

The next causal experiment should add an explicit **operational
state/obligation ledger** on top of this factual context:

`raw history → factual compiled context → compiled context + obligation ledger`

That comparison asks the question now supported by the evidence: whether
explicitly maintaining triggered commitments and their resolution state closes
the remaining long-horizon gap while preserving most of the context-efficiency
gain.

Held-out states remain untouched.
