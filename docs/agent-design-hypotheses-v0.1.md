# Agent-design hypotheses after the cross-family reactive baseline

This document freezes the **questions to test**, not a fashionable architecture
stack. A component enters ProcureHarness only if it addresses an observed
failure and earns its complexity through a controlled comparison on development
episodes 001–020.

Held-out starting states remain untouched.

## Current empirical starting point

The reactive policy already receives the complete visible initial state, all
revealed events, and the entire accepted action history on every model call.
Nevertheless, 107/241 actionable obligations remained unresolved across the
180-run cross-family experiment, while terminal feasibility was substantially
higher than feasible-obligation success.

Therefore the first research question is:

> What representation and additional computation let an agent reliably convert
> an accumulating event history into correct, economical, persistent action
> obligations?

The immediate bottleneck is **not proven to be missing storage**. It can be
representation, salience, planning, retrieval/selectivity, verification, or
some combination.

## Controlled hypothesis matrix

| Candidate | Failure hypothesis | Minimum controlled experiment | Inclusion gate |
| --- | --- | --- | --- |
| **Context-compiled reactive** | Raw chronological history contains the right facts but presents them with poor salience and token density. | Keep one model call per action and the same action space, but deterministically compile only **factual visible state**: current requirement/delta facts, visible supplier state, latest observed quote/revision per supplier/scope, and a compact action/event chronology. Do **not** label open obligations or inject evaluator-derived work. | Keep if obligation resolution improves without materially increasing calls/cost; this isolates serialization/salience/context engineering from obligation inference and extra reasoning. |
| **ReAct-like working state** | The agent needs an explicit iterative reasoning/working-state loop to track and update its plan after observations. | Persist a concise externally represented working state/plan between actions; do not add oracle information or extra tools. | Keep if it improves over both raw-history and context-compiled reactive, not merely because ReAct is a known pattern. |
| **Explicit plan-and-execute** | Long-horizon failures arise because locally plausible actions are not anchored to a maintained workflow plan. | Create a plan object and measure whether plan maintenance improves obligation completion. | Keep if gains survive matched model/action budgets and are distinct from context compilation. |
| **Structured obligation/state ledger** | The key failure is losing actionable commitments after they are triggered. | Maintain a typed visible-state ledger of open/resolved obligations, requirement versions, supplier statuses, quote versions, and award dependencies using only agent-visible information. | High-priority candidate: keep if it directly reduces non-response, amendment, withdrawal, revision, and requirement-gap misses without evaluator leakage. |
| **Operational state graph / environment map** | A flat ledger cannot reliably propagate relationships such as requirement revision → stale quote → affected award scope → new obligation. | Compare a flat ledger against a typed dependency graph with the same visible facts and reasoning budget. | Add graph structure only if relational/invalidation tasks measurably improve; do not add a graph database for naming value. |
| **Always-replan** | Reconsidering the whole plan after every event can recover more obligations, at high inference cost. | Replan on every accepted step/event and measure quality/cost. | Use mainly as a quality-heavy comparator/upper-cost baseline. |
| **Selective event-triggered replanning** | Extra reasoning is useful only when state changes invalidate assumptions or create unresolved obligations. | Trigger replanning only for meaningful deltas/open-obligation transitions and compare against always-replan. | Core ProcureHarness candidate if it approaches always-replan quality with materially lower calls/tokens/latency/cost. |
| **Pre-award verifier / guardrail** | Agents terminate once an award is feasible without checking remaining obligations or stale dependencies. | Before terminal action, evaluate generic visible procurement invariants and route failures back to planning. | Keep if it closes terminal-vs-obligation gaps without hard-coding episode or evaluator answers. |
| **Dynamic model routing** | Routine actions do not need the same reasoning budget as replanning/verification. | Use a lean model for routine transitions and a stronger model only at gated decision points. | Add after trigger semantics are stable if quality/cost Pareto improvement is measurable. |

## Development evidence update — operational ledger

The first two controlled architecture tests are now complete:

- **Factual context compilation** earned only a narrow efficiency-layer
  inclusion: it cut total tokens by about 40.6% and cost by 27.5%, but did not
  improve run-level long-horizon reliability.
- **Operational-ledger reactive v0.1** failed its predeclared reliability gate.
  Relative to factual context compilation, feasible-obligation success fell
  **20.0 pp** and terminal feasibility fell **25.0 pp**, while total tokens rose
  **295.4%** and model calls rose **132.1%**.

The ledger did resolve a larger fraction of the obligations created on its own
policy paths, but it also produced a strong clarification-loop failure: 652
buyer-clarification actions versus 47 under factual context compilation, with
11 runs reaching the 50-action cap. This is evidence against carrying this
**persistent commitment-ledger formulation** forward, not evidence that all
explicit state representations are harmful.

The planned stateless/recomputed-ledger attribution ablation was conditional on
the ledger treatment passing. It is therefore dropped. The next causal question
moves from **what commitments should remain salient?** to **what bounded plan
should govern the next action, replanning trigger, and stopping condition?**

Accordingly, the next controlled experiment should be an externally represented
**maintained working plan / plan-and-execute treatment** over factual compiled
context. Keep it separate from verifier and selective-replanning mechanisms so
that any gain can be attributed before additional components are introduced.

## Ideas that are intentionally deferred

### Knowledge graph / GraphRAG

Google's current agent architecture guidance describes GraphRAG as useful when
retrieval requires explicit relationships among data points. That is a real
capability, but the current benchmark does not yet stress large external
knowledge retrieval: the procurement state is already structured and small.

A knowledge graph should therefore **not** be added merely to claim one. The
operational state-graph experiment above is narrower and directly testable.
GraphRAG becomes justified only if later tasks require multi-hop retrieval across
documents, suppliers, project history, or enterprise knowledge.

### Persistent memory retrieval

The benchmark already provides complete within-episode raw history. A vector
memory that simply retrieves past actions would not address a demonstrated
absence of information.

Persistent retrieval becomes a first-class experiment if we add either:

1. context pressure where the complete history no longer fits economically, or
2. multi-session/cross-project experience where useful information is genuinely
   outside the active state.

**MemGPT** is a relevant comparator specifically for that future condition:
its contribution is virtual context management across memory tiers when useful
context exceeds the active window. That is not the bottleneck demonstrated by
the current 20-episode suite, so implementing it now would confound the state
question rather than answer it.

### Continual learning and self-improvement

Self-improvement is attractive, but it is a **separate learning axis** from the
current within-episode state-management failure.

If added, the safe experiment is development-only learning:

- run episodes;
- automatically distill generic failure/repair lessons or update a retrieval
  policy;
- evaluate transfer to other development episodes with a contamination-safe
  split or leave-one-episode-out protocol;
- freeze the learned memory/policy before any held-out episode is authored or
  evaluated.

No held-out result may be used to update the system.

The closest research prior to test here is **Agent Workflow Memory (AWM)**:
rather than merely retrieving old text, it induces reusable workflows from prior
agent trajectories and selectively supplies them on later tasks. That mechanism
maps much more directly to procurement self-improvement than adding an
undifferentiated vector-memory store. If we reach this stage, AWM-style workflow
induction is the first experience-memory comparator to implement.

This can become an optional ProcureHarness extension if the core state/replanning
method plateaus and cross-episode learning gives additional generalization.

### Multi-agent systems

There is no current evidence that specialization or inter-agent communication is
the bottleneck. Multiple agents would add model calls, orchestration complexity,
and another confound. Defer unless a single-agent decomposition limit appears.

### True long-running operation

LongProcureBench currently measures **long-horizon sequential behavior**, not
wall-clock days/weeks or disconnected-session durability. We should not overclaim
"long-running" yet.

A later long-running test can add checkpoint/pause/resume across process
boundaries, delayed events, and context rehydration. That would justify claims
about durable execution state without changing the held-out information
boundary.

## How current external design guidance maps to the evidence

Google Cloud's current agent-pattern guide recommends choosing patterns from
workload characteristics, cost, latency, and quality requirements rather than
treating complexity as inherently better. It explicitly lists ReAct for
iterative reason-act-observe workflows, and review/critique for workflows that
need a validation step.

Google's agent architecture guidance separately distinguishes working memory,
long-term knowledge/memory, and transactional memory/durable action state. That
distinction is useful here: the strongest immediate hypothesis is closer to a
**transactional operational state/obligation ledger** than generic long-term
memory.

The HumanLayer 12-Factor Agents guide is useful as an engineering hypothesis
catalog, especially "Own your context window" and "Unify execution state and
business state." Its central context-engineering argument maps directly to our
context-compiled baseline, but it is not treated as evidence that the technique
will work on LongProcureBench.

The original ReAct paper motivates interleaving reasoning and actions because
reasoning traces can help track/update plans and handle exceptions. We will test
that specific mechanism rather than adopt the name as an architectural goal.

## Proposed next experiment order

The default order after this evidence freeze is:

1. **Context-compiled reactive** — cheapest causal test; no extra model calls
   and no derived obligation labels.
2. **Structured obligation/state ledger** — **tested and dropped** after failing
   the frozen reliability gate and producing clarification-loop fixation.
3. **Maintained working plan / explicit plan-and-execute** — next causal test:
   determine whether bounded prospective planning and explicit stopping/replan
   state improves reliability beyond factual context compilation.
4. **Always-replan + verifier** — quality-heavy comparator.
5. **Selective replanning + verifier** — candidate efficient ProcureHarness.
6. Add **operational state graph**, **dynamic routing**, or **experience-based
   self-improvement** only when the preceding experiments identify a concrete
   need.

This order is a starting experimental plan, not a promise that all components
will survive.

## Candidate ProcureHarness contribution, if supported

The strongest current method hypothesis is:

> Maintain an explicit operational state of requirements, suppliers, quote
> versions, dependencies, and open obligations; compile only the decision-relevant
> context; invoke expensive replanning/verification when state transitions make
> it necessary rather than at every step.

If experiments support that hypothesis, ProcureHarness becomes a **selective
deliberation/state harness** rather than a collection of named agent patterns.

## References

- Google Cloud Architecture Center, *Choose a design pattern for your agentic AI
  system*: https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system
- Google Cloud, *Core concepts of AI agents*:
  https://cloud.google.com/resources/core-concepts-ai-agents
- HumanLayer, *12-Factor Agents — Own your context window*:
  https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-03-own-your-context-window.md
- HumanLayer, *12-Factor Agents — Unify execution state and business state*:
  https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-05-unify-execution-state.md
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*:
  https://arxiv.org/abs/2210.03629
- Shinn et al., *Reflexion: Language Agents with Verbal Reinforcement Learning*:
  https://arxiv.org/abs/2303.11366
- Wang et al., *Agent Workflow Memory*:
  https://arxiv.org/abs/2409.07429
- Packer et al., *MemGPT: Towards LLMs as Operating Systems*:
  https://arxiv.org/abs/2310.08560
- Wang et al., *Voyager: An Open-Ended Embodied Agent with Large Language Models*:
  https://arxiv.org/abs/2305.16291
