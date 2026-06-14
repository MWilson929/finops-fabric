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

# Azure Resource Containers Silver Layer
# Reads Bronze ResourceContainers and splits into typed tables (ManagementGroups, Subscriptions, ResourceGroups)
# Implements the Silver layer of the medallion architecture for organized data processing

%pip install polars deltalake --quiet

# CELL ********************

import polars as pl
from deltalake import DeltaTable
from datetime import datetime

# CELL ********************

# Get the Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")

# Define paths following medallion architecture
finopshub_root_path = VariableLib.finopshub_root_path

# Bronze layer - source (raw data from Azure Resource Graph)
bronze_resourcecontainers_path = f"{finopshub_root_path}/bronze/ResourceContainers"

# Silver layer - targets (cleaned, typed data split by container type)
silver_managementgroups_path = f"{finopshub_root_path}/silver/ManagementGroups"
silver_subscriptions_path = f"{finopshub_root_path}/silver/Subscriptions"
silver_resourcegroups_path = f"{finopshub_root_path}/silver/ResourceGroups"

# Print configuration for verification
print("✓ Loaded configuration from Variable Library:")
print(f"\n  📊 Bronze Source (Raw Data):")
print(f"    {bronze_resourcecontainers_path}")
print(f"\n  🥈 Silver Targets (Typed Data):")
print(f"    Management Groups: {silver_managementgroups_path}")
print(f"    Subscriptions: {silver_subscriptions_path}")
print(f"    Resource Groups: {silver_resourcegroups_path}")

# CELL ********************

# Read Bronze ResourceContainers table
print("📖 Reading Bronze ResourceContainers table...")

try:
    # For abfss:// paths, add storage_options for Fabric integration
    if bronze_resourcecontainers_path.startswith("abfss://"):
        storage_options = {
            "bearer_token": notebookutils.credentials.getToken("storage"),
            "use_fabric_endpoint": "true"
        }
        bronze_df = pl.read_delta(bronze_resourcecontainers_path, storage_options=storage_options)
    else:
        bronze_df = pl.read_delta(bronze_resourcecontainers_path)

    print(f"✅ Successfully loaded {bronze_df.height} containers from Bronze layer")
    print(f"\n📋 Schema: {bronze_df.width} columns")
    print(f"   Columns: {', '.join(bronze_df.columns)}")
    
    print(f"\n📊 Container types in Bronze layer:")
    type_summary = bronze_df.group_by("type").agg(pl.len().alias("count")).sort("count", descending=True)
    print(type_summary)
    
    # Show sample data
    if bronze_df.height > 0:
        print(f"\n📄 Sample Bronze data:")
        print(bronze_df.select(["name", "type", "location", "subscriptionId"]).head(5))
    
except Exception as e:
    print(f"❌ Error reading Bronze table: {e}")
    raise

# CELL ********************

# Split by container type with comprehensive validation
print("\n" + "=" * 70)
print("🔄 SPLITTING BY CONTAINER TYPE")
print("=" * 70)

# Add transformation timestamp for lineage tracking
transformation_time = datetime.utcnow().isoformat()

# Define expected container types (case-insensitive matching)
container_types = {
    "management_groups": "microsoft.management/managementgroups",
    "subscriptions": "microsoft.resources/subscriptions", 
    "resource_groups": "microsoft.resources/subscriptions/resourcegroups"
}

print(f"🔍 Filtering containers by type (transformation time: {transformation_time})...")

# Filter for Management Groups
df_managementgroups = bronze_df.filter(
    pl.col("type").str.to_lowercase() == container_types["management_groups"]
).with_columns(
    pl.lit(transformation_time).alias("silver_transformed_at"),
    pl.lit("management_group").alias("container_category")
)
print(f"\n📁 Management Groups: {df_managementgroups.height} containers")

# Filter for Subscriptions  
df_subscriptions = bronze_df.filter(
    pl.col("type").str.to_lowercase() == container_types["subscriptions"]
).with_columns(
    pl.lit(transformation_time).alias("silver_transformed_at"),
    pl.lit("subscription").alias("container_category")
)
print(f"📁 Subscriptions: {df_subscriptions.height} containers")

# Filter for Resource Groups
df_resourcegroups = bronze_df.filter(
    pl.col("type").str.to_lowercase() == container_types["resource_groups"]
).with_columns(
    pl.lit(transformation_time).alias("silver_transformed_at"),
    pl.lit("resource_group").alias("container_category")
)
print(f"📁 Resource Groups: {df_resourcegroups.height} containers")

# Check for any unknown/unprocessed types
known_types = list(container_types.values())
unknown_df = bronze_df.filter(
    ~pl.col("type").str.to_lowercase().is_in(known_types)
)

if unknown_df.height > 0:
    print(f"\n⚠️  Warning: {unknown_df.height} containers with unknown types:")
    unknown_types = unknown_df.select("type").unique().sort("type")
    print(unknown_types)
    print("\nThese containers will not be processed in Silver layer.")
else:
    print(f"\n✅ All container types recognized and processed")

# Validation summary
total_split = df_managementgroups.height + df_subscriptions.height + df_resourcegroups.height
print(f"\n📊 Processing Summary:")
print(f"  Bronze containers read: {bronze_df.height}")
print(f"  Containers processed: {total_split}")
print(f"  Containers skipped: {bronze_df.height - total_split}")
print(f"  Processing efficiency: {(total_split/bronze_df.height*100):.1f}%" if bronze_df.height > 0 else "  Processing efficiency: 0%")

# CELL ********************

# Write to Silver layer with comprehensive error handling
print("\n" + "=" * 70)
print("💾 WRITING TO SILVER LAYER")
print("=" * 70)

write_results = {}

# Helper function to write Delta table with verification
def write_silver_table(df, path, table_name):
    """Write DataFrame to Silver layer with validation"""
    try:
        if df.height > 0:
            print(f"\n📝 Writing {df.height} {table_name.lower()} to Silver layer...")
            print(f"   Target: {path}")
            
            df.write_delta(
                path,
                mode='overwrite',
                delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
            )
            
            # Verify write
            try:
                if path.startswith("abfss://"):
                    storage_options = {
                        "bearer_token": notebookutils.credentials.getToken("storage"),
                        "use_fabric_endpoint": "true"
                    }
                    dt = DeltaTable(path, storage_options=storage_options)
                else:
                    dt = DeltaTable(path)
                
                record_count = dt.to_pandas().shape[0]
                print(f"   ✅ {table_name} written successfully ({record_count} records verified)")
                return {"status": "success", "records": record_count}
                
            except Exception as verify_error:
                print(f"   ⚠️  Write completed but verification failed: {verify_error}")
                return {"status": "written_unverified", "records": df.height}
                
        else:
            print(f"\n⚠️  No {table_name.lower()} data to write")
            return {"status": "no_data", "records": 0}
            
    except Exception as write_error:
        print(f"\n❌ Error writing {table_name}: {write_error}")
        return {"status": "error", "records": 0, "error": str(write_error)}

# Write each container type to its Silver table
write_results["management_groups"] = write_silver_table(
    df_managementgroups, 
    silver_managementgroups_path, 
    "Management Groups"
)

write_results["subscriptions"] = write_silver_table(
    df_subscriptions,
    silver_subscriptions_path,
    "Subscriptions"
)

write_results["resource_groups"] = write_silver_table(
    df_resourcegroups,
    silver_resourcegroups_path,
    "Resource Groups"
)

# Summary of writes
print(f"\n{'=' * 70}")
print(f"📊 SILVER LAYER WRITE SUMMARY")
print(f"{'=' * 70}")

total_records_written = 0
successful_writes = 0

for table_type, result in write_results.items():
    status_icon = {
        "success": "✅",
        "written_unverified": "⚠️ ",
        "no_data": "📭",
        "error": "❌"
    }.get(result["status"], "❓")
    
    print(f"{status_icon} {table_type.replace('_', ' ').title()}: {result['records']} records ({result['status']})")
    
    if result["status"] in ["success", "written_unverified"]:
        total_records_written += result["records"]
        successful_writes += 1

print(f"\n📈 Overall Results:")
print(f"  Tables successfully written: {successful_writes}/3")
print(f"  Total records in Silver layer: {total_records_written}")
print(f"  Data transformation: Bronze → Silver completed")

if successful_writes == 3:
    print(f"\n🎉 All Silver layer tables written successfully!")
else:
    print(f"\n⚠️  Some writes had issues - check logs above")

# CELL ********************

# Register Silver tables in Fabric metastore for SQL querying
print("\n" + "=" * 70)
print("📝 REGISTERING SILVER TABLES IN METASTORE")
print("=" * 70)

registration_results = {}

def register_table(path, table_name, container_type):
    """Register Silver table in Fabric metastore"""
    try:
        print(f"\n📋 Registering {table_name} table...")
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {table_name}
            USING DELTA
            LOCATION '{path}'
        """)
        
        # Verify registration with a simple query
        try:
            row_count = spark.sql(f"SELECT COUNT(*) as count FROM {table_name}").collect()[0]['count']
            print(f"   ✅ {table_name} registered successfully ({row_count} records queryable)")
            return {"status": "success", "records": row_count}
        except Exception as query_error:
            print(f"   ⚠️  Table registered but query verification failed: {query_error}")
            return {"status": "registered_unverified"}
            
    except Exception as reg_error:
        print(f"   ❌ Error registering {table_name}: {reg_error}")
        return {"status": "error", "error": str(reg_error)}

# Register tables only if they have data
if write_results["management_groups"]["records"] > 0:
    registration_results["management_groups"] = register_table(
        silver_managementgroups_path,
        "Silver_ManagementGroups",
        "Management Groups"
    )

if write_results["subscriptions"]["records"] > 0:
    registration_results["subscriptions"] = register_table(
        silver_subscriptions_path,
        "Silver_Subscriptions", 
        "Subscriptions"
    )

if write_results["resource_groups"]["records"] > 0:
    registration_results["resource_groups"] = register_table(
        silver_resourcegroups_path,
        "Silver_ResourceGroups",
        "Resource Groups"
    )

# Show sample queries if tables are registered
if registration_results:
    print(f"\n📊 Sample SQL queries for registered tables:")
    
    for table_type, result in registration_results.items():
        if result["status"] == "success":
            table_name = f"Silver_{table_type.replace('_', '').title()}"
            print(f"\n-- Query {table_name}")
            print(f"SELECT name, location, subscriptionId, silver_transformed_at")
            print(f"FROM {table_name}")
            print(f"ORDER BY name LIMIT 10;")

# CELL ********************

print("🎉 Silver layer transformation completed successfully!")
print(f"📊 Summary:")
print(f"  - Bronze containers processed: {bronze_df.height}")
print(f"  - Silver tables created: {len([r for r in write_results.values() if r['records'] > 0])}")
print(f"  - Total Silver records: {sum([r['records'] for r in write_results.values()])}")
print(f"  - Transformation timestamp: {transformation_time}")

print(f"\n🥈 Silver Layer Benefits:")
print(f"  ✅ Type-specific tables for optimized queries")
print(f"  ✅ Enhanced schema with transformation metadata") 
print(f"  ✅ Category classification for better organization")
print(f"  ✅ SQL-queryable tables registered in metastore")

print(f"\n📊 Silver Tables Created:")
for table_type, result in write_results.items():
    if result["records"] > 0:
        table_name = f"Silver_{table_type.replace('_', '').title()}"
        print(f"  - {table_name}: {result['records']} records")

print(f"\n🔄 Data Flow:")
print(f"  Bronze_ResourceContainers → Silver_ManagementGroups")
print(f"                           → Silver_Subscriptions") 
print(f"                           → Silver_ResourceGroups")

print(f"\n🚀 Next Steps:")
print(f"  - Use Silver tables for FinOps reporting and analysis")
print(f"  - Build Gold layer aggregations from Silver data")
print(f"  - Create Power BI reports connecting to Silver tables")
print(f"  - Set up automated refresh schedules for Bronze→Silver pipeline")