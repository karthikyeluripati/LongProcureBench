# Cross-family reactive baseline v0.1 — frozen results

This is the first provider-diverse development/calibration experiment for
LongProcureBench. It evaluates the same **reactive/raw-history architecture**
across three model families on the 20 frozen development episodes.

This evidence is diagnostic and method-design data. It is **not** the final
held-out paper evaluation and it is not an estimate of real-world procurement
failure prevalence.

## Live experiment

- GitHub Actions run: `36220188934`
- Benchmark code commit: `a32efbfd570840c2c685525fd7ad88eade7ae87f`
- Execution commit: `9bf6e72f27343f949b999dac535b928e7bec79ab`
- Execution commit delta: only the workflow trigger used to launch the one-shot
  experiment; benchmark, agent, runtime, and evaluator code were unchanged.
- Models: `openai/gpt-5.6-sol`,
  `anthropic/claude-opus-5-5`, and
  `gemini/gemini-3.8-flash`
- Grid: 3 models × 20 episodes × 3 repeats = **180 runs**
- All 180 source runs completed and passed live execution/evaluation-status
  validation.

## Main results

| Model | Runs | Terminal feasible | Feasible-obligation success | Strict v0.2 success | Obligation resolution | Tokens | Known API cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GPT-5.6 Sol | 60 | 49/60 (**81.7%**) | 41/60 (**68.3%**) | 19/60 (**31.7%**) | 73/94 (**77.7%**) | 1,640,350 | $6.35 |
| Claude Opus 5.5 | 60 | 36/60 (**60.0%**) | 12/60 (**20.0%**) | 6/60 (**10.0%**) | 35/63 (**55.6%**) | 2,153,003 | $9.39 |
| Gemini 3.8 Flash | 60 | 28/60 (**46.7%**) | 4/60 (**6.7%**) | 1/60 (**1.7%**) | 26/84 (**31.0%**) | 1,679,456 | $1.90 |
| **Combined** | **180** | **113/180 (62.8%)** | **57/180 (31.7%)** | **26/180 (14.4%)** | **134/241 (55.6%)** | **5,472,809** | **$17.64** |

These rows are descriptive measurements under different provider/model
configurations. They are not intended as a model leaderboard.

## Failure taxonomy

Across the 180 runs, **107/241 actionable obligations were unresolved**:

| Obligation | Unresolved instances |
| --- | ---: |
| Follow up after observed supplier non-response | **42** |
| Resolve visible starting-state requirement gap | **35** |
| Recover from supplier withdrawal | **14** |
| Request required quote revision | **12** |
| Handle buyer amendment | **4** |

Only two additional obligations were scored `no_opportunity`; both were
amendment obligations revealed without a later accepted-action opportunity.

## Strong terminal-vs-process separation

The most useful diagnostic is not simply that agents fail. It is that they can
reach a feasible procurement decision while leaving stateful obligations
unfinished.

`electrical-dla-power-supply-016` is the cleanest example:

- terminal feasible: **9/9**
- feasible-obligation success: **0/9**
- actionable obligations: **25**
- resolved: **16**
- unresolved: **9**

The nine unresolved obligations are seven observed supplier non-response
follow-ups and two amendment-handling obligations.

Other large cross-model gaps include:

- `electrical-vre-generator-020`: 8/9 terminal feasible, 0/9 obligation
  success.
- `electrical-dla-transformer-013`: 9/9 terminal feasible, 2/9 obligation
  success.
- `electrical-bfar-generator-006`,
  `electrical-bongabon-generator-001`, and
  `electrical-negros-wire-007`: each 9/9 terminal feasible and 3/9
  obligation success.

## Action-induced obligations

The raw action counts also expose an efficiency mechanism that the method should
not ignore. Mean RFQs per run were approximately **2.75** for GPT-5.6 Sol,
**3.02** for Claude Opus 5.5, and **3.05** for Gemini 3.8 Flash. In contrast,
observed follow-up actions were only **2**, **8**, and **0** respectively across
60 runs per model.

This matters because agent actions can create downstream work. Soliciting an
additional supplier can reveal a non-response, question, revision need, or
withdrawal that must then be managed. An efficient long-horizon agent should
therefore optimize not only "what action is valid now?" but also the future
obligation load created by that action.

This is a benchmark-mechanism observation, not a claim that fewer suppliers are
always better in real procurement. Competition and sourcing policy can make
additional outreach valuable.

## What this does and does not establish

The result supports a cross-family phenomenon on this benchmark slice:

> Raw-history reactive agents can often find a feasible terminal procurement
> decision while failing to preserve and discharge obligations created by
> evolving state, supplier interactions, and their own earlier actions.

It does **not** establish that the missing ingredient is generic "memory." The
runtime already exposes the full accepted `action_history` and all
`revealed_events` at every step. The raw information is available; the failure
is more specifically about how that history is represented, prioritized, and
converted into persistent actionable state.

It also does not yet establish that a knowledge graph, multi-agent system,
continual learner, or any named agent framework is needed. Those are hypotheses
that require controlled comparisons.

## Durable evidence

The expiring Actions artifacts have been compacted to a deterministic replay
source under:

`evidence/cross-family-reactive-v0.1/`

The frozen source retains the model/episode/repeat identity, accepted semantic
decisions, and aggregate token/latency/cost metrics. Environment observations
and Evaluator v0.2 outputs are regenerated deterministically from the committed
benchmark.

Verify the source and replay all 180 trajectories offline with:

```sh
python scripts/audit_cross_family_reactive_v01.py --check
```

The compressed replay source is checksum-locked in
`evidence/cross-family-reactive-v0.1/manifest.json`.
