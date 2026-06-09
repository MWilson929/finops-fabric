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

# Azure Carbon Optimization Emissions Multi-Tenant Notebook
# Queries Azure Carbon Optimization API (ItemDetailsReport, resource-level) from two tenants
# and combines into one Delta table partitioned by report_month in the FinOpsHub lakehouse.
#
# Data characteristics (per API docs):
#   - Emissions data is MONTHLY only - no daily granularity exists
#   - 12 months of history available; previous month published by day 19 of current month
#   - ItemDetailsReport requires start == end (exactly one month per query)
#   - latest_month_emissions holds the emissions value for the queried month (report_month)
#
# Load strategy:
#   - Each month is loaded as a whole and atomically replaced (Delta overwrite with predicate)
#   - Re-running for any month is idempotent

%pip install polars deltalake azure-identity azure-keyvault-secrets azure-mgmt-carbonoptimization azure-mgmt-subscription --quiet

# PARAMETERS CELL ********************

# report_month controls which month(s) to load:
#   ""        -> latest available month plus the prior month (default for scheduled runs)
#   "YYYY-MM" -> that specific month only (re-run/backfill a single month)
#   "all"     -> full backfill of every month the API has available (initial load, up to 12 months)
report_month = ""

# CELL ********************

import polars as pl
from deltalake import DeltaTable
from azure.identity import ClientSecretCredential
from azure.mgmt.carbonoptimization import CarbonOptimizationMgmtClient
from azure.mgmt.carbonoptimization.models import (
    DateRange, EmissionScopeEnum, CategoryTypeEnum,
    OrderByColumnEnum, SortDirectionEnum, ItemDetailsQueryFilter
)
from azure.mgmt.subscription import SubscriptionClient
from datetime import datetime, date, timedelta, timezone
import json
import re

# CELL ********************

# Get the Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")
key_vault_url = VariableLib.key_vault_url
layer = "bronze"

# Use root path and append specific table name
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
emissions_delta_table_path = f"{finopshub_root_path}/{layer}/CarbonEmissions_MultiTenant"

# Get configuration for Tenant A
a_tenant_id = VariableLib.a_tenant_id
a_client_id = VariableLib.a_client_id
a_secret_name = VariableLib.a_secret_name

# Get configuration for Tenant B
b_tenant_id = VariableLib.b_tenant_id
b_client_id = VariableLib.b_client_id
b_secret_name = VariableLib.b_secret_name

# Validate the report_month parameter early
if report_month not in ("", "all") and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", report_month):
    raise ValueError(f"Invalid report_month parameter: '{report_month}'. Use '', 'all', or 'YYYY-MM'.")

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL: {key_vault_url}")
print(f"  Delta Table Path: {emissions_delta_table_path}")
print(f"  report_month parameter: '{report_month}' " +
      ("(latest + prior month)" if report_month == "" else
       "(full backfill)" if report_month == "all" else "(single month)"))
print(f"\n  Tenant A:")
print(f"    Tenant ID: {a_tenant_id}")
print(f"    Client ID: {a_client_id}")
print(f"    Secret Name: {a_secret_name}")
print(f"\n  Tenant B:")
print(f"    Tenant ID: {b_tenant_id}")
print(f"    Client ID: {b_client_id}")
print(f"    Secret Name: {b_secret_name}")

# CELL ********************

# Create credentials for both tenants

# Validate that we have required configuration for both tenants
if not all([a_tenant_id, a_client_id, a_secret_name, key_vault_url]):
    raise ValueError("Missing required configuration for Tenant A from Variable Library")

if not all([b_tenant_id, b_client_id, b_secret_name, key_vault_url]):
    raise ValueError("Missing required configuration for Tenant B from Variable Library")

print("🔐 Creating service principal credentials for both tenants...")

# Create credential for Tenant A
sp_credential_a = ClientSecretCredential(
    tenant_id=a_tenant_id,
    client_id=a_client_id,
    client_secret=notebookutils.credentials.getSecret(key_vault_url, a_secret_name)
)

# Create credential for Tenant B
sp_credential_b = ClientSecretCredential(
    tenant_id=b_tenant_id,
    client_id=b_client_id,
    client_secret=notebookutils.credentials.getSecret(key_vault_url, b_secret_name)
)

# Create Carbon Optimization and Subscription clients for both tenants
carbon_client_a = CarbonOptimizationMgmtClient(credential=sp_credential_a)
carbon_client_b = CarbonOptimizationMgmtClient(credential=sp_credential_b)
subscription_client_a = SubscriptionClient(sp_credential_a)
subscription_client_b = SubscriptionClient(sp_credential_b)

print("✓ Successfully created credentials, Carbon Optimization and Subscription clients for both tenants")

# CELL ********************

# Helper functions for month resolution

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
    print(f"  🗓️  {tenant_label} carbon data available: {available.start_date} to {available.end_date} ({len(available_months)} months)")

    if report_month_param == "all":
        selected = available_months
    elif report_month_param == "":
        # Latest available month plus the prior month (catches late/restated data)
        selected = available_months[-2:]
    else:
        requested = date.fromisoformat(f"{report_month_param}-01")
        if requested not in available_months:
            print(f"  ⚠️  Requested month {report_month_param} is outside the available range for {tenant_label} - skipping tenant")
            return []
        selected = [requested]

    print(f"  ✅ Months selected for {tenant_label}: {[m.strftime('%Y-%m') for m in selected]}")
    return selected

# CELL ********************

# Function to retrieve carbon emissions from a tenant using Azure Carbon Optimization
def get_emissions_from_tenant(carbon_client, subscription_client, tenant_id, tenant_label, report_month_param):
    """
    Retrieve resource-level carbon emissions data from a specific tenant for the
    resolved set of months.

    Args:
        carbon_client: CarbonOptimizationMgmtClient instance
        subscription_client: SubscriptionClient instance
        tenant_id: Tenant ID string
        tenant_label: Human-readable label for the tenant (e.g., "Tenant A")
        report_month_param: The report_month notebook parameter

    Returns:
        List of emission record dictionaries (one per resource/scope/month)
    """
    print(f"\n🔍 Querying {tenant_label} ({tenant_id})...")
    emissions_data = []
    carbon_service = carbon_client.carbon_service

    try:
        # Discover subscriptions in this tenant (API requires lowercase subscription IDs)
        subscriptions = list(subscription_client.subscriptions.list())
        subscription_ids = [sub.subscription_id.lower() for sub in subscriptions]
        subscription_names = {sub.subscription_id.lower(): sub.display_name for sub in subscriptions}

        print(f"  ✅ Found {len(subscription_ids)} subscriptions in {tenant_label}")

        if not subscription_ids:
            print(f"  ⚠️  No subscriptions found in {tenant_label} - skipping")
            return emissions_data

        # Resolve which months to load for this tenant
        months = resolve_months(carbon_service, report_month_param, tenant_label)
        if not months:
            return emissions_data

        # Calculate subscription batches (API supports max 100 subscriptions per request)
        max_subs_per_request = 100
        subscription_batches = [
            subscription_ids[i:i + max_subs_per_request]
            for i in range(0, len(subscription_ids), max_subs_per_request)
        ]

        print(f"  📊 Processing {len(months)} month(s) x {len(subscription_batches)} subscription batch(es)...")

        for month_start in months:
            month_label = month_start.strftime("%Y-%m")
            # ItemDetailsReport requires start == end (exactly one month per query)
            query_date_range = DateRange(start=month_start, end=month_start)
            month_records = 0

            for batch_num, subscription_batch in enumerate(subscription_batches, 1):
                # Build query filter for item detail report by resource
                query_filter = ItemDetailsQueryFilter(
                    date_range=query_date_range,
                    subscription_list=subscription_batch,
                    carbon_scope_list=[
                        EmissionScopeEnum.SCOPE1,
                        EmissionScopeEnum.SCOPE2,
                        EmissionScopeEnum.SCOPE3
                    ],
                    category_type=CategoryTypeEnum.RESOURCE,
                    order_by=OrderByColumnEnum.ITEM_NAME,
                    sort_direction=SortDirectionEnum.DESC,
                    page_size=5000  # API max page size (Carbon API allows 5000, unlike Resource Graph's 1000)
                )

                # Execute query and handle pagination for this batch
                batch_pages = 0

                while True:
                    batch_pages += 1

                    try:
                        result_list = carbon_service.query_carbon_emission_reports(query_filter)

                        # Process results
                        if result_list.value:
                            for item in result_list.value:
                                # Convert to dictionary
                                emission = item.as_dict()

                                # Add tenant and month identifiers
                                # latest_month_emissions is the emissions value FOR report_month
                                emission['tenant_id'] = tenant_id
                                emission['tenant_label'] = tenant_label
                                emission['report_month'] = month_label

                                # Add extraction metadata
                                emission['extracted_at'] = datetime.now(timezone.utc).isoformat()
                                emission['subscription_name'] = subscription_names.get(
                                    str(emission.get('subscription_id', '')).lower(), 'Unknown'
                                )

                                # Convert complex types to JSON strings IMMEDIATELY
                                # This ensures consistent types before DataFrame creation
                                for key, value in emission.items():
                                    if isinstance(value, (dict, list)):
                                        emission[key] = json.dumps(value) if value else None
                                    elif isinstance(value, date):
                                        emission[key] = value.isoformat()

                                emissions_data.append(emission)
                                month_records += 1

                        page_rows = len(result_list.value) if result_list.value else 0
                        print(f"    📄 {month_label} | Batch {batch_num}, Page {batch_pages}: {page_rows} records")

                        # Check if there are more results for this batch
                        if result_list.skip_token:
                            query_filter.skip_token = result_list.skip_token
                        else:
                            break

                    except Exception as api_error:
                        print(f"    ⚠️  API error for {month_label}, batch {batch_num}, page {batch_pages}: {api_error}")
                        break

            print(f"  ✅ {month_label} completed: {month_records} records")

        print(f"  ✅ Retrieved {len(emissions_data)} emissions records from {tenant_label}")
        return emissions_data

    except Exception as e:
        print(f"  ❌ Error retrieving emissions from {tenant_label}: {e}")
        raise

# Retrieve emissions from both tenants
print("=" * 70)
print("🌱 RETRIEVING CARBON EMISSIONS FROM BOTH TENANTS")
print("=" * 70)

tenant_a_emissions = get_emissions_from_tenant(carbon_client_a, subscription_client_a, a_tenant_id, "Tenant A", report_month)
tenant_b_emissions = get_emissions_from_tenant(carbon_client_b, subscription_client_b, b_tenant_id, "Tenant B", report_month)

# Combine emissions from both tenants
all_emissions_data = tenant_a_emissions + tenant_b_emissions

print(f"\n{'=' * 70}")
print(f"📊 EXTRACTION SUMMARY")
print(f"{'=' * 70}")
print(f"  Tenant A: {len(tenant_a_emissions)} emissions records")
print(f"  Tenant B: {len(tenant_b_emissions)} emissions records")
print(f"  📈 Total: {len(all_emissions_data)} emissions records")
print(f"{'=' * 70}")

# CELL ********************

# Create Polars DataFrame with proper data cleaning

if not all_emissions_data:
    print("⚠️  No emissions data found across both tenants.")
    df = pl.DataFrame()
else:
    print(f"📊 Creating DataFrame with {len(all_emissions_data)} emissions records...")
    df = pl.DataFrame(all_emissions_data)

# Cast columns with proper data types
# ItemDetailsReport fields: item_name, category_type, latest_month_emissions (= emissions for
# report_month), previous_month_emissions, month_over_month_emissions_change_ratio,
# monthly_emissions_change_value, plus resource metadata fields
if df.height > 0:
    string_columns = [
        "tenant_id", "tenant_label", "report_month", "item_name", "category_type",
        "subscription_id", "subscription_name", "resource_group", "resource_id",
        "location", "resource_type", "data_type", "extracted_at"
    ]

    for col in string_columns:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Utf8))

    # Cast numeric columns
    numeric_columns = [
        "latest_month_emissions", "previous_month_emissions",
        "month_over_month_emissions_change_ratio", "monthly_emissions_change_value"
    ]
    for col in numeric_columns:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64))

print(f"✅ Created DataFrame with {df.height} rows and {df.width} columns")

if df.height > 0:
    print(f"\n📋 Columns: {', '.join(df.columns)}")

    print(f"\n📊 Emissions records by tenant and month:")
    month_summary = df.group_by(["tenant_label", "report_month"]).agg([
        pl.len().alias("records"),
        pl.col("latest_month_emissions").sum().alias("total_emissions_kgco2e")
    ]).sort(["tenant_label", "report_month"])
    print(month_summary)

    print(f"\n📄 Sample data (first 5 rows):")
    display_cols = ["tenant_label", "report_month", "item_name", "subscription_name", "latest_month_emissions"]
    available_cols = [col for col in display_cols if col in df.columns]
    print(df.select(available_cols).head(5) if available_cols else df.head(5))
else:
    print(f"\n📄 Empty dataset - no emissions data found across both tenants")

# CELL ********************

# Write DataFrame to FinOpsHub Delta Lake table
# Strategy: month-level delete-and-replace. Each report_month present in the extract is
# atomically overwritten via a Delta predicate (replaceWhere), so re-runs are idempotent
# and months not in this run are untouched.

if df.height == 0:
    print("⚠️  Nothing to write - skipping Delta write to preserve existing table contents")
else:
    months_in_df = sorted(df["report_month"].unique().to_list())
    print(f"💾 Writing {df.height} records covering months: {months_in_df}")
    print(f"📍 Target path: {emissions_delta_table_path}")

    # Determine whether the table already exists
    try:
        DeltaTable(emissions_delta_table_path)
        table_exists = True
    except Exception:
        table_exists = False

    try:
        for m in months_in_df:
            month_df = df.filter(pl.col("report_month") == m)

            if not table_exists:
                # First ever write creates the table, partitioned by report_month
                month_df.write_delta(
                    emissions_delta_table_path,
                    mode='overwrite',
                    delta_write_options={
                        'partition_by': ['report_month'],
                        'engine': 'rust'
                    }
                )
                table_exists = True
            else:
                # Atomic replace of this month's partition only
                month_df.write_delta(
                    emissions_delta_table_path,
                    mode='overwrite',
                    delta_write_options={
                        'predicate': f"report_month = '{m}'",
                        'schema_mode': 'merge',
                        'engine': 'rust'
                    }
                )

            print(f"  ✅ {m}: replaced with {month_df.height} records")

        print(f"\n✅ Successfully wrote {df.height} carbon emissions records to Delta Lake")

        # Verify the write by reading back the per-month counts
        try:
            dt = DeltaTable(emissions_delta_table_path)
            table_df = pl.from_arrow(dt.to_pyarrow_table(columns=["report_month"]))
            for m in months_in_df:
                table_count = table_df.filter(pl.col("report_month") == m).height
                df_count = df.filter(pl.col("report_month") == m).height
                status = "✅" if table_count == df_count else "⚠️ "
                print(f"  {status} {m}: {table_count} records in table (expected {df_count})")
        except Exception as verify_error:
            print(f"⚠️  Could not verify write (table may still be valid): {verify_error}")

    except Exception as write_error:
        print(f"❌ Error writing to Delta Lake: {write_error}")
        raise

# CELL ********************

# Verify and register table in metastore for SQL queries
print("=" * 70)
print("📝 VERIFICATION AND REGISTRATION")
print("=" * 70)

try:
    # For abfss:// paths, add storage_options for Fabric integration
    if emissions_delta_table_path.startswith("abfss://"):
        storage_options = {
            "bearer_token": notebookutils.credentials.getToken("storage"),
            "use_fabric_endpoint": "true"
        }
        delta_table = DeltaTable(emissions_delta_table_path, storage_options=storage_options)
    else:
        delta_table = DeltaTable(emissions_delta_table_path)

    print(f"\n✅ Delta table verified:")
    print(f"   Version: {delta_table.version()}")
    print(f"   Files: {len(delta_table.files())}")

    # Register table in Fabric metastore for SQL queries
    print("\n📝 Registering table in Fabric metastore...")
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS CarbonEmissions_MultiTenant
        USING DELTA
        LOCATION '{emissions_delta_table_path}'
    """)
    print("✅ Table 'CarbonEmissions_MultiTenant' registered in metastore")

    # Verify we can query it
    row_count = spark.sql("SELECT COUNT(*) as count FROM CarbonEmissions_MultiTenant").collect()[0]['count']
    print(f"\n✅ Table is queryable! Row count: {row_count}")

    if row_count > 0:
        # Emissions by tenant and month (latest_month_emissions = emissions for report_month)
        print("\n🌍 Emissions by tenant and month:")
        spark.sql("""
            SELECT
                tenant_label,
                report_month,
                COUNT(*) as records,
                ROUND(SUM(latest_month_emissions), 4) as total_emissions_kgco2e
            FROM CarbonEmissions_MultiTenant
            GROUP BY tenant_label, report_month
            ORDER BY tenant_label, report_month
        """).show(50, truncate=False)

        # Top emitting resources in the most recent month
        print("\n📊 Top 10 emitting resources (most recent month):")
        spark.sql("""
            SELECT
                tenant_label,
                item_name,
                subscription_name,
                ROUND(latest_month_emissions, 4) as emissions_kgco2e
            FROM CarbonEmissions_MultiTenant
            WHERE report_month = (SELECT MAX(report_month) FROM CarbonEmissions_MultiTenant)
            ORDER BY latest_month_emissions DESC
            LIMIT 10
        """).show(truncate=False)

        # Tenant distribution summary
        print("\n📈 Tenant distribution summary:")
        spark.sql("""
            SELECT
                tenant_label,
                COUNT(DISTINCT report_month) as months,
                COUNT(DISTINCT subscription_id) as subscriptions,
                COUNT(*) as total_records,
                ROUND(SUM(latest_month_emissions), 4) as total_emissions_kgco2e
            FROM CarbonEmissions_MultiTenant
            GROUP BY tenant_label
            ORDER BY tenant_label
        """).show(truncate=False)

except Exception as e:
    print(f"\n❌ Error during verification: {e}")
    raise

# CELL ********************

print("🎉 Multi-tenant carbon emissions extraction completed successfully!")
print(f"📊 Summary:")
print(f"  - report_month parameter: '{report_month}'")
print(f"  - Total emissions records processed: {len(all_emissions_data)}")
print(f"  - Tenant A records: {len(tenant_a_emissions)}")
print(f"  - Tenant B records: {len(tenant_b_emissions)}")
print(f"  - Delta table path: {emissions_delta_table_path}")
print(f"  - Table name in metastore: CarbonEmissions_MultiTenant")
print(f"  - Extraction timestamp: {datetime.now(timezone.utc).isoformat()}")

if df.height > 0:
    print(f"\n📈 Key statistics:")
    tenant_stats = df.group_by("tenant_label").agg([
        pl.len().alias("records"),
        pl.col("report_month").n_unique().alias("months"),
        pl.col("subscription_id").n_unique().alias("subscriptions"),
        pl.col("latest_month_emissions").sum().alias("total_emissions")
    ]).sort("tenant_label")

    for row in tenant_stats.iter_rows(named=True):
        print(f"  {row['tenant_label']}:")
        print(f"    - Emissions records: {row['records']}")
        print(f"    - Months loaded: {row['months']}")
        print(f"    - Subscriptions: {row['subscriptions']}")
        print(f"    - Total emissions: {row['total_emissions']:.4f} kgCO2e")
else:
    print(f"\n📊 No emissions data found - this may indicate:")
    print(f"  - Service principals need Carbon Optimization Reader permissions")
    print(f"  - Requested report_month is outside the available 12-month window")
    print(f"  - Carbon optimization data not yet available for subscriptions")

print(f"\n{'=' * 70}")
print(f"✅ NOTEBOOK COMPLETE")
print(f"{'=' * 70}")
print(f"\n🌱 Operational notes:")
print(f"  - Initial load: run once with report_month = 'all' (backfills up to 12 months)")
print(f"  - Schedule: monthly around the 20th-21st with report_month = '' (loads latest + prior month)")
print(f"  - Backfill/correction: run with report_month = 'YYYY-MM' for a specific month")
print(f"  - All writes are idempotent month-level replacements")
