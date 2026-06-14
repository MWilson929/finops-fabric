# ADR-0002 — Forecast every hierarchy level, reconcile with MinT

**Status:** Accepted · **Date:** 2026-06-10

## Context

With a fixed cost hierarchy (ADR-0001), forecasts must be coherent: children must sum to parents, or drill-down in reports visibly breaks. Two pure options exist — bottom-up (forecast components only, sum upward: trivially coherent but parents inherit component noise) or independent per-level forecasts (each level gets the best model for its own smoother signal, but levels disagree).

## Decision

Forecast **every** level directly (MSTL + AutoARIMA via StatsForecast), then reconcile with **MinTrace (mint_shrink, nonnegative)** via Nixtla `hierarchicalforecast`, keeping **BottomUp** alongside as the trivially-coherent baseline, distinguished by `model_id`. A walk-forward backtest (WAPE by level and horizon) adjudicates which reconciler is published; the coherence check (total vs sum of components ≈ 0) is the standing validation.

## Consequences

- Power BI drill-down always adds up, for any published reconciler.
- MinT requires insample fitted values (residual covariance), which constrains the fitting calls (`fitted=True`) and the per-window reconciliation in backtests.
- Model choice is evidence-based and revisitable: the backtest harness, not opinion, picks the winner.
- Component-level series include genuine zero-cost days; MAPE is unreliable below division level — WAPE is the platform's headline accuracy metric.
