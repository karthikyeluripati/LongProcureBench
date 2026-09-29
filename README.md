# LongProcureBench

LongProcureBench is a benchmark-in-progress for **long-horizon procurement agents**.
The current electrical-procurement slice is deliberately real-data-centric:

- real public procurement requirements form the starting state;
- private supplier interactions are synthesized and explicitly labeled;
- benchmark oracles define constraints and acceptable outcomes without requiring
  one fixed reasoning trace;
- a deterministic runtime now executes the frozen episode contract without an LLM.

The repository now includes a deterministic evaluator and a first non-oracle reactive LLM baseline; there is still no leaderboard.

## Post-held-out ProcureHarness method track

The frozen LongProcureBench paper evaluation remains unchanged, but a **separate
post-held-out method-development track** is now preregistered. Its goal is to
search a bounded agentic design-pattern space toward a ProcureHarness
quality/economic-efficiency frontier before adding memory, knowledge graphs,
forecasting, dynamic model routing, or self-improvement.

- Episodes 001-020 remain development-exposed.
- Episodes 021-030 remain diagnostic-only for any newly designed method.
- New 031-040 episodes are reserved for architecture-search validation.
- New 041-050 episodes are reserved for the untouched final method test.
- The search ceiling is an operational Pareto plateau (two consecutive rounds
  without a new admissible frontier point), not a claim of global optimality.
- Continuous feasible-price regret and paired procurement savings must be
  implemented uniformly before any paid architecture-search run.
- See [`docs/procureharness-architecture-search-v0.1.md`](docs/procureharness-architecture-search-v0.1.md).

## Current milestones

### Initial-state dataset

- 20 real public electrical procurement starting states back development/calibration episodes 001–020.
- 10 additional real public starting states back frozen held-out episodes 021–030; the preregistered 160-run held-out paper evaluation is complete and durably frozen.
- Multiple source families and electrical subtypes.
- Strict provenance, missingness, and no-outcome-leakage checks.
- See [`docs/initial-state-v0.1-report.md`](docs/initial-state-v0.1-report.md), [`docs/heldout-initial-state-batch-1.md`](docs/heldout-initial-state-batch-1.md), and [`docs/heldout-initial-state-batch-2.md`](docs/heldout-initial-state-batch-2.md).

### Episode Model v0.1

- 30 semi-synthetic long-horizon procurement episodes grounded in 30 distinct real initial states: 20 development/calibration + 10 frozen held-out.
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

### Benchmark Data/Observability Freeze v0.1

- Episodes 001–020 are explicitly frozen as **development/calibration**, because they were used while building the runtime, Evaluator v0.2, and fairness diagnostics.
- The next ~10 distinct real public packages are reserved for a held-out paper evaluation slice.
- `BENCHMARK_SPEC.md` freezes the real-vs-synthetic boundary, temporal visibility rules, leakage rules, and held-out collection gate.
- `OBSERVABILITY_MATRIX.csv` audits every current episode.
- `scripts/validate_benchmark_contract.py` enforces the matrix and split policy in CI.

### Deterministic Runtime v0.1

- `reset(episode)` and `step(action)` execution environment.
- Accepted-action step counting and contract-defined event ordering.
- One-shot event consumption and hidden-event non-leakage.
- Supplier-directory reveal through `identify_suppliers`.
- Single- and multi-award terminal actions plus `no_award`.
- Scripted end-to-end execution tests for all 5 frozen episodes.
- See [`docs/runtime.md`](docs/runtime.md).

### Evaluator v0.2

- Replay-first deterministic scoring; no LLM judge.
- Keeps legacy v0.1 checkpoint/process fields for reproducibility.
- Adds trigger-aware obligation records with `resolved`, `unresolved`, `no_opportunity`, and `not_applicable` states.
- Event obligations are scored only after their trigger is visible; branch-conditional revisions are required only when the selected path genuinely needs repair.
- Withdrawal recovery is outcome-based rather than forcing one fixed "new quote then re-evaluate" sequence.
- Proxy/procedural checkpoints remain visible diagnostics but do not determine obligation success.
- Frozen 60-run Luna rescore: **62/91 actionable obligations resolved (68.1%)**; **50.0% feasible-obligation success** vs the legacy **18.3% process-complete rate**.
- See [`docs/evaluator.md`](docs/evaluator.md) and [`docs/evaluator-v0.2-luna-rescore.md`](docs/evaluator-v0.2-luna-rescore.md).

### Economic Regret v0.1

- Additive deterministic procurement-economics layer; Evaluator v0.2 semantics remain unchanged.
- Computes package and lot-level award costs from the frozen episode quote data.
- Reports feasible native-price regret and normalized regret when the oracle cost is positive.
- Freezes matched Coverage+Repair/ReAct run-key cohorts so failed candidate runs cannot disappear from the economic denominator.
- Handles zero-cost and empty-cohort cases without fabricated percentages or sentinel regret values.
- Computes paired procurement savings by native currency; currencies are never summed together.
- Provides an offline CLI and makes no model/provider calls.
- See [`docs/economic-regret-v0.1.md`](docs/economic-regret-v0.1.md).

### Benchmark Runner v0.1

- Minimal policy interface shared by future agent baselines.
- Runner-owned action IDs and deterministic environment execution.
- Standard result JSON with attempts, accepted trajectory, observations, and evaluator report.
- Oracle-aware scripted reference control for all committed episodes.
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

### Cross-Family Reactive Baseline v0.1

- Frozen provider-diverse development experiment: **3 model families × 20 episodes × 3 repeats = 180 runs**.
- Combined result: **62.8% terminal feasibility** vs **31.7% feasible-obligation success**; **134/241 actionable obligations resolved (55.6%)**.
- The largest unresolved classes are supplier non-response follow-up and visible requirement-gap resolution.
- Durable compact replay evidence is committed under `evidence/cross-family-reactive-v0.1/` and deterministically audited in CI.
- The next architecture experiments are hypothesis-driven: context compilation, explicit operational state/obligation tracking, planning/reasoning, verification, and selective replanning are tested separately before any component enters ProcureHarness.
- See [`docs/cross-family-reactive-v0.1-results.md`](docs/cross-family-reactive-v0.1-results.md) and [`docs/agent-design-hypotheses-v0.1.md`](docs/agent-design-hypotheses-v0.1.md).

### Context-Compiled Reactive Baseline v0.1

- First controlled architecture experiment after the cross-family evidence freeze.
- Keeps the same reactive policy, model-call cadence, action schema, runtime, evaluator, and GPT-5.6 Sol reasoning configuration.
- Changes only the model-facing factual state serialization; no inferred obligations, planner, verifier, or hidden memory.
- Frozen 60-run result vs raw history: **-40.6% total tokens**, **-27.5% known API cost**, **+6.1 pp aggregate obligation resolution**, but **-1.7 pp feasible-obligation success** and **-5.0 pp terminal feasibility**.
- Retained only as an **efficiency/context layer candidate**, not as the long-horizon reliability mechanism.
- See [`docs/context-compiled-reactive-v0.1.md`](docs/context-compiled-reactive-v0.1.md) and [`docs/context-compiled-reactive-v0.1-results.md`](docs/context-compiled-reactive-v0.1-results.md).

### Operational-Ledger Reactive Baseline v0.1

- Controlled test of factual compiled context plus a persistent, model-maintained ledger of open/resolved procurement commitments.
- Frozen selected grid: GPT-5.6 Sol × 20 development episodes × 3 repeats = **60 runs**; a provider-credit interruption was repaired with a key-frozen 43-original + 17-recovery selection.
- Compared with context compilation, terminal feasibility fell **25.0 pp** and feasible-obligation success fell **20.0 pp**, despite strict v0.2 rising **8.3 pp** and aggregate obligation resolution rising **6.3 pp**.
- The treatment used **+295.4% total tokens**, **+132.1% model calls**, and **+371.8% known API cost**; 11 runs hit the 50-action cap.
- The predeclared inclusion gate **failed**. This ledger formulation is dropped; the next causal axis is explicit planning/replanning rather than more memory infrastructure.
- Durable replay evidence is committed under `evidence/operational-ledger-reactive-v0.1/`.
- See [`docs/operational-ledger-reactive-v0.1.md`](docs/operational-ledger-reactive-v0.1.md) and [`docs/operational-ledger-reactive-v0.1-results.md`](docs/operational-ledger-reactive-v0.1-results.md).

### Maintained Working-Plan Reactive Baseline v0.1

- Controlled test of factual compiled context plus one bounded, replaceable prospective plan, still using one GPT-5.6 Sol call per semantic action.
- Frozen development grid: **20 episodes × 3 repeats = 60 completed runs**.
- Compared with context compilation, terminal feasibility fell **8.3 pp** and feasible-obligation success fell **21.7 pp**, while strict v0.2 rose **5.0 pp**.
- The treatment used **+35.1% total tokens**, **+70.3% known API cost**, and **+74.8% aggregate model latency**.
- The plan was active (85.3% first-step action-type agreement with the next accepted action), but the predeclared inclusion gate **failed**.
- This one-call working-plan formulation is dropped. The next causal axis is **additional deliberation/verification**, starting with an always-replan + pre-award-verifier quality comparator.
- Durable replay evidence is committed under `evidence/working-plan-reactive-v0.1/`.
- See [`docs/working-plan-reactive-v0.1.md`](docs/working-plan-reactive-v0.1.md) and [`docs/working-plan-reactive-v0.1-results.md`](docs/working-plan-reactive-v0.1-results.md).

### Always-Replan + Pre-Terminal Verifier v0.1

- Quality-heavy controlled test over factual compiled context: a fresh planner before every action, a separate verifier for proposed terminal decisions, and one repair call after verifier rejection.
- Frozen development grid: **20 episodes × 3 repeats = 60 runs**.
- Compared with context compilation, terminal feasibility fell **53.3 pp**, feasible-obligation success fell **46.7 pp**, and strict v0.2 success fell **15.0 pp**.
- Resource use increased **+1,945.1% total tokens**, **+934.9% model calls**, and **+2,418.8% known API cost**; **32/60** runs hit the 50-action cap.
- The verifier rejected **557/585 (95.2%)** proposed terminal decisions; **545/557** rejections recommended buyer clarification, and accepted clarifications rose from 47 to **1,329**.
- The predeclared gate **failed**. This formulation is dropped, and the conditional selective-replanning efficiency experiment is not run.
- The next causal axis is **actionability/progress**: distinguish actionable uncertainty from missing-at-source uncertainty and prevent repeated no-progress information seeking.
- Durable replay evidence is committed under `evidence/always-replan-verifier-v0.1/`.
- See [`docs/always-replan-verifier-v0.1.md`](docs/always-replan-verifier-v0.1.md) and [`docs/always-replan-verifier-v0.1-results.md`](docs/always-replan-verifier-v0.1-results.md).

### Progress-Aware Reactive v0.1

- Controlled test of factual compiled context plus a visible-evidence no-progress guard.
- Frozen development grid: **20 episodes × 3 repeats = 60 completed runs**.
- Compared with context compilation, terminal feasibility rose **1.7 pp** and strict v0.2 rose **1.7 pp**, but feasible-obligation success fell **16.7 pp** and obligation resolution fell **10.0 pp**.
- Total tokens rose **6.9%**, while known API cost fell **12.5%** and aggregate model latency fell **7.6%**.
- The guard recorded **15 no-progress marks across 13/60 runs but fired 0 interventions**, so the blocking/retry mechanism itself did not establish a reliability benefit.
- The predeclared gate **failed**. Per the frozen protocol, bespoke architecture search stops here; the next phase is recognizable external comparators, beginning with true ReAct, followed by the held-out paper evaluation after the development comparator set is frozen.
- Durable replay evidence is committed under `evidence/progress-aware-reactive-v0.1/`.
- See [`docs/progress-aware-reactive-v0.1.md`](docs/progress-aware-reactive-v0.1.md) and [`docs/progress-aware-reactive-v0.1-results.md`](docs/progress-aware-reactive-v0.1-results.md).

### ReAct External Comparator v0.1

- Recognizable Thought -> Action -> Observation external comparator over the retained factual compiled context.
- Frozen development grid: **20 episodes × 3 repeats = 60 completed runs**.
- Compared with context compilation, terminal feasibility rose **10.0 pp**, feasible-obligation success rose **1.7 pp**, and strict v0.2 success rose **21.7 pp**.
- The quality gain costs materially more inference: **+49.3% total tokens**, **+73.2% known API cost**, and **+46.6% aggregate model latency**.
- The paired episode-cluster bootstrap keeps the strict-success delta positive (**+10.0 to +35.0 pp**) but the feasible-obligation delta spans zero.
- ReAct is frozen as an **external quality/cost comparator**, not promoted into ProcureHarness and not used to reopen bespoke architecture search.
- Durable replay evidence is committed under `evidence/react-comparator-v0.1/`.
- Next: freeze the final development comparator/reporting matrix before any held-out episode authoring or evaluation.
- See [`docs/react-comparator-v0.1.md`](docs/react-comparator-v0.1.md) and [`docs/react-comparator-v0.1-results.md`](docs/react-comparator-v0.1-results.md).

### Development Comparator / Reporting Freeze v0.1

- Development-time method selection is now **closed** before held-out episode authoring/evaluation.
- Held-out-eligible model-backed rows are frozen to: the three raw-reactive model families, GPT-5.6 Sol factual-context compilation, and GPT-5.6 Sol ReAct.
- Failed bespoke mechanisms (operational ledger, working plan, always-replan/verifier, progress-aware) remain development-only failure analysis and are **not** eligible for held-out runs.
- The primary paper quality metric is frozen as **feasible-obligation success**, reported with terminal feasibility, strict v0.2 success, obligation resolution, economic objective, and mandatory efficiency metrics.
- The held-out plan is **10 episodes × 3 repeats** for five model-backed rows = **150 model runs**, plus 10 deterministic reference controls.
- No new method may be added, and no model/prompt/evaluator/agent tuning may use held-out outcomes.
- Next: author and deterministically validate/freeze the 10 held-out episodes; only after that package is frozen do model evaluations begin.
- See [`docs/development-comparator-matrix-v0.1.md`](docs/development-comparator-matrix-v0.1.md).

### Held-out Episode Package v0.1

- Final-test episodes **021–030** are now authored from the 10 pre-reserved real public starting states, one state per episode.
- The package was authored only after the development comparator/reporting freeze merged.
- Every held-out episode has a deterministic Evaluator v0.2 config, observability row, and oracle-aware reference control.
- CI requires all 10 reference controls to pass terminal feasibility, hard constraints, feasible-obligation success, strict v0.2, the economic objective, and **zero unresolved actionable obligations**.
- The package was frozen before any model/API held-out evaluation and remained unchanged through the completed final test.
- The package is merged and the frozen held-out execution below is now complete.
- See [`docs/heldout-episode-package-v0.1.md`](docs/heldout-episode-package-v0.1.md).

### Held-out Paper Evaluation Protocol v0.1

- Execution is frozen to **5 model-backed rows × 10 episodes × 3 repeats = 150 model runs**, plus **10 deterministic reference controls**.
- Model identity, episodes, repeats, max actions, temperature omission, reasoning effort, context strategy, and ReAct pattern are loaded from committed freeze artifacts; the runner exposes no research-setting overrides.
- All 10 reference controls and all provider credentials must pass preflight before any paid model job starts.
- OpenAI raw → context → ReAct rows are serialized; Anthropic and Gemini can run in parallel after the reference gate.
- Every row is independently checked for the exact episode/repeat grid, policy/settings identity, Evaluator v0.2 coverage, complete usage, known cost, and zero infrastructure/model-call failures.
- A final aggregate artifact is produced only after all six rows validate to exactly **160 runs**.
- The live workflow remained manual-only; workflow run `36329287113` completed successfully with the exact frozen matrix.
- See [`docs/heldout-paper-evaluation-v0.1.md`](docs/heldout-paper-evaluation-v0.1.md).

### Held-out Paper Evaluation Results v0.1

- Final held-out evidence: **150 model-backed + 10 reference = 160/160 validated runs**.
- Raw reactive terminal feasibility remains much higher than feasible-obligation success across all three model families, reproducing the long-horizon reliability gap on untouched held-out tasks.
- Matched GPT-5.6 Sol feasible-obligation success: raw **12/30 (40.0%)**, factual context **20/30 (66.7%)**, ReAct **20/30 (66.7%)**.
- ReAct does **not** improve the preregistered primary metric over factual context, but strict v0.2 rises from **6/30 (20.0%)** to **15/30 (50.0%)** while using **+73.9% tokens** and **+98.3% known API cost**.
- Exact source artifact ZIPs, all raw results, full ReAct transcripts, aggregate evidence, deterministic bootstrap outputs, and failure taxonomy are committed under `evidence/heldout-paper-evaluation-v0.1/` and audited in CI.
- Research execution for the frozen plan is complete. Next: manuscript claims, figures/tables, limitations, and final paper assembly—**no new architecture search**.
- See [`docs/heldout-paper-evaluation-v0.1-results.md`](docs/heldout-paper-evaluation-v0.1-results.md).

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
- `longprocurebench/context_compiled_reactive.py` — deterministic factual context compiler and matched reactive policy.
- `longprocurebench/operational_ledger_reactive.py` — model-maintained persistent commitment ledger over compiled context.
- `longprocurebench/working_plan_reactive.py` — bounded replaceable prospective working-plan policy over compiled context.
- `longprocurebench/always_replan_verifier.py` — quality-heavy fresh-planning and pre-terminal-verification policy over compiled context.
- `longprocurebench/progress_aware_reactive.py` — visible-evidence no-progress guard over the factual compiled reactive policy.
- `longprocurebench/react_comparator.py` — explicit Thought -> Action -> Observation external comparator over factual compiled context.
- `longprocurebench/litellm_client.py` — thin LiteLLM model adapter.
- `schema/evaluation.schema.json` — machine evaluation-rule contract.
- `schema/result.schema.json` — standardized run-result contract.
- `data/evaluation/electrical/` — hard-constraint rules for all 30 episodes.
- `schema/initial-state.schema.json` — real procurement starting-state contract.
- `schema/episode.schema.json` — semi-synthetic episode contract.
- `schema/action.schema.json` — semantic agent action contract.
- `data/initial_states/electrical/` — 30 real public starting states: 20 development/calibration + 10 frozen held-out-state reservations.
- `data/episodes/electrical/` — 30 frozen episodes: 20 development/calibration + 10 held-out.
- `data/splits/electrical-v0.3-plan.json` — development/held-out collection plan.
- `BENCHMARK_SPEC.md` — frozen benchmark grounding, visibility, leakage, and split contract.
- `OBSERVABILITY_MATRIX.csv` — episode-level observability audit.
- `docs/fields.md` — initial-state field guide.
- `docs/initial-state-v0.1-report.md` — initial-state coverage and limitations.
- `docs/episode-model.md` — reality boundary, action space, event ontology, and first five episodes.
- `docs/runtime.md` — runtime state, transition order, and terminal semantics.
- `scripts/validate_dataset.py` — initial-state validation.
- `scripts/validate_episodes.py` — episode validation.
- `scripts/test_runtime.py` — deterministic runtime regression/execution tests.
- `scripts/run_reactive_pilot.py` — repeated reactive-model pilot orchestration and aggregation.
- `scripts/run_context_compiled_pilot.py` — repeated context-compiled matched-policy experiment runner.
- `scripts/run_heldout_paper_row.py` — immutable row runner for the frozen 021–030 paper evaluation.
- `scripts/validate_heldout_row_results_v01.py` — exact per-row held-out evidence validator.
- `scripts/aggregate_heldout_matrix_results_v01.py` — six-row/160-run held-out aggregation and revalidation.
- `scripts/validate_heldout_execution_plan_v01.py` — pre-run provenance/settings/workflow freeze validator.
- `scripts/audit_heldout_paper_v01.py` — deterministic 160-run source-artifact, aggregate, bootstrap, taxonomy, and result audit.
- `scripts/run_operational_ledger_pilot.py` — repeated persistent-ledger matched-policy experiment runner.
- `scripts/run_working_plan_pilot.py` — repeated maintained-working-plan matched-policy experiment runner.
- `scripts/rescore_pilot.py` — non-destructive re-evaluation of saved pilot trajectories.
- `scripts/frozen_luna20_source.py` — verifies and reconstructs the durable 60-run Luna evidence source.
- `scripts/rescore_luna20_v02.py` — zero-call Evaluator v0.2 rescore of the frozen 60 Luna trajectories.
- `scripts/frozen_cross_family_reactive_v01.py` — checksum-verified loader for the frozen 180-run cross-family replay source.
- `scripts/audit_cross_family_reactive_v01.py` — deterministic replay/audit of all 180 cross-family trajectories.
- `scripts/frozen_operational_ledger_v01.py` — checksum-verified loader for the selected 60-run operational-ledger evidence.
- `scripts/audit_operational_ledger_v01.py` — deterministic matched replay/audit of the operational-ledger experiment.
- `scripts/frozen_working_plan_v01.py` — checksum-verified loader for the frozen 60-run working-plan evidence.
- `scripts/audit_working_plan_v01.py` — deterministic matched replay/audit of the working-plan experiment.
- `scripts/frozen_always_replan_verifier_v01.py` — checksum-verified loader for the frozen 60-run always-replan/verifier evidence.
- `scripts/audit_always_replan_verifier_v01.py` — deterministic matched replay/audit of the always-replan/verifier experiment.
- `scripts/materialize_always_replan_verifier_evidence_v01.py` — artifact-to-replay evidence materializer with exact provenance checks.
- `scripts/frozen_progress_aware_v01.py` — checksum-verified loader for the frozen 60-run progress-aware evidence.
- `scripts/audit_progress_aware_v01.py` — deterministic matched replay/audit of the progress-aware experiment.
- `scripts/materialize_progress_aware_evidence_v01.py` — artifact-to-replay progress-aware evidence materializer.
- `scripts/verify_progress_aware_source_artifact_v01.py` — independent progress-aware source-artifact provenance verifier.
- `scripts/frozen_react_comparator_v01.py` — checksum-verified loader for frozen ReAct comparator evidence.
- `scripts/audit_react_comparator_v01.py` — deterministic matched replay/bootstrap audit for the ReAct comparator.
- `scripts/materialize_react_comparator_evidence_v01.py` — source-artifact to compact ReAct replay materializer.
- `scripts/verify_react_source_artifact_v01.py` — independent ReAct source-artifact provenance verifier.
- `scripts/validate_development_comparator_matrix_v01.py` — machine-checks the frozen paper metrics, held-out-eligible method set, exact models, and planned run counts.
- `scripts/validate_heldout_episode_package_v01.py` — validates held-out 021–030 mappings and executes all deterministic held-out reference controls before any model run.
- `docs/development-comparator-matrix-v0.1.md` — final development method/reporting freeze before held-out episode authoring.
- `scripts/verify_working_plan_source_artifact_v01.py` — independent artifact-to-replay provenance verifier.
- `docs/cross-family-reactive-v0.1-results.md` — frozen cross-family baseline results and interpretation.
- `docs/operational-ledger-reactive-v0.1-results.md` — frozen operational-ledger matched result and failure analysis.
- `docs/working-plan-reactive-v0.1-results.md` — frozen working-plan matched result, plan diagnostics, and negative decision.
- `docs/always-replan-verifier-v0.1-results.md` — frozen always-replan/verifier matched result, failure mechanism, and negative decision.
- `docs/progress-aware-reactive-v0.1-results.md` — frozen progress-aware matched result, inactive-guard diagnostic, and architecture-search stop decision.
- `docs/react-comparator-v0.1-results.md` — frozen ReAct matched quality/cost result and external-comparator interpretation.
- `docs/agent-design-hypotheses-v0.1.md` — evidence-to-architecture experiment matrix and inclusion gates.

## Validate

```sh
python -m pip install -r requirements.txt
python scripts/validate_dataset.py
python scripts/validate_episodes.py
python scripts/validate_evaluation.py
python scripts/validate_benchmark_contract.py
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
