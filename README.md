# LongProcureBench

Milestone 1: three real, public **electrical procurement initial-state examples**.
Only a data contract, examples, documentation, and data validator are implemented.
Agent, simulator, event generation, and evaluation harness are outside this milestone.

## Contents

- `schema/initial-state.schema.json`: strict JSON Schema (Draft 2020-12).
- `data/initial_states/electrical/`: exactly three packages, seven goods lines.
- [Field guide](docs/fields.md): every field, purpose, and required/optional value.
- [Source review](docs/source-review.md): availability, evidence, and schema issues.
- `scripts/validate_dataset.py`: schema, references, missingness, IDs, and cost checks.

## Examples

| Package | Scope | Primary source |
|---|---|---|
| High Point 8017-112221 | 5 estimated 300 kVA transformers | [Original ITB](https://www.highpointnc.gov/DocumentCenter/View/18243/ITB-8017-112221-XFMR-Transformer-832?bidId=) |
| High Point 20-042022 | 5 cable lines; 120,000 estimated FT total | [Original ITB](https://www.highpointnc.gov/DocumentCenter/View/19135/ITB-20-042022-Cable?bidId=) |
| BFAR5BAC-2024-007 | 2 diesel generator sets, 5 kVA each | [PhilGEPS notice](https://notices.philgeps.gov.ph/GEPSNONPILOT/Tender/PrintableBidNoticeAbstractUI.aspx?refid=10485194) |

## Validate

Python 3.10+, from the repository root:

```sh
python -m pip install -r requirements.txt
python scripts/validate_dataset.py
python -m unittest discover -s scripts -p "test_*.py"
```

Validation is offline. It checks structure and internal consistency, not source truth.

## Development and CI

Use TDD for behavioral fixes: add a regression test, run it to demonstrate the
failure, implement the correction, then rerun tests and dataset validation.
See [AGENTS.md](AGENTS.md) for the repository workflow.

GitHub Actions runs `Dataset checks` on pushes and pull requests, using fresh
dependency installs on Python 3.10 and 3.12. It checks dependency compatibility,
regression tests, and all three dataset records. URI syntax validation has an
explicit dependency; source reachability is not checked by the offline suite.
These checks do not deploy anything. Making them mandatory for merging requires
repository branch protection or rulesets; the workflow alone does not enforce that.

## Initial-state policy

These are **reconstructions from buyer-authored solicitation requirements**, not
observed internal pre-RFQ records. The source issue date marks the requirement
baseline. Bid deadlines remain separate from delivery deadlines. Blank prices,
offered manufacturer/model, and supplier-proposed lead times stay `null`.
No bidder responses, negotiated terms, awards, or subsequent amendments are used.

The PhilGEPS page is a live notice with later status metadata. Only its buyer RFQ
requirements are extracted. Its first publication revision was not independently
archived, so historical immutability cannot be established. Do not pass the entire
live page to a future agent as initial-state input.

All requested goods rows are included, but technical and contractual text is
summarized selectively with page/section references. The original source remains
necessary for a complete specification. Each record catalogs retrieval date and
SHA-256 of retrieved bytes; hashes detect changes but do not make mutable URLs
reproducible archives. Raw sources are not redistributed, and public availability
is not a license grant.

Unknown values use `null`, never fabricated defaults or zero. Known gaps and
conflicts live in `missing_information`. Curator metadata (IDs, extraction notes,
hashes, boundaries) is distinguished from source-backed procurement facts.


## Current milestone

Initial State v0.1 candidate contains 20 real public electrical procurement starting states across multiple source families and equipment subtypes. See `docs/initial-state-v0.1-report.md`.
