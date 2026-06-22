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

# # finops_bronze_dynatrace
#
# **Purpose**: Lands Dynatrace Platform Subscription **cost** and **usage** at both subscription and environment grain, plus subscription metadata, for the configured Dynatrace account — in a single OAuth-authenticated pass.
#
# **Domain**: finops
# **Schema**: bronze
#
# **Inputs** (Dynatrace Account Management / Platform Subscription API):
# - `GET /sub/v2/accounts/{accountUuid}/subscriptions` — subscription list + metadata
# - `GET /sub/v2/accounts/{accountUuid}/subscriptions/{sub}/cost` and `/sub/v3/.../environments/cost`
# - `GET /sub/v2/accounts/{accountUuid}/subscriptions/{sub}/usage` and `/sub/v2/.../environments/usage`
#
# **Outputs**: `bronze.dynatrace_subscriptions`, `bronze.dynatrace_cost`, `bronze.dynatrace_usage`
#
# **Parameters** (pipeline via Variable Library):
# - `subscription_uuids` (string, "" = all discovered)
# - `environment_ids`, `capability_keys`, `cluster_ids` (string, "" = no filter; default from Variable Library)
# - `lookback_days` (int, default 35)
#
# **Trigger**: daily pipeline.
#
# ---
#
# **Scope decisions** (reviewed June 2026): this consolidates what were five separate Dynatrace notebooks. **Forecast** and **cost-allocation** extracts were dropped — FinOps Hub forecasts and allocates cost to ServiceID itself, so Dynatrace's own forecast/allocation views are redundant. **Cost is the priority.** Both subscription and environment **grain** are landed (`grain` column): the environment grain is the granular FinOps view (environment → service), and the subscription grain is the authoritative total that also captures any cost not attributable to an environment — so the §5 reconciliation can flag residuals.
#
# Built on **finops-core**: OAuth2 client-credentials auth (`oauth2_client_credentials`), config, secrets, and Delta writes all come from the library; only the Dynatrace endpoints + response shapes live here. The account's subscription list is fetched **once** and reused, rather than re-discovered per extract.

# CELL ********************

%%configure -f
{
    "vCores": 4
}

# CELL ********************

# Install finops-core from the Azure DevOps Artifact feed (PAT resolved from Key Vault).
_lib = notebookutils.variableLibrary.getLibrary("VariableLib")
_feed_pat = notebookutils.credentials.getSecret(_lib.key_vault_url, _lib.ado_feed_pat_secret_name)
get_ipython().run_line_magic(
    "pip",
    "install finops-core "
    f"--index-url=https://feed:{_feed_pat}@pkgs.dev.azure.com/"
    f"{_lib.ado_organization}/{_lib.ado_project}/_packaging/{_lib.ado_artifactory_feed}/pypi/simple/",
)
del _feed_pat

# CELL ********************

import logging
from datetime import datetime, timedelta, timezone

import polars as pl

from finops_core import (
    get_secret,
    get_var,
    load_variable_library,
    oauth2_client_credentials,
    write_delta,
)

logger = logging.getLogger(__name__)

# PARAMETERS CELL ********************

subscription_uuids = ""  # "" = all subscriptions discovered from the account
environment_ids = ""     # "" = no environment filter (default from Variable Library)
capability_keys = ""     # "" = no capability filter (default from Variable Library)
cluster_ids = ""         # "" = no cluster filter (default from Variable Library)
lookback_days = 35       # days of cost/usage to request per run

# CELL ********************

# ## 1. Configuration
#
# OAuth client-credentials config + optional comma-separated filters. Parameters override the Variable Library defaults; "" means no filter.

# CELL ********************

def csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]

VariableLib = load_variable_library("VariableLib")
key_vault_url = get_var(VariableLib, "key_vault_url")
finopshub_root_path = get_var(VariableLib, "finopshub_root_path")
bronze_root = f"{finopshub_root_path.rstrip('/')}/bronze"

account_uuid = get_var(VariableLib, "dynatrace_account_uuid")
client_id = get_var(VariableLib, "dynatrace_client_id")
client_secret_name = get_var(VariableLib, "dynatrace_client_secret_name")
token_url = get_var(VariableLib, "dynatrace_token_url", "https://sso.dynatrace.com/sso/oauth2/token")
api_base_url = get_var(VariableLib, "dynatrace_api_base_url", "https://api.dynatrace.com")

# Filters: parameter wins, else Variable Library default, else unset.
environment_ids = csv(environment_ids or get_var(VariableLib, "dynatrace_environment_ids", ""))
capability_keys = csv(capability_keys or get_var(VariableLib, "dynatrace_capability_keys", ""))
cluster_ids = csv(cluster_ids or get_var(VariableLib, "dynatrace_cluster_ids", ""))
requested_subscriptions = csv(subscription_uuids)

PLACEHOLDER_GUID = "00000000-0000-0000-0000-000000000000"
if not account_uuid or account_uuid == PLACEHOLDER_GUID:
    raise ValueError("dynatrace_account_uuid is not configured in the Variable Library")

ingestion_ts = datetime.now(timezone.utc)
snapshot_date = ingestion_ts.date()
end_time = ingestion_ts.replace(microsecond=0)
start_time = (end_time - timedelta(days=lookback_days)).replace(microsecond=0)
ISO = "%Y-%m-%dT%H:%M:%SZ"

logger.info(
    "Account %s | lookback=%dd | filters: env=%s capability=%s cluster=%s",
    account_uuid, lookback_days, environment_ids, capability_keys, cluster_ids,
)

# CELL ********************

# ## 2. Authenticate
#
# OAuth2 client-credentials grant via `finops_core.oauth2_client_credentials`. The secret is read from Key Vault; the client needs the `account-uac-read` scope, and Dynatrace requires the `resource=urn:dtaccount:<uuid>` form field.

# CELL ********************

client = oauth2_client_credentials(
    token_url,
    client_id,
    get_secret(key_vault_url, client_secret_name),
    base_url=api_base_url,
    scope="account-uac-read",
    extra={"resource": f"urn:dtaccount:{account_uuid}"},
)

def filter_params() -> dict[str, str]:
    params: dict[str, str] = {}
    if capability_keys:
        params["capabilityKeys"] = ",".join(capability_keys)
    if cluster_ids:
        params["clusterIds"] = ",".join(cluster_ids)
    if environment_ids:
        params["environmentIds"] = ",".join(environment_ids)
    return params

def paged(path: str, params: dict[str, str]):
    """Yield each page body, following Dynatrace `nextPageKey` / `page-key`."""
    page_params = dict(params)
    while True:
        body = client.get_json(path, params=page_params or None)
        yield body
        next_key = body.get("nextPageKey")
        if not next_key:
            return
        page_params = {"page-key": next_key}

# CELL ********************

# ## 3. Subscriptions
#
# Fetch the account's subscription list **once**: it both lands `bronze.dynatrace_subscriptions` and drives the cost/usage loop. The `subscription_uuids` parameter filters the loop (the table still reflects the full discovered list).

# CELL ********************

sub_body = client.get_json(f"/sub/v2/accounts/{account_uuid}/subscriptions")
subscription_records = sub_body.get("data", [])
if not subscription_records:
    raise RuntimeError("Dynatrace subscription list returned zero rows")

sub_rows = [
    {
        "account_uuid": account_uuid,
        "subscription_uuid": item.get("uuid"),
        "subscription_type": item.get("type"),
        "subscription_sub_type": item.get("subType"),
        "subscription_name": item.get("name"),
        "subscription_status": item.get("status"),
        "subscription_start_date": item.get("startTime"),
        "subscription_end_date": item.get("endTime"),
    }
    for item in subscription_records
]

subscriptions_df = pl.from_dicts(sub_rows).with_columns(
    pl.col("subscription_start_date").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
    pl.col("subscription_end_date").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
    pl.lit(ingestion_ts).alias("ingestion_timestamp"),
    pl.lit("GET /sub/v2/accounts/{accountUuid}/subscriptions").alias("source_file"),
    pl.lit(snapshot_date).alias("snapshot_date"),
)
write_delta(
    subscriptions_df,
    f"{bronze_root}/dynatrace_subscriptions",
    replace_where=f"snapshot_date = '{snapshot_date}'",
    partition_by=["snapshot_date"],
)
spark.sql(
    f"CREATE TABLE IF NOT EXISTS dynatrace_subscriptions USING DELTA "
    f"LOCATION '{bronze_root}/dynatrace_subscriptions'"
)
logger.info("Wrote %d rows to bronze.dynatrace_subscriptions", subscriptions_df.height)

# Subscriptions in scope for the cost/usage loop.
loop_subs = [
    {"uuid": item.get("uuid"), "name": item.get("name")}
    for item in subscription_records
    if item.get("uuid") and (not requested_subscriptions or item.get("uuid") in requested_subscriptions)
]
if not loop_subs:
    raise RuntimeError(f"No subscriptions match subscription_uuids='{subscription_uuids}'")

# CELL ********************

# ## 4. Cost and Usage
#
# Per subscription, land subscription-grain totals and the paginated environment-grain breakdown (capability-level) for both cost and usage. `grain` distinguishes the two levels in one table each.

# CELL ********************

cost_rows: list[dict] = []
usage_rows: list[dict] = []
base = f"/sub/v2/accounts/{account_uuid}/subscriptions"
cost_base_v3 = f"/sub/v3/accounts/{account_uuid}/subscriptions"
time_window = {"startTime": start_time.strftime(ISO), "endTime": end_time.strftime(ISO)}

for sub in loop_subs:
    uuid, name = sub["uuid"], sub["name"]

    # --- Cost: subscription grain (authoritative total) ---
    body = client.get_json(f"{base}/{uuid}/cost", params=filter_params() or None)
    for item in body.get("data", []):
        cost_rows.append({
            "account_uuid": account_uuid, "subscription_uuid": uuid, "subscription_name": name,
            "grain": "subscription", "environment_id": None, "cluster_id": None,
            "capability_key": None, "capability_name": None,
            "cost_start_time": item.get("startTime"), "cost_end_time": item.get("endTime"),
            "cost_value": item.get("value"), "currency_code": item.get("currencyCode"),
            "booking_date": item.get("lastBookingDate"), "last_modified_time": body.get("lastModifiedTime"),
        })
    # --- Cost: environment grain (capability breakdown, paginated) ---
    for page in paged(f"{cost_base_v3}/{uuid}/environments/cost", {**filter_params(), **time_window}):
        for env in page.get("data", []):
            for item in env.get("cost", []):
                cost_rows.append({
                    "account_uuid": account_uuid, "subscription_uuid": uuid, "subscription_name": name,
                    "grain": "environment", "environment_id": env.get("environmentId"),
                    "cluster_id": env.get("clusterId"),
                    "capability_key": item.get("capabilityKey"), "capability_name": item.get("capabilityName"),
                    "cost_start_time": item.get("startTime"), "cost_end_time": item.get("endTime"),
                    "cost_value": item.get("value"), "currency_code": item.get("currencyCode"),
                    "booking_date": item.get("bookingDate"), "last_modified_time": page.get("lastModifiedTime"),
                })

    # --- Usage: subscription grain ---
    body = client.get_json(f"{base}/{uuid}/usage", params=filter_params() or None)
    for item in body.get("data", []):
        usage_rows.append({
            "account_uuid": account_uuid, "subscription_uuid": uuid, "subscription_name": name,
            "grain": "subscription", "environment_id": None, "cluster_id": None,
            "capability_key": item.get("capabilityKey"), "capability_name": item.get("capabilityName"),
            "usage_start_time": item.get("startTime"), "usage_end_time": item.get("endTime"),
            "usage_value": item.get("value"), "unit_measure": item.get("unitMeasure"),
            "last_modified_time": body.get("lastModifiedTime"),
        })
    # --- Usage: environment grain (paginated) ---
    for page in paged(f"{base}/{uuid}/environments/usage", {**filter_params(), **time_window}):
        for env in page.get("data", []):
            for item in env.get("usage", []):
                usage_rows.append({
                    "account_uuid": account_uuid, "subscription_uuid": uuid, "subscription_name": name,
                    "grain": "environment", "environment_id": env.get("environmentId"), "cluster_id": None,
                    "capability_key": item.get("capabilityKey"), "capability_name": item.get("capabilityName"),
                    "usage_start_time": item.get("startTime"), "usage_end_time": item.get("endTime"),
                    "usage_value": item.get("value"), "unit_measure": item.get("unitMeasure"),
                    "last_modified_time": page.get("lastModifiedTime"),
                })

if not cost_rows:
    raise RuntimeError("Dynatrace cost APIs returned zero rows")

ts_cols = lambda *c: [pl.col(x).str.strptime(pl.Datetime(time_zone="UTC"), strict=False) for x in c]

cost_df = pl.from_dicts(cost_rows).with_columns(
    *ts_cols("cost_start_time", "cost_end_time", "last_modified_time"),
    pl.lit(ingestion_ts).alias("ingestion_timestamp"),
    pl.lit("Dynatrace Platform Subscription cost APIs").alias("source_file"),
    pl.lit(snapshot_date).alias("snapshot_date"),
)
usage_df = pl.from_dicts(usage_rows).with_columns(
    *ts_cols("usage_start_time", "usage_end_time", "last_modified_time"),
    pl.lit(ingestion_ts).alias("ingestion_timestamp"),
    pl.lit("Dynatrace Platform Subscription usage APIs").alias("source_file"),
    pl.lit(snapshot_date).alias("snapshot_date"),
)

for df, table in ((cost_df, "dynatrace_cost"), (usage_df, "dynatrace_usage")):
    write_delta(
        df, f"{bronze_root}/{table}",
        replace_where=f"snapshot_date = '{snapshot_date}'", partition_by=["snapshot_date"],
    )
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} USING DELTA LOCATION '{bronze_root}/{table}'")
    logger.info("Wrote %d rows to bronze.%s", df.height, table)

# CELL ********************

# ## 5. Validation and reconciliation
#
# Confirm both grains landed, and reconcile the environment-grain cost against the subscription-grain total per subscription — a non-zero gap is cost Dynatrace did not attribute to an environment (kept visible rather than silently lost).

# CELL ********************

display(
    cost_df.group_by(["subscription_uuid", "grain", "currency_code"])
    .agg(pl.col("cost_value").sum().alias("cost_value"), pl.len().alias("rows"))
    .sort(["subscription_uuid", "grain"])
)

recon = (
    cost_df.group_by(["subscription_uuid", "grain"])
    .agg(pl.col("cost_value").sum().alias("total"))
    .pivot(values="total", index="subscription_uuid", on="grain")
)
if {"subscription", "environment"} <= set(recon.columns):
    recon = recon.with_columns(
        (pl.col("subscription").fill_null(0) - pl.col("environment").fill_null(0)).alias("unattributed")
    )
    display(recon.sort("subscription_uuid"))
    gaps = recon.filter(pl.col("unattributed").abs() > 0.01)
    if not gaps.is_empty():
        logger.warning(
            "%d subscription(s) have cost not attributable to an environment "
            "(subscription-grain total > sum of environments)", gaps.height
        )

logger.info(
    "Done: subscriptions=%d cost_rows=%d usage_rows=%d snapshot_date=%s",
    subscriptions_df.height, cost_df.height, usage_df.height, snapshot_date,
)
