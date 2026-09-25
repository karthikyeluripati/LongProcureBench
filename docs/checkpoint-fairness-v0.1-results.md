# Checkpoint fairness audit v0.1 results

Audited **60** saved Luna trajectories across **20** frozen episodes from
workflow run `36173979424`. The source trajectories were not modified.

## Headline

| Finding | Count |
| --- | ---: |
| Current checkpoint failures on obligations that never became applicable | **55** |
| Applicable obligations revealed with no later action opportunity | **2** |
| Clearly applicable + actionable obligation failures | **32** |
| Failures from evaluator proxy checkpoints | **19** |
| Failures from procedural-policy checkpoints | **1** |
| Potentially over-prescriptive withdrawal-recovery cases | **3** |

## Non-applicable failures in the current evaluator

- `request_quote_revision`: **31**
- `follow_up_nonresponse`: **15**
- `handle_supplier_question`: **9**

These are currently scored as missing required checkpoints even when the branch
or event that creates the obligation was never observed on that trajectory.

## No-opportunity failures

- `handle_amendment`: **2**

Both occurred in `electrical-vre-generator-020`: the controlled requirement
change was emitted on the terminal award step, so the agent had no subsequent
action opportunity to issue an amendment.

## Applicable + actionable obligation failures

- `recover_from_withdrawal`: **10**
- `resolve_requirement_gap`: **10**
- `follow_up_nonresponse`: **6**
- `handle_amendment`: **6**

These are the strongest current candidates for the paper's actual long-horizon
obligation-failure signal.

## Proxy checkpoint failures

- `validate_compliance`: **16**
- `validate_eligibility`: **2**
- `normalize_quotes`: **1**

These do not correspond to explicit agent actions in the current action space.
They should remain separately reported rather than silently folded into an
obligation-success headline.

## Withdrawal-recovery caveat

Three `electrical-dla-relay-012` trajectories reached a feasible terminal award
and passed hard constraints after the preferred supplier withdrew, yet still
failed `recover_from_withdrawal` because the evaluator requires a fresh
post-withdrawal quote followed by re-evaluation.

That rule may be too prescriptive when an already-revealed, still-valid fallback
offer is sufficient for a correct recovery. It should be reconsidered in
Evaluator v0.2.

## Static episode audit

All 20 episode definitions contain the trigger/event classes needed by their
declared event-driven checkpoints. No static checkpoint/trigger mismatch was
found.

## Research consequence

The previously reported **18.3% feasible-process success rate should not be used
as the paper's primary long-horizon obligation metric** in its current form.

The fairness audit supports an Evaluator v0.2 with these principles:

1. event-driven obligations are scored only after their triggering event becomes
   visible;
2. an obligation is not scored as failed when it is revealed on the terminal
   step with no subsequent action opportunity;
3. quote-revision work is branch-conditional rather than universally mandatory;
4. proxy/procedural checkpoints are reported separately from genuine
   event/state obligations;
5. withdrawal recovery should judge whether the agent restored a valid award
   path, not require one fixed recovery sequence.

The raw 60-run trajectories remain useful and can be deterministically rescored
after these semantics are frozen.
