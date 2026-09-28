# Plan-and-Execute targeted diagnostic v0.1 — result

## Decision

**Do not run a 20x3 Plan-and-Execute development grid.**

The frozen three-episode mechanism pilot completed its exact protocol on
development episodes 008, 013, and 016 using GPT-5.6 Sol, medium reasoning,
temperature omitted, one repeat, and a 50-action cap.

| Episode | Status | Terminal | Strict | Economic | Actions | Tokens | Cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 008 Burauen | completed | 0 | 0 | 0 | 3 | 9,015 | $0.066 |
| 013 DLA transformer | completed | 0 | 0 | 0 | 6 | 17,084 | $0.109 |
| 016 DLA power supply | max_actions | 0 | 0 | 0 | 50 | 219,547 | $1.207 |

Aggregate: **0/3 terminal, 0/3 strict, 0/3 economic, 245,646 tokens,
$1.3815, and zero unplanned exceptions.**

## What happened

### 008 — the intended withdrawal test was never reached

The fixed plan contained clarification, sourcing, RFQ, repair, evaluation, and
award steps. Execution nevertheless chose buyer clarification twice and then
`no_award`. No supplier was identified or solicited, so the withdrawal event
never appeared.

### 013 — prerequisite recognition worked, but gating failed

The first buyer clarification revealed the controlled budget and therefore
resolved the benchmark's actionable starting requirement-gap obligation.
Instead of advancing to sourcing, the executor continued asking for unrelated
missing metadata four more times and then chose `no_award`.

This distinguishes **recognizing a prerequisite** from **knowing when the
prerequisite is sufficiently resolved to advance**.

### 016 — static planning amplified clarification fixation

The executor requested buyer clarification for steps 1-4. The requirement
change appeared at step 4, and the agent correctly issued an amendment at step
5. It then requested buyer clarification for steps 6-50 and hit the action cap.

The run used 219,547 tokens and $1.21 while never reaching supplier
solicitation, non-response recovery, or quote revision.

## Comparison to the stronger workflow diagnostic

This is not a matched statistical comparison because Plan-and-Execute has one
targeted repeat while frozen Coverage+Repair has three repeats per development
episode. The episode-level contrast is nevertheless diagnostic:

- 016: Coverage+Repair is **3/3 strict + economic**; Plan-and-Execute is 0/1 and
  hits the 50-action cap.
- 013: Coverage+Repair reaches a feasible terminal outcome in all 3 repeats
  (with remaining economic/revision weakness); Plan-and-Execute terminates
  before sourcing.
- 008: both remain unsuccessful. Coverage+Repair reaches the supplier
  withdrawal but fails to reopen/repair the decision path; Plan-and-Execute
  does not reach the withdrawal.

Thus **008 is the cleanest remaining control failure**, while 016 demonstrates
that free-text static planning can actively destroy a workflow already handled
well by explicit workflow control.

## Research consequence

Do not interpret this as "planning is useless." It is evidence against using a
free-text fixed plan as the missing control mechanism in this benchmark.

The next hypothesis should isolate:

1. **Structured state validity** — explicit, machine-checkable state saying
   which procurement facts/decisions are sufficient for the next stage.
2. **Event-driven invalidation** — requirement changes, withdrawals, revisions,
   and non-response invalidate only the dependent state/decision nodes.
3. **Decision frontier** — expose only currently valid unresolved decisions,
   preventing repeated clarification after its relevant prerequisite has been
   satisfied.
4. **Selective deliberation** — use the LLM only where multiple valid choices
   or genuinely ambiguous evidence remain; execute routine workflow transitions
   deterministically.

Coverage+Repair becomes the strong workflow baseline. Static Plan-and-Execute is
retained as a negative external comparator.

## Reflexion boundary

Canonical Reflexion uses task feedback from a prior trial to generate verbal
reflection that is retained in episodic memory for later trials. LongProcureBench
currently does not expose an external success/failure signal to the agent.
Providing Evaluator v0.2 / oracle-derived failure feedback only to Reflexion
would change the information boundary and make the comparison unfair.

Therefore do **not** run a Reflexion baseline until a matched retry/feedback
contract is specified for every comparator, or a strictly visible-feedback
variant is explicitly labeled as a different method.

## Provenance

- workflow run: 36396684099
- artifact: 10957769763
- artifact digest:
  `sha256:b5588478661f9ccc30ceeac563cdef2dc4b6fd48eb6515603b0117c7d935925f`
- benchmark code: `5257769482b79ff3c8c717715b96d2e116552ac1`
- execution workflow commit:
  `135ff49e61c557da6efc7dc5b36e57fbbc8e64a6`
- artifact expiry: 2026-10-28
