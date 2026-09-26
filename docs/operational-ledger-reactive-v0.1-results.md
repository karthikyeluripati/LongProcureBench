# Operational-ledger reactive v0.1 — matched result

This is a development/calibration experiment on the same frozen 20 episodes as
the factual context-compiled GPT-5.6 Sol baseline. The treatment adds explicit,
model-maintained commitment state while preserving one model call per accepted
action and the same runtime, evaluator, semantic action space, and reasoning
configuration.

The result is a **clear failure of the predeclared component gate**. This
operational-ledger formulation should **not** be carried forward as a
ProcureHarness component.

## Source and recovery

The intended grid is GPT-5.6 Sol × 20 development episodes × 3 repeats =
**60 selected runs**.

The original full workflow exhausted OpenAI credits after 43 valid runs:

- original workflow run: `36231717716`
- original artifact: `10902813768`
- artifact digest:
  `sha256:801decf63bc6e24f6bba2a20d6326dd482065aedd5bab266e8d9ff66c895e950`
- benchmark code: `4a3ef65b40f37b14816926e1e2d48110705c78f5`
- original execution head: `da3e0236b862b36f0eb607e9af5b72ecbdbe71c3`
- retained from the original artifact: episodes 001–014 × 3 plus 015/r1 =
  **43 runs**

After credits were restored, a recovery workflow ran episodes 015–020 × 3:

- recovery workflow run: `36235841640`
- recovery artifact: `10904540560`
- artifact digest:
  `sha256:53c4de34d9f8ce85935e7dd783d05b2e122b5dcc7d80b74d432ea87189f0be9b`
- recovery execution head: `55f5cba2c6349723bc46753b6025d37edd0640d3`

The selection rule was fixed before recovery outcomes were inspected:
**retain original 015/r1, discard the duplicate recovery 015/r1 by key, and use
recovery results only for 015/r2–r3 and 016–020/r1–r3**. The selected evidence
is therefore exactly **43 original + 17 recovery = 60 unique episode/repeat
keys**.

All retained runs have complete usage/cost records. There are **49 completed**
runs and **11 max-actions** runs; there are no retained provider/model execution
errors.

## Matched comparison

| Metric | Context compiled | Operational ledger | Delta |
| --- | ---: | ---: | ---: |
| Terminal feasible | 46/60 (**76.7%**) | 31/60 (**51.7%**) | **-25.0 pp** |
| Feasible-obligation success | 40/60 (**66.7%**) | 28/60 (**46.7%**) | **-20.0 pp** |
| Strict v0.2 success | 14/60 (**23.3%**) | 19/60 (**31.7%**) | **+8.3 pp** |
| Obligation resolution | 72/86 (**83.7%**) | 81/90 (**90.0%**) | **+6.3 pp** |
| Prompt tokens | 931,985 | 3,652,794 | **+291.9%** |
| Total tokens | 974,208 | 3,852,408 | **+295.4%** |
| Model calls | 464 | 1,077 | **+132.1%** |
| Known API cost | $4.61 | $21.74 | **+371.8%** |
| Aggregate model latency | 869,561 ms | 3,276,401 ms | **+276.8%** |

The aggregate obligation-resolution denominator is **policy-path dependent**:
the treatment can change which obligations become actionable. It is therefore a
useful diagnostic, not a substitute for the run-level feasible-obligation
success metric.

## Predeclared gate

The development inclusion gate was frozen before this experiment. Retain the
ledger if either:

1. feasible-obligation success improves by at least **5 percentage points**
   while terminal feasibility falls by no more than **5 points**; or
2. strict v0.2 success improves by at least **5 points**, while
   feasible-obligation success falls by no more than **2 points** and terminal
   feasibility falls by no more than **5 points**.

The treatment fails **both** conditions.

- condition 1: feasible-obligation success is **-20.0 pp** and terminal
  feasibility is **-25.0 pp**
- condition 2: strict success is **+8.3 pp**, but the FOS and terminal
  guardrails are violated by large margins

The strict-success increase therefore does not rescue the component under the
frozen rule.

## Episode-cluster bootstrap

A paired cluster bootstrap over the 20 episode IDs (20,000 resamples,
`sha256-index-v1`, seed `20260926`) gives descriptive 95% intervals:

| Delta | 95% interval |
| --- | ---: |
| Terminal feasible | **[-41.7, -8.3] pp** |
| Feasible-obligation success | **[-38.3, 0.0] pp** |
| Strict v0.2 success | **[-6.7, +23.3] pp** |
| Obligation resolution | **[-4.4, +19.3] pp** |
| Total tokens | **[+144.9%, +447.6%]** |
| Model calls | **[+58.9%, +213.5%]** |
| Cost | **[+208.0%, +530.8%]** |
| Aggregate model latency | **[+195.3%, +365.8%]** |

The reliability loss and resource increase are not artifacts of treating the
60 replicates as IID; the comparison resamples at the episode level.

## What changed behaviorally

The dominant behavioral shift was repeated buyer clarification:

- context compiled: **47** `request_buyer_clarification` actions
- operational ledger: **652**
- ledger treatment total model calls: **1,077**

The 11 max-action runs alone account for **550 actions**, of which **504
(91.6%)** are buyer clarifications. Those 11 runs consume **2,347,315 tokens
(60.9% of treatment tokens)** and approximately **$12.89 (59.3% of treatment
cost)**.

Representative diagnostics:

- episode 010: all three ledger runs reached the 50-action cap; one run used
  buyer clarification on all 50 actions
- episode 005: two runs reached the cap, again dominated by clarification
- episode 018: all three runs reached the cap, dominated by clarification
- episode 020/r1 completed only after 43 actions, including 41 buyer
  clarifications

Inspection of these trajectories is consistent with a **commitment-fixation
failure**: the ledger often externalized unresolved initial uncertainty as
persistent work, then repeatedly attempted clarification even when the
environment provided no additional resolution path. This is a trajectory-level
diagnostic, not a claim that explicit state always causes perseveration.

The treatment did help some episodes. For example, episode 012 improved from
1/3 to 3/3 feasible-obligation successes. But other episodes regressed sharply:
episode 010 went from 2/3 to 0/3, episode 013 from 2/3 to 0/3, and episode 020
from 3/3 to 0/3. The matched aggregate gate captures that tradeoff.

## Remaining unresolved obligations

Across the selected treatment runs, 9 actionable obligations remain unresolved:

- `recover_from_withdrawal`: **4**
- `follow_up_nonresponse`: **2**
- `handle_amendment`: **1**
- `request_quote_revision`: **1**
- `resolve_requirement_gap`: **1**

Thus the treatment reduced the count of unresolved obligation instances while
simultaneously reducing end-to-end feasibility and increasing looping. This is
why aggregate obligation-resolution rate alone is insufficient as the selection
criterion.

## Decision

**Drop operational-ledger reactive v0.1 as a ProcureHarness component.**

The planned stateless/recomputed-ledger ablation was conditional on this
treatment passing. Because it fails the frozen gate, that ablation is not needed
to decide component inclusion.

The next causal experiment should move to **explicit planning / maintained
working plan / replanning**, rather than adding more memory infrastructure. The
question is now whether a bounded representation of *what to do next and when
to stop/revise the plan* can improve long-horizon reliability without the
sticky-commitment behavior observed here.

Held-out starting states remain untouched, and no held-out episodes were
authored or evaluated.
