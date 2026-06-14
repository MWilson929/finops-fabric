# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "PLACEHOLDER_WORKSPACE_ID",
# META       "default_lakehouse_name": "FinOpsHub",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
# META     }
# META   }
# META }

# CELL ********************

# # finops_bronze_benefits_usage
#
# **Purpose**: Lands the hourly savings-plan-eligible PAYG usage series per subscription from the Cost Management Benefit Recommendations API, across all configured tenants.
#
# **Domain**: finops
# **Schema**: bronze
#
# **Inputs**:
# - Azure Cost Management `benefitRecommendations` API (api-version 2025-03-01), subscription scope, `$expand=properties/usage`
# - ARM `subscriptions` API for per-tenant subscription discovery
#
# **Output**: `bronze.benefits_usage`
#
# **Parameters** (pipeline via Variable Library):
# - `tenants` (string, "" = all configured; or comma-separated prefixes e.g. "a,b")
# - `lookback` (string, "Last60Days"), `term` (string, "P3Y")
#
# **Trigger**: monthly pipeline (hard requirement — the API only looks back 60 days, so a gap of >60 days between successful runs loses hourly history permanently)
#
# ---
#
# Built on **finops-core**: config, secrets, ARM auth/pagination/subscription discovery (`finops_core.arm`) and Delta writes come from the library; only the Benefit Recommendations specifics live here.
#
# Each run snapshots up to 60 days of hourly eligible on-demand charges per subscription. Runs **append** with a `snapshot_date` discriminator (LAKEHOUSE_TABLES.md snapshot pattern) — overlapping windows are kept deliberately, because Azure restates late-arriving usage and overlap disagreements reveal eligibility-basis changes. Silver dedupes to the latest snapshot per hour. Same-day reruns replace that day's snapshot (idempotent).
#
# The per-subscription `usage` series sum cleanly across subscriptions; the *recommendations* do not (single-scope forgoes shared-scope diversification) — commitment decisions come from `finops_bronze_benefits_recommendations` at billing-profile scope.

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
from datetime import datetime, timedelta, timezone

import polars as pl
from azure.identity import ClientSecretCredential

from finops_core import (
    arm_client,
    get_secret,
    get_var,
    list_subscriptions,
    load_variable_library,
    paginate_arm,
    write_delta,
)

logger = logging.getLogger(__name__)

# PARAMETERS CELL ********************

tenants = ""          # "" = all configured tenant prefixes; or "a" / "a,b"
lookback = "Last60Days"  # Last7Days | Last30Days | Last60Days
term = "P3Y"          # P1Y | P3Y (affects recommendation, not the usage series shape)

# CELL ********************

# ## 1. Configuration
#
# Config-driven tenancy (CarbonEmissions_v2 pattern): every tenant prefix with populated Variable Library entries is included; placeholders are skipped; the `tenants` parameter filters.

# CELL ********************

API_VERSION = "2025-03-01"
TENANT_PREFIXES = ["a", "b"]
PLACEHOLDER_GUID = "00000000-0000-0000-0000-000000000000"

VariableLib = load_variable_library("VariableLib")
key_vault_url = get_var(VariableLib, "key_vault_url")
finopshub_root_path = get_var(VariableLib, "finopshub_root_path")
usage_table_path = f"{finopshub_root_path.rstrip('/')}/bronze/benefits_usage"

if lookback not in ("Last7Days", "Last30Days", "Last60Days"):
    raise ValueError(f"Invalid lookback: '{lookback}'")
if term not in ("P1Y", "P3Y"):
    raise ValueError(f"Invalid term: '{term}'")

requested_prefixes = [p.strip().lower() for p in tenants.split(",") if p.strip()]
unknown = set(requested_prefixes) - set(TENANT_PREFIXES)
if unknown:
    raise ValueError(f"Unknown tenant prefix(es) {sorted(unknown)}. Known: {TENANT_PREFIXES}")

tenant_configs = []
for prefix in TENANT_PREFIXES:
    tenant_id = get_var(VariableLib, f"{prefix}_tenant_id", "")
    client_id = get_var(VariableLib, f"{prefix}_client_id", "")
    secret_name = get_var(VariableLib, f"{prefix}_secret_name", "")

    configured = all([tenant_id, client_id, secret_name]) and tenant_id != PLACEHOLDER_GUID
    if not configured:
        logger.info("Tenant '%s' not configured in Variable Library - skipping", prefix)
        continue
    if requested_prefixes and prefix not in requested_prefixes:
        continue
    tenant_configs.append({
        "prefix": prefix,
        "label": f"Tenant {prefix.upper()}",
        "tenant_id": tenant_id,
        "client_id": client_id,
        "secret_name": secret_name,
    })

if not tenant_configs:
    raise ValueError(f"No configured tenants match request '{tenants}'")

logger.info("Tenants in scope: %s | lookback=%s term=%s", [c["label"] for c in tenant_configs], lookback, term)

# CELL ********************

# ## 2. Fetch Hourly Usage per Subscription
#
# ARM auth, throttle-aware retries, `nextLink` pagination and subscription discovery all come from `finops_core.arm`. Subscription-scope call with `$expand=properties/usage`; hourly timestamps are reconstructed from `firstConsumptionDate` + index, with a hard assert that `totalHours` matches the series length. Subscriptions with no eligible usage return no recommendations and are skipped with a log line.

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
    subscriptions = list_subscriptions(client)
    logger.info("%s: %d subscriptions", cfg["label"], len(subscriptions))

    for sub in subscriptions:
        sub_id, sub_name = sub["subscriptionId"], sub["displayName"]
        recs = list(paginate_arm(
            client,
            f"/subscriptions/{sub_id}/providers/Microsoft.CostManagement/benefitRecommendations",
            params={
                "api-version": API_VERSION,
                "$expand": "properties/usage",
                "$filter": f"properties/lookBackPeriod eq '{lookback}' AND properties/term eq '{term}'",
            },
        ))

        if not recs:
            logger.info("  %s (%s): no eligible usage / no recommendation", sub_name, sub_id)
            continue
        if len(recs) > 1:
            logger.warning("  %s: %d recommendations returned, using first", sub_name, len(recs))

        props = recs[0]["properties"]
        charges = (props.get("usage") or {}).get("charges") or []
        if not charges:
            logger.info("  %s (%s): recommendation has no usage series", sub_name, sub_id)
            continue

        first_hour = datetime.fromisoformat(props["firstConsumptionDate"].replace("Z", "+00:00"))
        total_hours = props.get("totalHours")
        if total_hours is not None and total_hours != len(charges):
            raise ValueError(
                f"{sub_id}: totalHours {total_hours} != charges length {len(charges)} — timestamp reconstruction unsafe"
            )

        for i, charge in enumerate(charges):
            rows.append({
                "tenant_id": cfg["tenant_id"],
                "tenant_label": cfg["label"],
                "subscription_id": sub_id,
                "subscription_name": sub_name,
                "hour_utc": first_hour + timedelta(hours=i),
                "hourly_charge": float(charge),
                "currency_code": props.get("currencyCode"),
                "recommendation_scope": props.get("scope"),
                "look_back_period": props.get("lookBackPeriod"),
                "term": props.get("term"),
            })
        logger.info("  %s: %d hourly records (%s -> %s)", sub_name, len(charges),
                    props["firstConsumptionDate"], props["lastConsumptionDate"])

logger.info("Total: %d hourly records across tenants", len(rows))

# CELL ********************

# ## 3. Write Snapshot — `bronze.benefits_usage`
#
# `finops_core.write_delta` with `replace_where` on `snapshot_date`: appends this run as a new snapshot, a same-day rerun replaces it (idempotent), and table creation with partitioning is handled. Standard bronze audit columns per LAKEHOUSE_TABLES.md.

# CELL ********************

if not rows:
    raise RuntimeError("No usage data retrieved from any tenant — failing loudly rather than writing an empty snapshot")

df = pl.from_dicts(rows).with_columns(
    pl.lit(ingestion_ts).alias("ingestion_timestamp"),
    pl.lit(f"benefitRecommendations api-version={API_VERSION}").alias("source_file"),
    pl.lit(snapshot_date).alias("snapshot_date"),
)

write_delta(
    df,
    usage_table_path,
    replace_where=f"snapshot_date = '{snapshot_date}'",
    partition_by=["snapshot_date"],
)

logger.info("Written %d rows to bronze.benefits_usage, snapshot_date=%s", len(df), snapshot_date)

# CELL ********************

# ## 4. Continuity Check
#
# Gaps in this dataset are **permanently unrecoverable** (60-day API window). Compares this snapshot's start against the previous snapshots' coverage per subscription and fails the run — loudly, for the pipeline to alert on — if a gap has opened.

# CELL ********************

existing = pl.scan_delta(usage_table_path).filter(pl.col("snapshot_date") < snapshot_date)
prior_max = existing.group_by("subscription_id").agg(pl.col("hour_utc").max().alias("prior_max_hour")).collect()

if prior_max.is_empty():
    logger.info("First snapshot — no continuity to check")
else:
    new_min = df.group_by("subscription_id").agg(pl.col("hour_utc").min().alias("new_min_hour"))
    gaps = (
        prior_max.join(new_min, on="subscription_id", how="inner")
        .with_columns((pl.col("new_min_hour") - pl.col("prior_max_hour")).dt.total_hours().alias("gap_hours"))
        .filter(pl.col("gap_hours") > 1)
    )
    if gaps.is_empty():
        logger.info("Continuity OK: all %d previously-seen subscriptions overlap or abut", len(prior_max))
    else:
        display(gaps)
        raise RuntimeError(
            f"Hourly continuity broken for {len(gaps)} subscription(s) — "
            "data in the gap is unrecoverable; investigate run cadence"
        )

display(
    df.group_by(["tenant_label", "subscription_name"]).agg(
        pl.len().alias("hours"),
        pl.col("hour_utc").min().alias("from"),
        pl.col("hour_utc").max().alias("to"),
        pl.col("hourly_charge").sum().alias("total_eligible_charge"),
    ).sort(["tenant_label", "subscription_name"])
)
