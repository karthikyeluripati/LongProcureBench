# LongProcureBench

LongProcureBench is a benchmark-in-progress for **long-horizon procurement agents**.
The current electrical-procurement slice is deliberately real-data-centric:

- real public procurement requirements form the starting state;
- private supplier interactions are synthesized and explicitly labeled;
- benchmark oracles define constraints and acceptable outcomes without requiring
  one fixed reasoning trace;
- a deterministic runtime now executes the frozen episode contract without an LLM.

The repository now includes a deterministic evaluator and a first non-oracle reactive LLM baseline; there is still no leaderboard.

## Current milestones

### Initial State v0.1

- 20 real public electrical procurement starting states.
- Multiple source families and electrical subtypes.
- Strict provenance, missingness, and no-outcome-leakage checks.
- See [`docs/initial-state-v0.1-report.md`](docs/initial-state-v0.1-report.md).

### Episode Model v0.1

- 20 semi-synthetic long-horizon procurement episodes grounded in 20 distinct real initial states.
- Shared action contract and event ontology.
- Coverage includes non-response, clarification, quote revision, substitutions,
  requirement/quantity changes, lead-time conflicts, supplier eligibility,
  supplier withdrawal, multi-lot evaluation, and budget conflicts.
- See [`docs/episode-model.md`](docs/episode-model.md).

### Episode Suite v0.2

- Expands the original 5 episodes to 20 using all 20 currently collected real public starting states.
- New coverage: service-scope follow-up, source ambiguity clarification, supplier-withdrawal recovery, alternate-policy clarification, and split multi-line awards.
- Every episode has deterministic machine checks and an oracle-aware reference control.
- Batch 2 adds compound multi-obligation episodes; all 20 currently collected starting states are now used exactly once.
- See [`docs/episode-suite-v0.2.md`](docs/episode-suite-v0.2.md).

### Deterministic Runtime v0.1

- `reset(episode)` and `step(action)` execution environment.
- Accepted-action step counting and contract-defined event ordering.
- One-shot event consumption and hidden-event non-leakage.
- Supplier-directory reveal through `identify_suppliers`.
- Single- and multi-award terminal actions plus `no_award`.
- Scripted end-to-end execution tests for all 5 frozen episodes.
- See [`docs/runtime.md`](docs/runtime.md).

### Evaluator v0.1

- Replay-first deterministic scoring; no LLM judge.
- Exact terminal-outcome matching.
- Machine-checkable hard constraints for all 5 frozen episodes.
- Required checkpoint completion with direct/proxy evidence labels.
- Constraint violations and accepted action count.
- See [`docs/evaluator.md`](docs/evaluator.md).

### Benchmark Runner v0.1

- Minimal policy interface shared by future agent baselines.
- Runner-owned action IDs and deterministic environment execution.
- Standard result JSON with attempts, accepted trajectory, observations, and evaluator report.
- Oracle-aware scripted reference control for all 5 episodes.
- The reference control is a sanity check, not a competitive baseline.
- See [`docs/runner.md`](docs/runner.md).

### Reactive LLM Baseline v0.1

- First non-oracle model baseline.
- One fresh structured model call per environment step.
- Agent-visible state only; no oracle access or episode-specific logic.
- No planner, reflection, hidden conversation memory, or retry loop.
- LiteLLM used only as the provider-neutral model adapter.
- Token, latency, model-call, and estimated cost metrics captured in results.
- See [`docs/reactive-llm-baseline.md`](docs/reactive-llm-baseline.md).

### Reactive Baseline Pilot v0.1

- Repeated multi-model experiment harness for the reactive baseline.
- Intended matrix: 3 models × 5 pilot episodes × 3 repeats = 45 runs.
- Preserves every raw replicate and emits summary.json plus runs.csv.
- Aggregates failure modes without introducing a weighted score or ranking.
- See [`docs/reactive-pilot.md`](docs/reactive-pilot.md).

### Checkpoint fairness audit v0.1

- Audits whether required-checkpoint failures were actually agent-visible and actionable.
- On the 60-run Luna diagnostic, 50 current failures were non-applicable, 2 had no post-trigger action opportunity, and 19 came from proxy checkpoints.
- The current `feasible_process_success` metric is therefore not frozen as the paper's primary obligation metric yet.
- See [`docs/checkpoint-fairness-v0.1-results.md`](docs/checkpoint-fairness-v0.1-results.md).

### Pilot v0.1 audited evidence

- First frozen 45-run audited reactive-agent pilot.
- 73.3% terminal feasibility vs 28.9% strict process-complete success.
- Dominant failures are long-horizon follow-up, amendment, compliance, and recovery obligations.
- See [`docs/pilot-v0.1-audit.md`](docs/pilot-v0.1-audit.md).

### Pilot Rescore v0.1

- Re-evaluates saved raw trajectories under the current deterministic evaluator.
- Makes zero model/API calls.
- Preserves original raw evidence and writes separate audited results.
- Produces audited `runs.csv`, `summary.json`, and `failure-taxonomy.json`.
- See [`docs/pilot-rescore.md`](docs/pilot-rescore.md).

## Repository map

- `longprocurebench/runtime.py` — deterministic benchmark environment.
- `longprocurebench/evaluator.py` — deterministic trajectory evaluator.
- `longprocurebench/runner.py` — standard policy execution and result generation.
- `longprocurebench/reference.py` — oracle-aware reference control.
- `longprocurebench/reactive_llm.py` — naive reactive model baseline.
- `longprocurebench/litellm_client.py` — thin LiteLLM model adapter.
- `schema/evaluation.schema.json` — machine evaluation-rule contract.
- `schema/result.schema.json` — standardized run-result contract.
- `data/evaluation/electrical/` — hard-constraint rules for all 5 episodes.
- `schema/initial-state.schema.json` — real procurement starting-state contract.
- `schema/episode.schema.json` — semi-synthetic episode contract.
- `schema/action.schema.json` — semantic agent action contract.
- `data/initial_states/electrical/` — 20 real public starting states.
- `data/episodes/electrical/` — 20 frozen benchmark episodes in the current v0.2 suite.
- `docs/fields.md` — initial-state field guide.
- `docs/initial-state-v0.1-report.md` — initial-state coverage and limitations.
- `docs/episode-model.md` — reality boundary, action space, event ontology, and first five episodes.
- `docs/runtime.md` — runtime state, transition order, and terminal semantics.
- `scripts/validate_dataset.py` — initial-state validation.
- `scripts/validate_episodes.py` — episode validation.
- `scripts/test_runtime.py` — deterministic runtime regression/execution tests.
- `scripts/run_reactive_pilot.py` — repeated reactive-model pilot orchestration and aggregation.
- `scripts/rescore_pilot.py` — non-destructive re-evaluation of saved pilot trajectories.

## Validate

```sh
python -m pip install -r requirements.txt
python scripts/validate_dataset.py
python scripts/validate_episodes.py
python scripts/validate_evaluation.py
python scripts/run_reference.py
python -m unittest discover -s scripts -p "test_*.py" -v
```

Validation is offline. It checks structure and internal consistency, not whether
a live public source has changed since collection.

## Reality boundary

Initial states are **reconstructions from buyer-authored public procurement
requirements**, not observed private ERP snapshots. Unknown values remain `null`.
Bidder responses, negotiations, awards, and later outcomes do not leak into the
starting state.

Episode suppliers, messages, quote values, and event timing are **synthetic**.
They exist to create controlled long-horizon tasks over the real procurement
requirements. Synthetic vendor names are intentionally non-real and must never be
presented as historical actors.

> Preserve reality where it is observable; synthesize only the private
> interaction layer or controlled interventions required for evaluation.

## Development and CI

Use TDD for behavioral fixes. GitHub Actions runs the full unit/runtime regression suite plus both data validators on Python 3.10 and 3.12. See [`AGENTS.md`](AGENTS.md) for
repository workflow and review rules.
