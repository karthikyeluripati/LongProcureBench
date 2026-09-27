# Coverage + Repair confirmatory development run v0.1

## Purpose

The one-repeat 20-episode diagnostic suggested that deterministic supplier
coverage and bounded visible repair can recover part of the ReAct quality gain
while using materially fewer model calls/tokens/cost. This confirmatory run is
frozen before execution to determine whether that signal survives three repeats.

This remains a **diagnostic baseline**, not a proposed ProcureHarness method.

## Frozen execution

- episodes: development/calibration 001-020 only
- model: `openai/gpt-5.6-sol`
- reasoning effort: `medium`
- temperature: omitted
- repeats: 3
- maximum accepted actions: 50
- policy: `CoverageRepairContextPolicy`
- context: `factual_compiled_v0.1`
- same runtime, evaluator, semantic action space, and information boundary as
  the merged diagnostic implementation
- no held-out episodes 021-030

Total planned grid: **20 episodes x 3 = 60 model-backed runs**.

## Frozen comparisons

Compare against the already frozen 60-run GPT-5.6 Sol rows:

- factual context compiled:
  - terminal feasible 76.7%
  - feasible-obligation 66.7%
  - strict v0.2 23.3%
  - economic objective 23.3%
  - 974,208 total tokens
  - $4.6086564 known API cost
- true ReAct:
  - terminal feasible 86.7%
  - feasible-obligation 68.3%
  - strict v0.2 45.0%
  - economic objective 46.7%
  - 1,454,192 total tokens
  - $7.9842032 known API cost

## Predeclared interpretation

For strict v0.2 and economic objective, define ReAct-gain recovery as:

`(coverage_repair - context) / (react - context)`.

Interpret the result as follows:

1. **Substantial workflow explanation** if Coverage+Repair recovers at least
   50% of the ReAct improvement on both strict v0.2 and economic objective,
   while feasible-obligation and terminal feasibility are each no more than
   5 percentage points below factual context.
2. **Near-ReAct workflow explanation** if Coverage+Repair is within 5
   percentage points of ReAct on both strict v0.2 and economic objective while
   known API cost is at least 25% below ReAct.
3. Otherwise, treat the remaining gap as evidence that ReAct contributes a
   substantial reasoning benefit beyond deterministic supplier
   coverage/repair.

Efficiency is reported separately: accepted actions, model calls, tokens,
latency, and known API cost. No weighted composite score is used.

The result is development evidence only. It cannot be used as an untouched
final evaluation of any new method.
