# Reactive LLM Baseline v0.1

This is the first non-oracle model baseline for LongProcureBench.

## Definition

At each step, the policy receives only the current agent-visible runtime state, sends one system message plus that state to the model, receives one structured semantic action, and hands it unchanged to the existing BenchmarkRunner.

There is no planner, hidden scratch memory, reflection loop, retry loop, episode-specific heuristic, or oracle access.

## Model access

LiteLLM is used only as a thin provider-neutral model adapter. LongProcureBench still owns state, action validation, execution, result capture, and evaluation.
The dependency is pinned in `requirements.txt`.

## Metrics

The policy reports model identifier, model-call count, prompt/completion/total tokens, summed model-call latency, estimated USD cost when available, and per-call records. The runner stores these under `policy_metrics`.

## Run

Provider credentials use the normal LiteLLM/provider environment variables.

`python scripts/run_reactive_llm.py --model <provider/model>`

Use `--episode <episode-id>` to run a subset. Results default to `results/reactive-llm-v0.1/`.

## CI

CI does not call an external model. Tests inject a deterministic fake model client to validate prompting, statelessness, structured decisions, usage aggregation, and runner integration.


## Result isolation and command status

The CLI writes under a model-specific subdirectory derived from the model name, so running multiple models with the same root output directory does not overwrite earlier results.

A completed benchmark measurement may legitimately have `episode_success=false`; that does not make the command fail. The CLI exits nonzero only for execution-layer statuses such as policy/setup/environment/evaluation errors, not for the model's benchmark score.

## Failed calls

Attempted model calls are counted even when the provider request or structured-response parsing fails. When usage/cost information is unavailable, the call remains in the metrics with `usage_available=false` rather than disappearing from the run record.


## Collision-resistant result directories

Model directories combine a readable sanitized model name with a stable SHA-256
prefix derived from the exact model identifier. Distinct identifiers therefore do
not overwrite each other even when their sanitized names are identical.

## Usage completeness

Token totals are considered complete only when the provider response actually
contains token-usage fields. A normal response without usage metadata is recorded
with `usage_available=false`, causing aggregate `usage_incomplete=true`.
