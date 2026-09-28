# Economic Regret v0.1

This is the deterministic procurement-economics layer required by the
ProcureHarness architecture-search protocol. It is **additive** to Evaluator
v0.2: benchmark success, obligations, hard constraints, and existing frozen
evidence are not rescored or rewritten.

## Per-run eligibility

A run is price-regret eligible only when:

- Evaluator v0.2 has a valid report;
- the terminal outcome matches an acceptable feasible outcome;
- all machine hard constraints pass;
- the economic objective is `minimize_total_price`;
- the matched terminal outcome is an award rather than no-award;
- every awarded scope resolves to a numeric price in one native currency.

Infeasible/no-award runs remain visible in reliability metrics and report
economic regret as not eligible. They are never assigned an arbitrary monetary
penalty.

## Scope-aware award cost

Pricing matches the existing episode-validation semantics.

- package award → referenced quote `details.total_price`;
- `lot-<item_id>` award → referenced quote
  `details.lots[item_id].price`.

The referenced quote must match the awarded supplier and cover the award scope.
A multi-lot outcome sums exactly one price for each award. All price/cost/regret
inputs must be finite numeric values: `NaN`, `+Infinity`, and `-Infinity`
are rejected before any calculation. Economics JSON is serialized with
`allow_nan=False`, so non-standard JSON cannot be emitted.

The oracle cost is the minimum summed award cost among the episode's frozen
`preferred_outcome_ids`.

## Regret

For an eligible award:

```
native_regret = max(0, selected_cost - oracle_cost)
regret_pct = 100 * native_regret / oracle_cost
```

If `oracle_cost == 0`, native regret is retained but normalized regret is
`not_normalizable_zero_oracle`; no percentage is fabricated. Percentage
arithmetic divides before multiplying by 100 to avoid intermediate overflow
when the mathematically correct percentage is still representable; any truly
non-finite ratio/percentage is rejected before JSON serialization.

## Matched reference cohort

Coverage+Repair and ReAct economics reports must have the **same run-key grid**.
The frozen cohort artifact also stores SHA-256 bindings over the exact canonical
Coverage+Repair and ReAct economics-report sets used to derive it. Replacing
baseline runs while keeping the same cohort keys therefore changes the binding
and is rejected during candidate comparison.

The normalized-regret reference cohort is frozen to run keys
`(episode_id, repeat)` where:

1. both baselines are regret eligible; and
2. the episode oracle cost is strictly positive.

A candidate must be eligible/normalizable on every key in that frozen cohort
before regret may influence Pareto dominance, promotion, winner selection, or
final claims.

This prevents an unreliable candidate from appearing economically better merely
because its failed runs disappear from its regret denominator.

## Empty cohort

If the matched positive-oracle-cost cohort is empty:

- normalized regret is `unavailable_empty_reference_cohort`;
- no numeric zero/infinity/sentinel is imputed;
- regret is omitted uniformly from that package's Pareto vector;
- the development efficiency branch cannot use regret;
- validation winner ordering skips the regret priority for every candidate;
- a final paper-level "better design pattern" claim cannot pass without final
  regret evidence.

## Paired savings

For each frozen cohort run key:

```
paired_savings_native = baseline_selected_cost - candidate_selected_cost
```

Native savings are grouped by currency and never summed across currencies.
Savings percentage is reported only when the matched baseline selected cost is
strictly positive.

## API

`EconomicRegretEvaluator.score_result(result, repeat=N)` creates one per-run
report.

`freeze_reference_cohort(coverage_reports, react_reports)` freezes the matched
positive-oracle-cost baseline cohort.

`compare_candidate_on_reference_cohort(...)` checks full candidate
comparability, computes mean common-cohort regret, and emits matched savings
against both baselines.

## Offline CLI

Score one standardized result:

```bash
python scripts/evaluate_economics_v01.py score \
  --result results/run.json \
  --repeat 1 \
  --output results/run-economics.json
```

Freeze the common baseline cohort:

```bash
python scripts/evaluate_economics_v01.py cohort \
  --coverage results/coverage/*.economics.json \
  --react results/react/*.economics.json \
  --output results/reference-cohort.json
```

Compare a candidate on that exact cohort:

```bash
python scripts/evaluate_economics_v01.py compare \
  --candidate results/candidate/*.economics.json \
  --coverage results/coverage/*.economics.json \
  --react results/react/*.economics.json \
  --cohort results/reference-cohort.json \
  --output results/candidate-comparison.json
```

No command in this layer calls an LLM or provider API.
