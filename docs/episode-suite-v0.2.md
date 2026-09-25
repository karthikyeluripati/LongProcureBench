# Episode Suite v0.2

LongProcureBench v0.2 expands the original five electrical procurement episodes
using additional real public starting states while preserving the same controlled
semi-synthetic interaction model.

## Expansion strategy

The suite is expanded in reviewed batches rather than generated as opaque runtime
tasks. Every committed episode is static JSON with:

- a real public `initial_state_ref`;
- explicitly synthetic suppliers, quotes, messages, revisions, and event timing;
- deterministic hard-constraint checks;
- explicit feasible outcomes and minimum-price economic preference;
- a scripted oracle-aware reference control used only for integration sanity.

## Batch 1: episodes 006–010

| Episode | Real starting state | Main long-horizon obligations |
| --- | --- | --- |
| 006 BFAR generator | Two 5 kVA generators | non-response follow-up; service-scope question; revision |
| 007 Negros wire | #6 service-drop wire | resolve public-source quantity ambiguity before RFQ; stale quantity correction |
| 008 Burauen generator | 250 kVA generator + ATS | supplier withdrawal; replacement revision; re-evaluation |
| 009 High Point transformer | Five 300 kVA transformers | clarify missing schedule/budget and alternate policy; revision |
| 010 Painesville switchgear | Switchgear + solar switches | clarify missing quantities; partial offers; split award; delivery revision |

This first batch intentionally increases **state/obligation diversity**, not merely
the number of price-comparison tasks.

## Batch 2: episodes 011–020

| Episode | Real starting state | Main long-horizon obligations |
| --- | --- | --- |
| 011 Sagada generator | 60 kVA generator + ATS | non-response; schedule change; amendment; stale-offer refresh |
| 012 DLA relay | 24 electromagnetic relays | non-response; withdrawal; quantity correction; re-evaluation |
| 013 DLA transformer | 56 power transformers | commercial clarification; supplier question; delivery revision |
| 014 DLA battery supply | 5 delivery lines | eligibility; partial offers; multi-line normalization; late revision |
| 015 DLA battery charger | 34 aircraft battery chargers | eligibility; withdrawal; supplier question; recovery revision |
| 016 DLA power supply | 57 power supplies | non-response; expedited schedule amendment; multiple refreshed offers |
| 017 DLA QPL breaker | 161 circuit breakers | small-business eligibility; QPL compliance; supplier question; revision |
| 018 High Point cable | 5 cable lines | substitution ambiguity; clarification; priced substitution; split award |
| 019 USAF UPS | 80 UPS batteries + installation equipment | eligibility; scope omission; withdrawal; recovery revision |
| 020 VRE generator | 60 kW mobile generator | commercial clarification; non-response; schedule amendment; stale-offer refresh |

Batch 2 deliberately stacks multiple outstanding obligations in the same
trajectory. The full suite now covers all 20 currently collected real public
initial states exactly once.

## Next gate

The next benchmark-scale target is approximately 30 episodes. Reaching it now
requires collecting about ten additional real public procurement starting states;
the repository has exhausted its current 20-state pool.

Episodes 001–020 are now explicitly treated as **development/calibration**:
they were used to build the runtime, inspect model trajectories, audit checkpoint
fairness, and design Evaluator v0.2. The next ten distinct states are reserved for
the held-out paper evaluation slice. See `BENCHMARK_SPEC.md`,
`OBSERVABILITY_MATRIX.csv`, and
`data/splits/electrical-v0.3-plan.json`.


## Distinct-state invariant

Every committed benchmark episode must reference a distinct real public
`package_id`. Suite validation enforces one-to-one episode-to-initial-state
coverage, so distinct-state breadth grows automatically with the episode count.

## Revision-order invariant

`request_quote_revision` is a stateful runtime action: it is rejected unless a
quote from that supplier has already been revealed. This prevents an agent from
triggering a synthetic revision before the supplier has submitted an initial
offer.
