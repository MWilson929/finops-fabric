"""Like-for-like Claude caching test: Foundry claude-opus-4-8 vs Databricks
databricks-claude-opus-4-8, both via Anthropic Messages API with explicit
cache_control markers on the static prefix.

Anthropic's pass-through pricing makes list rates identical on both platforms,
so any pound delta in the billing is **pure platform mechanics**: does each
platform honour the cache_control marker and bill cache reads at the Anthropic-
standard 10% rate, or does it bill every input token at full rate?

Phase 1 (this script): the Anthropic API response carries
  usage.cache_creation_input_tokens
  usage.cache_read_input_tokens
which prove whether the model SERVER engaged the cache.

Phase 2 (billing readout tomorrow): the cost data proves whether the BILLING
system honoured it — separate meters/SKUs for cached input.

Usage:
    export FOUNDRY_BASE_URL=https://aiprice-fdy-mw929.services.ai.azure.com/anthropic
    export FOUNDRY_KEY=...
    export FOUNDRY_DEPLOYMENT=claude-opus-4-8
    export DATABRICKS_HOST=https://adb-...azuredatabricks.net
    export DATABRICKS_TOKEN=...
    python3 caching_test_claude.py
"""

import json
import os
import sys
import time

import requests

N_CALLS = 10
ANTHROPIC_VERSION = "2023-06-01"

# Same workload shape as the original test: ~2,500-token static prefix +
# small varying question. The cache_control marker on the system block tells
# Anthropic to cache it across requests.
STATIC_PREFIX = (
    "You are the FinOps Hub assistant for Trey Research. You answer questions about "
    "Azure cost data in the FOCUS format. Follow these rules precisely and in order. "
) + " ".join(
    f"Rule {i}: when analysing cost category {i}, always group by ServiceCategory, "
    f"then by SubAccountId, then by the Service_ID tag hierarchy level {i % 4}, and "
    f"report BilledCost for invoice reconciliation but EffectiveCost for cost-centre "
    f"allocation, never mixing the two in a single aggregate. Validate currency codes "
    f"against ISO 4217 and flag any row where ChargePeriodStart is not UTC-midnight "
    f"aligned. For commitment discounts apply treatment {i % 7} from the framework."
    for i in range(1, 61)
)

QUESTIONS = [f"In one sentence: what is rule {i * 3 + 1} about?" for i in range(N_CALLS)]


def call_endpoint(label, url, headers, model_name):
    """One conversation, 10 calls, identical shape on both platforms."""
    print(f"\n=== {label} ===")
    results = []
    for i, q in enumerate(QUESTIONS):
        body = {
            "model": model_name,
            "max_tokens": 60,
            # System block carries the cache_control marker. Anthropic format
            # requires the system field to be a list of content blocks (not a
            # plain string) for cache_control to attach.
            "system": [
                {
                    "type": "text",
                    "text": STATIC_PREFIX,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": q}],
        }
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if not r.ok:
            print(f"  call {i + 1}: HTTP {r.status_code}: {r.text[:400]}")
            sys.exit(1)
        body = r.json()
        usage = body.get("usage", {}) or {}
        row = {
            "call": i + 1,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        }
        results.append(row)
        print(
            f"  call {row['call']:>2}: "
            f"input={row['input_tokens']:>4} "
            f"cache_create={row['cache_creation_input_tokens']:>5} "
            f"cache_read={row['cache_read_input_tokens']:>5} "
            f"output={row['output_tokens']:>3}"
        )
        time.sleep(1)

    totals = {
        "input": sum(r["input_tokens"] or 0 for r in results),
        "cache_create": sum(r["cache_creation_input_tokens"] or 0 for r in results),
        "cache_read": sum(r["cache_read_input_tokens"] or 0 for r in results),
        "output": sum(r["output_tokens"] or 0 for r in results),
    }
    print(
        f"  TOTAL: input={totals['input']} "
        f"cache_create={totals['cache_create']} "
        f"cache_read={totals['cache_read']} "
        f"output={totals['output']}"
    )
    return {"calls": results, "totals": totals}


def main():
    foundry_base = os.environ["FOUNDRY_BASE_URL"].rstrip("/")
    foundry = call_endpoint(
        "Foundry claude-opus-4-8 (GlobalStandard)",
        f"{foundry_base}/v1/messages",
        {
            "x-api-key": os.environ["FOUNDRY_KEY"],
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        },
        os.environ["FOUNDRY_DEPLOYMENT"],
    )

    dbx_host = os.environ["DATABRICKS_HOST"].rstrip("/")
    dbx_endpoint = "databricks-claude-opus-4-8"
    databricks = call_endpoint(
        f"Databricks {dbx_endpoint} (pay-per-token)",
        f"{dbx_host}/serving-endpoints/{dbx_endpoint}/invocations",
        {
            "Authorization": f"Bearer {os.environ['DATABRICKS_TOKEN']}",
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        },
        dbx_endpoint,
    )

    out = {
        "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": "claude-opus-4-8 (Foundry) vs databricks-claude-opus-4-8 (Databricks)",
        "foundry": foundry,
        "databricks": databricks,
    }
    with open("caching_test_claude_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nSaved caching_test_claude_results.json — billing readout tomorrow.")


if __name__ == "__main__":
    main()
