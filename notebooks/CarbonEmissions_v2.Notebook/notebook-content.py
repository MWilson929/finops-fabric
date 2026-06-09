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

# Azure Carbon Optimization Emissions Notebook (v2 - finops-core)
# Queries the Azure Carbon Optimization API (ItemDetailsReport, resource-level) for one
# or more tenants and lands the combined result in a Delta table partitioned by
# report_month in the FinOpsHub lakehouse.
#
# Built on the finops-core package: config, secrets, transform and Delta writes come
# from the library; only the Carbon-specific query logic lives here.
#
# Tenancy is config-driven, not hardcoded: every tenant prefix in TENANT_PREFIXES whose
# Variable Library entries are populated is included. Run single-tenant by leaving the
# other tenant's variables at their placeholder defaults, or ad hoc via the tenants
# parameter.
#
# Data characteristics (per API docs):
#   - Emissions data is MONTHLY only; 12 months history; previous month published by
#     day 19 of the current month
#   - ItemDetailsReport requires start == end (exactly one month per query)
#   - latest_month_emissions holds the emissions value for the queried month

# Install finops-core from the Azure DevOps Artifact feed (PAT resolved from Key Vault),
# then the Azure SDKs from public PyPI.
_lib = notebookutils.variableLibrary.getLibrary("VariableLib")
_feed_pat = notebookutils.credentials.getSecret(_lib.key_vault_url, _lib.ado_feed_pat_secret_name)
get_ipython().run_line_magic(
    "pip",
    "install finops-core "
    f"--index-url=https://feed:{_feed_pat}@pkgs.dev.azure.com/"
    f"{_lib.ado_organization}/{_lib.ado_project}/_packaging/{_lib.ado_artifactory_feed}/pypi/simple/",
)
del _feed_pat

%pip install azure-identity azure-mgmt-carbonoptimization azure-mgmt-subscription --quiet

# PARAMETERS CELL ********************

# report_month controls which month(s) to load:
#   ""        -> latest available month plus the prior month (default for scheduled runs)
#   "YYYY-MM" -> that specific month only (re-run/backfill a single month)
#   "all"     -> full backfill of every month the API has available (initial load)
report_month = ""

# tenants restricts which configured tenants to query:
#   ""    -> all tenants with populated Variable Library config (default)
#   "a"   -> single tenant by prefix; comma-separated for several, e.g. "a,b"
tenants = ""

# CELL ********************

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

from finops_core import get_secret, get_var, load_variable_library, to_polars, write_delta

# CELL ********************

# Configuration: build the tenant list from the Variable Library

VariableLib = load_variable_library("VariableLib")
key_vault_url = get_var(VariableLib, "key_vault_url")
finopshub_root_path = get_var(VariableLib, "finopshub_root_path")

layer = "bronze"
table_name = "CarbonEmissions_MultiTenant"
emissions_delta_table_path = f"{finopshub_root_path.rstrip('/')}/{layer}/{table_name}"

# Tenant prefixes known to the Variable Library; extend this list to onboard a tenant.
TENANT_PREFIXES = ["a", "b"]
PLACEHOLDER_GUID = "00000000-0000-0000-0000-000000000000"

if report_month not in ("", "all") and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", report_month):
    raise ValueError(f"Invalid report_month parameter: '{report_month}'. Use '', 'all', or 'YYYY-MM'.")

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
        print(f"⏭️  Tenant '{prefix}' not configured in Variable Library - skipping")
        continue
    if requested_prefixes and prefix not in requested_prefixes:
        print(f"⏭️  Tenant '{prefix}' excluded by tenants parameter - skipping")
        continue

    tenant_configs.append({
        "prefix": prefix,
        "label": f"Tenant {prefix.upper()}",
        "tenant_id": tenant_id,
        "client_id": client_id,
        "secret_name": secret_name,
    })

if not tenant_configs:
    raise ValueError("No tenants selected - check Variable Library config and the tenants parameter")

print("✓ Configuration loaded:")
print(f"  Delta Table Path: {emissions_delta_table_path}")
print(f"  report_month: '{report_month}'")
print(f"  Tenants to query: {[t['label'] for t in tenant_configs]}")

# CELL ********************

# Month-resolution helpers

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
    """Resolve which months to query, based on the parameter and the tenant's available range."""
    available = carbon_service.query_carbon_emission_data_available_date_range()
    available_months = month_starts(available.start_date, available.end_date)
    print(f"  🗓️  {tenant_label} carbon data available: {available.start_date} to {available.end_date}")

    if report_month_param == "all":
        selected = available_months
    elif report_month_param == "":
        selected = available_months[-2:]  # latest + prior month (catches restated data)
    else:
        requested = date.fromisoformat(f"{report_month_param}-01")
        if requested not in available_months:
            print(f"  ⚠️  {report_month_param} outside available range for {tenant_label} - skipping tenant")
            return []
        selected = [requested]

    print(f"  ✅ Months selected: {[m.strftime('%Y-%m') for m in selected]}")
    return selected

# CELL ********************

# Carbon Optimization extraction (the only source-specific code in this notebook)

def get_emissions_from_tenant(tenant, report_month_param):
    """Return resource-level emission records for one tenant across the resolved months."""
    label = tenant["label"]
    print(f"\n🔍 Querying {label} ({tenant['tenant_id']})...")

    credential = ClientSecretCredential(
        tenant_id=tenant["tenant_id"],
        client_id=tenant["client_id"],
        client_secret=get_secret(key_vault_url, tenant["secret_name"]),
    )
    carbon_service = CarbonOptimizationMgmtClient(credential=credential).carbon_service
    subscription_client = SubscriptionClient(credential)

    # API requires lowercase subscription IDs, max 100 per request
    subscriptions = list(subscription_client.subscriptions.list())
    subscription_ids = [s.subscription_id.lower() for s in subscriptions]
    subscription_names = {s.subscription_id.lower(): s.display_name for s in subscriptions}
    print(f"  ✅ Found {len(subscription_ids)} subscriptions")
    if not subscription_ids:
        return []

    months = resolve_months(carbon_service, report_month_param, label)
    if not months:
        return []

    batches = [subscription_ids[i:i + 100] for i in range(0, len(subscription_ids), 100)]
    records = []

    for month_start in months:
        month_label = month_start.strftime("%Y-%m")
        month_count = 0

        for batch_num, batch in enumerate(batches, 1):
            query_filter = ItemDetailsQueryFilter(
                date_range=DateRange(start=month_start, end=month_start),  # start == end required
                subscription_list=batch,
                carbon_scope_list=[
                    EmissionScopeEnum.SCOPE1,
                    EmissionScopeEnum.SCOPE2,
                    EmissionScopeEnum.SCOPE3,
                ],
                category_type=CategoryTypeEnum.RESOURCE,
                order_by=OrderByColumnEnum.ITEM_NAME,
                sort_direction=SortDirectionEnum.DESC,
                page_size=5000,  # Carbon API max (unlike Resource Graph's 1000)
            )

            page = 0
            while True:
                page += 1
                result = carbon_service.query_carbon_emission_reports(query_filter)

                for item in result.value or []:
                    emission = item.as_dict()
                    # latest_month_emissions is the emissions value FOR report_month
                    emission["tenant_id"] = tenant["tenant_id"]
                    emission["tenant_label"] = label
                    emission["report_month"] = month_label
                    emission["subscription_name"] = subscription_names.get(
                        str(emission.get("subscription_id", "")).lower(), "Unknown"
                    )
                    emission["extracted_at"] = datetime.now(timezone.utc).isoformat()
                    records.append(emission)
                    month_count += 1

                print(f"    📄 {month_label} | batch {batch_num}/{len(batches)}, page {page}: "
                      f"{len(result.value) if result.value else 0} records")

                if result.skip_token:
                    query_filter.skip_token = result.skip_token
                else:
                    break

        print(f"  ✅ {month_label}: {month_count} records")

    print(f"  ✅ {label} total: {len(records)} records")
    return records


print("=" * 70)
print("🌱 RETRIEVING CARBON EMISSIONS")
print("=" * 70)

all_records = []
per_tenant_counts = {}
for tenant in tenant_configs:
    tenant_records = get_emissions_from_tenant(tenant, report_month)
    per_tenant_counts[tenant["label"]] = len(tenant_records)
    all_records.extend(tenant_records)

print(f"\n{'=' * 70}")
print(f"📊 EXTRACTION SUMMARY")
for label, count in per_tenant_counts.items():
    print(f"  {label}: {count} records")
print(f"  📈 Total: {len(all_records)} records")
print(f"{'=' * 70}")

# CELL ********************

# Build DataFrame (finops-core coerces nested values) and apply numeric types

df = to_polars(all_records)

if df.height > 0:
    for col in ("latest_month_emissions", "previous_month_emissions",
                "month_over_month_emissions_change_ratio", "monthly_emissions_change_value"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64))

    print(f"✅ DataFrame: {df.height} rows x {df.width} columns")
    print(df.group_by(["tenant_label", "report_month"]).agg([
        pl.len().alias("records"),
        pl.col("latest_month_emissions").sum().alias("total_emissions_kgco2e"),
    ]).sort(["tenant_label", "report_month"]))
else:
    print("⚠️  No emissions data found")

# CELL ********************

# Write to Delta: idempotent month-level replace via finops-core
# (replace_where swaps each month atomically; partition_by applies on first creation;
# an empty frame is a no-op so a failed extract can never wipe the table)

if df.height == 0:
    print("⚠️  Nothing to write - existing table contents preserved")
else:
    months_in_df = sorted(df["report_month"].unique().to_list())
    print(f"💾 Writing {df.height} records covering: {months_in_df}")

    for m in months_in_df:
        month_df = df.filter(pl.col("report_month") == m)
        write_delta(
            month_df,
            emissions_delta_table_path,
            replace_where=f"report_month = '{m}'",
            partition_by=["report_month"],
        )
        print(f"  ✅ {m}: replaced with {month_df.height} records")

# CELL ********************

# Register in the Fabric metastore and verify

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {table_name}
    USING DELTA
    LOCATION '{emissions_delta_table_path}'
""")
print(f"✅ Table '{table_name}' registered in metastore")

row_count = spark.sql(f"SELECT COUNT(*) as count FROM {table_name}").collect()[0]["count"]
print(f"✅ Table is queryable - row count: {row_count}")

if row_count > 0:
    print("\n🌍 Emissions by tenant and month (kgCO2e):")
    spark.sql(f"""
        SELECT tenant_label, report_month, COUNT(*) as records,
               ROUND(SUM(latest_month_emissions), 4) as total_emissions_kgco2e
        FROM {table_name}
        GROUP BY tenant_label, report_month
        ORDER BY tenant_label, report_month
    """).show(50, truncate=False)

# CELL ********************

print("🎉 Carbon emissions extraction complete")
print(f"  - Tenants queried: {[t['label'] for t in tenant_configs]}")
print(f"  - Records: {len(all_records)}")
print(f"  - Table: {table_name} at {emissions_delta_table_path}")
print(f"\n🌱 Operational notes:")
print(f"  - Initial load: report_month = 'all'")
print(f"  - Scheduled run: monthly ~20th-21st, report_month = '' (latest + prior month)")
print(f"  - Single tenant: tenants = 'a' (or leave the other tenant unconfigured)")
print(f"  - All writes are idempotent month-level replacements")
