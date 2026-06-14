# ADR-0009 — Commitment chargeback on EffectiveCost; unused is a period variance

**Status:** Accepted · **Date:** 2026-06-12

## Context

Savings plans and RIs are purchased at tenant-root/billing scope; on `BilledCost` (the invoice view) the purchase is an unallocatable lump and covered usage looks free, destroying cost-centre unit economics as commitment coverage grows. Invoice reconciliation is mandatory, so the allocation view must provably tie back to the invoice rather than coexist loosely beside it.

## Decision

Cost-centre allocation, chargeback, and unit economics use **`EffectiveCost`** (FOCUS's amortized view — commitment cost re-attributed to consuming rows hour by hour). Invoice reconciliation and cash stay on **`BilledCost`**. The two are bound by a standing monthly bridge per `CommitmentDiscountId`:

```
Invoice (Σ BilledCost) = Σ EffectiveCost allocated (Used + uncovered usage)
                       + Unused commitment (central variance line)
                       + prepayment movement (upfront-paid commitments only)
```

Accounting treatment: **expired-but-unused** commitment hours are a period cost (under-absorbed capacity variance, a named central line) — never a balance-sheet item, because the hourly benefit expires worthless. The only balance-sheet item is **unexpired** coverage on upfront-paid commitments (a genuine prepayment, amortizing as Σ EffectiveCost), including the small straddle on monthly-billed cycles that cross month-end. The bridge identity is implemented as a data-quality check (`gold.chargeback_reconciliation`): it must sum to zero or the run fails.

## Consequences

- One set of accounts: cost-centre totals + variance line + prepayment movement provably equal the invoice.
- The visible unused-variance line forces the "who eats the waste" governance decision into the open, and pairs with predicted wastage (ADR-0004) for forecast-vs-actual on commitment sizing.
- Requires the amortized-flavour FOCUS export; if `EffectiveCost` equals `BilledCost` on committed usage rows, the export is wrong and everything downstream is too — checked in ingestion.
- Whether consumers keep the discount (charged at EffectiveCost) or it's banked centrally remains a policy choice; both are computable (`ContractedCost`/`ListCost` give the counterfactual).
