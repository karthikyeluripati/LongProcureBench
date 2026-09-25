# LongProcureBench development

- Use test-driven development for behavioral fixes: add a focused regression
  test, observe it fail, implement the fix, then run the tests and dataset validator.
- Install dependencies from requirements.txt in a fresh environment when changing
  dependencies; do not rely on optional packages installed elsewhere.
- Keep initial-state facts separate from offers, negotiations, and awards. Unknown
  values remain null with accurate missing-information reasons.
- Cite scalar fields with specific document pages, rows, or sections. Related
  scalar fields may share a locator when they come from the same source passage.
- After publishing a PR update, inspect GitHub Actions and Greptile feedback.
  Address valid findings; report pending or unavailable reviews without calling
  them passed. Do not dismiss reviews or resolve threads solely because of a push.
- Do not merge unless the user explicitly requests it.
