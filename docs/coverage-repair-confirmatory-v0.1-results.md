# Coverage + Repair confirmatory v0.1 — frozen development result

## Question

How much of the frozen ReAct improvement is explained by a much simpler
procurement workflow rule: finish visible supplier coverage and discharge
obvious visible supplier-interaction repair without purchasing a model call for
every routine action?

Coverage + Repair is a **diagnostic baseline**, not a proposed ProcureHarness
method.

## Source

- protocol frozen before execution: `005c526416eb18789a2431d347c1cc3f635f035d`
- execution commit: `e2bdf265bd284cfbebab5eddf16629acd1a0a885`
- workflow run: `36345529581`
- artifact: `10941001111`
- artifact digest:
  `sha256:c8a0c85e6ec00af8199d0085a9bcbc64ea46826d92d0a20a0df00aad485474a5`
- grid: GPT-5.6 Sol × 20 frozen development episodes × 3 repeats = **60 runs**
- **60/60 completed**
- exact 20 × 3 grid validation passed
- no held-out episodes 021-030 were run

## Main comparison

| Method | Terminal | Feasible + obligations | Strict v0.2 | Economic | Model calls | Tokens | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Factual context | 46/60 (76.7%) | 40/60 (66.7%) | 14/60 (23.3%) | 14/60 (23.3%) | 464 | 974,208 | $4.61 |
| ReAct | 52/60 (86.7%) | 41/60 (68.3%) | 27/60 (45.0%) | 28/60 (46.7%) | 488 | 1,454,192 | $7.98 |
| **Coverage + Repair** | **52/60 (86.7%)** | **50/60 (83.3%)** | **30/60 (50.0%)** | **30/60 (50.0%)** | **324** | **687,462** | **$2.98** |

Relative to factual context, Coverage + Repair changes:

- terminal feasibility: **+10.0 pp**
- feasible-obligation success: **+16.7 pp**
- strict v0.2: **+26.7 pp**
- economic objective: **+26.7 pp**
- model calls: **-30.2%**
- tokens: **-29.4%**
- known API cost: **-35.4%**
- aggregate model latency: **-23.3%**

Relative to ReAct:

- terminal feasibility: **0.0 pp**
- feasible-obligation success: **+15.0 pp**
- strict v0.2: **+5.0 pp**
- economic objective: **+3.3 pp**
- model calls: **-33.6%**
- tokens: **-52.7%**
- known API cost: **-62.7%**
- aggregate model latency: **-47.7%**

The point estimates do **not** establish statistical superiority over ReAct.
They do establish that this simple external workflow baseline reaches the same
development quality region while using substantially less inference.

## Predeclared interpretation

The confirmatory protocol defined ReAct-gain recovery as:

`(CoverageRepair - Context) / (ReAct - Context)`.

Observed:

- strict-v0.2 ReAct-gain recovery: **123.1%**
- economic-objective ReAct-gain recovery: **114.3%**

Both predeclared branches pass:

1. **Substantial workflow explanation:** passed.
2. **Near-ReAct workflow explanation:** passed.

This means the earlier ReAct result cannot be interpreted as evidence that
Thought -> Action -> Observation reasoning itself is the main source of the
procurement gain. A large share of the gain is recoverable through explicit
workflow coverage and bounded repair.

## Mechanism diagnostics

Coverage + Repair performed **152 deterministic interventions**:

- 123 RFQs to complete visible supplier coverage
- 21 non-response follow-ups
- 8 supplier-question answers

Those actions replaced model decisions rather than adding model calls.
Coverage + Repair executed 476 accepted actions but only 324 model calls.

Action distributions also sharpen the mechanism:

- RFQs: context 149; ReAct 178; Coverage + Repair **183**
- follow-ups: context 12; ReAct 10; Coverage + Repair **21**
- quote-revision requests: context 41; ReAct 51; Coverage + Repair **22**

The strongest evidence is therefore not "more reasoning is better." It is that
reliably executing routine procurement coverage/repair can expose enough useful
market state for the LLM to make better downstream decisions while spending
less inference.

## Remaining failures

Coverage + Repair still leaves **8/98 actionable obligations unresolved**:

- withdrawal recovery: 3
- quote revision: 3
- starting requirement-gap resolution: 2

These are important because the deterministic baseline does not solve the whole
long-horizon problem. They define cleaner residual failure classes for the next
agent-pattern comparisons.

## Research consequence

The next paper step should **not** be to promote Coverage + Repair as the novel
agent architecture. It is deliberately simple and domain-engineered.

Instead it becomes a strong diagnostic baseline. Any proposed new pattern must
now beat or extend:

**Reactive -> ReAct -> Plan/Execute or Reflexion -> Coverage+Repair -> proposed method**

The new method must add something that cannot be explained by merely completing
a procurement workflow skeleton.

In particular, remaining candidates should be justified against residual
failures such as dynamic invalidation, withdrawal recovery, selective revision,
requirement-gap handling, and deciding when more evidence is worth acquiring.

## Evidence status

This is development evidence. The exact Actions artifact is retained temporarily
and its ID/digest are frozen under
`evidence/coverage-repair-confirmatory-v0.1/`. If this diagnostic is promoted
into final paper evidence, materialize a compact replay source before the
Actions artifact expires.
