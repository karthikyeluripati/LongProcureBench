# Development comparator and reporting freeze v0.1

This document is the **last development-time selection gate** before the held-out
paper slice. It freezes which methods exist, which ones are reportable only as
development failure analysis, which methods are eligible for held-out
evaluation, and the metrics/tables that will be reported.

No held-out episode has been authored or evaluated as part of this freeze.

## Frozen development set

| Method | Role | Development evidence | Held-out? |
| --- | --- | ---: | --- |
| Raw reactive — GPT-5.6 Sol | provider-diverse baseline | 60 runs | **Yes** |
| Raw reactive — Claude Opus 5.5 | provider-diverse baseline | 60 runs | **Yes** |
| Raw reactive — Gemini 3.8 Flash | provider-diverse baseline | 60 runs | **Yes** |
| Factual context compiled — GPT-5.6 Sol | efficiency/context baseline | 60 runs | **Yes** |
| True ReAct — GPT-5.6 Sol | external quality/cost comparator | 60 runs | **Yes** |
| Operational ledger | failed bespoke mechanism | 60 runs | **No** |
| Maintained working plan | failed bespoke mechanism | 60 runs | **No** |
| Always-replan + verifier | failed bespoke mechanism | 60 runs | **No** |
| Progress-aware guard | failed bespoke mechanism | 60 runs | **No** |

The dropped bespoke mechanisms remain in the paper as controlled development
failure analysis. They are **not** promoted to held-out methods.

## Frozen metric hierarchy

The primary benchmark quality metric is **feasible-obligation success**: a run
must end feasibly while resolving every actionable obligation for the policy
path it actually created.

Always report alongside it:

- terminal feasibility;
- strict Evaluator v0.2 success;
- aggregate obligation resolution rate;
- economic-objective satisfaction.

Efficiency reporting is mandatory:

- accepted actions;
- model calls;
- prompt/completion/total tokens;
- aggregate model latency;
- known API cost.

Also retain status counts, unresolved-obligation taxonomy, and action-type counts
as diagnostics.

There is **no weighted composite score**. Report numerators/denominators plus
percentages for run-level metrics.

## Development anchor results

The provider-diverse raw reactive grid is 180 completed runs:

| Model | Terminal | Feasible-obligation | Strict v0.2 | Obligation resolution |
| --- | ---: | ---: | ---: | ---: |
| GPT-5.6 Sol | 49/60 (81.7%) | 41/60 (68.3%) | 19/60 (31.7%) | 73/94 (77.7%) |
| Claude Opus 5.5 | 36/60 (60.0%) | 12/60 (20.0%) | 6/60 (10.0%) | 35/63 (55.6%) |
| Gemini 3.8 Flash | 28/60 (46.7%) | 4/60 (6.7%) | 1/60 (1.7%) | 26/84 (31.0%) |
| **Combined** | **113/180 (62.8%)** | **57/180 (31.7%)** | **26/180 (14.4%)** | **134/241 (55.6%)** |

For the matched GPT-5.6 Sol methods:

| Method | Terminal | Feasible-obligation | Strict v0.2 | Obligation resolution | Tokens | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw history | 49/60 (81.7%) | 41/60 (68.3%) | 19/60 (31.7%) | 73/94 (77.7%) | 1,640,350 | $6.35 |
| Context compiled | 46/60 (76.7%) | 40/60 (66.7%) | 14/60 (23.3%) | 72/86 (83.7%) | 974,208 | $4.61 |
| ReAct | 52/60 (86.7%) | 41/60 (68.3%) | 27/60 (45.0%) | 95/112 (84.8%) | 1,454,192 | $7.98 |

These are development measurements, not final paper generalization results.

## Development-only mechanism table

The paper keeps one matched failure-analysis table, all relative to factual
context compilation:

| Treatment | Terminal Δ | Feasible-obligation Δ | Strict Δ | Token Δ | Cost Δ | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Operational ledger | -25.0 pp | -20.0 pp | +8.3 pp | +295.4% | +371.8% | Drop |
| Working plan | -8.3 pp | -21.7 pp | +5.0 pp | +35.1% | +70.3% | Drop |
| Always-replan + verifier | -53.3 pp | -46.7 pp | -15.0 pp | +1,945.1% | +2,418.8% | Drop |
| Progress-aware | +1.7 pp | -16.7 pp | +1.7 pp | +6.9% | -12.5% | Drop |
| ReAct external comparator | +10.0 pp | +1.7 pp | +21.7 pp | +49.3% | +73.2% | Report as external comparator |

This table is **development-only**. It is not used to select another bespoke
architecture.

## Frozen held-out protocol

The held-out slice will contain **10 episodes**, exactly one from each of the 10
already-reserved real public starting states. Episode authoring begins only
after this comparator freeze.

Model-backed methods receive **3 repeats per held-out episode**:

1. raw reactive — GPT-5.6 Sol;
2. raw reactive — Claude Opus 5.5;
3. raw reactive — Gemini 3.8 Flash;
4. factual context compiled — GPT-5.6 Sol;
5. true ReAct — GPT-5.6 Sol.

That is **150 model-backed held-out runs** for 10 episodes. The deterministic
reference control runs once per episode (**10 additional sanity-control runs**)
and is not a competitive baseline.

Exact model identifiers and their frozen provider/sampling configurations must
be reused. A model may not be silently replaced because of an unfavorable
result or temporary provider behavior.

The operational ledger, working plan, always-replan/verifier, and progress-aware
mechanisms are **not held-out eligible**.

## Frozen paper tables

### Main table A — provider-diverse raw reactive

Rows: the three frozen raw-reactive model families.

Columns: runs, terminal feasibility, feasible-obligation success, strict v0.2,
obligation-resolution rate, economic-objective satisfaction, mean accepted
actions, total tokens, known API cost.

This is benchmark characterization, **not a model leaderboard**.

### Main table B — matched GPT-5.6 Sol methods

Rows: raw reactive, factual context compiled, ReAct.

Columns: the full quality set plus accepted actions, model calls, total tokens,
latency, and known cost.

Matched comparisons use a paired episode-cluster bootstrap with **20,000
resamples**, seed **20260926**, sampler **sha256-index-v1**.

### Development table — mechanism analysis

Rows: context baseline, ledger, working plan, always-replan/verifier,
progress-aware, ReAct.

Report deltas relative to context compiled and the frozen development decision.

### Failure taxonomy

Report unresolved actionable obligations by class for the held-out methods. Do
not convert the taxonomy into a weighted score.

## Anti-tuning / contamination rule

After this freeze:

- do not add another method after seeing a held-out result;
- do not tune prompts, planning, verification, memory, context compilation,
  semantic actions, evaluator rules, or model settings from held-out outcomes;
- do not use held-out trajectories to update a method;
- do not run dropped bespoke mechanisms on held-out;
- do not reinterpret a failed development mechanism as the proposed method.

The **next step is held-out episode authoring and deterministic validation**.
Model evaluation starts only after the 10-episode held-out package itself is
frozen.
