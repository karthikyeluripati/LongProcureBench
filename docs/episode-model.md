# LongProcureBench episode model

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
conditions. Timing, quote scope, and terminal-outcome representation are normative
parts of the episode contract. Different agent architectures can therefore solve the same task using
different planning and memory strategies.


## Runtime timing semantics

Timing is deterministic and **steps count accepted agent actions only**. Events and
observations do not increment the counter.

For accepted action number `n`, the environment must:

1. validate and apply action `n`;
2. emit matching `after_action` events in the order they appear in the episode file;
3. emit every `at_step` event whose `step == n`, again in episode-file order;
4. return all observations from that step to the agent;
5. only then accept the next agent action.

The agent cannot act between two events emitted during the same step. Thus an
`at_step: 4` quantity amendment is visible **after the fourth accepted action and
before the fifth action**.

Every event is **one-shot**. Once an event is emitted, its `event_id` is consumed
for the rest of the episode. Repeating an action that matches the same
`after_action` trigger does not emit that event again, and an `at_step` event can
fire only once. Implementations must retain the consumed-event set as part of the
environment state.

## Quote and award scope

Every `quote_received` and `quote_revision` event declares `offer_scope`.
`package` covers every real initial-state line item; `items` lists the exact
initial-state `item_id` values covered. Oracle awards use `package` or
`lot-<item_id>` scope in v0.1, and validation rejects an award whose cited quote
does not cover that scope.

Terminal outcomes now carry an explicit `decision`:

- `award` requires at least one award entry.
- `no_award` requires `awards: []`.

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

## Original five episodes

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

The original five episodes froze the v0.1 data contract. The suite is now designed to expand while preserving the same real/synthetic boundary, deterministic runtime, evaluator semantics, and reference-control sanity checks.
