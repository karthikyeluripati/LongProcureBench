# Progress-aware reactive v0.1

## Research question

Can a procurement agent distinguish an information-seeking action that can
still produce new visible evidence from one that has already produced no
progress, and thereby avoid repeated information-seeking loops without adding
oracle state, evaluator labels, a planner, or an always-on verifier?

This experiment follows the negative always-replan + verifier result, where
557/585 terminal proposals were rejected and 545 rejections routed back to
buyer clarification, producing 1,329 accepted clarification actions.

## Frozen treatment

Matched to the frozen factual context-compiled GPT-5.6 Sol baseline:

- same 20 development/calibration episodes 001-020;
- same model: GPT-5.6 Sol;
- reasoning effort: medium;
- temperature omitted;
- same runtime, evaluator, semantic action contract, and 50 accepted-action cap;
- same factual context compiler;
- no planner, terminal verifier, obligation ledger, hidden memory, tool calls,
  evaluator labels, or oracle fields.

The treatment adds only a deterministic visible-evidence progress guard.

### Evidence epoch

A canonical fingerprint is computed from four fields already present in the
compiled visible state:

1. visible_suppliers
2. latest_offers
3. requirement_updates
4. event_history

Step count and action history are excluded. A new fingerprint begins a new
evidence epoch and clears all no-progress blocks.

### Information-seeking actions

The frozen information-seeking set is:

- request_buyer_clarification
- identify_suppliers
- send_rfq
- send_follow_up
- request_quote_revision

The action signature is exactly (action_type, supplier_id). Free-text reasons
are intentionally excluded so paraphrasing the same request cannot evade the
guard.

After an accepted information-seeking action, if the visible-evidence
fingerprint is unchanged, that signature is marked as no-progress for the
current evidence epoch.

### Bounded guard intervention

The model receives the current no-progress signature list in a compact
progress_control block.

If the first proposed action repeats a blocked signature, the harness does not
execute that proposal. It performs one additional selector call over the same
visible state, explicitly marking the blocked proposal. The retry is the action
returned to the environment. If the retry still repeats a blocked signature, it
is executed and the noncompliance is recorded; there is no hidden deterministic
fallback or episode-specific action substitution.

This isolates a small progress-control mechanism rather than buying a new
planner/verifier stack.

## Information boundary

The guard may use only action signatures and the four agent-visible factual
fields above. It may not inspect:

- evaluator obligations/checkpoints;
- oracle constraints or outcomes;
- hidden suppliers or future events;
- held-out data;
- episode-specific rules.

Held-out starting states and future held-out episodes remain untouched.

## Predeclared development gate

Compare the 60-run treatment grid against the frozen 60-run context-compiled
GPT-5.6 Sol grid.

Retain the mechanism only if either:

1. feasible-obligation success improves by at least 5 percentage points,
   terminal feasibility falls by no more than 5 points, and total tokens
   increase by no more than 15%; or
2. strict v0.2 success improves by at least 5 points, feasible-obligation
   success falls by no more than 2 points, terminal feasibility falls by no
   more than 5 points, and total tokens increase by no more than 15%.

The resource guard prevents a reliability gain from being accepted if the
bounded retry mechanism becomes another expensive inference loop.

Mechanism diagnostics are:

- no-progress marks;
- guard interventions;
- guard retry calls;
- retry noncompliance;
- evidence-epoch resets;
- action-type distribution;
- max-action runs;
- accepted actions, model calls, tokens, latency, and known API cost.

## Conditional next step

- Pass: keep progress control as a ProcureHarness candidate and then test
  whether selective deliberation/tool use can be layered on top without
  reintroducing loops.
- Fail: drop this formulation and use the accumulated failure evidence to
  decide whether the paper should stop architecture search and move to external
  comparator/held-out evaluation.

No held-out episode is inspected, authored, or evaluated by this experiment.
