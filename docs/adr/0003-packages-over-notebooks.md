# ADR-0003 — Shared plumbing lives in versioned packages, threshold of three

**Status:** Accepted · **Date:** 2026-06-10 (records earlier practice; arm module extraction 2026-06-12)

## Context

Ingestion notebooks repeat the same concerns: config, secrets, authenticated REST with retry/pagination, Polars assembly, Delta writes. Copy-paste across notebooks drifts; premature packaging adds release coordination for code used once.

## Decision

Shared code is packaged (`finops-core`, API-agnostic; `ghcopilot-finops`, source-specific) and published to the ADO Artifact feed with lockstep versioning from repo-root `v*` tags. The threshold is **three consumers**: a function used in one or two notebooks stays in the notebook; the third consumer triggers extraction. Notebooks are thin consumers installing trusted versions from the feed.

Applied 2026-06-12: ARM subscription discovery and throttle-aware paging reached three consumers (Carbon, Resource Graph, Benefit Recommendations) and moved into `finops_core.arm` — designed around discovery + paging primitives, not "the loop", because consumers batch differently (Carbon: 100/request; benefits: one-by-one; ARG: whole list).

## Consequences

- Reproducible notebook behaviour; testable plumbing (pytest off-platform; `notebookutils` resolved lazily).
- A release step (tag → pipeline → feed) sits between fixing shared code and notebooks consuming the fix.
- The threshold is judged, not enforced — review must watch for the third copy-paste.
