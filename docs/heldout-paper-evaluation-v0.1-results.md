# Held-out paper evaluation v0.1 — frozen results

This is the final held-out LongProcureBench paper evaluation. The experiment was
fully preregistered in the development comparator matrix and the held-out
execution protocol before any model-backed held-out result was observed.

- Source workflow: `36329287113`
- Source commit: `cf725f239fcc76cba1f0e2e51fee9d726fbca590`
- Workflow attempt: 1
- **160/160 validated runs**
- 150 model-backed runs + 10 deterministic reference controls
- every workflow job and the final aggregate validation completed successfully
- exact raw workflow artifact ZIPs are committed under
  `evidence/heldout-paper-evaluation-v0.1/source-artifacts/`

No model, prompt, episode, evaluator rule, or paper reporting contract was
changed from held-out outcomes.

## Sanity control

The deterministic reference control passed **10/10** held-out episodes:

- terminal feasibility: 10/10
- feasible-obligation success: 10/10
- strict Evaluator v0.2: 10/10
- economic objective: 10/10
- actionable obligations resolved: **20/20**

This establishes that all ten frozen tasks have a valid executable path under
the benchmark contract.

## Main table A — provider-diverse raw reactive

This table characterizes the benchmark across the three preregistered raw
reactive model families. It is **not a model leaderboard**.

| Raw reactive model | Terminal feasible | Feasible-obligation success | Strict v0.2 | Obligation resolution | Economic objective | Mean actions | Tokens | Known cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GPT-5.6 Sol | 26/30 (**86.7%**) | 12/30 (**40.0%**) | 3/30 (**10.0%**) | 26/47 (**55.3%**) | 10/30 (**33.3%**) | 7.10 | 623,547 | $2.29 |
| Claude Opus 5.5 | 22/30 (**73.3%**) | 4/30 (**13.3%**) | 0/30 (**0.0%**) | 18/42 (**42.9%**) | 18/30 (**60.0%**) | 6.23 | 923,495 | $4.02 |
| Gemini 3.8 Flash | 23/30 (**76.7%**) | 6/30 (**20.0%**) | 0/30 (**0.0%**) | 15/45 (**33.3%**) | 11/30 (**36.7%**) | 6.50 | 695,298 | $0.86 |

The held-out slice reproduces the development finding that **terminal
feasibility substantially overstates long-horizon obligation reliability**.
All three raw-reactive rows frequently reach a feasible terminal award while
leaving actionable obligations unresolved.

## Main table B — matched GPT-5.6 Sol methods

| Method | Terminal feasible | Feasible-obligation success | Strict v0.2 | Obligation resolution | Economic objective | Mean actions | Model calls | Tokens | Latency | Known cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw reactive | 26/30 (**86.7%**) | 12/30 (**40.0%**) | 3/30 (**10.0%**) | 26/47 (**55.3%**) | 10/30 (**33.3%**) | 7.10 | 213 | 623,547 | 418,208 ms | $2.29 |
| Factual context compiled | 23/30 (**76.7%**) | 20/30 (**66.7%**) | 6/30 (**20.0%**) | 29/39 (**74.4%**) | 8/30 (**26.7%**) | 6.77 | 203 | 453,429 | 416,517 ms | $2.16 |
| ReAct | 24/30 (**80.0%**) | 20/30 (**66.7%**) | 15/30 (**50.0%**) | 40/49 (**81.6%**) | 19/30 (**63.3%**) | 8.13 | 244 | 788,503 | 654,692 ms | $4.27 |

### Context compilation vs raw history

Descriptively, context compilation trades some terminal-feasibility rate for
substantially better obligation handling and lower token use:

- terminal feasibility: **-10.0 pp**
- feasible-obligation success: **+26.7 pp**
- strict v0.2: **+10.0 pp**
- obligation resolution: **+19.0 pp**
- total tokens: **27.3% lower** than raw history
- known cost: **6.0% lower**
- aggregate latency: approximately unchanged

In the preregistered 20,000-resample episode-cluster bootstrap, the
context-over-raw obligation-resolution delta is the inverse of the stored
raw-minus-context interval: approximately **[+1.1, +39.2] pp**. The
feasible-obligation success interval still spans zero on this ten-episode
held-out slice, so the primary-metric difference should be reported with that
uncertainty rather than as a universal improvement.

### ReAct vs factual context compilation

The preregistered primary metric is **feasible-obligation success**. ReAct does
**not** improve that metric on held-out: both methods are **20/30 (66.7%)**.

ReAct does improve stricter completion measures:

- strict v0.2: **20.0% → 50.0% (+30.0 pp)**
- economic objective: **26.7% → 63.3% (+36.7 pp)**
- obligation resolution: **74.4% → 81.6% (+7.3 pp)**
- terminal feasibility: **76.7% → 80.0% (+3.3 pp)**

The paired episode-cluster bootstrap keeps the strict-success delta positive:
**[+6.7, +56.7] pp**. The economic-objective delta is also positive:
**[+13.3, +60.0] pp**. The feasible-obligation interval is
**[-10.0, +10.0] pp**, and the terminal and obligation-resolution intervals also
span zero.

The additional quality comes with a substantial inference premium versus
context compilation:

- accepted actions/model calls: **+20.2%**
  (95% interval **[+16.2%, +24.7%]**)
- total tokens: **+73.9%**
  (95% interval **[+60.9%, +87.8%]**)
- known API cost: **+98.3%**
  (95% interval **[+83.7%, +116.4%]**)
- aggregate model latency: **+57.2%**
  (95% interval **[+44.6%, +73.2%]**)

The supported statement is therefore a **quality/cost tradeoff**, not a claim
that ReAct improves every reliability measure.

## Failure taxonomy

The dominant unresolved held-out obligation remains
`resolve_requirement_gap`:

| Method | Requirement gap | Non-response follow-up | Withdrawal recovery | Quote revision | Overall obligation resolution |
| --- | ---: | ---: | ---: | ---: | ---: |
| Raw OpenAI | 14 | 6 | 1 | 0 | 26/47 (55.3%) |
| Raw Anthropic | 24 | 0 | 0 | 0 | 18/42 (42.9%) |
| Raw Gemini | 24 | 6 | 0 | 0 | 15/45 (33.3%) |
| Context compiled | 6 | 1 | 2 | 1 | 29/39 (74.4%) |
| ReAct | 6 | 0 | 3 | 0 | 40/49 (81.6%) |

This supports the benchmark's original diagnosis: a policy can make a plausible
award yet fail to resolve information and recovery obligations generated by its
own path through an evolving procurement process.

## What the final evidence supports

The frozen evidence supports three paper-level findings:

1. **Long-horizon obligation reliability is distinct from terminal
   feasibility.** The gap appears across all three raw-reactive model families
   on untouched held-out episodes.
2. **Factual context engineering is a useful efficiency/reliability layer.**
   On held-out it uses fewer tokens than raw GPT-5.6 Sol and resolves a larger
   share of actionable obligations; uncertainty remains on the run-level
   feasible-obligation success difference because there are only ten episode
   clusters.
3. **Explicit ReAct improves strict task completion at substantial inference
   cost, but does not improve the preregistered primary feasible-obligation
   success rate over factual context compilation.**

The evidence does **not** support reopening bespoke architecture search or
claiming that the failed ledger/planner/verifier/progress mechanisms form a new
ProcureHarness reliability architecture. Those negative experiments remain
development-only controlled failure analysis.

## Durable evidence and audit

The exact source ZIPs from workflow run `36329287113` are committed
byte-for-byte, including all 160 raw result JSON files, full ReAct
Thought/Action/Observation transcripts, row-level CSV/summary products, and the
workflow aggregate.

Run:

`python scripts/audit_heldout_paper_v01.py`

The audit verifies source ZIP byte counts, SHA-256 digests and Git blob IDs,
re-runs each row's raw-evidence checks, reproduces the 160-run aggregate,
recomputes the preregistered bootstrap/taxonomy/tables, and compares them with
the committed frozen outputs.

## Next step

**Research execution is complete for the frozen paper plan.**

Next is manuscript work: finalize the paper claims, tables/figures, limitations,
and the benchmark + controlled failure-analysis narrative from the frozen
development and held-out evidence. Do not run another architecture experiment
from these held-out outcomes.
