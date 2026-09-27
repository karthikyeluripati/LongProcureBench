# Progress-aware reactive v0.1 — matched result

This is the fifth controlled architecture experiment on the frozen 20-episode
LongProcureBench development suite. It keeps factual context compilation and the
same GPT-5.6 Sol/runtime/evaluator/action contract, and adds a deterministic
visible-evidence progress guard intended to suppress repeated no-progress
information-seeking actions.

The result **fails the predeclared inclusion gate**. More importantly, the
guard itself never had to intervene in the 60-run grid, so this experiment does
not establish that deterministic blocking improves reliability.

## Source

- Live workflow run: `36312020696`
- Source artifact: `10929711515`
- Artifact digest: `sha256:063cc839f2338116a3a4776ce68a17bdbd5293bcde551bcd4dbc203909238688`
- Benchmark code: `aa0560a43c81c14931e22e2f6ac2bd142820b834`
- Execution head: `e615af9ca23806e3dcd14e0cca83aea6297c38be`
- Execution-head delta: workflow trigger only
- Grid: GPT-5.6 Sol × 20 development episodes × 3 repeats = **60 runs**
- All 60 runs completed and passed live execution/evaluator validation.
- Usage and known API cost are complete for all 60 runs.

After downloading the source artifact ZIP, independently verify every raw-run
hash and compact-record provenance entry with:

`python scripts/verify_progress_aware_source_artifact_v01.py --artifact-zip <artifact.zip>`

## Matched comparison

| Metric | Context compiled | Progress aware | Delta |
| --- | ---: | ---: | ---: |
| Terminal feasible | 46/60 (**76.7%**) | 47/60 (**78.3%**) | **+1.7 pp** |
| Feasible-obligation success | 40/60 (**66.7%**) | 30/60 (**50.0%**) | **-16.7 pp** |
| Strict v0.2 success | 14/60 (**23.3%**) | 15/60 (**25.0%**) | **+1.7 pp** |
| Obligation resolution | 72/86 (**83.7%**) | 73/99 (**73.7%**) | **-10.0 pp** |
| Accepted actions | 464 | 449 | **-3.2%** |
| Model calls | 464 | 449 | **-3.2%** |
| Total tokens | 974,208 | 1,041,842 | **+6.9%** |
| Known API cost | $4.61 | $4.03 | **-12.5%** |
| Aggregate model latency | 869,561 ms | 803,182 ms | **-7.6%** |

Terminal feasibility and strict success move slightly upward, but the primary
long-horizon obligation metric regresses substantially.

## Predeclared gate

Retain the mechanism only if either:

1. feasible-obligation success improves by at least **5 pp**, terminal
   feasibility falls by no more than **5 pp**, and total tokens increase by no
   more than **15%**; or
2. strict v0.2 success improves by at least **5 pp**, feasible-obligation
   success falls by no more than **2 pp**, terminal feasibility falls by no
   more than **5 pp**, and total tokens increase by no more than **15%**.

Observed:

- feasible-obligation success: **-16.7 pp**
- terminal feasibility: **+1.7 pp**
- strict v0.2: **+1.7 pp**
- total tokens: **+6.9%**

Therefore **neither branch passes**.

## Episode-cluster bootstrap

A paired episode-cluster bootstrap over the 20 episode IDs (20,000 resamples,
seed `20260926`, deterministic `sha256-index-v1` sampling) gives descriptive
95% intervals:

| Delta | 95% interval |
| --- | ---: |
| Terminal feasible | **[-5.0, +10.0] pp** |
| Feasible-obligation success | **[-31.7, -1.7] pp** |
| Strict v0.2 success | **[-6.7, +11.7] pp** |
| Obligation resolution | **[-18.5, -2.4] pp** |
| Accepted actions | **[-10.5%, +4.8%]** |
| Model calls | **[-10.5%, +4.8%]** |
| Total tokens | **[-3.0%, +18.7%]** |
| Cost | **[-23.6%, -0.8%]** |
| Aggregate model latency | **[-16.7%, +2.7%]** |

The feasible-obligation and obligation-resolution intervals remain below zero.

## Mechanism diagnostic

The most important result is that the intended guard barely activated at all:

- **15** accepted information-seeking actions were marked no-progress;
- those marks occurred across **13/60** runs;
- **315** visible-evidence progress events were observed;
- maximum evidence epoch was **7**;
- **0 guard interventions** occurred;
- **0 retry calls** occurred;
- **0 retry-noncompliance events** occurred.

So the model did not subsequently repeat the exact blocked
`(action_type, supplier_id)` signature within the same evidence epoch. The
deterministic block/retry mechanism therefore never changed an executed action.

The treatment still changed model behavior because the progress-control framing
was visible in the prompt. Compared with context compilation:

- buyer clarifications: **47 → 20**
- supplier follow-ups: **12 → 1**
- RFQs: **149 → 178**
- quote evaluations: **74 → 59**
- quote revisions: **41 → 48**

Feasible-obligation success improved on only **1/20** episode clusters,
worsened on **7/20**, and tied on 12.

## Decision

**Drop progress-aware reactive v0.1 as a ProcureHarness mechanism.**

The predeclared protocol said that if this treatment failed, the architecture
search should stop rather than continue inventing bespoke mechanisms. That is
now the evidence-supported decision.

The development sequence has tested:

1. factual context compilation;
2. persistent operational ledger;
3. maintained working plan;
4. always-replan + pre-terminal verifier;
5. visible-evidence progress control.

Only factual context compilation remains useful as an efficiency/context layer;
none of the bespoke reliability mechanisms has earned inclusion.

## Next phase

Move from mechanism invention to **benchmark characterization and external
comparators**:

1. implement a recognizable **true ReAct** baseline/comparator without treating
   it as the proposed ProcureHarness method;
2. complete the final comparator matrix and matched efficiency reporting;
3. freeze the development-time method/baseline set;
4. only then author/evaluate the held-out paper slice under the existing split
   contract.

Do not reopen bespoke architecture search unless a comparator or held-out result
reveals a new, specific causal gap that cannot be answered by the existing
evidence.

Held-out states and future held-out episodes remain untouched.
