# ADR-0011 — Unofficial sources get a version-pinned schema contract

**Status:** Accepted · **Date:** 2026-06-12

## Context

Some required data has no supported API and is extracted from surfaces that can change without notice — the Capacity Metrics app's internal semantic model (ADR-0007) being the first. Community-documented schemas proved wrong in detail against the live model (table and column names differ by app version). Silent schema drift in such sources produces silently wrong data, which is worse than no data.

## Decision

Every ingestion from an unofficial surface carries an explicit, version-pinned **schema contract** in its configuration: the exact tables/columns/identifiers it depends on (`EXPECTED_SCHEMA`), the queries built from them, and a pinned source version string. On every run, **before extraction**, the contract is validated against the live source; violations fail the run with a printed diff of expected vs actual. Upgrades of the source become a deliberate recalibration: read the diff, adjust the contract, bump the pin.

Calibration is done against the live source, not documentation — for semantic models, DAX `INFO.VIEW.TABLES()`/`INFO.VIEW.COLUMNS()` via `executeQueries` enumerates the real schema in one call.

## Consequences

- Source upgrades convert from silent corruption into an explicit, fast fix (diff in hand, one config edit).
- Slight run overhead and a maintenance ritual per source upgrade — accepted as the price of unsupported surfaces.
- The pattern is mandatory for future unofficial sources (their notebooks should cite this ADR), and pairs with freshness/continuity gates where source retention makes gaps unrecoverable.
