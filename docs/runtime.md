# Deterministic runtime v0.1

The runtime executes the frozen five-episode contract without an LLM. It is a
state machine, not an agent and not a scorer.

## Interface

```python
from longprocurebench import LongProcureBenchEnv

env = LongProcureBenchEnv()
state = env.reset("electrical-bongabon-generator-001")
state = env.step({
    "action_id": "a1",
    "episode_id": state["episode_id"],
    "type": "identify_suppliers",
    "supplier_id": None,
    "arguments": {},
})
```

`reset()` accepts an episode ID, repository-relative JSON path, absolute JSON
path, or parsed episode dictionary.

## Visible vs hidden state

At reset, the agent-visible state contains the real public initial state and no
synthetic suppliers or future events. `identify_suppliers` reveals the synthetic
supplier directory. Future quotes, questions, amendments, withdrawals, and other
events remain hidden until their episode triggers fire.

Returned state contains:

- `step`: accepted-action count;
- `initial_state`: immutable real starting state;
- `visible_suppliers`: empty until supplier discovery;
- `observations`: events emitted by the current action;
- `revealed_events`: cumulative visible event history;
- `action_history`: accepted actions only;
- `terminated` and `terminal`: terminal runtime state.

The pending event list, oracle, and unrevealed supplier/event information are not
returned by the environment interface.

## Deterministic transition order

For an accepted action number `n`:

1. validate the action and current-state semantics;
2. increment the accepted-action counter;
3. apply built-in action effects such as revealing the supplier directory;
4. emit unconsumed matching `after_action` events in episode-file order;
5. emit unconsumed `at_step: n` events in episode-file order;
6. consume each emitted event permanently;
7. apply terminal state for `award_supplier` or `no_award`;
8. return the new visible state.

Invalid actions do not increment `step` or enter `action_history`.

## Supplier actions

`send_rfq`, `send_follow_up`, `answer_supplier_question`, and
`request_quote_revision` require a known supplier and require the supplier
directory to have been revealed first.

`request_buyer_clarification`, `identify_suppliers`, `issue_amendment`,
`evaluate_quotes`, and `no_award` require `supplier_id: null`.

## Terminal actions

`award_supplier` is allowed only against revealed quote events. Its
`arguments.awards` value is a non-empty list of:

```json
{
  "scope": "package",
  "supplier_id": "syn-example",
  "quote_event_id": "e5"
}
```

For multi-lot awards, multiple entries are supplied and the action's top-level
`supplier_id` is null. The runtime verifies quote ownership, visibility, and
scope coverage, but **does not decide whether the economic/procurement choice is
correct**. Oracle scoring is a later milestone.

`no_award` terminates immediately and may include a free-text
`arguments.reason`. Correctness is likewise left to the future scorer.

## What is deliberately not included

- no LLM or agent implementation;
- no stochastic simulator;
- no benchmark score or oracle grader;
- no baseline comparison;
- no leaderboard.

All five frozen Episode Model v0.1 episodes have deterministic scripted execution
tests in `scripts/test_runtime.py`.
