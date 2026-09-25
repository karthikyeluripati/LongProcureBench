# Pilot v0.1 audited evidence

This report freezes the first usable LongProcureBench reactive-agent pilot after
the evaluator/oracle audit in PR #12.

## Evidence provenance

- Raw pilot workflow run: `36159375317`
- Raw runs: 45
- Models: `openai/gpt-5.6-sol`, `openai/gpt-5.6-terra`,
  `openai/gpt-5.6-luna`
- Episodes: 5 frozen electrical procurement episodes
- Repeats: 3 per model/episode
- Re-score workflow run: `36164075715`
- Re-score made **zero model/API calls**
- Raw trajectories and original model/cost metadata were preserved unchanged
- Only the deterministic evaluation block was recomputed under the current
  evaluator/oracle

The audited evidence artifact is:
`audited-pilot-36159375317-36164075715`.

## Overall result

| Dimension | Result |
| --- | ---: |
| Terminally feasible award | 33 / 45 (73.3%) |
| Feasible + process complete | 13 / 45 (28.9%) |
| Strict episode success | 13 / 45 (28.9%) |
| Terminally infeasible | 12 / 45 (26.7%) |
| Feasible but process incomplete | 20 / 45 (44.4%) |
| Process-complete but economically suboptimal | 0 / 45 |

The main pilot signal is therefore **not** simply poor supplier selection.
Almost three quarters of runs reached a feasible terminal award, but fewer than
one third completed the required procurement process correctly.

## Model-level audited results

| Model | Terminal feasible | Feasible + process complete | Strict success | Economic objective satisfied | Cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPT-5.6 Luna | 12/15 (80.0%) | 7/15 (46.7%) | 7/15 (46.7%) | 8/15 (53.3%) | $0.0731 |
| GPT-5.6 Sol | 12/15 (80.0%) | 6/15 (40.0%) | 6/15 (40.0%) | 8/15 (53.3%) | $1.7509 |
| GPT-5.6 Terra | 9/15 (60.0%) | 0/15 (0.0%) | 0/15 (0.0%) | 6/15 (40.0%) | $0.6790 |
| **Overall** | **33/45 (73.3%)** | **13/45 (28.9%)** | **13/45 (28.9%)** | **22/45 (48.9%)** | **$2.5030** |

These are pilot measurements over five episodes, not paper-level model rankings.

## Episode-level audited results

| Episode | Terminal feasible | Feasible + process complete | Strict success |
| --- | ---: | ---: | ---: |
| Bongabon generator | 9/9 | 0/9 | 0/9 |
| National Museum lighting | 7/9 | 6/9 | 6/9 |
| NEUST cable | 0/9 | 0/9 | 0/9 |
| DLA breaker | 8/9 | 4/9 | 4/9 |
| Barrie transformer | 9/9 | 3/9 | 3/9 |

Two episodes are especially diagnostic:

- **Bongabon:** every run reached a feasible terminal award, but all 9 failed the
  required non-response follow-up checkpoint.
- **NEUST:** all 9 runs failed to reach a feasible terminal award and all 9 also
  failed amendment handling and non-response follow-up.

## Failure taxonomy

### Required-checkpoint failures

| Checkpoint | Failed runs |
| --- | ---: |
| follow_up_nonresponse | 18 |
| validate_compliance | 17 |
| evaluate_quotes | 10 |
| normalize_quotes | 10 |
| handle_amendment | 9 |
| request_quote_revision | 9 |
| recover_from_withdrawal | 5 |
| handle_supplier_question | 2 |
| resolve_requirement_gap | 1 |
| validate_eligibility | 1 |

### Hard-constraint failures

| Constraint position | Failed runs |
| --- | ---: |
| c4 | 12 |
| c2 | 11 |
| c3 | 10 |
| c1 | 8 |

Constraint IDs are episode-local, so these counts should not be interpreted as
one common semantic constraint across episodes.

## Research interpretation

The strongest pilot pattern is:

> Agents frequently reach a feasible procurement decision while failing to
> maintain and discharge obligations introduced earlier in the workflow.

Examples include:

- a supplier becomes non-responsive, but the agent never follows up;
- a requirement changes, but the agent does not issue an amendment and refresh
  stale offers;
- a supplier withdraws, but the agent fails to obtain and re-evaluate a
  replacement active offer;
- the agent reaches an award without an explicit quote-evaluation/normalization
  stage.

This is stronger evidence for a **long-horizon obligation/state-management
problem** than for a simple final-choice problem.

## What this pilot does not establish

The evidence is still limited to:

- five episodes;
- one procurement vertical slice;
- one provider/model family;
- one deliberately naive reactive architecture.

It is appropriate for benchmark debugging, failure discovery, and hypothesis
formation. It is not sufficient for broad claims about model families, agent
architectures, or enterprise procurement in general.

## Next research gate

Before designing a stronger agent, the next benchmark milestone should expand
episode coverage while preserving the observed failure mechanisms. After that,
cross-family baselines can test whether the obligation-tracking failures
generalize beyond the current OpenAI pilot.
