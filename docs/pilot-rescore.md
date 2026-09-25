# Pilot trajectory re-scoring

The re-scoring tool audits previously saved benchmark runs under the **current**
LongProcureBench evaluator without making any new model/API calls.

## Source of truth

The raw run JSON remains immutable evidence. Re-scoring reads only the accepted
actions from each saved trajectory and replays those actions through the current
deterministic evaluator.

It does not regenerate model decisions, edit the original raw files, or infer
missing actions.

## Command

```sh
python scripts/rescore_pilot.py \
  --input-dir <raw-pilot-directory> \
  --output-dir <new-audit-directory>
```

The output directory must be empty/new.

## Outputs

- `rescored/**/run-XXX.json` — copies of each saved result with the evaluation
  block recomputed under the current evaluator;
- `runs.csv` — flattened audited metrics;
- `summary.json` — per-model aggregate metrics;
- `failure-taxonomy.json` — cross-run counts separating:
  - terminal infeasibility,
  - feasible but process-incomplete trajectories,
  - feasible/process-complete but economically suboptimal trajectories,
  - strict successes.

The original policy/model metrics are preserved exactly from the raw runs.

## Interpretation

Re-scoring is appropriate when evaluator/oracle semantics change but the executed
agent trajectories remain valid evidence. If runtime transition semantics or
agent-visible observations change, the old trajectories must be audited more
carefully before reuse.

## Artifact acceptance

Automatic artifact selection accepts a raw pilot artifact only when both conditions hold:

1. the corresponding producer workflow attempt concluded `success`; and
2. the artifact contains the expected number of raw `run-*.json` files.

This prevents an artifact uploaded by a failed/cancelled producer attempt from being treated as valid merely because it contains all expected filenames. When no attempt is explicitly requested, the workflow searches newest-to-oldest and selects the newest artifact satisfying both conditions.
