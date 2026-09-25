# LongProcureBench

LongProcureBench is a benchmark-in-progress for **long-horizon procurement agents**.
The current electrical-procurement slice is deliberately real-data-centric:

- real public procurement requirements form the starting state;
- private supplier interactions are synthesized and explicitly labeled;
- benchmark oracles define constraints and acceptable outcomes without requiring
  one fixed reasoning trace.

There is still no executable simulator, agent baseline, scoring implementation,
or leaderboard.

## Current milestones

### Initial State v0.1

- 20 real public electrical procurement starting states.
- Multiple source families and electrical subtypes.
- Strict provenance, missingness, and no-outcome-leakage checks.
- See [`docs/initial-state-v0.1-report.md`](docs/initial-state-v0.1-report.md).

### Episode Model v0.1

- 5 semi-synthetic long-horizon procurement episodes grounded in 5 distinct real initial states.
- Shared action contract and event ontology.
- Coverage includes non-response, clarification, quote revision, substitutions,
  requirement/quantity changes, lead-time conflicts, supplier eligibility,
  supplier withdrawal, multi-lot evaluation, and budget conflicts.
- See [`docs/episode-model.md`](docs/episode-model.md).

## Repository map

- `schema/initial-state.schema.json` — real procurement starting-state contract.
- `schema/episode.schema.json` — semi-synthetic episode contract.
- `schema/action.schema.json` — semantic agent action contract.
- `data/initial_states/electrical/` — 20 real public starting states.
- `data/episodes/electrical/` — first 5 benchmark episodes.
- `docs/fields.md` — initial-state field guide.
- `docs/initial-state-v0.1-report.md` — initial-state coverage and limitations.
- `docs/episode-model.md` — reality boundary, action space, event ontology, and first five episodes.
- `scripts/validate_dataset.py` — initial-state validation.
- `scripts/validate_episodes.py` — episode validation.

## Validate

```sh
python -m pip install -r requirements.txt
python scripts/validate_dataset.py
python scripts/validate_episodes.py
python -m unittest discover -s scripts -p "test_*.py" -v
```

Validation is offline. It checks structure and internal consistency, not whether
a live public source has changed since collection.

## Reality boundary

Initial states are **reconstructions from buyer-authored public procurement
requirements**, not observed private ERP snapshots. Unknown values remain `null`.
Bidder responses, negotiations, awards, and later outcomes do not leak into the
starting state.

Episode suppliers, messages, quote values, and event timing are **synthetic**.
They exist to create controlled long-horizon tasks over the real procurement
requirements. Synthetic vendor names are intentionally non-real and must never be
presented as historical actors.

> Preserve reality where it is observable; synthesize only the private
> interaction layer or controlled interventions required for evaluation.

## Development and CI

Use TDD for behavioral fixes. GitHub Actions runs regression tests plus both
initial-state and episode validators on Python 3.10 and 3.12. See
[`AGENTS.md`](AGENTS.md) for repository workflow and review rules.
