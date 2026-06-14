# Architecture Decision Records

One page per significant decision: **Context** (the situation and forces), **Decision** (what we chose), **Consequences** (what follows, good and bad). Statuses: Proposed, Accepted, Superseded (by link). Records are immutable once accepted — write a superseding ADR rather than editing history.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-service-id-hierarchy.md) | Service_ID tag is the allocation and forecasting hierarchy | Accepted | 2026-06-10 |
| [0002](0002-hierarchical-forecast-mint.md) | Forecast every hierarchy level, reconcile with MinT | Accepted | 2026-06-10 |
| [0003](0003-packages-over-notebooks.md) | Shared plumbing lives in versioned packages, threshold of three | Accepted | 2026-06-10 |
| [0004](0004-benefits-hourly-stitching.md) | Stitch Benefit Recommendations hourly usage; size at shared scope | Accepted | 2026-06-12 |
| [0005](0005-edp-uniform-scalar.md) | EDP treated as a uniform scalar in cross-platform AI price comparison | Accepted | 2026-06-12 |
| [0006](0006-lakehouse-master-budgets.md) | Lakehouse is the budget system of record; Azure budgets are generated guardrails | Accepted | 2026-06-12 |
| [0007](0007-capacity-telemetry-three-tiers.md) | Fabric capacity telemetry: three tiers, metrics-model scrape for attribution | Accepted | 2026-06-12 |
| [0008](0008-platform-telemetry-identities.md) | Platform telemetry identities baked into capacity deployment templates | Accepted | 2026-06-12 |
| [0009](0009-commitment-chargeback-effectivecost.md) | Commitment chargeback on EffectiveCost; unused is a period variance | Accepted | 2026-06-12 |
| [0010](0010-system-table-hybrid-synthesis.md) | Databricks system-table test data: generate small, synthesize the rest | Accepted | 2026-06-12 |
| [0011](0011-schema-contract-unofficial-sources.md) | Unofficial sources get a version-pinned schema contract | Accepted | 2026-06-12 |
