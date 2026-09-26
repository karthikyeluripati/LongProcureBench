# Cross-family reactive baseline v0.1

This milestone tests whether the long-horizon obligation failures observed in the
OpenAI diagnostic generalize across model providers before stronger agent
architectures are introduced.

## Frozen development suite

Only episodes 001-020 are eligible. The ten reserved held-out starting states are
not used.

## Models

The initial provider-diverse set is:

- `openai/gpt-5.6-sol` — reasoning effort explicitly set to medium;
- `anthropic/claude-opus-5-5` — provider default adaptive thinking (medium);
- `gemini/gemini-3.8-flash` — provider default thinking level (medium).

The benchmark does not treat this as a model ranking. The purpose is to test
whether the reactive architecture exhibits the same stateful-obligation failure
pattern across providers.

## Architecture

All models use the existing `ReactiveLLMPolicy` and `BenchmarkRunner`.
There is no planner, reflection loop, hidden memory, episode-specific heuristic,
or oracle access. LiteLLM remains the only provider adapter.

## Primary metrics

Evaluator v0.2 metrics are primary:

- terminal feasibility;
- feasible-obligation success;
- strict v0.2 success;
- actionable/resolved/unresolved obligations;
- obligation-resolution rate and unresolved-obligation type.

Legacy process/checkpoint metrics are retained only for diagnostics and
historical comparability.

Efficiency metrics remain model calls, accepted actions, tokens, latency, and
known USD cost.

## Cost gate

Before the full 3 models x 20 episodes x 3 repeats = 180-run experiment, run one
development episode once per provider. Use that smoke to confirm credentials,
structured-output compatibility, and estimate full-run cost. Do not launch the
180-run matrix until the projected spend is reviewed.
