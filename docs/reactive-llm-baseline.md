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
