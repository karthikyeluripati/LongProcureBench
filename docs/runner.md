# Benchmark Runner v0.1

Runner v0.1 is the thin execution contract between any future agent policy and the existing LongProcureBench runtime/evaluator.

It is intentionally not an agent framework.

## Policy interface

A policy exposes `policy_id`, `policy_kind`, `reset(state)`, and `act(state)`.
The `act` method returns only semantic fields: `type`, `supplier_id`, and `arguments`.
The runner owns `episode_id`, sequential `action_id`, environment execution, and evaluation.

## Execution

`BenchmarkRunner.run(policy, episode_id)` resets a fresh environment, repeatedly asks the policy for one action, records accepted transitions, stops on terminal state/error/max-actions, runs Evaluator v0.1, and returns one schema-versioned result.

## Standard result

Results contain benchmark/runner version, run and episode IDs, policy metadata, run status, all policy attempts, accepted trajectory with observations, deterministic evaluator report, and top-level error metadata when applicable.
The result contract lives at `schema/result.schema.json`.
Generated artifacts belong under `results/` and are gitignored.

## Reference control

`ScriptedReferencePolicy` is labeled `policy_kind = "reference_control"`.
It uses frozen oracle-aware scripts only to verify integration across runner, runtime, and evaluator.
It is not a competitive baseline and must not be reported as model performance.

Run it locally with `python scripts/run_reference.py`.

## External frameworks

No external orchestration or observability framework is needed at this layer. The runner standardizes only policy calls, deterministic environment steps, and evaluation. Framework selection should happen when the first real model agent introduces model calls, retries, state management, token/cost accounting, or trace-analysis requirements.

## Failure statuses

Runner v0.1 distinguishes where a failure originated:

- `setup_error` — episode/runtime/evaluator setup failed before policy execution;
- `policy_error` — policy code failed or returned an invalid/illegal action;
- `environment_error` — unexpected runtime failure not attributable to the policy action;
- `evaluation_error` — execution record exists but deterministic evaluation could not be produced;
- `max_actions` — the run hit the configured accepted-action budget.

When setup or evaluation fails, `evaluation` is `null`; the standardized run
record and error metadata are still returned so batch execution never loses the
failure record.
