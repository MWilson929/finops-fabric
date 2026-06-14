# Naming Convention — FinOps Fabric Platform

This document is the source of truth for naming deployable Fabric notebooks in this repository. Other Fabric item types retain their platform names until an item-specific standard is agreed. Notebook adherence is required for merge and is enforced by CI pipeline validation.

## Why This Exists

Microsoft has not published a Fabric-specific naming standard. This convention adapts widely-cited practitioner frameworks (Databricks community guidance, XTIVIA, Marc Lelijveld, Data Mozart, Plainsight) to the specific shape of this platform: a single-domain FinOps capability serving forecasting, chargeback, ESG reporting, and operational monitoring on shared FOCUS-formatted cost data.

A team following a slightly suboptimal naming convention consistently will outperform a team following individually perfect ones. The pattern below is the pattern. The exact characters matter less than universal adherence.

## The Pattern

```
{domain}_{layer}_{source}_{entity}
```

Always exactly four underscore-separated tokens. All tokens lowercase. Mechanically parseable: `split('_')` returns four elements for every deployable notebook.

## Token Definitions

### Domain (token 1)

Identifies the primary owner or consumer of the item.

| Token   | Meaning                                                 |
|---------|---------------------------------------------------------|
| finops  | Shared foundation data consumed by multiple capabilities |
| fcst    | Forecasting capability                                  |
| cback   | Chargeback capability                                   |
| esg     | Sustainability / carbon reporting capability            |
| ops     | Platform operations and monitoring                      |
| gov     | Governance / policy / compliance                        |

**Rule:** Use `finops` for foundation data consumed by three or more capabilities. Use a specific capability token when one capability owns the item's lifecycle and purpose. When in doubt, default to `finops` and refactor later if a clear single owner emerges.

Adding a new domain token requires a documented decision and update to this file.

### Layer (token 2)

Standard medallion layer of the Delta output the notebook produces.

| Token  | Meaning                                              |
|--------|------------------------------------------------------|
| bronze | Raw landed data, source-shaped, minimal transformation |
| silver | Cleaned, conformed, typed, deduplicated              |
| gold   | Purpose-shaped, ready for consumption                |

**Rule:** Every notebook in this platform produces a Delta table at one of these three layers. Work that does not produce a Delta output belongs elsewhere (semantic models, pipelines, exploratory workspaces outside the platform).

### Source or subject (token 3)

Token 3 changes meaning by layer, mirroring the table convention in lakehouse_standards.md:

- **Bronze and silver**: token 3 is the **source** — where the data came from.
- **Gold**: token 3 is the **subject area** — what the output is about. Gold items are synthesised from multiple silver inputs and rarely have a single source, so naming them by source would be misleading.

#### Source (bronze and silver)

Identifies what the data fundamentally *is*, expressed in terms natural to a FinOps reader. Not the API endpoint, not the plumbing.

| Token         | Meaning                                              |
|---------------|------------------------------------------------------|
| focusazure    | FOCUS-formatted billing data from Azure              |
| focusm365     | FOCUS-formatted billing data from Microsoft 365      |
| arg           | Azure Resource Graph                                 |
| arm           | Azure Resource Manager direct APIs (subscriptions, ARM management endpoints) — distinct from `arg` (graph queries) |
| ado           | Azure DevOps REST API (work items, pipelines, runs)  |
| pricesheet    | Negotiated EA/MCA price sheet (golden source)        |
| reservations  | Azure reservation data (details, recommendations, transactions) |
| savingsplan   | Azure savings plan data (recommendations, eligibility, hourly usage). Distinct from `reservations`; combine only if a true commitments-agnostic source emerges. |
| carbon        | Azure Carbon Optimization API                        |
| defender      | Defender for Cloud                                   |
| github        | GitHub API                                           |
| instana       | Instana                                              |
| fabric        | Microsoft Fabric platform telemetry from other workspaces (e.g. Capacity Metrics app). Distinct from `monitoring`, which is our own platform's observability. |
| monitoring    | Our own platform's Workspace Monitoring telemetry    |

**Rule:** Source describes the *primary* dataset being transformed. Reference data (lookups, dimensions, mapping tables) joined into the transformation does not change the source token — the entity token reflects the resulting shape instead.

**Compound sources** (e.g. `focusazure`, `focusm365`) are joined without separator. Adding a new source requires an entry in this table.

#### Subject area (gold)

The authoritative enumeration of gold subject areas. lakehouse_standards.md references this list for gold table naming (token 1); it is not duplicated there.

| Token       | Meaning                          |
|-------------|----------------------------------|
| forecast    | Forecasting outputs and inputs   |
| chargeback  | Chargeback / showback datasets   |
| emissions   | Carbon / ESG reporting datasets  |
| monitoring  | Operational monitoring datasets  |
| budget      | Budget and variance datasets     |

Adding a subject area requires a documented decision and an update to this table.

### Entity (token 4)

Describes what the Delta output contains.

**Rule:** Single word. Lowercase. No separators. No abbreviations beyond established industry terms. If a concept genuinely cannot be expressed in one word, the domain or source choice is probably wrong — revisit those before reaching for compound entities.

Acceptable: `billing`, `resources`, `normalised`, `enriched`, `allocated`, `monthly`, `input`, `output`, `rates`, `emissions`, `logs`, `capacity`.

Unacceptable: `forecast_input`, `monthly_summary`, `capacity_metrics_daily`, `v2`, `final`, `temp`, `test`.

## Worked Examples

### Foundation data (finops domain)

```
finops_bronze_focusazure_billing
finops_bronze_focusm365_billing
finops_bronze_arg_resources
finops_bronze_arg_advisors
finops_bronze_arg_policies
finops_bronze_carbon_emissions
finops_silver_focusazure_normalised
finops_silver_focusazure_enriched
finops_silver_arg_tagged
```

### Chargeback

```
cback_bronze_pricesheet_rates
cback_silver_instana_allocated
cback_gold_chargeback_monthly
```

### Forecasting

```
fcst_gold_forecast_input
fcst_gold_forecast_arima
fcst_gold_forecast_mstl
fcst_gold_forecast_ensemble
```

### ESG

```
esg_silver_carbon_normalised
esg_gold_emissions_allocated
```

### Operations

```
ops_bronze_monitoring_logs
ops_silver_monitoring_capacity
ops_gold_monitoring_dashboard
```

## Folder Structure

Folders provide a second axis of organisation orthogonal to the name. Tier-1 folders group by service or capability:

```
azure/
m365/
chargeback/
forecast/
esg/
_platform/
  monitoring/
  load_testing/
```

**Rules:**

- Leading underscore (`_platform/`) reserves the folder for platform-internal items and sorts predictably.
- Subfolders earn their place when they contain three or more items, or group items that are conceptually inseparable. A subfolder containing one notebook is noise — promote the notebook up.
- Items are named with the full convention regardless of folder location. Names must stand alone because they appear in pipeline activity references, monitoring logs, lineage views, and Data Agent tool descriptions where folder context is absent.

## Validation

For deployable notebooks, the pattern is enforced by:

1. **CI pipeline** — validates all deployable `*.Notebook/.platform` files against the regex below before the `fabric-cicd` publish step.
2. **Semantic model BPA** — planned separately for table, column, and measure naming inside semantic models; it is not part of this notebook naming rule.

### Validation regex

Token 3 is layer-dependent (source at bronze/silver, subject at gold), so validation is two alternatives:

```
^(finops|fcst|cback|esg|ops|gov)_(bronze|silver)_(focusazure|focusm365|arg|arm|ado|pricesheet|reservations|savingsplan|carbon|defender|github|instana|fabric|monitoring)_[a-z]+$
^(finops|fcst|cback|esg|ops|gov)_gold_(forecast|chargeback|emissions|monitoring|budget)_[a-z]+$
```

A name is valid if it matches either line. The regex is generated from the enumerated lists in this document by the validation script. Update this document to change the convention; the script picks up the change on next run.

## Exceptions

Exceptions are break-glass controls, not an alternative naming convention.
They are permitted only when immediate compliance would block a necessary
release and the exception is:

- recorded in `config/policy_exceptions.yml`;
- scoped to one exact repository path and one validation rule;
- supported by a reason, owner, approver, and tracking ticket;
- time-boxed with an ISO `expires_on` date no more than 90 days ahead;
- approved through the pull request and protected environment controls.

Expired, malformed, broad, or no-longer-required exceptions fail validation.
Repeated exceptions for the same pattern trigger a review of this standard.

## Decision Log

This section records why specific choices were made, so future maintainers don't repeat the analysis.

- **Why `finops` and not `cost`?** `cost` is too narrow — the platform also serves carbon/ESG, governance, and operational data, all of which are FinOps concerns broadly defined. `finops` reflects the platform's scope.
- **Why `cback` not `chargeback`?** Established FinOps industry abbreviation. Keeps the domain token short to leave budget for descriptive entity names.
- **Why `fcst` not `forecast`?** Established abbreviation across finance and statistics tooling. Same reasoning.
- **Why `focusazure` and `focusm365` rather than `focus` with folder differentiation?** Folder duplication would produce two notebooks with identical names in different folders, confusing in pipeline references, lineage, and monitoring. Joined source tokens preserve global uniqueness.
- **Why does token 3 mean source at bronze/silver but subject at gold?** Same reasoning as the table convention (lakehouse_standards.md): bronze/silver items are *about* their source; gold items are *about* a purpose synthesised from many sources. The original single source-only regex rejected this document's own gold worked examples (`fcst_gold_forecast_input`) — fixed by splitting validation per layer.
- **Why single-word entities only?** Allowing multi-word entities produces drift toward verbose descriptive names (`forecast_input_v2_reviewed`). The single-word rule is mechanically enforceable; "be concise" is not.
- **Why no environment suffix (e.g. `_dev`, `_prod`)?** Environment is carried by workspace, not item name. Identical items deploy across workspaces via `fabric-cicd` with the same name.
- **Why double underscore rejected as pattern separator?** Investigated and rejected. Not a Databricks or wider community standard; single underscore with disciplined entity constraints achieves the same parseability with established conventions.
- **Why this document doesn't govern Git repo names** — its scope is Fabric items, where snake_case mechanical parseability matters for pipeline references and lineage. Git repos live in GitHub/ADO URLs and on PyPI, where the convention is **kebab-case** (`finops-py`, `finops-governance`). Snake_case for repos would look out of place in a URL and conflict with PyPI's user-facing form. Python imports remain snake_case (mandatory) — that's a Python language constraint, separate from naming convention.
## Maintenance

Changes to this document follow the same review process as code changes. Pull requests modifying enumerated lists, the pattern, or rules require approval from the platform owner. The validation regex updates automatically from the lists above on next CI run.
