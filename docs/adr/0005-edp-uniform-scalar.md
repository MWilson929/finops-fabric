# ADR-0005 — EDP treated as a uniform scalar in cross-platform AI price comparison

**Status:** Accepted · **Date:** 2026-06-12

## Context

The AI endpoint price comparison (Azure Foundry vs GCP Vertex vs Azure Databricks) initially assumed per-channel discount modelling would be needed. Contractual confirmation: the Azure EDP applies at the same rate to almost all Azure consumption **including Databricks DBUs**, with exactly two contractual exceptions, both unrelated to AI billing channels.

## Decision

The comparison treats Azure-side discounts as a single scalar (`effective = list × (1 − EDP)`) applied uniformly, footnoted once. The report is built at list prices. A uniform discount cancels out of any Azure-vs-Azure comparison; remaining deltas are **structural**: cached-input and batch billing mechanics, open-weight hosting margins, and currency conversion. GCP's negotiated position is handled separately as the one genuine discount asymmetry.

## Consequences

- The report avoids a per-meter discount model that would add complexity without changing any ranking.
- Frontier-model rate cards (priced for parity by providers) are known to be uninformative; investigation concentrates on caching/batch mechanics — empirically tested, not read off rate cards (Foundry caches and discounts cached input ~90%; Databricks pay-per-token reported zero cached tokens on identical workloads, phase-2 billing confirmation pending).
- If either contractual exception ever changes to touch an AI channel, this ADR is invalidated and per-channel modelling returns.
- Databricks "external models" (BYO provider key) bill provider-direct, bypassing Azure entirely — invisible to FOCUS; shadow-spend ingestion from provider usage APIs is a known gap.
