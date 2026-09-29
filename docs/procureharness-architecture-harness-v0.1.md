# ProcureHarness architecture harness v0.1

This implementation realizes the agent-design grammar preregistered in
`procureharness-architecture-search-v0.1`. It is an implementation/freeze
milestone only: **no model-backed architecture-search run is performed by this
PR**.

## Core architecture

The policy is an event-driven, obligation-centric hierarchical skill graph with
four required core components:

1. **obligation router** — builds candidate obligations from agent-visible
   state and chooses the next skill;
2. **procurement skill graph** — ten domain skills from requirement resolution
   through terminal award/no-award;
3. **event-interrupt control** — newly visible non-response, supplier question,
   requirement change, substitution, and withdrawal events create explicit
   obligations;
4. **deterministic forced transitions** — unambiguous work is executed without a
   model call.

The ten skills are:

- `resolve_requirement_gap`
- `supplier_discovery`
- `rfq_coverage`
- `nonresponse_followup`
- `supplier_question_handling`
- `amendment_handling`
- `quote_revision`
- `withdrawal_recovery`
- `quote_leveling`
- `terminal_decision`

All model prompts receive only `factual_compiled_v0.1` state. No episode
oracle, evaluator label, future event, hidden supplier profile, persistent
cross-episode memory, KG, forecasting tool, model router, or multi-agent state
is available.

## Search axes

The frozen 18-candidate registry spans the five preregistered axes:

- obligation routing: deterministic priority / hybrid LLM tie-break;
- local planning: none / bounded local plan;
- skill reasoning: direct action / bounded mini-ReAct;
- verification: none / deterministic visible invariants / one terminal LLM
  critique;
- fallback: none / bounded ReAct fallback.

Candidates are arranged as **6 per round × 3 rounds**. Round 1 emphasizes
single-axis ablations; rounds 2–3 recombine the same frozen modules. Every
candidate records its conceptual parent candidate(s) and explicit module delta
relative to the first parent, so the search lineage is auditable rather than
name-driven. CI reconstructs each child configuration from that lineage and
rejects missing, cyclic/out-of-order, or inconsistent deltas. This is a bounded
architecture search, not a claim of global optimality.

## Complexity limits

Exactly as preregistered:

- maximum 3 model calls between accepted actions;
- maximum 4 local-plan steps;
- maximum 3 fallback actions per episode;
- no multi-agent execution;
- no persistent cross-episode memory.

Clear obligations such as supplier discovery, RFQ coverage, visible
non-response, supplier questions, amendments, and quote leveling are
deterministic. Model calls are reserved for ambiguous routing/planning,
skill-level reasoning, terminal verification, and bounded recovery.

## Execution gates

`scripts/run_procureharness_search_v01.py` is **plan-only by default**.

Model execution requires an explicit `--execute` flag.

Executable phases are intentionally limited to:

| Phase | Episodes | Repeats | Runs/candidate |
| --- | --- | ---: | ---: |
| screening | 001–020 | 1 | 20 |
| development_confirmation | 001–020 | 3 | 60 |
| validation | 031–040 | 3 | 30 |

**041–050 are not an executable architecture-search phase.** They remain
untouched until a validation winner is frozen under the final-method protocol.

Round-1 screening needs no prior authorization. Round-2/3 screening requires
a frozen prior-round authorization proving that validation for the preceding
round is complete, the two-round plateau stop has not fired, and the search
budget is not exhausted.

Development confirmation requires a frozen round selection containing the
candidate and **at most two candidates total**. Validation likewise requires a
single frozen **at-most-two-candidate** round selection, development-confirmation
completion, the confirmation floor, and the quality/efficiency promotion
branch. The validation selection rule is explicitly bound to the frozen
lexicographic entry rule.

A candidate/phase output tree must be empty before execution. The runner refuses
a second invocation into an existing result tree, preventing accidental paid
reruns from silently exceeding the search budget.

## Candidate registry

The committed source of truth is
`docs/procureharness-candidate-registry-v0.1.json`.

CI checks that:

- exactly 18 candidates exist;
- each round contains exactly 6;
- every protocol choice is represented;
- JSON and code configs match exactly;
- hard complexity limits match the protocol;
- model/settings match the protocol;
- 001–020 and 031–040 exposure sets remain exact;
- 041–050 never appear in executable search phases.

## What comes after merge

After this implementation is hash-frozen, search execution proceeds under the
existing protocol:

1. screen round candidates on 001–020 ×1;
2. select at most two candidates/round for 001–020 ×3 confirmation;
3. promote only candidates meeting a frozen quality/efficiency branch;
4. run promoted candidates on 031–040 ×3;
5. recompute the cumulative admissible Pareto frontier and stop under the
   frozen plateau/budget rule;
6. freeze a winner (or no-winner result) **before any model call on 041–050**.


## Evidence-derived selection gates

Paid phases are authorized from recomputed frozen artifacts, not from trusted
booleans in an authorization JSON.

### Screening → development confirmation

`scripts/select_procureharness_screening_v01.py`:

- requires all six 001-020 x1 screening summaries for the round;
- verifies the exact 20-run grid and clean execution;
- aggregates quality, obligation, token, and cost metrics;
- applies the registry-frozen lexicographic ranking;
- selects at most two candidates;
- binds every source summary by SHA-256;
- writes the selection and per-candidate authorizations atomically after
  preflighting every target path.

The runner revalidates the frozen selection from the bound summaries before a
development-confirmation run can start.

### Development confirmation → 031-040 validation

`scripts/select_procureharness_validation_v01.py`:

- revalidates the screening selection;
- requires each selected candidate's complete 001-020 x3 confirmation summary;
- recomputes the 47/60 feasible, 27/60 strict, and 27/60 economic floor;
- recomputes the frozen quality-promotion branch against Coverage+Repair;
- applies the protocol's validation-entry lexicographic ranking;
- selects at most two candidates and binds all confirmation summaries by hash.

The runner revalidates this artifact before any 031-040 model call. An
authorization cannot manufacture completion, floor passage, promotion, or
selection.

The efficiency-only promotion branch is deliberately fail-closed until a
separately frozen economic-comparison gate supplies the required full-cohort
regret evidence. This does **not** block a peer that already qualifies through
the independent quality branch: quality-qualified candidates receive validation
authorization immediately, while unresolved peers are recorded in
`pending_efficiency_candidate_ids`. This avoids treating an unverified
boolean as economic evidence without withholding an independently justified
promotion.

### Later search rounds

Round-2/3 screening is deliberately fail-closed in harness v0.1 until a frozen
frontier/plateau progression gate recomputes prior-round validation,
nondominance, plateau state, and budget state from bound evidence. Claimed
`prior_round_validation_complete`, `plateau_stop_fired`, or
`search_budget_exhausted` fields cannot unlock paid runs.


### Gate-write concurrency

Screening and validation selectors acquire an exclusive per-round lock in the
gate output directory before recomputing or writing any frozen artifact.
Concurrent selector invocations for the same round therefore fail before they
can pass independent existence checks. After acquiring the lock, each selector
preflights all final paths, stages every artifact, and only then finalizes the
selection and authorizations. A pre-existing target leaves no partial selection
behind.
