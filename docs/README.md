# FinOps Platform Handbook

The platform's working documentation: what exists, where it lives, why it's shaped the way it is. Fabric-specific standards (`naming_standards.md`, `notebook_standards.md`, `lakehouse_standards.md`) live alongside this handbook in `docs/`. Cross-platform governance — the control framework and tagging policy — lives in the `finops-governance` repo and is referenced from here, never duplicated.

**How this is organised:** one taxonomy — the control framework's domains — with the section index below as the human-readable map onto it. Sections gain their own page under `docs/` only when this index can no longer hold them (same rule as folders in naming_standards.md: subpages earn their place).

**Decisions** are recorded as ADRs in [`adr/`](adr/README.md). A section without its ADRs linked is a section whose reasoning is at risk.

## Section index

| # | Section | Domains | Key assets today | Decisions |
|---|---|---|---|---|
| 1 | Costs, pricing & reservation data | FIN, CMT | `focus_cost` ingestion (finops-fabric); price sheet planned (`pricesheet` token reserved); reservations planned (`reservations` token reserved) | [0005](adr/0005-edp-uniform-scalar.md) |
| 2 | AI & GitHub | AIG, SVC-CPL | `ghcopilot-finops` package + notebooks; AI endpoint price comparison in progress (caching test live) | [0005](adr/0005-edp-uniform-scalar.md) |
| 3 | Fabric, Databricks & SQL | SVC-FAB, FIN | `ops_bronze_monitoring_capacity` notebook; Databricks system-table synthesis in progress; SQL split TBD (only needed for shared pools) | [0007](adr/0007-capacity-telemetry-three-tiers.md), [0008](adr/0008-platform-telemetry-identities.md), [0010](adr/0010-system-table-hybrid-synthesis.md) |
| 4 | Forecasting & budgeting | FOR, BUD | `focus_cost_forecast_*` notebooks in `finops-fabric/notebooks/` (hierarchical forecast, backtest, changepoints, synthesise); budgets designed, not built | [0001](adr/0001-service-id-hierarchy.md), [0002](adr/0002-hierarchical-forecast-mint.md), [0006](adr/0006-lakehouse-master-budgets.md) |
| 5 | Chargeback | RPT, CMT | Designed: `gold.chargeback_monthly`, `gold.chargeback_reconciliation` (EffectiveCost allocation, variance bridge) | [0009](adr/0009-commitment-chargeback-effectivecost.md) |
| 6 | Compute & commitments (savings plans, RI, K8s) | CMT, SVC-AKS | `finops_bronze_benefits_usage` + `finops_bronze_benefits_recommendations` notebooks; RI recommendations planned | [0004](adr/0004-benefits-hourly-stitching.md), [0009](adr/0009-commitment-chargeback-effectivecost.md) |
| 7 | ESG / carbon | esg domain (naming_standards.md) | CarbonEmissions notebooks (v2 on finops-core); Carbon API constraints documented in notebook headers | — |
| 8 | Platform considerations | GOV, SVC | finops-core / ghcopilot-finops packages, ADO feed, lockstep versioning; Fabric networking constraints (UDF vs Private Link) | [0003](adr/0003-packages-over-notebooks.md), [0011](adr/0011-schema-contract-unofficial-sources.md) |
| 9 | FinOps tools for AI | AIG | Evaluation stance: build on FOCUS in-hub rather than adopt packaged tools (FCA assessed: cost-only; Chargeback app assessed: skipped) | [0007](adr/0007-capacity-telemetry-three-tiers.md) |
| 10 | Resource graph (subscriptions, resources) | FIN, TAG | Resources_MultiTenant notebook (pre-finops-core; refactor planned); `arg` token; subscription discovery now in `finops_core.arm` | [0003](adr/0003-packages-over-notebooks.md) |
| 11 | Other sources (on-prem, Turbonomic) | FIN, OPT | Not started; Turbonomic referenced by SVC-SQL/SVC-VM controls | — |
| 12 | Recommendations workflow | OPT, RPT | Designed only: AI-generated commentary, translytical feedback capture; depends on budgets writeback mechanism | [0006](adr/0006-lakehouse-master-budgets.md) |

## Documentation system

- **ADRs** (`adr/`) — one page per significant decision: context, decision, consequences. Written when the decision is made; never edited to flatter hindsight (supersede instead).
- **Dataset catalogue** *(planned)* — generated from notebook_standards.md header blocks across repos by a tool in `tools/`; never hand-written, so it cannot drift.
- **Runbooks** *(planned)* — operational procedures currently embedded in notebook markdown (continuity-check failure response, metrics-app recalibration, package release) extracted to `docs/runbooks/` as they prove themselves.

## Repo map

| Repo | Role |
|---|---|
| `finops-fabric` | Fabric items (notebooks, lakehouses, pipelines, UDFs, SQL), the platform-specific standards, this handbook, and ADRs |
| `finops-governance` | Cross-platform governance: control framework, tagging policy |
| `finops-py` | Python packages monorepo (`finops-core`, `ghcopilot-finops`) → ADO feed |
