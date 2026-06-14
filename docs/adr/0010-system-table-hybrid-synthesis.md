# ADR-0010 — Databricks system-table test data: generate small, synthesize the rest

**Status:** Accepted · **Date:** 2026-06-12

## Context

Development of Databricks cost analysis (target: the `cloud-infra-costs` FOCUS query, which reads seven system tables) requires representative system-table data. Production system tables are not accessible from the development environment, and the vendor publishes no sample data. Fully synthetic data risks inventing schema and semantics; generating everything for real means provisioning heavyweight features (vector search, Lakebase, monitoring) for marginal realism.

## Decision

Hybrid, in a disposable test workspace:

1. **Generate real rows cheaply** for the common categories: MODEL_SERVING (endpoint calls), SQL (serverless warehouse), JOBS (trivial serverless job), ALL_PURPOSE (short-lived single-node cluster) — jobs and clusters carry `Service_ID`-style custom tags so the `custom_tags` map is realistic, while serving/warehouse rows are untagged (realistically imperfect coverage).
2. **Take the freebies**: `list_prices` and `account_prices` populate with the full price list regardless of usage; `workspaces_latest`, `compute.warehouses` etc. populate as a side effect.
3. **Synthesize the exotic categories** (VECTOR_SEARCH, LAKEHOUSE_MONITORING, PREDICTIVE_OPTIMIZATION, ONLINE_TABLES, AI_GATEWAY, DATABASE) by perturbing the real template rows, with SKU names drawn from `list_prices` for internal consistency, into a `dev_system` clone catalogue (the `system` catalogue is read-only). The FOCUS query targets the clone via its catalogue reference.
4. In synthesis, fake a discount delta in `account_prices` to mirror corporate reality (contracted-vs-list columns hinge on it).

## Consequences

- Schema and semantics are anchored in vendor-real rows; only volumes and rare categories are invented.
- New-metastore system-table ingestion lags hours — sample harvesting waits for it; the workspace must not be torn down before harvest.
- The synthesis tooling mirrors the existing Azure-side pattern (`focus_cost_synthesise.ipynb`), keeping one mental model for "fake data with real shape".
