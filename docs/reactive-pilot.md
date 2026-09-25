# Reactive Baseline Pilot v0.1

This harness runs the existing non-oracle ReactiveLLMPolicy repeatedly without changing agent behavior.

## Frozen pilot matrix

- 3 provider-diverse model IDs
- 5 frozen pilot episodes
- 3 repeats per model/episode
- 45 total episode runs

The harness accepts model IDs explicitly rather than hard-coding providers so the exact evaluated models remain part of the experiment command and raw results.

## Why repeats

Repeated runs expose serving/model nondeterminism and prevent one lucky or unlucky trajectory from being treated as stable baseline performance.

## Raw evidence layout

Each replicate is preserved separately under:

results/reactive-pilot-v0.1/<model-slug>/<episode-id>/run-001.json
results/reactive-pilot-v0.1/<model-slug>/<episode-id>/run-002.json
results/reactive-pilot-v0.1/<model-slug>/<episode-id>/run-003.json

The per-run JSON remains the source of truth.

## Aggregate outputs

The harness also writes:

- summary.json — per-model success, terminal correctness, status counts, constraint/checkpoint failure counts, mean actions/tokens/latency, total known cost, and incomplete-usage count.
- runs.csv — one flattened row per replicate for analysis.

No model ranking or weighted score is introduced.

## Run

Example:

python scripts/run_reactive_pilot.py --model provider-a/model-a --model provider-b/model-b --model provider-c/model-c --repeats 3

Provider credentials must already be available through the normal LiteLLM/provider environment variables. The benchmark never stores provider secrets.

## Interpretation

This five-episode experiment is a pilot for benchmark validation and failure taxonomy. It is not enough for paper-level claims about model rankings or the superiority of an agent architecture.
