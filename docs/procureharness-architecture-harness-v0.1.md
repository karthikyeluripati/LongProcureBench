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
