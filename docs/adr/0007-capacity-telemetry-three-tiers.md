# ADR-0007 — Fabric capacity telemetry: three tiers, metrics-model scrape for attribution

**Status:** Accepted · **Date:** 2026-06-12

## Context

Fabric capacity cost in FOCUS stops at the capacity resource; chargeback needs intra-capacity attribution (which workspace/item consumed the CUs). Assessment of available surfaces: **FCA** (fabric-toolbox) is FOCUS-cost-only — its codebase never touches utilisation despite report pages named "Capacity Usage". The **Chargeback app** is a packaged report over capacity metrics with onboarding limits. A preview **ARM Capacities "List Usages" API** exists but reports capacity-level usage vs limits only. **No public API exposes item/operation-level CU consumption**; the Capacity Metrics app's semantic model is the only granular surface, and its backend endpoint is internal.

## Decision

Three tiers, by grain and access quality:

| Tier | Source | Grain |
|---|---|---|
| Money | FOCUS (already landed) | capacity × day |
| Utilisation | ARM Capacities usages API (preview; payload to verify) | capacity × point-in-time |
| Attribution | Capacity Metrics semantic-model scrape (sempy DAX) → `bronze.monitoring_capacity` | workspace/item/operation × day |

Both packaged tools (FCA, Chargeback app) are skipped: the requirement is data in the lakehouse, not another report. The scrape runs daily (14-day source retention; gaps unrecoverable) under ADR-0011's schema-contract pattern.

## Consequences

- Chargeback gets the grain it needs from the only surface that has it, at the cost of depending on an unofficial model schema (mitigated by ADR-0011).
- The metrics app itself remains in the chain: its refresh (service-account-owned, interactive OAuth — SPs cannot refresh it) is a monitored dependency with a freshness gate.
- If Microsoft ships a granular metrics API, the scrape tier is replaced and this ADR superseded — the bronze schema is designed to survive that swap.
