# AI Endpoint Prompt-Caching Billing Test — Results

**Date:** 2026-06-12 (test) / 2026-06-13 (billing readout)
**Question:** Is Azure Foundry's published 90% cached-input discount real, and does Databricks have an equivalent? Worked-example arithmetic predicted +73% on Databricks for a 75%-cache-hit agentic workload at identical headline list rates.
**Verdict:** Confirmed — Foundry caches and bills cached input at 1/10 the fresh rate; Databricks Foundation Model APIs have no cached-input billing SKU.

## Test setup

- **Foundry**: `aiprice-fdy-mw929` (Azure AI Services, East US 2), deployment `gpt-54-test` (gpt-5.4 2026-03-05, DataZoneStandard). gpt-5.5 / gpt-5.4 GlobalStandard quota was 0; DataZone used.
- **Databricks**: workspace `dbx-aiprice-mw929` (Premium, East US 2), pay-per-token endpoint `databricks-gpt-oss-120b`. Claude endpoint `databricks-claude-opus-4-8` was blocked by a fresh-workspace partner-model "rate limit of 0" — fallback to gpt-oss-120b.
- **Workload**: 10 sequential calls per side, identical shape — ~2,500-token static prefix (system prompt + 60 rules) + small varying question. `max_tokens=60`. Script: `scratch/caching_test.py`.

## Phase 1 — API usage fields (2026-06-12)

| Side | Prompt tokens / call | `cached_tokens` from call 2 | Total cached |
|---|---|---|---|
| Foundry gpt-5.4 | 5,693 | **5,504 (~97%)** | 55,040 / 56,930 |
| Databricks gpt-oss-120b | 5,769 | **0** (every call) | 0 / 57,690 |

Both responses populated `usage.prompt_tokens_details.cached_tokens` — Databricks reports the field for OpenAI-compatibility, but the value is zero on every call. (Cache may engage internally; it isn't surfaced to billing.)

## Phase 2 — Billing readout (2026-06-13)

Two test runs hit each side overnight; billing aggregates both. Currency GBP, account FX.

### Foundry — Azure Cost Management (per ResourceGroup query)

| Meter | Quantity (M tokens) | Cost | Effective £/1M tokens |
|---|---|---|---|
| `5.4 cd inp Dz` (cached input) | 0.104576 | £0.0214 | **£0.205** |
| `5.4 inp Dz` (fresh input) | 0.009284 | £0.0190 | £2.049 |
| `5.4 opt Dz` (output) | 0.001200 | £0.0148 | £12.30 |

**Cached input is its own billable SKU.** The cached:fresh rate ratio is exactly 1:10 (£0.205 / £2.049 = 0.100). At account FX, all three rates land within ~3% of Microsoft's published gpt-5.4 USD list price ($0.25 / $2.50 / $15.00 per 1M for cached/input/output) — independently confirming ADR-0005 (uniform-EDP scalar) for this meter family.

### Databricks — `system.billing.usage` + `list_prices` join

| `billing_origin_product` | DBUs | List $/DBU | Estimated $ | Invoice (GBP) |
|---|---|---|---|---|
| MODEL_SERVING (both runs, gpt-oss-120b) | 0.1292 | $0.07 | $0.0090 | £0.00674 |

The MODEL_SERVING line is **a single DBU rate**, no cached/fresh split. We inspected the full `usage_metadata` struct on each billing row (~50 fields including `endpoint_name`, `endpoint_id`, `cluster_id`, etc.) — there is no `cached_tokens` or equivalent dimension. The billing pipeline doesn't see cached tokens because there's no SKU to bill them against.

## What this proves (and what it doesn't)

**Mechanism — proven:**
1. Foundry charges separately for cached input, at exactly 1/10 of the fresh-input rate.
2. Databricks pay-per-token has no cached-input SKU in `system.billing.list_prices` and no cached dimension in `system.billing.usage` rows.
3. EDP applies uniformly to both meter families at list-equivalent rates (consistent with ADR-0005).

**Which platform is cheaper for the same model — NOT proven by this run.** The Claude endpoint was rate-limit blocked on the fresh workspace, forcing us onto `databricks-gpt-oss-120b` (an open-weight model) while Foundry ran gpt-5.4 (a frontier model). The absolute pound figures (Databricks £0.007 vs Foundry £0.055) reflect that model-class gap, not the platform gap, and **must not be quoted as platform-comparison evidence**.

The thesis still holds via arithmetic: at identical list rates (Anthropic's pass-through pricing being the cleanest case), the Foundry+caching path costs less than Databricks for cache-heavy workloads because the cached-input SKU exists on one side and not the other. The +73% worked example is the magnitude; this test is the mechanism evidence; a like-for-like re-run against `databricks-claude-opus-4-8` (after the account-console rate-limit toggle) would close the loop empirically.

## For the report

- Lead with the mechanism finding: agentic workloads (large static prefixes, high cache-hit rate) take a structural penalty on Databricks pay-per-token that Foundry avoids by design.
- Quote the +73% worked example as the magnitude; cite this test as the mechanism evidence; mark the like-for-like cost ratio as "verify against Claude endpoint."
- The Foundry rate-ladder proof (£0.205 / £2.049 / £12.30 in 1:10:60 ratio at list FX) is the cleanest single fact to put in front of stakeholders.

## Total test spend

- Foundry: £0.055 (six meters across two runs)
- Databricks DBUs: £0.974 (~94% of which is the SQL serverless warehouse used to read the answer; MODEL_SERVING itself was £0.007)
- **Total: ~£1.03**
