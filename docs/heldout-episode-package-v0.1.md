# Held-out episode package v0.1

This package is the **frozen final-test task set** for the LongProcureBench paper.
It was authored only after the development comparator/reporting freeze was
merged at `0a9378f005d9c66a5d991b1af77d865a4fe2f75b`.

No model/API evaluation is included in this package.

## Frozen mapping

| ID | Real public starting state | Controlled long-horizon mechanisms |
| --- | --- | --- |
| 021 Columbus switchgear | `us-columbus-rfq029445` | requirement gap, qualification, non-response |
| 022 EWEB transformer | `us-eweb-rfp-25-030-g` | requirement gap, compliance correction, revision |
| 023 Lompoc transformer | `us-lompoc-rfq-3099` | severe requirement gap, withdrawal recovery |
| 024 NJANG generator | `us-njang-w50s8f26qa022` | generator + maintenance scope, set-aside eligibility |
| 025 Port Angeles transformers | `us-port-angeles-mec-2025-18` | six-item coverage, Buy American, schedule |
| 026 Greenport transformers | `us-greenport-transformers-2025` | qualification, test compliance, supplier question/revision |
| 027 San Bruno EV chargers | `us-san-bruno-ev-chargers-51035` | quantity, contractor qualification, non-response |
| 028 Shelter Island solar/BESS | `us-shelter-island-solar-bess-2026` | required PV + optional BESS, supplier clarification |
| 029 Philadelphia switchgear/MCC | `us-philadelphia-b2627071` | prequalification, mid-cycle amendment, stale quotes |
| 030 Detroit generator/ATS | `us-detroit-or-s-q10041-00016402` | two-part scope, withdrawal, partial-offer recovery |

The real/public layer remains the initial procurement requirement. Supplier
identities, supplier states, messages, quote values, and event timing are
synthetic controlled interventions and are explicitly labeled as such.

## Freeze gates

Before any model-backed held-out run:

1. all 10 episode JSON files must pass the frozen episode schema and semantic
   validator;
2. all 10 evaluator configs must pass one-to-one constraint coverage;
3. the benchmark split/observability contract must map suffixes 021–030
   one-to-one to the 10 pre-reserved starting states;
4. every deterministic reference path must complete and pass:
   terminal feasibility, all hard constraints, feasible-obligation success,
   strict Evaluator v0.2 success, economic objective, and **zero unresolved
   actionable obligations**;
5. the final development comparator matrix remains unchanged.

The validator is:

`python scripts/validate_heldout_episode_package_v01.py`

## Contamination rule

No held-out trajectory or score may be used to modify a prompt, policy,
context compiler, ReAct transcript design, model setting, action contract,
evaluator semantics, or episode content after model evaluation begins.

If an **offline structural/runtime defect** is discovered before any model call,
it may be repaired in this package with a regression test and documented before
the package is merged. Once the first model-backed held-out run begins, the
episode/evaluator package is immutable for the paper slice.

## Next step after merge

Run exactly the held-out matrix frozen in
`evidence/development-comparator-matrix-v0.1/matrix.json`:

- 5 model-backed rows × 10 episodes × 3 repeats = **150 model runs**;
- 10 deterministic reference controls as non-competitive sanity checks.

No dropped bespoke development mechanism is run on held-out.
