# ADR-0006 — Lakehouse is the budget system of record; Azure budgets are generated guardrails

**Status:** Accepted · **Date:** 2026-06-12

## Context

Azure Cost Management budgets are flat amounts per scope per period with threshold alerts. They cannot express FY-phased profiles (Sept–Aug), budgets along the Service_ID hierarchy at ~300 nodes, coherence with the published forecast, or approval/override workflow. They are, however, zero-maintenance alerting that fires even when our platform is down.

## Decision

Budgets are modelled in the lakehouse: `gold.budget_targets` (monthly phased amounts per Service_ID node, **seeded from the reconciled forecast**, adjusted via translytical writeback) and `gold.budget_variance` (targets vs EffectiveCost actuals **and** vs rolling forecast, so breaches are predicted, not just observed). Alerting via Fabric Activator. A handful of coarse Azure guardrail budgets are **generated from** the lakehouse targets (idempotent diff-and-PUT sync, subscription scope) as the dead-man's switch — the sync direction is lakehouse → Azure, not the reverse.

## Consequences

- Budget modelling capability matches the forecast and hierarchy machinery instead of fighting Azure's flat model.
- The pipeline joins the control loop: a broken ingestion mutes fine-grained alerts. The Azure guardrails exist precisely to cover that failure mode.
- Depends on translytical writeback (UDFs), whose compatibility with tenant Private Link / blocked public access is unverified — must be tested in the locked tenant before the writeback UX is designed (see Fabric networking notes, section 8 of the handbook).
- BUD 2.3's evidence shifts from Azure budget configs to lakehouse variance + Activator history plus the generated guardrails.
