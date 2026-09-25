# Checkpoint fairness audit

This audit checks whether required-checkpoint failures in saved trajectories
represent obligations that were both agent-visible and actionable.

It does not change benchmark scores.

## Categories

- event obligation: applicable only after a corresponding visible event;
- starting-state obligation: visible from the initial procurement state;
- branch-conditional: required only when the selected solution path depends on
  that branch;
- proxy: evaluator proxy rather than a direct agent action;
- procedural: benchmark process-policy action such as explicit quote evaluation.

The audit separately flags a checkpoint that fires on the terminal action itself,
because the agent has no subsequent action opportunity to satisfy it.

The first audit is pinned to the immutable 60-run Luna diagnostic from workflow
run 36173979424.
