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

# Azure Resource Graph - Resource Containers Bronze Layer
# Queries Azure Resource Graph for ALL container types and writes to Bronze layer
# Includes Management Groups, Subscriptions, and Resource Groups

%pip install polars deltalake azure-identity azure-keyvault-secrets azure-mgmt-resourcegraph --quiet

# CELL ********************

import polars as pl
from deltalake import write_deltalake, DeltaTable
from azure.identity import ClientSecretCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
from datetime import datetime
import json

# CELL ********************

# Get the Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")
key_vault_url = VariableLib.key_vault_url
secret_name = VariableLib.secret_name

# Bronze layer path - raw data from Azure Resource Graph
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
bronze_resourcecontainers_path = f"{finopshub_root_path}/bronze/ResourceContainers"

# Get non-sensitive configuration from Variable Library
tenant_id = VariableLib.tenant_id
client_id = VariableLib.client_id

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL: {key_vault_url}")
print(f"  Secret Name: {secret_name}")
print(f"  Bronze Table Path: {bronze_resourcecontainers_path}")
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

# Create Resource Graph client
resource_graph_client = ResourceGraphClient(sp_credential)

print("✓ Successfully created Resource Graph client")

# CELL ********************

# Query Azure Resource Graph for ALL resource containers
print("🔍 Querying Azure Resource Graph for all resource containers...")
print("📦 This includes: Management Groups, Subscriptions, and Resource Groups")
print("")

# Define the KQL query - NO WHERE clause to get ALL container types
query = """
ResourceContainers
| project 
    id,
    name,
    type,
    location,
    subscriptionId,
    resourceGroup,
    tags,
    properties,
    managedBy,
    tenantId
| order by type, name asc
"""

# Create query request (omitting subscriptions queries all accessible subscriptions)
request = QueryRequest(
    query=query,
    options=QueryRequestOptions(
        result_format="objectArray",  # Return results as array of objects
        skip_token=None,
        top=1000  # Maximum results per page
    )
)

# Execute query and handle pagination
containers_data = []
page_count = 0
type_counts = {}
subscription_ids_found = set()

print("📊 Processing results...")

while True:
    page_count += 1
    response = resource_graph_client.resources(request)
    
    # Process results
    if response.data:
        for container in response.data:
            # Track type counts and subscriptions
            container_type = container.get('type', 'unknown')
            type_counts[container_type] = type_counts.get(container_type, 0) + 1
            
            if container.get('subscriptionId'):
                subscription_ids_found.add(container['subscriptionId'])
            
            # Add extraction timestamp
            container['extracted_at'] = datetime.utcnow().isoformat()
            
            # Convert complex types to JSON strings (Layer 1 cleaning)
            if 'tags' in container and container['tags']:
                container['tags'] = json.dumps(container['tags'])
            if 'properties' in container and container['properties']:
                container['properties'] = json.dumps(container['properties'])
            
            containers_data.append(container)
    
    print(f"  📄 Page {page_count}: Retrieved {len(response.data)} containers (Total: {len(containers_data)})")
    
    # Check if there are more results
    if response.skip_token:
        request.options.skip_token = response.skip_token
    else:
        break

print(f"\n✅ Successfully retrieved {len(containers_data)} total containers across {page_count} pages")
print(f"📊 Found containers across {len(subscription_ids_found)} subscriptions")

print(f"\n📦 Container types breakdown:")
for container_type, count in sorted(type_counts.items()):
    print(f"  - {container_type}: {count}")

# CELL ********************

# Clean data - convert ALL remaining dict/complex types to strings (Layer 2 cleaning)

if not containers_data:
    print("⚠️  No containers found. Creating empty DataFrame with schema...")
    # Create empty DataFrame with expected schema
    df = pl.DataFrame({
        "id": [],
        "name": [],
        "type": [],
        "location": [],
        "subscriptionId": [],
        "resourceGroup": [],
        "tags": [],
        "properties": [],
        "managedBy": [],
        "tenantId": [],
        "extracted_at": []
    })
else:
    print("🧹 Cleaning data before DataFrame creation...")
    # Layer 2 cleaning - ensure all complex types are converted to strings
    for container in containers_data:
        for key, value in container.items():
            # Convert any remaining dicts (including empty {}) to JSON string or None
            if isinstance(value, dict):
                if len(value) > 0:
                    container[key] = json.dumps(value)
                else:
                    container[key] = None
            # Convert any lists to JSON strings
            elif isinstance(value, list):
                if len(value) > 0:
                    container[key] = json.dumps(value)
                else:
                    container[key] = None

    print("✓ Data cleaned successfully")

    # Create Polars DataFrame - now all values should be simple types
    df = pl.DataFrame(containers_data)

# Cast columns to proper string types to avoid Null type issues
string_columns = [
    "id", "name", "type", "location", "subscriptionId", 
    "resourceGroup", "tags", "properties", "managedBy", 
    "tenantId", "extracted_at"
]

for col in string_columns:
    if col in df.columns:
        df = df.with_columns(pl.col(col).cast(pl.Utf8))

print(f"✅ Created DataFrame with {df.height} rows and {df.width} columns")

if df.height > 0:
    print(f"\n📋 Columns: {', '.join(df.columns)}")
    
    print(f"\n📦 Container types in DataFrame:")
    type_breakdown = df.group_by("type").agg(pl.count().alias("count")).sort("count", descending=True)
    print(type_breakdown)
    
    print(f"\n🌍 Location distribution:")
    location_breakdown = df.group_by("location").agg(pl.count().alias("count")).sort("count", descending=True).head(10)
    print(location_breakdown)
    
    print(f"\n📄 Sample data (first 5 rows):")
    print(df.select(["name", "type", "location", "subscriptionId"]).head(5))
else:
    print(f"\n📄 Empty dataset - no containers found")

# CELL ********************

# Write DataFrame to Bronze layer
print(f"💾 Writing {df.height} resource containers to Bronze layer...")
print(f"📍 Target path: {bronze_resourcecontainers_path}")

try:
    df.write_delta(
        bronze_resourcecontainers_path,
        mode='overwrite',
        delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
    )
    
    print(f"✅ Successfully wrote {df.height} container records to Bronze Delta Lake table")
    
    # Verify the write by reading back the count
    try:
        dt = DeltaTable(bronze_resourcecontainers_path)
        record_count = dt.to_pandas().shape[0]
        print(f"🔍 Verification: {record_count} records in Bronze Delta table")
        
        if record_count != df.height:
            print(f"⚠️  Warning: Row count mismatch - DataFrame had {df.height} rows, table has {record_count}")
        else:
            print(f"✅ Row count verification passed")
            
    except Exception as verify_error:
        print(f"⚠️  Could not verify write (table may still be valid): {verify_error}")

except Exception as write_error:
    print(f"❌ Error writing to Bronze Delta Lake: {write_error}")
    raise

# CELL ********************

# Verify and register table in metastore
print("\n" + "=" * 70)
print("📝 VERIFICATION AND REGISTRATION")
print("=" * 70)

try:
    # For abfss:// paths, add storage_options for Fabric integration
    if bronze_resourcecontainers_path.startswith("abfss://"):
        storage_options = {
            "bearer_token": notebookutils.credentials.getToken("storage"),
            "use_fabric_endpoint": "true"
        }
        delta_table = DeltaTable(bronze_resourcecontainers_path, storage_options=storage_options)
    else:
        delta_table = DeltaTable(bronze_resourcecontainers_path)
    
    print(f"\n✅ Delta table verified:")
    print(f"   Version: {delta_table.version()}")
    print(f"   Files: {len(delta_table.files())}")
    
    # Register table in Fabric metastore for SQL queries
    print("\n📝 Registering table in Fabric metastore...")
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS Bronze_ResourceContainers
        USING DELTA
        LOCATION '{bronze_resourcecontainers_path}'
    """)
    print("✅ Table 'Bronze_ResourceContainers' registered in metastore")
    
    # Verify we can query it
    row_count = spark.sql("SELECT COUNT(*) as count FROM Bronze_ResourceContainers").collect()[0]['count']
    print(f"\n✅ Table is queryable! Row count: {row_count}")
    
    if row_count > 0:
        # Show breakdown by type
        print("\n📊 Container types in Bronze table:")
        spark.sql("""
            SELECT type, COUNT(*) as count
            FROM Bronze_ResourceContainers
            GROUP BY type
            ORDER BY count DESC
        """).show(truncate=False)
        
        # Show subscription coverage
        print("\n📈 Subscription coverage:")
        spark.sql("""
            SELECT 
                COUNT(DISTINCT subscriptionId) as unique_subscriptions,
                COUNT(*) as total_containers
            FROM Bronze_ResourceContainers
            WHERE subscriptionId IS NOT NULL
        """).show(truncate=False)
        
        # Sample data by type
        print("\n📄 Sample containers by type:")
        spark.sql("""
            SELECT type, name, location, subscriptionId
            FROM Bronze_ResourceContainers
            ORDER BY type, name
            LIMIT 10
        """).show(truncate=False)
    
except Exception as e:
    print(f"\n❌ Error during verification: {e}")
    raise

# CELL ********************

print("🎉 Bronze layer ingestion completed successfully!")
print(f"📊 Summary:")
print(f"  - Total containers processed: {len(containers_data)}")
print(f"  - Container types found: {len(type_counts)}")
print(f"  - Subscriptions covered: {len(subscription_ids_found)}")
print(f"  - Bronze table path: {bronze_resourcecontainers_path}")
print(f"  - Table name in metastore: Bronze_ResourceContainers")
print(f"  - Extraction timestamp: {datetime.utcnow().isoformat()}")

if df.height > 0:
    print(f"\n📦 Container type details:")
    for container_type, count in sorted(type_counts.items()):
        print(f"  - {container_type}: {count} containers")
        
    # Check for containers with tags
    tagged_containers = df.filter(pl.col("tags").is_not_null() & (pl.col("tags") != "null") & (pl.col("tags") != "{}")).height
    print(f"\n🏷️  Containers with tags: {tagged_containers} ({tagged_containers/df.height*100:.1f}%)")
else:
    print(f"\n📊 No containers found - this may indicate:")
    print(f"  - Service principal has no access to management hierarchy")
    print(f"  - Authentication or permission issues")
    print(f"  - No subscriptions or resource groups accessible")

print(f"\n{'=' * 70}")
print(f"✅ BRONZE LAYER INGESTION COMPLETE")
print(f"{'=' * 70}")
print(f"\n🔄 Next step: Run ResourceContainers_Silver notebook to split into typed tables")
print(f"   (Management Groups, Subscriptions, Resource Groups)")
print(f"\n📊 This Bronze table provides the foundation for:")
print(f"   - Organizational hierarchy analysis")
print(f"   - Resource group governance reporting")  
print(f"   - Subscription management insights")
print(f"   - Cross-container tagging analysis")