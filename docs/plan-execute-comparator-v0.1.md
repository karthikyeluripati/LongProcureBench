# Static Plan-and-Execute comparator v0.1

## Research question

Coverage + Repair showed that much of the apparent ReAct development advantage
can be recovered by explicit procurement workflow execution with fewer model
calls. The remaining failures are concentrated in prerequisite handling and
post-event recovery.

This comparator asks:

> Does generating a complete plan **before acting**, then executing against that
> fixed plan as observations arrive, solve those residual failures?

This is an external comparator, not a proposed ProcureHarness method.

## Pattern

The comparator adapts the Plan-and-Solve / Plan-and-Execute separation:

1. **Planner call** before the first environment action:
   - sees only `factual_compiled_v0.1`;
   - creates one fixed high-level plan of at most 10 semantic operations;
   - may describe observable conditions for applying each step;
   - cannot see hidden suppliers, future events, evaluator state, or oracle
     outcomes.
2. **Executor calls**:
   - receive the unchanged fixed plan plus current factual visible state;
   - choose one semantic action and identify the plan step being executed;
   - may reuse a planned step when its condition remains applicable.
3. **Unplanned exception**:
   - `plan_step_index = 0` is valid when the chosen operation is absent from
     the fixed plan;
   - if the operation is already represented in the plan, index 0 is valid
     only when a relevant post-plan event motivates the departure;
   - one post-plan event may legitimately drive different downstream recovery
     operations and separate supplier-scoped repairs (for example, requirement
     change -> amendment -> revision A -> revision B); it may justify the same
     operation once per target supplier;
   - when several unused relevant events could explain an exception, the
     controller attributes it to the most recently revealed event batch;
   - cross-supplier disruptions such as a supplier withdrawal may motivate
     recovery work on a different remaining supplier;
   - the plan is still not rewritten.

The comparator performs **no replanning**. That is intentional: the experiment
separates up-front planning from any future invalidation-triggered replanning
mechanism.

## Matched conditions

- model: `openai/gpt-5.6-sol`
- reasoning effort: `medium`
- temperature: omitted
- same runtime / Evaluator v0.2 / semantic action space
- same factual compiled information boundary
- no held-out episodes 021-030
- one additional planner call per episode; one executor call per proposed
  semantic action

## Stage 1 targeted protocol

Run exactly one repeat on three development episodes:

- `electrical-burauen-generator-008` — supplier withdrawal + recovery /
  revision;
- `electrical-dla-transformer-013` — visible starting prerequisite gap +
  revision path;
- `electrical-dla-power-supply-016` — midstream requirement change /
  amendment.

This is a mechanism pilot, not paper evidence. A default runner invocation with
only `--model` selects exactly these three episodes, one repeat, medium
reasoning, and omitted temperature.

Continue only if:

- all three runs execute/evaluate cleanly;
- each run records exactly one planner call;
- fixed-plan state is actually present;
- no run hits the action cap;
- the executor does not systematically fail the plan-step protocol.

## Interpretation

The three cases test different hypotheses:

- If 013 improves, up-front planning may help enforce prerequisites.
- If 008 still fails or uses an unplanned exception after withdrawal, static
  planning is insufficient for state invalidation/recovery.
- If 016 requires an unplanned exception after the buyer change, evolving
  requirements expose the same limitation.

Do not run a 20x3 grid from this pilot. If the mechanism is valid, the next
step is a small repeated residual-set comparison before deciding whether a
full development comparator is scientifically justified.
