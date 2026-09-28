# State Validity Frontier development v0.2 — frozen result

## Verdict

**Negative development result. The preregistered v0.2 development gate failed.**

Do not tune State Validity Frontier on episodes 001-020 from this result. Do
not proceed to the planned component ablations or a new 031+ held-out
evaluation under the v0.2 protocol.

## Frozen development result

| Metric | SVF v0.2 | Frozen Coverage+Repair | Delta |
| --- | ---: | ---: | ---: |
| Terminal feasible | 39/60 (65.0%) | 52/60 (86.7%) | -21.7 pp |
| Feasible-obligation | 38/60 (63.3%) | 50/60 (83.3%) | -20.0 pp |
| Strict v0.2 | 23/60 (38.3%) | 30/60 (50.0%) | -11.7 pp |
| Economic objective | 24/60 (40.0%) | 30/60 (50.0%) | -10.0 pp |
| Accepted actions | 517 | 476 | +8.6% |
| Model calls | 233 | 324 | -28.1% |
| Total tokens | 561,945 | 687,462 | -18.3% |
| Model latency | 479,978.94 ms | 667,333.28 ms | -28.1% |
| Known API cost | $2.7652 | $2.9777 | -7.1% |

SVF is substantially cheaper than ReAct ($2.765 vs $7.984), but the frozen
comparison is not an efficiency win because quality is materially lower than
Coverage+Repair and the cost reduction versus Coverage+Repair is only 7.1%,
below the preregistered 20% efficiency branch.

## Execution failure

Nine of the 60 runs ended in `StateValidityFrontierError`:

- episode 004: 3/3 repeats;
- episode 012: 3/3 repeats;
- episode 015: 3/3 repeats.

All nine share the same error:

> Withdrawal recovery has no unattempted active-supplier quote evidence left;
> replacement evidence was not obtained.

This is a generalization failure of the withdrawal-recovery frontier, not a
provider/infrastructure failure.

## Prerequisite sequence gate

Episode 013:

| Repeat | buyer clarification | first RFQ | Pass |
| --- | ---: | ---: | --- |
| 1 | step 1 | step 3 | yes |
| 2 | step 2 | step 3 | yes |
| 3 | not revealed | step 2 | **no** |

Therefore the explicit v0.2 prerequisite sequence gate also fails.

## Frozen gate

- execution clean: **fail**
- 013 prerequisite sequence: **fail**
- feasible-obligation >= 47/60: **fail** (38/60)
- strict >= 30/60: **fail** (23/60)
- economic >= 30/60: **fail** (24/60)
- quality contribution branch: **fail**
- efficiency contribution branch: **fail**
- overall development gate: **fail**

## Interpretation

The targeted 008/013/016 Stage-1 result did not generalize across the full
development suite. State Validity Frontier successfully reduces LLM
deliberation—284 of 517 actions were deterministic frontier actions—but its
current recovery semantics are brittle on other withdrawal episodes and its
overall procurement quality/economic performance falls below Coverage+Repair.

This closes the v0.2 method branch as a negative development result. The
Coverage+Repair result remains the strongest development quality/cost point
among the tested workflow controllers.

## Source evidence

Workflow run: `36418270289`

Artifact: `10968521526`

Artifact SHA-256:
`29e8ae46319336c5d508c116784523ddaca191352b369a100e4d663b91817a4c`

The committed replay is linked to every raw run by byte size and SHA-256 and is
replay-audited through the deterministic LongProcureBench environment and
Evaluator v0.2.
