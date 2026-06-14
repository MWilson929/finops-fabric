# ADR-0001 — Service_ID tag is the allocation and forecasting hierarchy

**Status:** Accepted · **Date:** 2026-06-10

## Context

Cost allocation and forecasting need a stable organisational hierarchy. Azure's native structures (management groups, subscriptions, resource groups) don't match how the business consumes spend, and change for operational reasons unrelated to ownership. The estate already carries a `Service_ID` tag: a fixed multipart identifier `{Division}/{Platform}/{Workload}/{Component}`.

## Decision

`Service_ID` is the canonical cost hierarchy. Forecasting, allocation, and reporting key on its four levels plus a synthetic grand total (total → division → platform → workload → component). Costs with a missing or malformed tag map to an `Untagged/Untagged/Untagged/Untagged` bucket rather than being dropped or smeared.

## Consequences

- Totals always reconcile to billing; the Untagged bucket's size doubles as a tagging-hygiene KPI (TAG 4.4).
- ~300 components → ~500–600 series across all levels: comfortably single-node for modelling.
- Everything downstream inherits the tag's quality; tag governance (tagging_policy.md, PRJ 10.3) is load-bearing for the whole platform.
- Subscription-level views remain available from FOCUS but are secondary.
