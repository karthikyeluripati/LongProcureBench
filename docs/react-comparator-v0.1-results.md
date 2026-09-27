# ReAct comparator v0.1 — frozen development result

This experiment evaluates a recognizable external **ReAct**
Thought -> Action -> Observation comparator on the frozen LongProcureBench
development suite. It is not a ProcureHarness candidate and has no inclusion
gate.

The information boundary is matched to the retained factual-context baseline:
the same `factual_compiled_v0.1` state, runtime, Evaluator v0.2, semantic
actions, GPT-5.6 Sol reasoning configuration, and 50-action cap are used.
ReAct adds only an explicit bounded thought summary and an accepted
Thought/Action/Observation transcript, with one model call per semantic action.

## Source

- Workflow run: `36316652236`
- Source artifact: `10931387170`
- Artifact digest: `sha256:d767d296d077a5e693bfc18e7429b35627bf5f5939283f98208372cc5f63e373`
- Benchmark code: `9e0da4df909f271ac797898ea6daa9b6f9781a57`
- Execution head: `8e3721d6f067613b9750f1b6aa7f954fd947a7db`
- Execution-head delta: workflow trigger only
- Grid: GPT-5.6 Sol × 20 development episodes × 3 repeats = **60 runs**
- **60/60 completed**
- Live execution/evaluator validation passed
- Token usage and known API cost are complete for all 60 runs

The exact source ZIP can be independently checked against the committed compact
replay and per-record provenance using:

`python scripts/verify_react_source_artifact_v01.py --artifact-zip <artifact.zip>`

The Actions artifact has temporary retention, so the complete compact
**Thought/Action/Observation transcript** is also committed durably at
`evidence/react-comparator-v0.1/transcript-source.b64`. It contains all 60
episode/repeat transcripts with bounded thought summaries, semantic actions, and
the same factual-visible observation fields shown to ReAct. The frozen
transcript is checksum-verified in CI and linked back to the accepted-action
replay. Therefore the mechanism diagnostics remain inspectable after the
temporary source artifact expires.

## Matched comparison

| Metric | Context compiled | ReAct | Delta |
| --- | ---: | ---: | ---: |
| Terminal feasible | 46/60 (**76.7%**) | 52/60 (**86.7%**) | **+10.0 pp** |
| Feasible-obligation success | 40/60 (**66.7%**) | 41/60 (**68.3%**) | **+1.7 pp** |
| Strict v0.2 success | 14/60 (**23.3%**) | 27/60 (**45.0%**) | **+21.7 pp** |
| Obligation resolution | 72/86 (**83.7%**) | 95/112 (**84.8%**) | **+1.1 pp** |
| Accepted actions | 464 | 488 | **+5.2%** |
| Model calls | 464 | 488 | **+5.2%** |
| Total tokens | 974,208 | 1,454,192 | **+49.3%** |
| Known API cost | $4.61 | $7.98 | **+73.2%** |
| Aggregate model latency | 869,561 ms | 1,275,207 ms | **+46.6%** |

ReAct therefore shows a clear **quality / inference-cost tradeoff**. The largest
quality change is strict v0.2 success; the primary feasible-obligation metric
moves only slightly.

## Episode-cluster bootstrap

A paired bootstrap over the 20 episode IDs uses 20,000 deterministic resamples,
seed `20260926`, and `sha256-index-v1` sampling.

| Delta | 95% interval |
| --- | ---: |
| Terminal feasible | **[0.0, +21.7] pp** |
| Feasible-obligation success | **[-16.7, +18.3] pp** |
| Strict v0.2 success | **[+10.0, +35.0] pp** |
| Obligation resolution | **[-7.7, +10.2] pp** |
| Accepted actions | **[-2.3%, +13.5%]** |
| Model calls | **[-2.3%, +13.5%]** |
| Total tokens | **[+35.9%, +64.7%]** |
| Known API cost | **[+52.2%, +100.1%]** |
| Aggregate model latency | **[+33.6%, +61.8%]** |

The strict-success increase remains positive across this paired descriptive
interval. The feasible-obligation and obligation-resolution differences do not.
The resource increase is consistently positive.

## ReAct mechanism diagnostics

The comparator was active rather than silently collapsing to the reactive
baseline:

- **488** ReAct steps proposed
- **488** accepted
- all **60/60** runs have complete accepted ReAct step accounting
- **81,495** total thought-summary characters
- **167.0** mean characters per accepted ReAct step
- **252** maximum thought-summary characters

At the episode-cluster level, strict v0.2 success improved on **8/20** episodes,
worsened on **0/20**, and tied on 12. Terminal feasibility improved on 4,
worsened on 1, and tied on 15. Feasible-obligation success improved on 5,
worsened on 4, and tied on 11.

ReAct also changed the action distribution. For example, RFQs rose from
149 to **178** and quote revisions from 41 to **51**, while quote evaluations
fell from 74 to **64**.

## Interpretation

This result supports a limited statement:

> Explicit ReAct-style thought/action/observation iteration can improve strict
> long-horizon procurement completion on this development suite, but at a
> substantial token, cost, and latency premium.

It does **not** establish that ReAct should become ProcureHarness, and it does
not reopen the bespoke architecture-search loop. ReAct was preregistered as an
external comparator and is reported regardless of outcome.

The result also sharpens the benchmark story: simply adding persistent memory,
a maintained plan, or generic planning/verification harmed performance in prior
controlled experiments, whereas a recognizable ReAct comparator improves strict
completion while consuming materially more inference resources.

## Decision and next step

**Freeze ReAct as an external development comparator.**

There is no inclusion gate and no tuning from this result. The next step is to
freeze the complete **development comparator set and reporting matrix** before
any held-out episode is authored or evaluated.

Held-out starting states remain untouched.
