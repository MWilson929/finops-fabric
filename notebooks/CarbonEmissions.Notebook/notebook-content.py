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

# Azure Carbon Optimization Emissions Notebook
# Queries Azure Carbon Optimization API for emissions data across all Azure subscriptions
# Supports sustainability reporting and carbon footprint analysis for FinOps Hub

%pip install polars deltalake azure-identity azure-keyvault-secrets azure-mgmt-carbonoptimization azure-mgmt-subscription --quiet

# CELL ********************

import polars as pl
from deltalake import write_deltalake, DeltaTable
from azure.identity import ClientSecretCredential
from azure.mgmt.carbonoptimization import CarbonOptimizationMgmtClient
from azure.mgmt.carbonoptimization.models import (
    DateRange, EmissionScopeEnum, CategoryTypeEnum, 
    OrderByColumnEnum, SortDirectionEnum, ItemDetailsQueryFilter
)
from azure.mgmt.subscription import SubscriptionClient
from datetime import datetime, date
import json

# CELL ********************

# Get the Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")
key_vault_url = VariableLib.key_vault_url
secret_name = VariableLib.secret_name
layer = "bronze"

# Use root path and append specific table name
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
emissions_delta_table_path = f"{finopshub_root_path}/{layer}/CarbonEmissions"

# Get non-sensitive configuration from Variable Library
tenant_id = VariableLib.tenant_id
client_id = VariableLib.client_id

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL: {key_vault_url}")
print(f"  Secret Name: {secret_name}")
print(f"  Delta Table Path: {emissions_delta_table_path}")
print(f"  Tenant ID: {tenant_id}")
print(f"  Client ID: {client_id}")

# CELL ********************

# Create credential using the service principal

# Validate that we have required configuration
if not all([tenant_id, client_id, key_vault_url, secret_name]):
    raise ValueError("Missing required configuration from Variable Library")

print("🔐 Creating service principal credential...")

# Create credential - retrieve secret inline without storing in a variable
sp_credential = ClientSecretCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=notebookutils.credentials.getSecret(key_vault_url, secret_name)
)

# Create Carbon Optimization client
carbon_client = CarbonOptimizationMgmtClient(credential=sp_credential)
carbon_service = carbon_client.carbon_service

# Create Subscription client to get list of subscriptions
subscription_client = SubscriptionClient(sp_credential)

print("✓ Successfully created Azure Carbon Optimization and Subscription clients")

# CELL ********************

# Get all subscription IDs and available carbon data date range
print("🌍 Discovering Azure subscriptions and carbon data availability...")

try:
    # Get subscriptions
    subscriptions = list(subscription_client.subscriptions.list())
    subscription_ids = [sub.subscription_id for sub in subscriptions]
    subscription_names = {sub.subscription_id: sub.display_name for sub in subscriptions}
    
    print(f"✅ Found {len(subscription_ids)} subscriptions")
    if len(subscription_ids) <= 5:
        print(f"  📋 Subscriptions:")
        for sub_id in subscription_ids:
            print(f"    - {subscription_names[sub_id]} ({sub_id})")
    else:
        print(f"  📋 First 5 subscriptions:")
        for sub_id in subscription_ids[:5]:
            print(f"    - {subscription_names[sub_id]} ({sub_id})")
        print(f"    ... and {len(subscription_ids) - 5} more")
    
    # Get available date range for carbon data
    available_date_range = carbon_service.query_carbon_emission_data_available_date_range()
    start_date = available_date_range.start_date
    end_date = available_date_range.end_date
    
    print(f"\n🗓️  Carbon emissions data available:")
    print(f"   From: {start_date}")
    print(f"   To: {end_date}")
    
    # Calculate subscription batches (API supports max 100 subscriptions per request)
    max_subs_per_request = 100
    subscription_batches = [
        subscription_ids[i:i + max_subs_per_request] 
        for i in range(0, len(subscription_ids), max_subs_per_request)
    ]
    
    print(f"\n📊 Processing plan:")
    print(f"   Total subscriptions: {len(subscription_ids)}")
    print(f"   API batches needed: {len(subscription_batches)}")
    print(f"   Query date range: {end_date} (latest available month)")
    
except Exception as e:
    print(f"❌ Error during discovery: {e}")
    raise

# CELL ********************

# Query Carbon Optimization API for emissions by resource
print("\n" + "=" * 70)
print("🌱 QUERYING AZURE CARBON OPTIMIZATION FOR EMISSIONS DATA")
print("=" * 70)

# Use latest month for emissions data (most recent complete data)
query_date_range = DateRange(
    start=date.fromisoformat(end_date),
    end=date.fromisoformat(end_date)
)

print(f"\n🔍 Query configuration:")
print(f"   Date range: {end_date}")
print(f"   Emission scopes: Scope 1, 2, 3 (comprehensive)")
print(f"   Category type: Resource-level emissions")
print(f"   Max page size: 1000 records")

# Collect all emissions data across subscription batches
all_emissions_data = []
total_pages = 0

for batch_num, subscription_batch in enumerate(subscription_batches, 1):
    print(f"\n📦 Processing batch {batch_num}/{len(subscription_batches)} ({len(subscription_batch)} subscriptions)...")
    
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
        page_size=1000  # Max page size
    )

    # Execute query and handle pagination for this batch
    batch_emissions = []
    batch_pages = 0

    while True:
        batch_pages += 1
        total_pages += 1
        
        try:
            result_list = carbon_service.query_carbon_emission_reports(query_filter)
            
            # Process results
            if result_list.value:
                for item in result_list.value:
                    # Convert to dictionary
                    emission = item.as_dict()
                    
                    # Add extraction and batch metadata
                    emission['extracted_at'] = datetime.utcnow().isoformat()
                    emission['query_start_date'] = end_date
                    emission['query_end_date'] = end_date
                    emission['batch_number'] = batch_num
                    emission['subscription_name'] = subscription_names.get(emission.get('subscription_id'), 'Unknown')
                    
                    # Convert any nested objects to JSON strings for Delta Lake compatibility
                    for key, value in emission.items():
                        if isinstance(value, (dict, list)):
                            if value:  # Non-empty
                                emission[key] = json.dumps(value)
                            else:  # Empty
                                emission[key] = None
                    
                    batch_emissions.append(emission)
            
            print(f"    📄 Batch {batch_num}, Page {batch_pages}: {len(result_list.value) if result_list.value else 0} emissions records")
            
            # Check if there are more results for this batch
            if result_list.skip_token:
                query_filter.skip_token = result_list.skip_token
            else:
                break
                
        except Exception as api_error:
            print(f"    ⚠️  API error on batch {batch_num}, page {batch_pages}: {api_error}")
            break
    
    all_emissions_data.extend(batch_emissions)
    print(f"  ✅ Batch {batch_num} completed: {len(batch_emissions)} records")

print(f"\n{'=' * 70}")
print(f"📊 EMISSIONS DATA COLLECTION SUMMARY")
print(f"{'=' * 70}")
print(f"  Total subscription batches processed: {len(subscription_batches)}")
print(f"  Total API pages retrieved: {total_pages}")
print(f"  Total emissions records collected: {len(all_emissions_data)}")
print(f"  Query date: {end_date}")
print(f"{'=' * 70}")

# CELL ********************

# Create Polars DataFrame with comprehensive data validation

if not all_emissions_data:
    print("⚠️  No emissions data found. Creating empty DataFrame with expected schema...")
    # Create empty DataFrame with expected schema
    df = pl.DataFrame({
        "subscription_id": [],
        "subscription_name": [],
        "resource_id": [],
        "resource_name": [],
        "resource_type": [],
        "resource_location": [],
        "emission_scope": [],
        "carbon_emission_quantity": [],
        "carbon_emission_unit": [],
        "cost": [],
        "cost_currency": [],
        "tags": [],
        "extracted_at": [],
        "query_start_date": [],
        "query_end_date": [],
        "batch_number": []
    })
else:
    print(f"🧹 Cleaning and validating {len(all_emissions_data)} emissions records...")
    
    # Additional data cleaning for any remaining complex types
    for emission in all_emissions_data:
        for key, value in emission.items():
            # Convert any remaining dicts or lists to JSON strings
            if isinstance(value, (dict, list)):
                if value:  # Non-empty
                    emission[key] = json.dumps(value)
                else:  # Empty
                    emission[key] = None
            # Handle date objects
            elif isinstance(value, date):
                emission[key] = value.isoformat()
    
    print("✓ Data cleaned successfully")
    
    # Create Polars DataFrame
    df = pl.DataFrame(all_emissions_data)

# Cast key columns to proper string types to avoid Null type issues
if df.height > 0:
    string_columns = [
        "subscription_id", "subscription_name", "resource_id", "resource_name", 
        "resource_type", "resource_location", "emission_scope", "carbon_emission_unit",
        "cost_currency", "tags", "extracted_at", "query_start_date", "query_end_date"
    ]
    
    for col in string_columns:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Utf8))
    
    # Cast numeric columns
    numeric_columns = ["carbon_emission_quantity", "cost", "batch_number"]
    for col in numeric_columns:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64))

print(f"✅ Created DataFrame with {df.height} rows and {df.width} columns")

if df.height > 0:
    print(f"\n📋 Schema ({df.width} columns):")
    for col_name, dtype in zip(df.columns, df.dtypes):
        print(f"  {col_name}: {dtype}")
    
    print(f"\n🌍 Emissions by scope:")
    if "emission_scope" in df.columns:
        scope_summary = df.group_by("emission_scope").agg([
            pl.count().alias("records"),
            pl.col("carbon_emission_quantity").sum().alias("total_emissions")
        ]).sort("total_emissions", descending=True)
        print(scope_summary)
    
    print(f"\n📊 Top resource types by emissions:")
    if "resource_type" in df.columns and "carbon_emission_quantity" in df.columns:
        type_summary = df.group_by("resource_type").agg([
            pl.count().alias("resources"),
            pl.col("carbon_emission_quantity").sum().alias("total_emissions")
        ]).sort("total_emissions", descending=True).head(10)
        print(type_summary)
    
    print(f"\n📄 Sample data (first 5 rows):")
    display_cols = ["subscription_name", "resource_type", "emission_scope", "carbon_emission_quantity", "carbon_emission_unit"]
    available_cols = [col for col in display_cols if col in df.columns]
    if available_cols:
        print(df.select(available_cols).head(5))
    else:
        print(df.head(5))
        
else:
    print(f"\n📄 Empty dataset - no emissions data available for {end_date}")

# CELL ********************

# Write DataFrame to FinOpsHub Delta Lake table

print(f"💾 Writing {df.height} carbon emissions records to Delta Lake...")
print(f"📍 Target path: {emissions_delta_table_path}")

try:
    df.write_delta(
        emissions_delta_table_path,
        mode='overwrite',
        delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
    )
    
    print(f"✅ Successfully wrote {df.height} carbon emissions records to Delta Lake")
    
    # Verify the write by reading back the count
    try:
        dt = DeltaTable(emissions_delta_table_path)
        record_count = dt.to_pandas().shape[0]
        print(f"🔍 Verification: {record_count} records in Delta table")
        
        if record_count != df.height:
            print(f"⚠️  Warning: Row count mismatch - DataFrame had {df.height} rows, table has {record_count}")
        else:
            print(f"✅ Row count verification passed")
            
    except Exception as verify_error:
        print(f"⚠️  Could not verify write (table may still be valid): {verify_error}")

except Exception as write_error:
    print(f"❌ Error writing to Delta Lake: {write_error}")
    raise

# CELL ********************

# Verify and register table in metastore for SQL queries
print("\n" + "=" * 70)
print("📝 VERIFICATION AND METASTORE REGISTRATION")
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
        CREATE TABLE IF NOT EXISTS CarbonEmissions
        USING DELTA
        LOCATION '{emissions_delta_table_path}'
    """)
    print("✅ Table 'CarbonEmissions' registered in metastore")
    
    # Verify we can query it
    row_count = spark.sql("SELECT COUNT(*) as count FROM CarbonEmissions").collect()[0]['count']
    print(f"\n✅ Table is queryable! Row count: {row_count}")
    
    if row_count > 0:
        # Show emissions summary by scope
        print("\n🌍 Emissions summary by scope:")
        spark.sql("""
            SELECT 
                emission_scope,
                COUNT(*) as resource_count,
                ROUND(SUM(carbon_emission_quantity), 4) as total_emissions,
                carbon_emission_unit,
                ROUND(SUM(cost), 2) as total_cost,
                cost_currency
            FROM CarbonEmissions
            GROUP BY emission_scope, carbon_emission_unit, cost_currency
            ORDER BY total_emissions DESC
        """).show(truncate=False)
        
        # Show top emitting resource types
        print("\n📊 Top 10 resource types by emissions:")
        spark.sql("""
            SELECT 
                resource_type,
                COUNT(*) as resource_count,
                ROUND(SUM(carbon_emission_quantity), 4) as total_emissions,
                carbon_emission_unit
            FROM CarbonEmissions
            GROUP BY resource_type, carbon_emission_unit
            ORDER BY total_emissions DESC
            LIMIT 10
        """).show(truncate=False)
        
        # Show subscription summary
        print("\n📈 Emissions by subscription:")
        spark.sql("""
            SELECT 
                subscription_name,
                COUNT(*) as resource_count,
                ROUND(SUM(carbon_emission_quantity), 4) as total_emissions,
                carbon_emission_unit
            FROM CarbonEmissions
            GROUP BY subscription_name, carbon_emission_unit
            ORDER BY total_emissions DESC
            LIMIT 10
        """).show(truncate=False)
    
except Exception as e:
    print(f"\n❌ Error during verification: {e}")
    raise

# CELL ********************

print("🌱 Carbon emissions data extraction completed successfully!")
print(f"📊 Summary:")
print(f"  - Total subscriptions analyzed: {len(subscription_ids)}")
print(f"  - Total emissions records processed: {len(all_emissions_data)}")
print(f"  - API batches processed: {len(subscription_batches)}")
print(f"  - Total API pages retrieved: {total_pages}")
print(f"  - Query date: {end_date}")
print(f"  - Delta table path: {emissions_delta_table_path}")
print(f"  - Table name in metastore: CarbonEmissions")
print(f"  - Extraction timestamp: {datetime.utcnow().isoformat()}")

if df.height > 0:
    print(f"\n🌍 Sustainability insights:")
    
    # Calculate total emissions by scope
    if "emission_scope" in df.columns and "carbon_emission_quantity" in df.columns:
        scope_totals = df.group_by("emission_scope").agg(
            pl.col("carbon_emission_quantity").sum().alias("total_emissions")
        ).sort("total_emissions", descending=True)
        
        for row in scope_totals.iter_rows(named=True):
            scope = row['emission_scope']
            emissions = row['total_emissions']
            print(f"  - {scope}: {emissions:.4f} units")
    
    # Calculate resource coverage
    unique_resources = df.select("resource_id").n_unique()
    unique_subscriptions = df.select("subscription_id").n_unique()
    print(f"\n📈 Coverage statistics:")
    print(f"  - Unique resources analyzed: {unique_resources}")
    print(f"  - Subscriptions with emissions data: {unique_subscriptions}")
    
    if "cost" in df.columns:
        total_cost = df.select(pl.col("cost").sum()).item()
        print(f"  - Total associated cost: {total_cost:.2f}")
        
else:
    print(f"\n📊 No emissions data found - this may indicate:")
    print(f"  - No carbon emissions recorded for {end_date}")
    print(f"  - Service principal needs Carbon Optimization Reader permissions")
    print(f"  - Carbon optimization data not yet available for subscriptions")
    print(f"  - Resources have zero carbon footprint for the query period")

print(f"\n{'=' * 70}")
print(f"✅ CARBON EMISSIONS EXTRACTION COMPLETE")
print(f"{'=' * 70}")
print(f"\n🌱 This data supports:")
print(f"  - Sustainability reporting and ESG compliance")
print(f"  - Carbon footprint analysis by resource and subscription")
print(f"  - Cost-carbon correlation analysis for optimization")
print(f"  - Scope 1, 2, 3 emissions tracking and management")
print(f"  - Resource-level carbon attribution for accountability")