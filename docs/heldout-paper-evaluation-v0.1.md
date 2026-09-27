# Held-out paper evaluation v0.1 — execution protocol

This protocol executes the **already-frozen** LongProcureBench held-out paper
slice. It does not select a method, alter an episode, tune a prompt, or change
Evaluator v0.2.

The held-out package was merged at
`4d58ddc8021c6298cf9f345cbbb3adb059067219`. The development comparator
matrix was merged before that at
`0a9378f005d9c66a5d991b1af77d865a4fe2f75b`.

No model-backed held-out run is triggered by this PR.

## Frozen execution matrix

| Row | Model | Episodes | Repeats | Runs |
| --- | --- | ---: | ---: | ---: |
| Reference control | none | 021–030 | 1 | 10 |
| Raw reactive OpenAI | `openai/gpt-5.6-sol` | 021–030 | 3 | 30 |
| Raw reactive Anthropic | `anthropic/claude-opus-5-5` | 021–030 | 3 | 30 |
| Raw reactive Gemini | `gemini/gemini-3.8-flash` | 021–030 | 3 | 30 |
| Context-compiled OpenAI | `openai/gpt-5.6-sol` | 021–030 | 3 | 30 |
| ReAct OpenAI | `openai/gpt-5.6-sol` | 021–030 | 3 | 30 |

Total: **150 model-backed runs + 10 deterministic reference runs = 160**.

The exact sampling/context settings are loaded from
`evidence/development-comparator-matrix-v0.1/matrix.json`. The row runner does
not expose CLI switches for model, episode set, repeats, max actions,
temperature, reasoning effort, policy kind, context strategy, or agent pattern.

## Execution order

The manual workflow
`.github/workflows/heldout-paper-evaluation-v0.1.yml` performs:

1. offline freeze validation and provider-credential presence checks;
2. all 10 deterministic held-out reference controls;
3. raw OpenAI, Anthropic, and Gemini rows;
4. context-compiled OpenAI after raw OpenAI;
5. ReAct OpenAI after context-compiled OpenAI;
6. full six-row revalidation and aggregation.

The three OpenAI rows are intentionally serialized to reduce provider
rate-limit pressure without changing the scientific protocol.

## Evidence gates

Each model-backed row must contain exactly 30 episode/repeat cells and the
reference row exactly 10. Row validation rejects:

- missing/duplicate/extra episode-repeat cells;
- model or policy-kind drift;
- temperature/reasoning/context/ReAct-pattern drift;
- infrastructure/evaluator failures;
- incomplete provider usage;
- unknown API cost;
- failed model calls.

The aggregate artifact is created only after all six row artifacts independently
pass their contracts. It must contain exactly **160** rows.

Agent mistakes that are valid benchmark outcomes remain measurements; they are
not converted into infrastructure failures and are not retried for performance.

## No tuning rule

After the first model-backed held-out call, no held-out outcome may change:

- model or provider;
- prompt or reasoning configuration;
- action contract;
- context compiler or ReAct mechanism;
- benchmark episode/event content;
- evaluator semantics;
- reporting metrics/tables;
- held-out inclusion/exclusion.

A provider outage or execution failure may be documented and the failed job
re-run with the **same frozen settings**; it may not be replaced with another
model or configuration.

## After the workflow

The next artifact is a durable held-out evidence freeze containing the exact raw
results, source workflow/artifact provenance, the frozen paper tables, and
paired episode-cluster comparisons specified before held-out evaluation.

No additional architecture experiment follows this held-out run.
