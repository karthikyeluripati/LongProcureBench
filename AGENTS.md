# LongProcureBench development

- Use test-driven development for behavioral fixes: add a focused regression
  test, observe it fail, implement the fix, then run the tests and both validators.
- Install dependencies from requirements.txt in a fresh environment when changing
  dependencies; do not rely on optional packages installed elsewhere.
- Keep initial-state facts separate from offers, negotiations, and awards. Unknown
  values remain null with accurate missing-information reasons.
- Preserve the real/synthetic boundary in episodes. Real public facts come only
  through `initial_state_ref`; suppliers, messages, quotes, and event timing in
  v0.1 episodes are synthetic and must be labeled as such.
- The runtime must never expose pending events, the oracle, or synthetic suppliers
  before their contract-defined reveal point.
- Invalid runtime actions must not advance the accepted-action step or mutate
  visible history. Emitted events are one-shot and permanently consumed.
- Do not use a real supplier name to represent synthetic behavior.
- Cite initial-state scalar fields with specific document pages, rows, or sections.
  Related scalar fields may share a locator when they come from the same passage.
- After publishing a PR update, inspect GitHub Actions and Greptile feedback.
  Address valid findings; report pending or unavailable reviews without calling
  them passed. Do not dismiss reviews or resolve threads solely because of a push.
- Do not merge unless the user explicitly requests it.
