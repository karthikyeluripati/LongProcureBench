# State Validity Frontier v0.1 — frozen method protocol

## Status

**Preregistered method candidate. No implementation and no results yet.**

This protocol reopens architecture work only because the post-hoc diagnostics
identified a narrower causal gap than the earlier broad mechanism search:
visible history is present, but agents repeatedly act as if already-resolved
prerequisites or invalidated decisions were still current.

The proposed controller is the candidate core of a future ProcureHarness
method. It is **not** yet evidence of a successful ProcureHarness architecture.

## Research question

> Can a recomputed, versioned workflow-validity graph with dependency-scoped
> invalidation and a minimal valid-action frontier recover from evolving
> procurement state while spending LLM calls only where more than one valid
> choice remains?

The hypothesis is deliberately narrower than “state machines help agents.”
The benchmark already showed that free-text ledgers, maintained plans,
always-replanning, and static Plan-and-Execute can all become expensive failure
amplifiers.

## What is carried forward

The controller builds on **Coverage+Repair v0.1**, because that diagnostic
already recovered the ReAct development quality region at much lower inference
cost. We do not re-open supplier-coverage as an unsolved problem.

The new mechanism adds only:

1. a deterministically recomputed validity graph;
2. dependency-scoped invalidation from newly visible events;
3. a minimal valid-action / repair frontier;
4. LLM deliberation only when the frontier contains multiple legitimate
   choices.

There is no free-text persistent plan and no free-text state ledger.

## Information boundary

The controller may use only the same information already available to
`factual_compiled_v0.1`:

- visible initial-state facts;
- currently visible suppliers;
- accepted action history;
- revealed event history;
- latest visible quote/revision facts;
- deterministic ordering and version bookkeeping derived from those facts.

It may **not** use the episode oracle, Evaluator v0.2 output, hidden event
triggers, required-checkpoint labels, preferred outcomes, future events, or
episode/supplier-specific recovery rules.

The controller is allowed to decide that an artifact is **stale** because of a
visible dependency/version change. It is not allowed to decide that a quote is
economically optimal or feasible using hidden evaluator knowledge.

## Validity graph

The minimum graph is:

```text
requirements(version)
        |
        +--> solicitation[supplier](version)
        |          |
        |          +--> offer[supplier](version)
        |                         |
supplier_active[supplier] --------+
                                  |
                                  v
                            evaluation(snapshot)
                                  |
                                  v
                          terminal_decision
```

The graph is recomputed from visible facts and accepted history on every action
decision. It is not another learned/persistent memory structure.

### Requirement epoch

`requirement_epoch` starts at 0 and increments only on a visible
`requirement_change` or `quantity_change`.

Existing offers from an earlier epoch become stale. If sourcing had already
started, the current epoch cannot proceed to offer evaluation until an
amendment has been issued and affected offers have been repaired/refreshed.

### Clarification lease

A maximum of **one** `request_buyer_clarification` is valid in a requirement
epoch.

After one accepted clarification request, clarification leaves the frontier
until a new requirement/quantity change creates another epoch. A visible
`buyer_clarification` resolves the current clarification opportunity; an
unanswered request does not justify immediate repeated clarification.

This is the explicit control against the clarification fixation observed in the
ledger, verifier, and static Plan-and-Execute experiments.

## Generic invalidation rules

| Visible event | Validity effect |
| --- | --- |
| requirement / quantity change | increment requirement epoch; invalidate evaluation/terminal state; old offers become stale; require amendment if sourcing already began |
| supplier withdrawal | mark supplier inactive; invalidate evaluation/terminal state; supplier is no longer awardable |
| quote received / revision | replace current supplier offer; invalidate any prior evaluation/terminal state |
| supplier non-response | open one bounded supplier-repair obligation |
| supplier question | open one bounded supplier-repair obligation |

These rules are event-type generic. The implementation must not branch on
episode ID, known future event IDs, or supplier names.

## Decision frontier

The controller exposes only currently valid unresolved actions, in this
priority order:

1. post-change amendment when requirements changed after sourcing;
2. visible supplier question/non-response repair inherited from
   Coverage+Repair;
3. RFQ coverage after sourcing starts;
4. refresh offers made stale by the requirement epoch;
5. recovery after supplier/evaluation invalidation using active visible
   suppliers only;
6. evaluate the current visible offer set;
7. terminal decision only from a current evaluation.

Before sourcing starts, the LLM may choose among the valid start actions
(e.g. one clarification opportunity versus supplier discovery). Once sourcing
starts, Coverage+Repair's bounded coverage behavior remains in force.

When the frontier contains exactly one valid action, execute it
**deterministically**. When it contains multiple valid actions, make one LLM
call constrained to those actions.

After a withdrawal, for example, `evaluate_quotes` can coexist with
`request_quote_revision` for active suppliers. That is a genuine
evidence-acquisition decision and is left to the model rather than hard-coded.

## Stage-1 targeted pilot

Exactly **3 paid runs total**:

- model: `openai/gpt-5.6-sol`
- reasoning: `medium`
- temperature: omitted
- max actions: 50
- repeats: 1
- no held-out episodes

### 008 — supplier withdrawal

The mechanism must:

- mark the withdrawn supplier inactive;
- invalidate the pre-withdrawal evaluation;
- exclude that supplier from any later terminal action;
- take at least one post-withdrawal recovery/evaluation action before terminal;
- not reopen buyer clarification absent a new requirement epoch.

### 013 — starting prerequisite

The mechanism must:

- permit at most one clarification in requirement epoch 0;
- remove clarification from the frontier after the buyer response;
- advance to supplier discovery/RFQ afterward;
- disallow a terminal decision without a current evaluation.

### 016 — requirement change

The mechanism must:

- increment the requirement epoch on the visible change;
- require an amendment because sourcing already began;
- mark pre-change offers stale;
- expose post-amendment quote/non-response repair before terminal;
- avoid a clarification loop in the unchanged epoch.

## Frozen go / no-go gate

Do **not** run a development-wide grid unless all of the following hold:

- all three runs execute without policy/protocol errors;
- every episode-specific mechanism assertion passes;
- no run hits the 50-action cap;
- each run records at least one validity/frontier intervention;
- terminal feasibility is at least **2/3**;
- feasible-obligation success is at least **2/3**.

Passing this gate does not authorize an ad-hoc full experiment. It authorizes a
**separate frozen repeated-development protocol** before more paid runs.

If the gate fails, freeze the negative diagnostic and inspect the specific
mechanism failure rather than tuning against the three trajectories until they
pass.

## Later comparisons and ablations

If Stage 1 passes, the method must eventually be compared against the frozen:

- factual-context baseline;
- ReAct comparator;
- Coverage+Repair;
- static Plan-and-Execute negative comparator.

Planned component ablations:

1. remove dependency invalidation but retain frontier gating;
2. retain visible validity annotations but remove frontier gating;
3. replace deterministic singleton execution with an LLM call at every
   frontier step.

These are needed before attributing any gain to the proposed control mechanism.

## Held-out hygiene

Episodes **021-030 are not untouched for this new method**. They have already
been evaluated and inspected and may only be cited as prior diagnostic
evidence.

After development and method freeze, author a **new untouched 031+ held-out
set**, validate/freeze it before model calls, and never update the method from
those results.

## Related-work boundary

Two nearby lines of work make the novelty boundary important:

- **StateFlow** already frames LLM task solving as state-machine process
  grounding plus within-state actions. We therefore do not claim that
  “state-driven workflows” are new.
- **PlanFence** studies dependency-scoped validation of plans under changing
  shared records. We therefore do not claim that dependency validity or
  invalidation alone is new.

The candidate contribution, **if the experiments support it**, must be narrower:
a recomputed versioned workflow-validity representation that produces a
minimal repair/decision frontier and selectively allocates model deliberation,
evaluated under long-horizon procurement quality, obligation, and economic-cost
metrics.

If the eventual implementation reduces to a generic state machine or
dependency validator, it is not sufficient as a new method claim.

## Claim discipline

Before Stage 1 results:

- do not call the controller successful;
- do not claim superiority;
- do not claim novelty;
- do not relabel the existing paper evidence as support for this method.

Paper-level method claims require the targeted mechanism gate, repeated
development comparison, component ablations, and a new untouched held-out set.
