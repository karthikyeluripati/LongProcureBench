# LongProcureBench Initial State v0.1 candidate

This milestone expands the electrical initial-state set from 3 to **20 real public procurement packages**.

## Diversity
- Existing seed: transformers, underground cable, generators.
- Added: lighting, additional cable, generators, switchgear, transformers, circuit breakers, power supplies, relays/controls, UPS/batteries.
- Sources include PhilGEPS, SAM.gov, and municipal/agency procurement portals across the Philippines, United States, and Canada.

## Availability pattern
- Strongest public fields: item identity, quantity/unit, solicitation timing, relative delivery terms, and buyer-authored technical text.
- Buyer budgets/cost ceilings are much more consistently exposed by PhilGEPS than by SAM.gov or municipal preview pages.
- Whole-item manufacturer/model and absolute need-by dates are usually missing.
- Some portals expose indexed/browser content but not raw immutable source bytes; those records use `sha256: null` plus `source_snapshot_unavailable`.
- Some detailed attachments remain inaccessible from public preview pages; these records explicitly carry `partial_extraction`.

## Limitation
This is a curated feasibility sample, not a statistically representative sample of electrical procurement. Public solicitations approximate the buyer's pre-RFQ state; they do not reproduce private ERP history, supplier relationships, internal approvals, or communications.

## Freeze
Treat this as the **Initial State v0.1 candidate**. Do not build the agent yet. The next milestone is the event/scenario ontology that turns these starting states into long-horizon procurement episodes.
