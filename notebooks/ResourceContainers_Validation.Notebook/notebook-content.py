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

# ResourceContainers Silver Layer Validation Notebook
# Validates data quality and completeness after Bronze to Silver transformation
# Used in ResourceContainers_Ingestion data pipeline for quality assurance

import notebookutils
from datetime import datetime

print("🔍 ResourceContainers Silver Layer Data Validation")
print("=" * 60)

# CELL ********************

# Get configuration from Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")
finopshub_root_path = VariableLib.finopshub_root_path

# Define table paths
bronze_path = f"{finopshub_root_path}/bronze/ResourceContainers"
silver_mg_path = f"{finopshub_root_path}/silver/ManagementGroups"
silver_sub_path = f"{finopshub_root_path}/silver/Subscriptions_Hierarchy"
silver_rg_path = f"{finopshub_root_path}/silver/ResourceGroups_Hierarchy"

print(f"📍 Validation Paths:")
print(f"  Bronze: {bronze_path}")
print(f"  Silver Management Groups: {silver_mg_path}")
print(f"  Silver Subscriptions: {silver_sub_path}")
print(f"  Silver Resource Groups: {silver_rg_path}")

# CELL ********************

# Validation function
def validate_table(table_name, table_path, expected_columns=None):
    """Validate table exists and has expected structure"""
    try:
        # Check if table exists and get row count
        df = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{table_path}`")
        row_count = df.collect()[0]['count']
        
        # Get schema information
        schema_df = spark.sql(f"DESCRIBE delta.`{table_path}`")
        columns = [row.col_name for row in schema_df.collect() if row.col_name not in ['', '# Partitioning', '# col_name']]
        
        print(f"✅ {table_name}:")
        print(f"   📊 Rows: {row_count:,}")
        print(f"   📋 Columns: {len(columns)}")
        
        if expected_columns:
            missing_cols = set(expected_columns) - set(columns)
            extra_cols = set(columns) - set(expected_columns)
            
            if missing_cols:
                print(f"   ⚠️  Missing columns: {missing_cols}")
                return False
            if extra_cols:
                print(f"   ℹ️  Extra columns: {extra_cols}")
        
        if row_count == 0:
            print(f"   ⚠️  WARNING: Table is empty")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ {table_name}: FAILED - {e}")
        return False

# CELL ********************

# Validate Bronze layer
print("\n🥉 BRONZE LAYER VALIDATION")
print("-" * 40)

bronze_expected_cols = ['container_id', 'container_name', 'container_type', 'parent_id', 'subscription_id', 'extracted_at']
bronze_valid = validate_table("ResourceContainers (Bronze)", bronze_path, bronze_expected_cols)

# CELL ********************

# Validate Silver layer tables
print("\n🥈 SILVER LAYER VALIDATION")
print("-" * 40)

# Management Groups validation
mg_expected_cols = ['management_group_id', 'management_group_name', 'parent_management_group_id', 'tenant_id', 'extracted_at']
mg_valid = validate_table("Management Groups", silver_mg_path, mg_expected_cols)

# Subscriptions validation  
sub_expected_cols = ['subscription_id', 'subscription_name', 'management_group_id', 'management_group_name', 'tenant_id', 'extracted_at']
sub_valid = validate_table("Subscriptions Hierarchy", silver_sub_path, sub_expected_cols)

# Resource Groups validation
rg_expected_cols = ['resource_group_id', 'resource_group_name', 'subscription_id', 'subscription_name', 'management_group_id', 'extracted_at']
rg_valid = validate_table("Resource Groups Hierarchy", silver_rg_path, rg_expected_cols)

# CELL ********************

# Cross-layer validation checks
print("\n🔄 CROSS-LAYER VALIDATION")
print("-" * 40)

validation_passed = True

try:
    # Check Bronze to Silver record consistency
    bronze_mg_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{bronze_path}` WHERE container_type = 'Management Group'").collect()[0]['count']
    silver_mg_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{silver_mg_path}`").collect()[0]['count']
    
    bronze_sub_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{bronze_path}` WHERE container_type = 'Subscription'").collect()[0]['count']
    silver_sub_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{silver_sub_path}`").collect()[0]['count']
    
    bronze_rg_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{bronze_path}` WHERE container_type = 'Resource Group'").collect()[0]['count']
    silver_rg_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{silver_rg_path}`").collect()[0]['count']
    
    print(f"📊 Record Count Comparison:")
    print(f"   Management Groups: Bronze={bronze_mg_count:,} → Silver={silver_mg_count:,}")
    print(f"   Subscriptions: Bronze={bronze_sub_count:,} → Silver={silver_sub_count:,}")
    print(f"   Resource Groups: Bronze={bronze_rg_count:,} → Silver={silver_rg_count:,}")
    
    # Validate record counts match (allowing for some data quality filtering)
    if silver_mg_count > bronze_mg_count * 1.1 or silver_mg_count < bronze_mg_count * 0.9:
        print(f"   ⚠️  Management Groups count mismatch beyond 10% tolerance")
        validation_passed = False
        
    if silver_sub_count > bronze_sub_count * 1.1 or silver_sub_count < bronze_sub_count * 0.9:
        print(f"   ⚠️  Subscriptions count mismatch beyond 10% tolerance")
        validation_passed = False
        
    if silver_rg_count > bronze_rg_count * 1.1 or silver_rg_count < bronze_rg_count * 0.9:
        print(f"   ⚠️  Resource Groups count mismatch beyond 10% tolerance")
        validation_passed = False
    
    # Check for recent data (extracted within last 24 hours)
    recent_data_check = spark.sql(f"""
        SELECT 
            MAX(extracted_at) as latest_bronze,
            COUNT(*) as recent_records
        FROM delta.`{bronze_path}` 
        WHERE extracted_at >= current_timestamp() - interval 1 day
    """).collect()[0]
    
    if recent_data_check['recent_records'] == 0:
        print(f"   ⚠️  No recent data found (last 24 hours)")
        validation_passed = False
    else:
        print(f"   ✅ Recent data found: {recent_data_check['recent_records']:,} records")
        print(f"   📅 Latest extraction: {recent_data_check['latest_bronze']}")

except Exception as e:
    print(f"❌ Cross-layer validation failed: {e}")
    validation_passed = False

# CELL ********************

# Data quality checks
print("\n🔍 DATA QUALITY CHECKS")
print("-" * 40)

try:
    # Check for null key values
    null_checks = [
        ("Management Groups", silver_mg_path, "management_group_id"),
        ("Subscriptions", silver_sub_path, "subscription_id"),
        ("Resource Groups", silver_rg_path, "resource_group_id")
    ]
    
    for table_name, path, key_col in null_checks:
        null_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{path}` WHERE {key_col} IS NULL").collect()[0]['count']
        if null_count > 0:
            print(f"   ⚠️  {table_name}: {null_count} records with null {key_col}")
            validation_passed = False
        else:
            print(f"   ✅ {table_name}: No null key values")
    
    # Check for duplicate keys
    for table_name, path, key_col in null_checks:
        total_count = spark.sql(f"SELECT COUNT(*) as count FROM delta.`{path}`").collect()[0]['count']
        distinct_count = spark.sql(f"SELECT COUNT(DISTINCT {key_col}) as count FROM delta.`{path}`").collect()[0]['count']
        
        if total_count != distinct_count:
            duplicates = total_count - distinct_count
            print(f"   ⚠️  {table_name}: {duplicates} duplicate {key_col} values")
            validation_passed = False
        else:
            print(f"   ✅ {table_name}: No duplicate key values")

except Exception as e:
    print(f"❌ Data quality checks failed: {e}")
    validation_passed = False

# CELL ********************

# Final validation summary
print("\n" + "=" * 60)
print("📋 VALIDATION SUMMARY")
print("=" * 60)

overall_valid = bronze_valid and mg_valid and sub_valid and rg_valid and validation_passed

if overall_valid:
    print("✅ ALL VALIDATIONS PASSED")
    print("   📊 All tables exist with expected schemas")
    print("   🔍 Data quality checks passed")
    print("   🔄 Cross-layer consistency verified")
    print("   📅 Recent data available")
    
    # Pipeline success metrics
    total_silver_records = (
        spark.sql(f"SELECT COUNT(*) as count FROM delta.`{silver_mg_path}`").collect()[0]['count'] +
        spark.sql(f"SELECT COUNT(*) as count FROM delta.`{silver_sub_path}`").collect()[0]['count'] +
        spark.sql(f"SELECT COUNT(*) as count FROM delta.`{silver_rg_path}`").collect()[0]['count']
    )
    
    print(f"\n📈 Pipeline Success Metrics:")
    print(f"   🥈 Total Silver records: {total_silver_records:,}")
    print(f"   🏗️  Management Groups: {spark.sql(f'SELECT COUNT(*) as count FROM delta.`{silver_mg_path}`').collect()[0]['count']:,}")
    print(f"   🔄 Subscriptions: {spark.sql(f'SELECT COUNT(*) as count FROM delta.`{silver_sub_path}`').collect()[0]['count']:,}")
    print(f"   📦 Resource Groups: {spark.sql(f'SELECT COUNT(*) as count FROM delta.`{silver_rg_path}`').collect()[0]['count']:,}")
    print(f"   ⏰ Validation completed: {datetime.utcnow().isoformat()}")
    
else:
    print("❌ VALIDATION FAILURES DETECTED")
    print("   🚨 Pipeline should be investigated")
    print("   📋 Check logs above for specific issues")
    print("   🔧 Manual intervention may be required")
    
    # Raise exception to fail pipeline activity
    raise Exception("ResourceContainers Silver layer validation failed - see output for details")

print("=" * 60)