# ProcureHarness Phase-1 Search Termination Summary v0.1

This package is an offline, evidence-bound summary of the preregistered ProcureHarness Phase-1 architecture search.

## Search accounting

- Completed rounds: 2 / 3
- Screened candidates: 12 / 18
- Development-confirmed candidates: 4
- Development runs: 480
- 031-040 search-validation runs: 0
- 041-050 final-test runs: 0
- Round 3 executed: false
- Known model cost across executed search rows: USD 7.7604622
- Total tokens across executed search rows: 1789236

## Round outcomes

Round 1 screened C01-C06 and selected ph-r1-c02, ph-r1-c05 for 001-020 x3 confirmation. Both passed the development floor, neither passed the quality-promotion branch, and neither passed the frozen efficiency branch.

Round 2 screened C07-C12 and selected ph-r2-c12, ph-r2-c09 for 001-020 x3 confirmation. Both passed the development floor, neither passed the quality-promotion branch, and neither passed the frozen efficiency branch.

Across all four confirmed candidates, the efficiency branch failed full regret comparability: 42/48 frozen reference-cohort runs were eligible (87.5%), while 48/48 was required.

## Termination

The frozen progression gate recorded 2 consecutive completed rounds with no new validation-frontier point. The plateau threshold is 2, so the search decision is **stop**. No Round-3 screening authorization exists.

## Claim boundary

This is a development-search termination result. It does **not** establish a global optimum, a 031-040 validation advantage, or a 041-050 final-test advantage. Those claims are not supported because no ProcureHarness candidate entered search validation.
