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

## Next batches

The target is approximately 30 episodes. Later batches will add relays, power
supplies, breakers, UPS/battery, additional generator packages, and compound
episodes with multiple outstanding obligations active at once.


## Distinct-state invariant

Every committed benchmark episode must reference a distinct real public
`package_id`. Suite validation enforces one-to-one episode-to-initial-state
coverage, so distinct-state breadth grows automatically with the episode count.

## Revision-order invariant

`request_quote_revision` is a stateful runtime action: it is rejected unless a
quote from that supplier has already been revealed. This prevents an agent from
triggering a synthetic revision before the supplier has submitted an initial
offer.
