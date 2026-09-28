# ProcureHarness architecture search v0.1

## Decision

Reopen method development as a **separate post-held-out research track**. The
goal is not to add another isolated mechanism. The goal is to search a bounded,
interpretable design-pattern space until the quality/economic-efficiency frontier
plateaus, then freeze one ProcureHarness skeleton before adding memory,
knowledge graphs, forecasting, model routing, or self-improvement.

This protocol does **not** rewrite the frozen LongProcureBench paper evidence.
Episodes 001-020 are development-exposed and 021-030 are already held-out
exposed. Neither may be called a fresh test set for the new method.

The machine-readable freeze is
[`procureharness-architecture-search-v0.1-protocol.json`](procureharness-architecture-search-v0.1-protocol.json).

## Why architecture search is reopened

The completed experiments do not show an agent-design ceiling.

- **Coverage+Repair** is the strongest observed development point:
  50/60 feasible-obligation, 30/60 strict v0.2, 30/60 economic objective,
  90/98 obligations resolved, 324 model calls, and $2.9777 known API cost.
  It shows that explicit procurement workflow control can recover substantial
  quality without reasoning on every action.
- **ReAct** improves strict/economic behavior over factual context but is much
  more expensive and does not dominate the primary feasible-obligation metric.
- **Static Plan-and-Execute** failed its targeted diagnostic.
- **State Validity Frontier v0.2** reduced deliberative calls but failed to
  generalize: 38/60 feasible-obligation, 23/60 strict, 24/60 economic, with
  nine identical withdrawal-recovery policy errors.

The evidence therefore rejects several formulations, not the broader space of
agentic design patterns.

## Research basis

The next phase uses a constrained architecture-search framing rather than
choosing another popular pattern by name.

- **ReAct** interleaves reasoning and acting so reasoning can update plans and
  handle exceptions during interaction.
  https://arxiv.org/abs/2210.03629
- **AdaPlanner** motivates closed-loop plan refinement from environment feedback
  instead of static plans.
  https://proceedings.neurips.cc/paper_files/paper/2023/hash/b5c8c1c117618267944b2617add0a766-Abstract-Conference.html
- **Automated Design of Agentic Systems (ADAS)** treats code-represented agent
  systems as a search space rather than assuming hand-designed workflows are
  optimal.
  https://proceedings.iclr.cc/paper_files/paper/2025/hash/36b7acf6f6010652b3f2a433774a66fe-Abstract-Conference.html
- **AgentSquare** explicitly searches modular agent designs and separates
  planning, reasoning, tool use, and memory as distinct axes.
  https://proceedings.iclr.cc/paper_files/paper/2025/hash/0ae94013da7cd459402fd77874e09ee3-Abstract-Conference.html
- **AFlow** searches code-represented workflows using execution feedback and a
  tree search.
  https://arxiv.org/abs/2410.10762
- **Agent S** provides evidence for hierarchical planning with subtask execution
  on long-horizon interactive tasks.
  https://proceedings.iclr.cc/paper_files/paper/2025/hash/394c7c30ea87b5c3521b4d9e9d419071-Abstract-Conference.html
- **Agent Workflow Memory (AWM)** is intentionally deferred to phase 2 because
  it tests reusable cross-task workflow memory, a different causal axis from
  the within-episode controller skeleton.
  https://openreview.net/pdf?id=NTAhi2JEEE

These papers motivate the search formulation. They are not evidence that their
reported gains transfer to procurement.

## Initial hypothesis: event-driven hierarchical skill graph

The seed hypothesis for ProcureHarness is:

> Track visible actionable obligations, route the highest-priority obligation
> to a bounded procurement skill, execute mechanically forced transitions
> deterministically, deliberate only inside the active skill when semantic
> choice is necessary, and locally replan or fall back when a new visible event
> invalidates the current skill.

This is deliberately between Coverage+Repair and ReAct.

- Coverage+Repair is efficient but contains only a small set of explicit repair
  routines.
- ReAct is flexible but pays for reasoning on essentially every semantic action.
- Static global plans are too rigid.
- The SVF global validity graph was too brittle on recovery behavior.

### Required skill graph

The frozen skill vocabulary is:

1. resolve requirement gap;
2. supplier discovery;
3. RFQ coverage;
4. non-response follow-up;
5. supplier-question handling;
6. amendment handling;
7. quote revision;
8. withdrawal recovery;
9. quote leveling;
10. terminal award/no-award decision.

A new event may interrupt the active skill. Recovery is local by default rather
than rebuilding a global plan.

## Search space

Phase 1 keeps the information boundary and semantic action contract fixed.
Candidates may vary only these modules:

- obligation routing: deterministic priority vs hybrid LLM tie-break;
- local planning: none vs bounded local plan;
- skill reasoning: direct action vs bounded mini-ReAct;
- verification: none vs deterministic visible invariants vs one terminal LLM
  critique;
- fallback: none vs bounded ReAct fallback.

Every candidate is code-represented, committed before execution, and records
its parent candidates and module deltas. Enumeration, recombination, or a
meta-agent proposal is allowed only inside this grammar.

Hard limits prevent an architecture-search system from winning merely by
spending unlimited inference:

- at most 3 model calls between accepted actions;
- at most 4 steps in a local plan;
- at most 3 actions in a ReAct fallback;
- no multi-agent system;
- no cross-episode persistent memory in phase 1.

## What is intentionally **not** searched yet

The following are harness axes, not part of this causal design-pattern search:

- persistent workflow memory / AWM;
- operational knowledge graph / GraphRAG;
- cross-episode self-improvement;
- dynamic cheap/strong-model routing (including a future Jev-style router if
  that remains the intended option);
- forecasting/risk tools;
- multi-agent orchestration;
- true long-running checkpoint/resume state.

They enter only after a design-pattern winner is frozen, one matched ablation at
a time.

## Data hygiene

The existing 30 episodes cannot support another untouched method claim:

- **001-020**: architecture-development exposed;
- **021-030**: prior held-out exposed and diagnostic-only for the new method.

Before architecture search can claim generalization, collect **20 additional
distinct real public starting states**:

- **031-040**: architecture-search validation; may guide later search rounds;
- **041-050**: untouched final method test; cannot guide design.

Both packages retain the existing real-public starting state / controlled
synthetic interaction boundary and must pass deterministic reference control
before model-backed execution.

## Search budget and operational ceiling

Maximum search:

- 3 search rounds;
- at most 6 new candidates per round;
- at most 18 unique candidates total.

Cheap screening uses 001-020 once per candidate. At most two candidates per
round receive the full 20 x 3 development confirmation. Frozen development
comparator evidence is reused exactly; Coverage+Repair, ReAct, and factual
context are **not rerun** on 001-020.

A candidate may enter 031-040 validation only if it:

1. executes cleanly;
2. passes the frozen 20 x 3 development quality floor; and
3. passes either the frozen development quality-promotion branch or the frozen
   efficiency-promotion branch.

If more than two candidates qualify in a round, the two validation slots are
chosen by a frozen lexicographic order: feasible-obligation success, strict
v0.2, economic objective, obligation resolution, API cost, total tokens, then
candidate ID.

Once 031-040 exists, matched Coverage+Repair and ReAct rows are executed once
for that frozen package. A candidate is admitted to the **validation frontier**
only if execution is clean, it is within 2/30 of the per-metric better matched
baseline on feasible-obligation, strict, and economic success, and its regret
comparison is fully comparable on the frozen reference cohort.

Pareto dominance is exact: A dominates B only if A is no worse on every frozen
frontier dimension and strictly better on at least one. After each round the
cumulative frontier is recomputed over admitted candidates plus the two matched
baseline rows. A round counts as improving the frontier only if a candidate
first validated in that round remains on the recomputed candidate frontier
**and its metric vector is not equivalent to any pre-round frontier row**.
Integer/count dimensions use exact equality; floating dimensions use
`rel_tol=1e-12`, `abs_tol=1e-9`. Candidate ID is not part of the vector, so
an exact/numerical tie does not reset the plateau counter.

**Operational design-pattern ceiling:** stop after two consecutive completed
rounds add no new candidate under that rule, or the 3-round / 18-candidate
budget is exhausted. This is a search plateau, **not a claim of global
optimality**.

## Metrics

There is still **no weighted magic score**.

### Reliability

Primary:

- feasible-obligation success.

Mandatory:

- terminal feasibility;
- strict v0.2 success;
- obligation resolution;
- economic-objective satisfaction.

### Procurement economics

Before any paid architecture-search run, implement the same deterministic
scope-aware price logic for every method.

For each award:

- `scope == "package"` → use the referenced quote event's
  `details.total_price`;
- `scope == "lot-<item_id>"` → use the referenced quote event's
  `details.lots[item_id].price`.

The outcome cost is the sum of one resolved price per award, matching
`scripts/validate_episodes.py::_award_price`. The quote must cover the award
scope.

For an eligible feasible award:

`regret = selected feasible outcome cost - oracle minimum feasible outcome cost`.

We report:

- feasible price regret in native currency;
- per-run feasible price regret percent;
- frozen reference-cohort size;
- candidate regret-eligibility count/rate on that cohort;
- mean regret percent on the reference cohort;
- paired savings versus each baseline in native currency and percent.

Infeasible or unsupported no-award runs remain `not_eligible` for monetary
regret instead of receiving an arbitrary dollar penalty. **They are not silently
dropped when candidates are compared.**

For each matched comparison package, the normalized-regret reference cohort is
frozen as the intersection of run keys `(episode_id, repeat)` where **both
Coverage+Repair and ReAct** are regret-eligible **and the episode oracle cost is
strictly greater than zero**. The zero-cost exclusion is episode-defined, so it
is identical for every method. A candidate may use regret for Pareto dominance,
promotion, winner selection, or a final claim only if it is regret-eligible on
**every run key in that same cohort**. Candidate-specific eligible subsets may
be reported diagnostically but cannot be used to rank architectures.

If `oracle_cost == 0`, native regret is still reported. Normalized regret is
marked `not_normalizable_zero_oracle` rather than dividing by zero. Likewise,
if a paired baseline selected cost is zero, paired native savings are reported
but savings percentage is marked `not_normalizable_zero_baseline`.

If the frozen positive-oracle-cost reference cohort is **empty**, normalized
regret is marked `unavailable_empty_reference_cohort`; it is never imputed as
0, infinity, or another numeric sentinel. For that matched package, the regret
dimension is omitted uniformly from every Pareto vector and winner ordering
continues at API cost. The development **efficiency** promotion branch is
unavailable because it requires regret evidence. If the final 041-050 regret
cohort is empty, neither paper-level method-claim branch may pass; the quality,
reliability, and cost results are still reported without a "better design
pattern" claim.

Do not sum dollars/pesos/etc. across currencies. Native regret is reported by
currency; only normalized regret percentages on the frozen positive-oracle-cost
common cohort are aggregated.

### Agent efficiency

Always report:

- accepted actions;
- model calls;
- prompt/completion/total tokens;
- model latency;
- known API cost;
- deterministic-action fraction.

## Promotion logic

A candidate first has to execute cleanly and pass the minimum development
quality floor: at least 47/60 feasible-obligation, 27/60 strict v0.2, and
27/60 economic success.

Development promotion can happen through either frozen structured branch:

- **quality branch:** improve at least one of feasible-obligation, strict, or
  economic success by **3/60** versus Coverage+Repair; no other mandatory
  success metric may be more than **3/60 worse**; known API cost may not exceed
  frozen ReAct cost (**$7.9842032**);
- **efficiency branch:** remain within **3/60** of Coverage+Repair on
  feasible-obligation, strict, and economic success; regret must be no worse on
  the full frozen reference cohort; and known API cost must be at least
  **20% lower** than Coverage+Repair.

The machine-readable JSON stores these as numeric fields, and CI checks the
exact values rather than matching phrases.

## Final method claim

When the stop rule fires, the winner is selected **once** from the cumulative
ProcureHarness validation frontier. If the frontier contains no candidate, the
result is frozen as **no winner** and no ProcureHarness model-backed row is run
on 041-050.

If multiple candidates remain, selection is deterministic and lexicographic:

1. feasible-obligation success (higher);
2. strict v0.2 (higher);
3. economic objective (higher);
4. obligation resolution (higher);
5. common-cohort regret percent (lower);
6. API cost (lower);
7. tokens (lower);
8. latency (lower);
9. model calls (lower);
10. candidate ID (ascending).

The chosen code/config/prompts/settings are then frozen before any 041-050
model-backed call.

If a winner exists, the final 041-050 comparison contains:

- ProcureHarness winner;
- Coverage+Repair;
- ReAct;
- deterministic reference control;

with 3 repeats for each model-backed row and no tuning after the first final-test
model call. If there is no winner, only deterministic reference control is used
to validate the 041-050 benchmark package; there is no new-method final test.

A paper-level "better design pattern" claim then requires one of the exact
structured gates in the protocol JSON:

- **quality:** +3/30 feasible-obligation versus the per-metric baseline envelope,
  no more than 1/30 deficit on strict/economic, no worse regret on the full
  reference cohort, and cost no higher than ReAct; or
- **efficiency:** within 1/30 of the per-metric baseline envelope on
  feasible-obligation/strict/economic, no worse common-cohort regret, and at
  least 30% lower API cost than the cheaper matched baseline.

If neither passes, the honest result is a negative architecture-search result.

## Immediate implementation order

1. **This PR:** freeze architecture grammar, search budget, data hygiene,
   metrics, economic-regret semantics, stop rule, and claim gate.
2. Implement and regression-test economic regret uniformly.
3. Collect/freeze real public starting states and episodes 031-050.
4. Implement the code-represented skill-graph search harness.
5. Run bounded architecture search to the frozen plateau rule.
6. Freeze the winner.
7. Run the one-time 041-050 method comparison.
8. Only then start the memory/KG/forecasting/routing/self-improvement harness
   phase.
