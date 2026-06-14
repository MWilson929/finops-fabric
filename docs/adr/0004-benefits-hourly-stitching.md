# ADR-0004 — Stitch Benefit Recommendations hourly usage; size at shared scope

**Status:** Accepted · **Date:** 2026-06-12

## Context

The Cost Management Benefit Recommendations API exposes the hourly savings-plan-eligible PAYG usage series the recommendation engine itself analyses — the only hourly cost-shaped signal Azure offers — but with a hard 60-day lookback. It also returns alternative commitment levels (coverage/savings/wastage per level), not just the headline number. Recommendations at subscription scope are **not additive**: single-scope commitments forgo cross-subscription diversification.

## Decision

Two ingestions, two purposes:

1. `bronze.savingsplan_usage` — per-subscription hourly series, fetched **monthly** (gap > 60 days is permanently unrecoverable; a continuity check fails the run loudly), snapshot-append with `snapshot_date`. Purpose: visibility and a multi-year hourly demand profile; the per-subscription *usage* sums cleanly even though recommendations don't.
2. `bronze.savingsplan_recommendations` — shared-scope (billing profile / EA) alternatives for both terms, `is_recommended` flagged. Purpose: the **purchase decision**, and the predicted-wastage history for forecast-vs-actual variance.

## Consequences

- Over time the platform owns a continuous hourly demand profile no Azure surface provides directly.
- Missed runs lose data forever: the monthly pipeline is a hard operational commitment with alerting.
- Eligibility-basis changes (new SKUs, scope membership) appear as step changes; overlapping snapshots make them detectable.
- Predicted `wastage_cost` vs realized FOCUS `Unused` closes the sizing feedback loop (CMT 6.2).
