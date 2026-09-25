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

## Bounded model directory names

The readable portion of the model directory is truncated before the stable hash suffix is appended. The complete directory component is capped at 120 ASCII bytes, well below common 255-byte filesystem component limits, while the hash continues to identify the exact original model string.

## Complete token usage

A call is considered to have complete usage only when both prompt-token and completion-token counts are present. If the provider omits total_tokens, the total is safely derived from those two counts. Any missing prompt/completion count sets usage_available=false and therefore usage_incomplete=true for the run.

## Sampling and reasoning configuration

The provider-neutral baseline preserves the original sampling default: temperature=0.0 and no reasoning-effort parameter. Reasoning effort is opt-in because not every provider/model accepts that parameter.

The OpenAI GPT-5.6 pilot is an explicit exception: its workflow omits temperature and requests reasoning_effort=medium because GPT-5.6 reasoning rejects temperature=0 while reasoning is enabled. Both settings are recorded in policy_metrics so experiment configurations remain comparable and auditable.


## CLI reasoning safety

Both reactive CLIs keep temperature=0.0 as the default when reasoning is not
requested. Supplying --reasoning-effort automatically omits temperature from the
provider request. An explicitly supplied --temperature cannot be combined with
--reasoning-effort, and --temperature cannot be combined with
--omit-temperature. This prevents accidentally sending the invalid GPT-5.6
reasoning-plus-temperature combination.

## Optional live smoke on main

The OpenAI smoke workflow still triggers on relevant main-branch changes, but the
live model step is optional. If OPENAI_API_KEY is absent, it records a skip and
exits successfully after the offline tests. The repository's normal CI therefore
does not require external credentials.
