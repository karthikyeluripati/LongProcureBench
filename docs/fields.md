# LongProcureBench field guide

All established v0.1 keys are required for a stable record shape. **Required** means a non-null value is necessary; **Optional value** means the key stays present but may be `null`. `line_items[].award_requirement` is a backward-compatible optional key; omission means `required`. Never invent missing facts. Empty arrays are allowed only for `missing_information`; unknown lists use `null`.

Provenance pointers identify scalar fields, not whole objects or arrays. Related
fields may share a precise page/row/section locator. Every populated procurement
fact needs an exact pointer in the evidence list. `not_stated` and
`bidder_to_provide` notes require a null target; `conflicting_source`,
`partial_extraction`, and `retrospective_source` may qualify populated fields.
An omitted optional verbatim excerpt is a curator choice and does not require a
missing-information note. URI validation checks syntax offline, not link reachability.

| Field | Requirement | Meaning / why it matters |
|---|---|---|
| `schema_version` | Required | Version of this data contract. |
| `package_id` | Required | Curator-assigned stable package ID. |
| `procurement_category` | Required | Milestone category. |
| `project` | Required | Project context. |
| `project.source_organization` | Required | Buyer organization establishes authority and context. |
| `project.project_name` | Required | Source procurement title or clearly descriptive package label. |
| `project.project_description` | Required | Buyer need and intended use. |
| `project.location` | Optional value | Delivery/project location, not a bid-submission address. |
| `package_subscope` | Required | Included goods/services and extraction boundary. |
| `initial_state` | Required | Temporal boundary prevents outcome leakage. |
| `initial_state.basis` | Required | These are requirement reconstructions, not observed internal pre-RFQ snapshots. |
| `initial_state.source_issue_date` | Optional value | Requirement baseline date; not a claim of historical immutability. |
| `initial_state.boundary` | Required | Information inclusion rule and excluded later-stage information. |
| `line_items` | Required | All goods lines within the stated package scope. |
| `line_items[].item_id` | Required | Stable source line/stock identifier, or explicitly curator-assigned identifier. |
| `line_items[].description` | Required | Equipment/material identity enables matching. |
| `line_items[].award_requirement` | Optional key | `required` or `optional`; omitted means required. Use `optional` for additive alternates that may correctly remain unawarded. |
| `line_items[].quantity` | Optional value | Requested quantity; null if unknown. |
| `line_items[].quantity_basis` | Optional value | Distinguishes estimates from firm demand. |
| `line_items[].unit` | Optional value | Original unit token; avoids silent conversion. |
| `line_items[].technical_specifications` | Optional value | Known technical constraints; null if unavailable. |
| `line_items[].technical_specifications[].summary` | Required | Concise factual specification summary; not a replacement for the source. |
| `line_items[].technical_specifications[].verbatim_excerpt` | Optional value | Optional short exact wording for a critical requirement. |
| `line_items[].technical_specifications[].source_locator` | Required | Page/section containing the requirement for verification. |
| `line_items[].manufacturer` | Optional value | Buyer-specified whole-item manufacturer, not a future winning supplier. |
| `line_items[].model` | Optional value | Buyer-specified whole-item model; stock IDs are not models. |
| `line_items[].acceptable_alternates` | Optional value | Optional substitution rules; null means unknown, not prohibited. |
| `line_items[].estimated_unit_cost` | Optional value | Optional known buyer cost; null when unavailable. |
| `line_items[].estimated_unit_cost.amount` | Required | Buyer estimate or budget amount; never a supplier quote. |
| `line_items[].estimated_unit_cost.currency` | Required | ISO 4217 currency prevents ambiguous cost comparisons. |
| `line_items[].estimated_unit_cost.basis` | Required | Estimate basis and inclusions; distinguishes budget ceilings from prices. |
| `line_items[].estimated_total_cost` | Optional value | Optional known buyer cost; null when unavailable. |
| `line_items[].estimated_total_cost.amount` | Required | Buyer estimate or budget amount; never a supplier quote. |
| `line_items[].estimated_total_cost.currency` | Required | ISO 4217 currency prevents ambiguous cost comparisons. |
| `line_items[].estimated_total_cost.basis` | Required | Estimate basis and inclusions; distinguishes budget ceilings from prices. |
| `total_estimated_budget` | Optional value | Optional known buyer cost; null when unavailable. |
| `total_estimated_budget.amount` | Required | Buyer estimate or budget amount; never a supplier quote. |
| `total_estimated_budget.currency` | Required | ISO 4217 currency prevents ambiguous cost comparisons. |
| `total_estimated_budget.basis` | Required | Estimate basis and inclusions; distinguishes budget ceilings from prices. |
| `schedule` | Required | Schedule constraints. |
| `schedule.need_by_date` | Optional value | Calendar delivery deadline only; never bid closing date. |
| `schedule.delivery_requirement` | Optional value | Relative delivery term or schedule when no absolute date is known. |
| `schedule.bid_submission_deadline` | Optional value | Source-stated bidding deadline retained separately as context. |
| `supplier_eligibility_constraints` | Optional value | Known eligibility requirements; null if unavailable. |
| `certifications_compliance` | Optional value | Known compliance requirements; not a certification of any supplier. |
| `supporting_documents` | Required | Primary-source document catalog. |
| `supporting_documents[].document_id` | Required | Local identifier used by provenance references. |
| `supporting_documents[].title` | Required | Human-readable source title. |
| `supporting_documents[].url` | Required | Original primary-source location. |
| `supporting_documents[].document_type` | Required | Source medium. |
| `supporting_documents[].issued_date` | Optional value | Original issue/publication date, not retrieval date. |
| `supporting_documents[].retrieved_date` | Required | Date source bytes were retrieved. |
| `supporting_documents[].sha256` | Optional value | SHA-256 when raw source bytes were captured; null when unavailable through the collection path. |
| `supporting_documents[].snapshot_policy` | Required | Explains what was retained and why; source bytes are not agent input. |
| `source_provenance` | Required | Field-level evidence; metadata and missing-information notes are curator-authored. |
| `source_provenance[].field_paths` | Required | Fields supported by this evidence. |
| `source_provenance[].document_id` | Required | Supporting document identifier. |
| `source_provenance[].locator` | Required | One-based PDF pages or HTML section; reproducible evidence location. |
| `source_provenance[].interpretation` | Required | Extraction decisions, scope, and caveats. |
| `missing_information` | Required | Every null field plus material extraction gaps; empty only if none are known. |
| `missing_information[].field_path` | Required | JSON Pointer to an unknown, incomplete, or conflicting field. |
| `missing_information[].reason` | Required | Why information is missing or unreliable. |
| `missing_information[].detail` | Required | Specific limitation; prevents treating null as absence of a requirement. |
