# Always-replan + pre-terminal verifier v0.1 — matched result

This is the fourth controlled architecture experiment on the frozen 20-episode
LongProcureBench development suite. It keeps factual context compilation and the
same GPT-5.6 Sol/runtime/evaluator/action contract, but explicitly buys extra
inference: a fresh planner before every action, a separate verifier for proposed
terminal award/no-award decisions, and one repair call after a verifier
rejection.

The result **fails the predeclared inclusion gate by a wide margin**. The
quality-heavy replanning/verifier formulation is dropped, and the conditional
selective-replanning efficiency experiment is **not justified** by this result.

## Source

- Live workflow run: `36286064411`
- Source artifact: `10924959171`
- Artifact digest: `sha256:8e08847b3fb9725703adb7d0d4046e88a92fdc6ead9f0f7226fe8ccdabf7f7df`
- Benchmark code: `6fa855bf33698aa0380c794dcba4a3ab15b07e89`
- Execution head: `2c66dd7f79a04a99d0d29afee46dd14095b7a7a6`
- Execution-head delta: workflow trigger only
- Grid: GPT-5.6 Sol × 20 development episodes × 3 repeats = **60 runs**
- Live execution/evaluator validation passed for all 60 runs; usage and API cost
  are complete. **32/60 runs reached the 50-action cap.**
- After downloading the source artifact ZIP, independently verify every raw-run
  hash and compact-record provenance entry with:
  `python scripts/verify_always_replan_verifier_source_artifact_v01.py --artifact-zip <artifact.zip>`

The earlier one-episode smoke was only a provider/protocol check and is not used
as paper evidence.

## Matched comparison

| Metric | Context compiled | Always-replan + verifier | Delta |
| --- | ---: | ---: | ---: |
| Terminal feasible | 46/60 (**76.7%**) | 14/60 (**23.3%**) | **-53.3 pp** |
| Feasible-obligation success | 40/60 (**66.7%**) | 12/60 (**20.0%**) | **-46.7 pp** |
| Strict v0.2 success | 14/60 (**23.3%**) | 5/60 (**8.3%**) | **-15.0 pp** |
| Obligation resolution | 72/86 (**83.7%**) | 49/67 (**73.1%**) | **-10.6 pp** |
| Accepted actions | 464 | 1,830 | **+294.4%** |
| Model calls | 464 | 4,802 | **+934.9%** |
| Total tokens | 974,208 | 19,923,896 | **+1,945.1%** |
| Known API cost | $4.61 | $116.08 | **+2,418.8%** |
| Aggregate model latency | 869,561 ms | 16,977,794 ms | **+1,852.5%** |

This is not a quality/cost tradeoff. Reliability and efficiency both regress
substantially.

## Predeclared gate

The protocol was frozen before the full treatment. Retain the mechanism if
either:

1. feasible-obligation success improves by at least **5 pp** while terminal
   feasibility falls by no more than **5 pp**; or
2. strict v0.2 success improves by at least **5 pp**, while feasible-obligation
   success falls by no more than **2 pp** and terminal feasibility falls by no
   more than **5 pp**.

Observed:

- feasible-obligation success: **-46.7 pp**
- terminal feasibility: **-53.3 pp**
- strict v0.2: **-15.0 pp**

Therefore **neither branch passes**.

## Episode-cluster bootstrap

A paired episode-cluster bootstrap over the 20 episode IDs (20,000 resamples,
seed `20260926`, deterministic `sha256-index-v1` sampling) gives descriptive
95% intervals:

| Delta | 95% interval |
| --- | ---: |
| Terminal feasible | **[-71.7, -35.0] pp** |
| Feasible-obligation success | **[-68.3, -25.0] pp** |
| Strict v0.2 success | **[-31.7, 0.0] pp** |
| Obligation resolution | **[-26.4, +6.1] pp** |
| Accepted actions | **[+204.3%, +395.6%]** |
| Model calls | **[+689.8%, +1,216.2%]** |
| Total tokens | **[+1,413.0%, +2,558.2%]** |
| Cost | **[+1,734.0%, +3,301.1%]** |
| Aggregate model latency | **[+1,372.9%, +2,386.8%]** |

The two primary run-level reliability intervals remain entirely below zero,
while resource increases remain entirely above zero.

## Mechanism diagnostic

The dominant behavioral shift is a verifier-induced information-seeking loop:

- the selector proposed **585** terminal decisions;
- the verifier rejected **557/585 (95.2%)**;
- **545/557 (97.8%)** rejected terminals were routed to
  `request_buyer_clarification`;
- accepted buyer-clarification actions increased from **47 → 1,329**;
- **32/60** runs reached the 50-action cap;
- terminal awards fell from **58 → 15**.

The treatment therefore did use the intended extra computation, but the
verifier repeatedly treated visible uncertainty or missing source information
as a reason to seek more buyer evidence, even when the environment often had no
new resolution path. This is a mechanism diagnostic for this formulation, not a
claim that verification is universally harmful.

Feasible-obligation success improved on only **3/20** episode clusters, worsened
on **14/20**, and tied on 3.

## Decision

**Drop always-replan + pre-terminal verifier v0.1.**

Do **not** run the previously planned selective event-triggered replanning +
verifier experiment as an efficiency optimization: the parent quality-heavy
mechanism did not establish a quality gain to preserve.

The controlled development sequence now says:

- compact factual context is useful primarily for efficiency;
- persistent commitment state can create fixation;
- a maintained prospective plan does not solve reliability;
- buying much more planning and verification compute can make both reliability
  and cost dramatically worse.

The next research question should therefore focus on **actionability/progress**,
not more state or more generic reasoning:

> Can the agent distinguish uncertainty that has a currently available evidence-
> gathering action from irreducible/missing-at-source uncertainty, and avoid
> repeating information-seeking actions when the visible state has not changed?

A future treatment should be specified only after that mechanism is defined
without evaluator leakage. A true ReAct implementation remains useful as a
recognizable comparator, but it should not be confused with the next
ProcureHarness mechanism.

Held-out states and future held-out episodes remain untouched.
