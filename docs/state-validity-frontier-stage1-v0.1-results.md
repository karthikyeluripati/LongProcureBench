# State Validity Frontier Stage-1 v0.1 — frozen result

## Result

The preregistered three-run development mechanism pilot executed exactly:

- `electrical-burauen-generator-008`
- `electrical-dla-transformer-013`
- `electrical-dla-power-supply-016`
- GPT-5.6 Sol, medium reasoning, temperature omitted
- one repeat each, max 50 actions

All three runs completed in 10 accepted actions.

| Episode | Terminal | Feasible obligations | Strict v0.2 | Economic objective | Calls | Tokens | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 008 | 1 | 1 | 1 | 1 | 4 | 9,444 | $0.0520 |
| 013 | 1 | 1 | 1 | 1 | 6 | 14,848 | $0.0811 |
| 016 | 1 | 1 | 1 | 1 | 4 | 9,369 | $0.0525 |

Aggregate: **3/3 terminal-feasible, 3/3 feasible-obligation, 3/3 strict,
3/3 economically optimal, 7/7 actionable obligations resolved, 0 unresolved,
33,661 tokens, 14 model calls, and $0.185558 known API cost.**

## Mechanism traces

### 008 — withdrawal recovery succeeded

The controller covered all suppliers, evaluated, observed Supplier A's
withdrawal, invalidated the prior evaluation, acquired a new Supplier C
revision, reevaluated, and awarded C.

Sequence after withdrawal:

`withdrawal -> request_quote_revision(C) -> quote_revision -> evaluate_quotes -> award(C)`

This satisfies the frozen 008 recovery requirement.

### 013 — quality succeeded; one frozen ordering assertion did not

The run identified suppliers at step 1, requested buyer clarification at step
2, and sent its first RFQ at step 3. It later recovered the supplier-question
path and awarded the economically preferred revised Supplier C quote.

Thus:

- exactly one clarification: pass;
- clarification removed from the frontier after response: pass;
- first RFQ occurs after clarification response: pass;
- revision -> supplier question -> answer -> revised quote -> evaluation: pass;
- terminal action only after a current evaluation: pass;
- **literal frozen assertion that supplier discovery/RFQ begins after the
  clarification response: fail**, because `identify_suppliers` occurred at
  step 1 before the step-2 clarification.

This sequencing deviation does not change the 3/3 quality/economic outcome, but
the preregistration requires all episode-specific mechanism assertions to pass.

### 016 — requirement-change recovery succeeded

The controller sourced all suppliers, observed non-response plus the requirement
change, incremented the requirement epoch, issued the amendment, followed up the
non-responder, refreshed both stale offers, reevaluated, and awarded the
economically preferred Supplier C offer.

## Frozen verdict

- execution clean: **pass**
- no max-action run: **pass**
- validity/frontier mechanism activated in all runs: **pass**
- quality gate (>=2/3 terminal + >=2/3 feasible-obligation): **pass, 3/3 + 3/3**
- strict episode-specific mechanism gate: **fail**
- overall preregistered Stage-1 go gate: **fail**

Therefore **do not run the repeated development grid from this pilot**.

The result should be treated as strong positive quality/economic evidence from a
three-case mechanism diagnostic, accompanied by one preregistered ordering
deviation in episode 013. Do not tune and rerun the same three cases until they
pass.

## Durable evidence

The temporary Actions artifact expires on 2026-10-28, but the repository
contains a checksum-locked compact replay preserving every accepted action,
observation, frontier trace, validity diagnostic, and usage metric required to
replay Evaluator v0.2 and audit this verdict.

- workflow run: `36410695850`
- artifact: `10964162663`
- artifact digest:
  `sha256:92c3c7fe4cd7550a2c91141ff9fde3c98c143d6d632bfa767c4fd860800fdf96`
- benchmark implementation: `fcffd9ccefdf07d7922d67d40ab1e67dc4781172`
- execution workflow commit:
  `2cf4aa43bf1986078926c513c148a2e3a46fb06d`
- durable manifest:
  `evidence/state-validity-frontier-stage1-v0.1/manifest.json`
- deterministic audit:
  `scripts/audit_state_validity_frontier_stage1_v01.py`
