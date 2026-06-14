# ADR-0008 — Platform telemetry identities baked into capacity deployment templates

**Status:** Accepted · **Date:** 2026-06-12

## Context

The attribution scrape (ADR-0007) needs the Capacity Metrics app to see every capacity, which requires its refresh identity to be capacity admin on each. Granting capacity admin to named individuals fails the leaver test and requires per-capacity agreement that does not scale. A federated alternative — scraping each capacity owner's own app install via per-model read grants — was considered and **rejected**: it makes every owner's app hygiene (refresh schedules, versions, continued existence) an upstream dependency of the telemetry pipeline.

Decisive fact: all capacities are deployed from platform-owned templates, and the platform deployment identity already holds ARM control (scale/pause/delete) of every capacity resource. Verified: F SKU capacity administrators may be service principals or managed identities (portal and ARM `properties.administration.members`).

## Decision

The standard capacity deployment template includes two standing administrators: the **FinOps service account** (user identity — owns and refreshes the consolidated metrics app, since the app connector requires interactive OAuth) and the **FinOps service principal** (programmatic reader; ARM usages tier). Codified as control **SVC-FAB 1.1**; identities are declared telemetry-only.

## Consequences

- Telemetry coverage is a property of deployment; capacities onboard by existing.
- Marginal privilege granted is near nil (existing ARM control already exceeds it), and the grant is codified as written policy (SVC-FAB 1.1) rather than per-capacity agreement.
- The service account needs a licence, a conditional-access carve-out for non-interactive refresh, and a named owner — standard service-account governance.
- Existing capacities need one template reconciliation pass to backfill the identities.
