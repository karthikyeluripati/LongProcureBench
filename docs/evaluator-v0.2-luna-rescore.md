# Evaluator v0.2 — Luna 20-episode rescore

This is a zero-model-call deterministic rescore of the same **60 frozen Luna
trajectories** (20 episodes × 3 repeats) produced by workflow run
`36173979424`.

The source trajectories are durably stored as six committed base64 chunks under
`evidence/luna20-diagnostic-v0.1/`. Reconstruction is verified before use:

- compressed bytes: **18,140**
- compressed SHA-256:
  `e67bf0a7408e239cfb677d1f3143e7f09a485f72c714ede4e385115eda577707`
- 60 unique runs
- 20 episode IDs × 3 repeats

Rescore workflow: `36185075656`  
Artifact ID: `10885743123`

## Main result

| Group | Runs | Terminal feasible | Legacy process success | v0.2 obligation success | v0.2 strict success | Obligation resolution |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All 20 | 60 | **71.7%** | 18.3% | **50.0%** | **26.7%** | **68.1%** |
| Original 5 | 15 | 80.0% | 53.3% | 66.7% | 60.0% | 80.8% |
| Expanded 15 | 45 | 68.9% | 6.7% | 44.4% | 15.6% | 63.1% |
| Episodes 001–010 | 30 | 70.0% | 30.0% | 53.3% | 33.3% | 62.8% |
| Compound 011–020 | 30 | 73.3% | 6.7% | 46.7% | 20.0% | 72.9% |

The legacy 18.3% process-complete rate is retained only for reproducibility. It
mixed non-applicable branches, no-opportunity events, proxy checks, and
prescriptive recovery sequences into one mandatory checkpoint denominator.

## Obligation accounting

Across all 60 trajectories:

- actionable obligations: **91**
- resolved: **62**
- unresolved: **29**
- no opportunity: **2**
- not applicable: **54**
- obligation-resolution rate: **68.1%**

Unresolved actionable obligations:

| Obligation | Count |
| --- | ---: |
| resolve requirement gap | **10** |
| follow up after observed non-response | **6** |
| request required quote revision | **6** |
| handle amendment after requirement/quantity change | **4** |
| recover from supplier withdrawal | **3** |

## Interpretation

The fairness correction does **not** eliminate the long-horizon reliability
signal. It changes its magnitude and makes the denominator defensible.

A reactive Luna agent resolved about two thirds of obligations that actually
became actionable. Roughly one third (**29/91**) remained unresolved. Meanwhile,
terminal feasibility remained substantially higher at **71.7%**.

The defensible phenomenon is therefore:

> Agents can often reach a feasible procurement decision while failing to
> discharge a meaningful fraction of the stateful obligations that actually
> arise during the workflow.

This is a stress-test benchmark result, not an estimate of real-world procurement
failure prevalence. Episodes 006–020 were deliberately constructed around
controlled long-horizon failure mechanisms.

## Metric definitions

- **Terminal feasible:** terminal award/no-award matches an acceptable feasible
  outcome.
- **Obligation resolution rate:** resolved actionable obligation instances /
  all actionable obligation instances.
- **Feasible obligation success:** terminal feasible + all hard constraints pass
  + every actionable obligation is resolved.
- **Strict v0.2 success:** feasible obligation success + economic objective
  satisfied.
- **Legacy process success:** original v0.1 all-required-checkpoint metric,
  retained only for historical comparison.

No weighted score is introduced.
