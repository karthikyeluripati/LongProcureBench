# LongProcureBench: three-example source review

Reviewed on 2026-09-25. These are equipment/material procurements from primary
public sources. Two buyers and two countries provide initial variation, but this
small convenience-selected set is not representative of electrical procurement.

## Evidence and boundaries

1. **High Point transformers, 8017-112221.** Issued 2021-10-29. PDF p. 9:
   sole row, 5 EA, blank prices/delivery term. Pages 6-8: specifications;
   pp. 4-5: quantity qualifications and eligibility. Quantity is estimated.
   Named component brands are not whole-transformer manufacturers.
2. **High Point cable, 20-042022.** Issued 2022-04-04. PDF p. 13:
   five unpriced rows; pp. 6-12: specifications. Estimated quantities are
   30,000/30,000/30,000/15,000/15,000 FT, totaling 120,000 FT, not reels.
   The quantity tables and discrepant stock-number page were visually checked.
3. **BFAR generators, BFAR5BAC-2024-007 / PhilGEPS 10485194.** Published
   2024-01-20; created 2024-01-18. Description/Line Items: 2 Unit, PHP 75,000
   per unit, PHP 150,000 total; ABC agrees. These are buyer amounts, not offers.
   Delivery: 15 calendar days after supplier receives the purchase order.
   No order date is known. Post-publication status is omitted.

Each JSON record contains the original URL, retrieved-byte hash, source date,
and field locators. PDF pages are one-based physical pages.

## Availability

| Field group | Available in these examples |
|---|---|
| Buyer, context, delivery location | 3/3 |
| Equipment, quantity, original units | 3/3; 7/7 rows |
| Technical requirements | 3/3; selective summaries |
| Source date and bid deadline | 3/3 |
| Supplier qualification requirements | 3/3 |
| Compliance language | 3/3; product standards only in High Point sources |
| Buyer cost estimates and budget | 1/3, generators only |
| Delivery duration | 1/3, generators only |
| Absolute need-by date | 0/3 |
| Whole-item manufacturer/model | 0/3 |
| Unambiguous package-wide alternate policy | 0/3 |

## Schema issues

- **Quantity:** `quantity_basis` avoids treating estimates as committed demand.
- **Dates:** bid closing differs from delivery. Relative delivery terms require
  an unknown future event, so no calendar date is inferred.
- **Money:** cost objects distinguish buyer estimates/ceilings from prices and
  include currency. Blank bid-price cells supply no estimate.
- **Conflicting IDs:** cable schedule 4523 appears as 4253 on specification
  p. 11. Retain the schedule ID and record the discrepancy.
- **Alternates:** cable 2904 prohibits substitutions while general terms permit
  comparable products. Transformer component equivalents coexist with restrictive
  general terms. Neither conflict is silently resolved.
- **Brands:** cable code names are not confirmed models; the supplier list on
  p. 12 has unclear applicability elsewhere. Transformer brands name components.
- **Units:** generator DC output remains `12V/8.3`; its current unit is unknown.
  Original `FT` and `EA` unit tokens are retained.
- **Completeness:** nulls are individually explained. Non-null spec summaries
  are not exhaustive; every package flags this. Missing optional quotations are
  curator choices, not missing buyer facts.
- **Time boundary:** solicitations approximate pre-RFQ knowledge. The live notice
  cannot prove its requirement text is unchanged since initial publication.

No compliance engine, unit ontology, event model, or evaluation framework is
introduced. Structured relative schedules and typed technical attributes can be
considered after a larger sample demonstrates a need.
