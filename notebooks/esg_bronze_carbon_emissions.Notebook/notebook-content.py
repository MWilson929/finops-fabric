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

# # esg_bronze_carbon_emissions
#
# **Purpose**: Lands monthly resource-level carbon emissions from the Azure Carbon Optimization API across two configured tenants into a partitioned Delta table.
#
# **Domain**: esg
# **Schema**: bronze
#
# **Inputs**:
# - Azure Carbon Optimization API (`ItemDetailsReport`, resource-level), one query per tenant per month
# - ARM `subscriptions` API for per-tenant subscription discovery
#
# **Output**: `bronze.carbon_emissions` (partitioned by `report_month`)
#
# **Parameters** (pipeline via Variable Library):
# - `report_month` (string): `""` = latest + prior month (default for schedule); `"YYYY-MM"` = specific month (re-run/backfill); `"all"` = full 12-month backfill (initial load)
#
# **Trigger**: monthly pipeline, runs around day 20–21 (Azure publishes the previous month by day 19)
#
# **Exit value**: JSON dict with `total_records`, per-tenant counts, `delta_table_path`, `extracted_at` — returned via `notebookutils.notebook.exit` for the orchestrating pipeline.
#
# ---
#
# **Data characteristics** (per API docs):
# - Emissions data is monthly only; 12 months history; previous month published by day 19
# - `ItemDetailsReport` requires `start == end` (one month per query)
# - `latest_month_emissions` is the emissions value for the queried `report_month`
#
# **Load strategy**: each month is loaded as a whole and atomically replaced via Delta `replaceWhere` — re-runs are idempotent and months absent from this run are untouched.
#
# > **Tenancy**: two hardcoded tenants (A and B). The config-driven 1..N variant lives in `incubation/esg_bronze_carbon_emissions` pending finops-core graduation.

# CELL ********************

%pip install polars deltalake azure-identity azure-keyvault-secrets azure-mgmt-carbonoptimization azure-mgmt-subscription --quiet

# PARAMETERS CELL ********************

# Override via pipeline / scheduler. See markdown header for value semantics.
report_month = ""

# CELL ********************

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

import polars as pl
from azure.identity import ClientSecretCredential
from azure.mgmt.carbonoptimization import CarbonOptimizationMgmtClient
from azure.mgmt.carbonoptimization.models import (
    CategoryTypeEnum,
    DateRange,
    EmissionScopeEnum,
    ItemDetailsQueryFilter,
    OrderByColumnEnum,
    SortDirectionEnum,
)
from azure.mgmt.subscription import SubscriptionClient
from deltalake import DeltaTable

logger = logging.getLogger(__name__)

# CELL ********************

# ## 1. Configuration
#
# Load storage paths and per-tenant service-principal references from the Variable Library. The `report_month` parameter is validated up-front so a malformed value fails before any API call.

# CELL ********************

VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")
key_vault_url = VariableLib.key_vault_url
layer = "bronze"

finopshub_root_path = VariableLib.finopshub_root_path
emissions_delta_table_path = f"{finopshub_root_path}/{layer}/carbon_emissions"

a_tenant_id = VariableLib.a_tenant_id
a_client_id = VariableLib.a_client_id
a_secret_name = VariableLib.a_secret_name

b_tenant_id = VariableLib.b_tenant_id
b_client_id = VariableLib.b_client_id
b_secret_name = VariableLib.b_secret_name

if report_month not in ("", "all") and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", report_month):
    raise ValueError(f"Invalid report_month parameter: '{report_month}'. Use '', 'all', or 'YYYY-MM'.")

mode = "latest + prior" if report_month == "" else "full backfill" if report_month == "all" else "single month"
logger.info("report_month=%r (%s); writing to %s", report_month, mode, emissions_delta_table_path)

# CELL ********************

# ## 2. Credentials
#
# Build a service-principal credential per tenant from the Key Vault secret, then instantiate the Carbon Optimization and Subscription management clients. Missing config fails fast before any API call.

# CELL ********************

if not all([a_tenant_id, a_client_id, a_secret_name, key_vault_url]):
    raise ValueError("Missing required configuration for Tenant A from Variable Library")

if not all([b_tenant_id, b_client_id, b_secret_name, key_vault_url]):
    raise ValueError("Missing required configuration for Tenant B from Variable Library")

sp_credential_a = ClientSecretCredential(
    tenant_id=a_tenant_id,
    client_id=a_client_id,
    client_secret=notebookutils.credentials.getSecret(key_vault_url, a_secret_name),
)

sp_credential_b = ClientSecretCredential(
    tenant_id=b_tenant_id,
    client_id=b_client_id,
    client_secret=notebookutils.credentials.getSecret(key_vault_url, b_secret_name),
)

carbon_client_a = CarbonOptimizationMgmtClient(credential=sp_credential_a)
carbon_client_b = CarbonOptimizationMgmtClient(credential=sp_credential_b)
subscription_client_a = SubscriptionClient(sp_credential_a)
subscription_client_b = SubscriptionClient(sp_credential_b)

# CELL ********************

# ## 3. Month Resolution Helpers
#
# `resolve_months` interprets the `report_month` parameter against the *actual* date range each tenant's data covers — the available window can vary per tenant if onboarding dates differ.

# CELL ********************

def month_starts(start_str, end_str):
    """Return a list of first-of-month dates from start_str to end_str inclusive."""
    start = date.fromisoformat(str(start_str)[:10]).replace(day=1)
    end = date.fromisoformat(str(end_str)[:10]).replace(day=1)
    months = []
    cur = start
    while cur <= end:
        months.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def resolve_months(carbon_service, report_month_param, tenant_label):
    """
    Resolve which months to query for a tenant, based on the report_month parameter
    and the tenant's available carbon data date range.
    """
    available = carbon_service.query_carbon_emission_data_available_date_range()
    available_months = month_starts(available.start_date, available.end_date)
    logger.info(
        "%s available range: %s to %s (%d months)",
        tenant_label, available.start_date, available.end_date, len(available_months),
    )

    if report_month_param == "all":
        selected = available_months
    elif report_month_param == "":
        # Latest available month plus the prior month (catches late/restated data)
        selected = available_months[-2:]
    else:
        requested = date.fromisoformat(f"{report_month_param}-01")
        if requested not in available_months:
            logger.warning(
                "%s: requested month %s outside available range — skipping",
                tenant_label, report_month_param,
            )
            return []
        selected = [requested]

    logger.info("%s: months selected %s", tenant_label, [m.strftime("%Y-%m") for m in selected])
    return selected

# CELL ********************

# ## 4. Extract Emissions per Tenant
#
# Discovers subscriptions per tenant (lowercased — the Carbon API requires it), batches them at 100 per request (the API maximum, higher than Resource Graph's 1000), and pages through `query_carbon_emission_reports` for each resolved month. Complex nested fields are JSON-stringified as they arrive so the DataFrame schema below is stable across tenants.

# CELL ********************

def get_emissions_from_tenant(carbon_client, subscription_client, tenant_id, tenant_label, report_month_param):
    """
    Retrieve resource-level carbon emissions data from a specific tenant for the
    resolved set of months.

    Returns a list of emission record dicts (one per resource/scope/month).
    """
    emissions_data = []
    carbon_service = carbon_client.carbon_service

    try:
        # API requires lowercase subscription IDs
        subscriptions = list(subscription_client.subscriptions.list())
        subscription_ids = [sub.subscription_id.lower() for sub in subscriptions]
        subscription_names = {sub.subscription_id.lower(): sub.display_name for sub in subscriptions}

        logger.info("%s (%s): %d subscriptions", tenant_label, tenant_id, len(subscription_ids))

        if not subscription_ids:
            logger.warning("%s: no subscriptions — skipping", tenant_label)
            return emissions_data

        months = resolve_months(carbon_service, report_month_param, tenant_label)
        if not months:
            return emissions_data

        # API supports max 100 subscriptions per request
        max_subs_per_request = 100
        subscription_batches = [
            subscription_ids[i:i + max_subs_per_request]
            for i in range(0, len(subscription_ids), max_subs_per_request)
        ]

        logger.info(
            "%s: processing %d month(s) x %d subscription batch(es)",
            tenant_label, len(months), len(subscription_batches),
        )

        for month_start in months:
            month_label = month_start.strftime("%Y-%m")
            # ItemDetailsReport requires start == end (exactly one month per query)
            query_date_range = DateRange(start=month_start, end=month_start)
            month_records = 0

            for batch_num, subscription_batch in enumerate(subscription_batches, 1):
                query_filter = ItemDetailsQueryFilter(
                    date_range=query_date_range,
                    subscription_list=subscription_batch,
                    carbon_scope_list=[
                        EmissionScopeEnum.SCOPE1,
                        EmissionScopeEnum.SCOPE2,
                        EmissionScopeEnum.SCOPE3,
                    ],
                    category_type=CategoryTypeEnum.RESOURCE,
                    order_by=OrderByColumnEnum.ITEM_NAME,
                    sort_direction=SortDirectionEnum.DESC,
                    page_size=5000,  # API max (Carbon API allows 5000, unlike Resource Graph's 1000)
                )

                batch_pages = 0
                while True:
                    batch_pages += 1
                    result_list = carbon_service.query_carbon_emission_reports(query_filter)

                    if result_list.value:
                        for item in result_list.value:
                            emission = item.as_dict()
                            # latest_month_emissions is the emissions value FOR report_month
                            emission["tenant_id"] = tenant_id
                            emission["tenant_label"] = tenant_label
                            emission["report_month"] = month_label
                            emission["extracted_at"] = datetime.now(timezone.utc).isoformat()
                            emission["subscription_name"] = subscription_names.get(
                                str(emission.get("subscription_id", "")).lower(), "Unknown",
                            )

                            # Stringify complex types IMMEDIATELY for consistent DataFrame schema
                            for key, value in emission.items():
                                if isinstance(value, (dict, list)):
                                    emission[key] = json.dumps(value) if value else None
                                elif isinstance(value, date):
                                    emission[key] = value.isoformat()

                            emissions_data.append(emission)
                            month_records += 1

                    page_rows = len(result_list.value) if result_list.value else 0
                    logger.debug(
                        "%s %s batch=%d page=%d: %d records",
                        tenant_label, month_label, batch_num, batch_pages, page_rows,
                    )

                    if result_list.skip_token:
                        query_filter.skip_token = result_list.skip_token
                    else:
                        break

            logger.info("%s %s: %d records", tenant_label, month_label, month_records)

        logger.info("%s: %d emissions records total", tenant_label, len(emissions_data))
        return emissions_data

    except Exception:
        logger.exception("Error retrieving emissions from %s", tenant_label)
        raise


tenant_a_emissions = get_emissions_from_tenant(
    carbon_client_a, subscription_client_a, a_tenant_id, "Tenant A", report_month,
)
tenant_b_emissions = get_emissions_from_tenant(
    carbon_client_b, subscription_client_b, b_tenant_id, "Tenant B", report_month,
)

all_emissions_data = tenant_a_emissions + tenant_b_emissions
logger.info(
    "Extraction complete: Tenant A %d, Tenant B %d, total %d",
    len(tenant_a_emissions), len(tenant_b_emissions), len(all_emissions_data),
)

# CELL ********************

# ## 5. Frame and Type-Cast
#
# Combine both tenants' records into a Polars DataFrame with explicit type casts. Numeric emissions columns become `Float64`; identifier and metadata columns become `Utf8`. Done at the bronze layer so the downstream Delta write has a stable schema regardless of which fields the API populated.

# CELL ********************

if not all_emissions_data:
    logger.warning("No emissions data across both tenants")
    df = pl.DataFrame()
else:
    df = pl.DataFrame(all_emissions_data)

# ItemDetailsReport fields: item_name, category_type, latest_month_emissions (= emissions for
# report_month), previous_month_emissions, month_over_month_emissions_change_ratio,
# monthly_emissions_change_value, plus resource metadata fields
if df.height > 0:
    string_columns = [
        "tenant_id", "tenant_label", "report_month", "item_name", "category_type",
        "subscription_id", "subscription_name", "resource_group", "resource_id",
        "location", "resource_type", "data_type", "extracted_at",
    ]
    for col in string_columns:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Utf8))

    numeric_columns = [
        "latest_month_emissions", "previous_month_emissions",
        "month_over_month_emissions_change_ratio", "monthly_emissions_change_value",
    ]
    for col in numeric_columns:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64))

logger.info("DataFrame: %d rows × %d columns", df.height, df.width)

if df.height > 0:
    month_summary = df.group_by(["tenant_label", "report_month"]).agg([
        pl.len().alias("records"),
        pl.col("latest_month_emissions").sum().alias("total_emissions_kgco2e"),
    ]).sort(["tenant_label", "report_month"])
    display(month_summary)

    display_cols = [
        "tenant_label", "report_month", "item_name", "subscription_name", "latest_month_emissions",
    ]
    available_cols = [col for col in display_cols if col in df.columns]
    display(df.select(available_cols).head(5) if available_cols else df.head(5))

# CELL ********************

# ## 6. Write to Delta — Month-Partition Replace
#
# Each `report_month` present in the extract is atomically overwritten via Delta `replaceWhere` on the partition column. Months not in this run remain untouched. First write creates the table partitioned by `report_month`; subsequent runs reuse the layout. On re-runs the same predicate replaces only that month — idempotent by construction.

# CELL ********************

if df.height == 0:
    logger.warning("Nothing to write — skipping Delta write (preserves existing table contents)")
else:
    months_in_df = sorted(df["report_month"].unique().to_list())
    logger.info("Writing %d records covering %s to %s",
                df.height, months_in_df, emissions_delta_table_path)

    try:
        DeltaTable(emissions_delta_table_path)
        table_exists = True
    except Exception:
        table_exists = False

    for m in months_in_df:
        month_df = df.filter(pl.col("report_month") == m)

        if not table_exists:
            # First ever write creates the table, partitioned by report_month
            month_df.write_delta(
                emissions_delta_table_path,
                mode="overwrite",
                delta_write_options={"partition_by": ["report_month"], "engine": "rust"},
            )
            table_exists = True
        else:
            # Atomic replace of this month's partition only
            month_df.write_delta(
                emissions_delta_table_path,
                mode="overwrite",
                delta_write_options={
                    "predicate": f"report_month = '{m}'",
                    "schema_mode": "merge",
                    "engine": "rust",
                },
            )

        logger.info("%s: replaced %d records", m, month_df.height)

    # Sanity-check the write by reading back per-month counts
    try:
        dt = DeltaTable(emissions_delta_table_path)
        table_df = pl.from_arrow(dt.to_pyarrow_table(columns=["report_month"]))
        for m in months_in_df:
            table_count = table_df.filter(pl.col("report_month") == m).height
            df_count = df.filter(pl.col("report_month") == m).height
            if table_count != df_count:
                logger.warning("%s: %d in table, expected %d", m, table_count, df_count)
    except Exception:
        logger.exception("Could not verify write (table may still be valid)")

# CELL ********************

# ## 7. Register and Verify
#
# Register the Delta location in the Fabric metastore so the table is queryable via SQL endpoint, then run three sanity SELECTs: per-tenant per-month record/emissions totals, top-10 emitters this month, and a tenant distribution summary. Read-only — purely diagnostic.

# CELL ********************

if emissions_delta_table_path.startswith("abfss://"):
    storage_options = {
        "bearer_token": notebookutils.credentials.getToken("storage"),
        "use_fabric_endpoint": "true",
    }
    delta_table = DeltaTable(emissions_delta_table_path, storage_options=storage_options)
else:
    delta_table = DeltaTable(emissions_delta_table_path)

logger.info(
    "Delta table verified: version=%d, %d files", delta_table.version(), len(delta_table.files()),
)

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS carbon_emissions
    USING DELTA
    LOCATION '{emissions_delta_table_path}'
""")

row_count = spark.sql("SELECT COUNT(*) AS c FROM carbon_emissions").collect()[0]["c"]
logger.info("carbon_emissions registered: %d rows", row_count)

if row_count > 0:
    # Per-tenant per-month totals
    spark.sql("""
        SELECT tenant_label, report_month, COUNT(*) AS records,
               ROUND(SUM(latest_month_emissions), 4) AS total_emissions_kgco2e
        FROM carbon_emissions
        GROUP BY tenant_label, report_month
        ORDER BY tenant_label, report_month
    """).show(50, truncate=False)

    # Top 10 emitting resources in the most recent month
    spark.sql("""
        SELECT tenant_label, item_name, subscription_name,
               ROUND(latest_month_emissions, 4) AS emissions_kgco2e
        FROM carbon_emissions
        WHERE report_month = (SELECT MAX(report_month) FROM carbon_emissions)
        ORDER BY latest_month_emissions DESC
        LIMIT 10
    """).show(truncate=False)

    # Tenant distribution summary
    spark.sql("""
        SELECT tenant_label,
               COUNT(DISTINCT report_month) AS months,
               COUNT(DISTINCT subscription_id) AS subscriptions,
               COUNT(*) AS total_records,
               ROUND(SUM(latest_month_emissions), 4) AS total_emissions_kgco2e
        FROM carbon_emissions
        GROUP BY tenant_label
        ORDER BY tenant_label
    """).show(truncate=False)

# CELL ********************

# ## 8. Run Summary
#
# Build a structured summary dict and return it to the calling pipeline via `notebookutils.notebook.exit` (per `notebook_standards.md` — orchestration should not depend on parsing print output).

# CELL ********************

summary = {
    "report_month_param": report_month,
    "total_records": len(all_emissions_data),
    "tenant_a_records": len(tenant_a_emissions),
    "tenant_b_records": len(tenant_b_emissions),
    "delta_table_path": emissions_delta_table_path,
    "metastore_table": "carbon_emissions",
    "extracted_at": datetime.now(timezone.utc).isoformat(),
}

if df.height > 0:
    tenant_stats = df.group_by("tenant_label").agg([
        pl.len().alias("records"),
        pl.col("report_month").n_unique().alias("months"),
        pl.col("subscription_id").n_unique().alias("subscriptions"),
        pl.col("latest_month_emissions").sum().alias("total_emissions"),
    ]).sort("tenant_label")
    display(tenant_stats)
    summary["tenant_stats"] = tenant_stats.to_dicts()

logger.info("Run summary: %s", summary)

# Return to the calling pipeline
notebookutils.notebook.exit(json.dumps(summary, default=str))
