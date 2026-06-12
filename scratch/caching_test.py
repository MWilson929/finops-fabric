"""Empirical prompt-caching billing test: Foundry gpt-5.4 vs Databricks databricks-gpt-5-4.

Sends the same cache-heavy conversation shape to both endpoints: a large static
prefix (system prompt + tool definitions, ~2,500 tokens — well past the 1,024-token
caching threshold) with a small varying question per call. Calls run back-to-back so
the prefix is hot in cache from call 2 onward.

Phase 1 readout (immediate): usage.prompt_tokens_details.cached_tokens from both
APIs — proves whether caching ENGAGES.
Phase 2 readout (next day): Foundry cached-input meter in Azure cost data vs
Databricks system.billing.usage DBUs per token — proves whether caching is BILLED.

Usage:
    export FOUNDRY_ENDPOINT=https://<name>.cognitiveservices.azure.com
    export FOUNDRY_KEY=...
    export FOUNDRY_DEPLOYMENT=gpt-54-test
    export DATABRICKS_HOST=https://adb-....azuredatabricks.net
    export DATABRICKS_TOKEN=...
    python3 caching_test.py
"""

import json
import os
import sys
import time

import requests

N_CALLS = 10
FOUNDRY_API_VERSION = "2024-10-21"

# ~2,500 tokens of static prefix: a plausible agent system prompt + tool definitions.
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


def call_endpoint(label, url, headers, max_tokens_param):
    print(f"\n=== {label} ===")
    results = []
    for i, q in enumerate(QUESTIONS):
        body = {
            "messages": [
                {"role": "system", "content": STATIC_PREFIX},
                {"role": "user", "content": q},
            ],
            max_tokens_param: 60,
        }
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if not r.ok:
            print(f"  call {i + 1}: HTTP {r.status_code}: {r.text[:300]}")
            sys.exit(1)
        usage = r.json().get("usage", {})
        details = usage.get("prompt_tokens_details") or {}
        row = {
            "call": i + 1,
            "prompt_tokens": usage.get("prompt_tokens"),
            "cached_tokens": details.get("cached_tokens", 0),
            "completion_tokens": usage.get("completion_tokens"),
        }
        results.append(row)
        print(f"  call {row['call']:>2}: prompt={row['prompt_tokens']} "
              f"cached={row['cached_tokens']} completion={row['completion_tokens']}")
        time.sleep(1)

    total_prompt = sum(r["prompt_tokens"] or 0 for r in results)
    total_cached = sum(r["cached_tokens"] or 0 for r in results)
    pct = 100 * total_cached / total_prompt if total_prompt else 0
    print(f"  TOTAL: prompt={total_prompt} cached={total_cached} ({pct:.0f}% cached)")
    return results


def main():
    foundry_endpoint = os.environ["FOUNDRY_ENDPOINT"].rstrip("/")
    foundry_results = call_endpoint(
        "Foundry gpt-5.4 (DataZoneStandard) — control",
        f"{foundry_endpoint}/openai/deployments/{os.environ['FOUNDRY_DEPLOYMENT']}"
        f"/chat/completions?api-version={FOUNDRY_API_VERSION}",
        {"api-key": os.environ["FOUNDRY_KEY"]},
        "max_completion_tokens",
    )

    dbx_host = os.environ["DATABRICKS_HOST"].rstrip("/")
    dbx_endpoint = os.environ.get("DATABRICKS_FM_ENDPOINT", "databricks-claude-opus-4-8")
    dbx_results = call_endpoint(
        f"Databricks {dbx_endpoint} (pay-per-token)",
        f"{dbx_host}/serving-endpoints/{dbx_endpoint}/invocations",
        {"Authorization": f"Bearer {os.environ['DATABRICKS_TOKEN']}"},
        "max_tokens",
    )

    out = {"foundry": foundry_results, "databricks": dbx_results,
           "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open("caching_test_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nSaved caching_test_results.json — phase 2 (billing readout) tomorrow.")


if __name__ == "__main__":
    main()
