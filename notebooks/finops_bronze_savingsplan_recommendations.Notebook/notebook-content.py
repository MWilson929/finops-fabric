# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "PLACEHOLDER_LAKEHOUSE_ID",
# META       "default_lakehouse_name": "FinOpsHub",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
# META     }
# META   }
# META }

# CELL ********************

# # finops_bronze_savingsplan_recommendations
#
# **Purpose**: Lands the shared-scope savings plan recommendation and all alternative commitment levels (coverage / savings / wastage per level) at MCA billing-profile scope, per tenant, for both terms.
#
# **Domain**: finops
# **Schema**: bronze
#
# **Inputs**:
# - Azure Cost Management `benefitRecommendations` API (api-version 2025-03-01), billing-profile scope, `$expand=properties/allRecommendationDetails`
#
# **Output**: `bronze.benefits_recommendations`
#
# **Parameters** (pipeline via Variable Library):
# - `tenants` (string, "" = all configured prefixes)
# - `lookback` (string, "Last60Days")
#
# **Trigger**: monthly pipeline, alongside `finops_bronze_benefits_usage`
#
# ---
#
# Built on **finops-core**: config, secrets, ARM auth/pagination (`finops_core.arm`) and Delta writes come from the library; only the Benefit Recommendations specifics live here.
#
# This is the **purchase-decision** dataset: shared-scope recommendations benefit from diversification across subscriptions, so commitment sizing happens here — the per-subscription usage series (`bronze.benefits_usage`) is for visibility and allocation, not sizing. Both P1Y and P3Y are fetched each run so the term trade-off is always current.
#
# One row per (tenant, term, alternative commitment level), with `is_recommended` flagging the engine's pick. Snapshot-append per run date; the snapshot history is what lets you compare `wastage_cost` *predicted* here against *realized* unused commitment in FOCUS (`CommitmentDiscountStatus = 'Unused'`).
#
# **Variable Library additions required**: `{prefix}_billing_scope` per tenant, e.g. `providers/Microsoft.Billing/billingAccounts/{baId}/billingProfiles/{bpId}` (MCA) or `providers/Microsoft.Billing/billingAccounts/{enrollmentId}` (EA). Tenants without it are skipped with a warning.

# CELL ********************

%%configure -f
{
    "vCores": 4
}

# CELL ********************

# Install finops-core from the Azure DevOps Artifact feed (PAT resolved from Key Vault),
# then azure-identity from public PyPI.
_lib = notebookutils.variableLibrary.getLibrary("VariableLib")
_feed_pat = notebookutils.credentials.getSecret(_lib.key_vault_url, _lib.ado_feed_pat_secret_name)
get_ipython().run_line_magic(
    "pip",
    "install finops-core "
    f"--index-url=https://feed:{_feed_pat}@pkgs.dev.azure.com/"
    f"{_lib.ado_organization}/{_lib.ado_project}/_packaging/{_lib.ado_artifactory_feed}/pypi/simple/",
)
del _feed_pat

%pip install azure-identity --quiet

# CELL ********************

import logging
from datetime import datetime, timezone

import polars as pl
from azure.identity import ClientSecretCredential

from finops_core import (
    arm_client,
    get_secret,
    get_var,
    load_variable_library,
    paginate_arm,
    write_delta,
)

logger = logging.getLogger(__name__)

# PARAMETERS CELL ********************

tenants = ""             # "" = all configured tenant prefixes; or "a" / "a,b"
lookback = "Last60Days"  # Last7Days | Last30Days | Last60Days

# CELL ********************

# ## 1. Configuration
#
# Config-driven tenancy (CarbonEmissions_v2 pattern), plus the per-tenant `{prefix}_billing_scope` this notebook additionally requires.

# CELL ********************

API_VERSION = "2025-03-01"
TENANT_PREFIXES = ["a", "b"]
PLACEHOLDER_GUID = "00000000-0000-0000-0000-000000000000"
TERMS = ["P1Y", "P3Y"]

VariableLib = load_variable_library("VariableLib")
key_vault_url = get_var(VariableLib, "key_vault_url")
finopshub_root_path = get_var(VariableLib, "finopshub_root_path")
recommendations_table_path = f"{finopshub_root_path.rstrip('/')}/bronze/benefits_recommendations"

if lookback not in ("Last7Days", "Last30Days", "Last60Days"):
    raise ValueError(f"Invalid lookback: '{lookback}'")

requested_prefixes = [p.strip().lower() for p in tenants.split(",") if p.strip()]
unknown = set(requested_prefixes) - set(TENANT_PREFIXES)
if unknown:
    raise ValueError(f"Unknown tenant prefix(es) {sorted(unknown)}. Known: {TENANT_PREFIXES}")

tenant_configs = []
for prefix in TENANT_PREFIXES:
    tenant_id = get_var(VariableLib, f"{prefix}_tenant_id", "")
    client_id = get_var(VariableLib, f"{prefix}_client_id", "")
    secret_name = get_var(VariableLib, f"{prefix}_secret_name", "")
    billing_scope = get_var(VariableLib, f"{prefix}_billing_scope", "")

    configured = all([tenant_id, client_id, secret_name]) and tenant_id != PLACEHOLDER_GUID
    if not configured:
        logger.info("Tenant '%s' not configured in Variable Library - skipping", prefix)
        continue
    if requested_prefixes and prefix not in requested_prefixes:
        continue
    if not billing_scope:
        logger.warning("Tenant '%s' configured but %s_billing_scope missing - skipping", prefix, prefix)
        continue
    tenant_configs.append({
        "prefix": prefix,
        "label": f"Tenant {prefix.upper()}",
        "tenant_id": tenant_id,
        "client_id": client_id,
        "secret_name": secret_name,
        "billing_scope": billing_scope.strip("/"),
    })

if not tenant_configs:
    raise ValueError(f"No configured tenants with billing scopes match request '{tenants}'")

logger.info("Tenants in scope: %s | lookback=%s terms=%s", [c["label"] for c in tenant_configs], lookback, TERMS)

# CELL ********************

# ## 2. Fetch Recommendations per Tenant and Term
#
# Billing-profile scope returns the Shared-scope recommendation (no per-subscription split — by design). Each alternative in `allRecommendationDetails` becomes a row; `is_recommended` marks the engine's pick by matching `recommendationDetails.commitmentAmount`.

# CELL ********************

def tenant_arm_client(cfg):
    credential = ClientSecretCredential(
        tenant_id=cfg["tenant_id"],
        client_id=cfg["client_id"],
        client_secret=get_secret(key_vault_url, cfg["secret_name"]),
    )
    return arm_client(credential)

ingestion_ts = datetime.now(timezone.utc)
snapshot_date = ingestion_ts.date()
rows = []

for cfg in tenant_configs:
    client = tenant_arm_client(cfg)
    scope_path = f"/{cfg['billing_scope']}/providers/Microsoft.CostManagement/benefitRecommendations"

    for term in TERMS:
        recs = list(paginate_arm(client, scope_path, params={
            "api-version": API_VERSION,
            "$expand": "properties/allRecommendationDetails",
            "$filter": f"properties/lookBackPeriod eq '{lookback}' AND properties/term eq '{term}'",
        }))
        if not recs:
            logger.warning("%s %s: no recommendation returned", cfg["label"], term)
            continue
        if len(recs) > 1:
            logger.warning("%s %s: %d recommendations returned, using first", cfg["label"], term, len(recs))

        props = recs[0]["properties"]
        recommended_amount = (props.get("recommendationDetails") or {}).get("commitmentAmount")
        alternatives = ((props.get("allRecommendationDetails") or {}).get("value")) or []
        if not alternatives:
            logger.warning("%s %s: recommendation has no alternatives list", cfg["label"], term)
            continue

        for alt in alternatives:
            rows.append({
                "tenant_id": cfg["tenant_id"],
                "tenant_label": cfg["label"],
                "billing_scope": cfg["billing_scope"],
                "recommendation_scope": props.get("scope"),
                "term": props.get("term"),
                "look_back_period": props.get("lookBackPeriod"),
                "currency_code": props.get("currencyCode"),
                "arm_sku_name": props.get("armSkuName"),
                "first_consumption_date": props.get("firstConsumptionDate"),
                "last_consumption_date": props.get("lastConsumptionDate"),
                "total_hours": props.get("totalHours"),
                "cost_without_benefit": props.get("costWithoutBenefit"),
                "commitment_amount": alt.get("commitmentAmount"),
                "coverage_percentage": alt.get("coveragePercentage"),
                "average_utilization_percentage": alt.get("averageUtilizationPercentage"),
                "benefit_cost": alt.get("benefitCost"),
                "overage_cost": alt.get("overageCost"),
                "savings_amount": alt.get("savingsAmount"),
                "savings_percentage": alt.get("savingsPercentage"),
                "total_cost": alt.get("totalCost"),
                "wastage_cost": alt.get("wastageCost"),
                "is_recommended": alt.get("commitmentAmount") == recommended_amount,
            })
        logger.info("%s %s: %d alternatives (recommended commitment %s/hr)",
                    cfg["label"], term, len(alternatives), recommended_amount)

logger.info("Total: %d alternative rows", len(rows))

# CELL ********************

# ## 3. Write Snapshot — `bronze.benefits_recommendations`
#
# `finops_core.write_delta` with `replace_where` on `snapshot_date` — snapshot-append per run date, same-day rerun replaces (idempotent), table creation handled. The accumulated snapshots are the predicted-wastage history for the forecast-vs-actual variance loop.

# CELL ********************

if not rows:
    raise RuntimeError("No recommendations retrieved from any tenant — failing loudly rather than writing an empty snapshot")

df = pl.from_dicts(rows).with_columns(
    pl.lit(ingestion_ts).alias("ingestion_timestamp"),
    pl.lit(f"benefitRecommendations api-version={API_VERSION}").alias("source_file"),
    pl.lit(snapshot_date).alias("snapshot_date"),
)

write_delta(
    df,
    recommendations_table_path,
    replace_where=f"snapshot_date = '{snapshot_date}'",
    partition_by=["snapshot_date"],
)

logger.info("Written %d rows to bronze.benefits_recommendations, snapshot_date=%s", len(df), snapshot_date)

# CELL ********************

# ## 4. Diagnostics
#
# The commitment lever, per tenant and term — the same table the steering-meeting conversation runs on.

# CELL ********************

display(
    df.select([
        "tenant_label", "term", "is_recommended", "commitment_amount",
        "coverage_percentage", "savings_percentage", "wastage_cost",
        "average_utilization_percentage",
    ]).sort(["tenant_label", "term", "commitment_amount"])
)
