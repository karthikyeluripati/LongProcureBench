# LongProcureBench episode model v0.1

This layer converts real public procurement starting states into controlled,
semi-synthetic long-horizon episodes. It does **not** claim that the synthetic
supplier names, quotes, messages, or timelines happened historically.

## Reality boundary

| Layer | Status in v0.1 |
|---|---|
| Procurement starting state | **Real public data** from `data/initial_states/` |
| Buyer requirement fields already in the initial state | **Real public data** |
| Supplier identities used inside an episode | **Synthetic** |
| Supplier responses, prices, questions and revisions | **Synthetic** |
| Timing/order of episode events | **Synthetic** |
| Oracle/checkpoints | Curator-authored benchmark ground truth |
| Procurement process patterns used to design events | Calibrated against public procurement guidance |

The benchmark rule is: **preserve reality where it is observable; synthesize only
the private interaction layer or controlled interventions needed for evaluation.**

## Agent/environment contract

At reset, the agent sees only the referenced real initial state. The environment
holds synthetic supplier profiles and future events. The agent acts through
`schema/action.schema.json`. An event becomes visible only when its trigger fires.
Previously revealed events and the agent's own action history remain observable.

The benchmark does not prescribe one exact action sequence. The oracle defines
hard constraints, required checkpoints, acceptable terminal outcomes, and failure
conditions. Different agent architectures can therefore solve the same task using
different planning and memory strategies.

## v0.1 action space

- `request_buyer_clarification`
- `identify_suppliers`
- `send_rfq`
- `send_follow_up`
- `answer_supplier_question`
- `issue_amendment`
- `request_quote_revision`
- `evaluate_quotes`
- `award_supplier`
- `no_award`

## v0.1 event ontology

| Event | What it tests |
|---|---|
| `buyer_clarification` | Resolving missing starting information |
| `supplier_non_response` | Follow-up and recovery |
| `supplier_question` | Maintaining requirement state while answering vendors |
| `quote_received` | Quote ingestion and normalization |
| `quote_revision` | Versioning and stale-offer handling |
| `substitution_proposed` | Technical compliance / alternate handling |
| `requirement_change` | Midstream buyer change |
| `quantity_change` | Concrete amendment to demand |
| `lead_time_change` | Schedule risk |
| `supplier_withdrawal` | Recovery after a viable option disappears |

## First five episodes

1. **Bongabon generator** — non-response, lead-time conflict, warranty revision.
2. **National Museum lighting** — two lots, partial offers, accelerated revision.
3. **NEUST cable** — quantity amendment, stale quotes, aluminum substitution.
4. **DLA circuit breakers** — SDVOSB eligibility, withdrawal, delivery recovery.
5. **Barrie transformer** — missing quantity/unit, buyer clarification, incomplete quote revision.

## Process-pattern references

These references justify the event classes; they are not governing law for every episode:

- FAR 15.306: https://www.acquisition.gov/far/15.306
- FAR 15.206: https://www.acquisition.gov/far/15.206
- FAR 15.208: https://www.acquisition.gov/far/15.208
- UNDP, *How we buy*: https://www.undp.org/procurement/doing-business-undp/how-we-buy
- World Bank Procurement Framework: https://www.worldbank.org/ext/en/what-we-do/project-procurement/framework

## Not built yet

There is still **no runtime simulator, agent baseline, scoring implementation, or
leaderboard**. This milestone freezes the episode data contract and provides five
reviewable episodes before runtime behavior is implemented.
