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

# Azure Resource Graph Multi-Tenant Notebook
# Queries Azure Resource Graph for resource inventory from two tenants and combines into one table
# Stores results in Delta Lake format in FinOpsHub lakehouse

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
layer = "bronze"

# Use root path and append specific table name
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
resources_delta_table_path = f"{finopshub_root_path}/{layer}/Resources_MultiTenant"

# Get configuration for Tenant A
a_tenant_id = VariableLib.a_tenant_id
a_client_id = VariableLib.a_client_id
a_secret_name = VariableLib.a_secret_name

# Get configuration for Tenant B
b_tenant_id = VariableLib.b_tenant_id
b_client_id = VariableLib.b_client_id
b_secret_name = VariableLib.b_secret_name

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL: {key_vault_url}")
print(f"  Delta Table Path: {resources_delta_table_path}")
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

# Create Resource Graph clients for both tenants
resource_graph_client_a = ResourceGraphClient(sp_credential_a)
resource_graph_client_b = ResourceGraphClient(sp_credential_b)

print("✓ Successfully created credentials and Resource Graph clients for both tenants")

# CELL ********************

# Function to retrieve resources from a tenant using Azure Resource Graph
def get_resources_from_tenant(resource_graph_client, tenant_id, tenant_label):
    """
    Retrieve resources from a specific tenant using Azure Resource Graph.
    
    Args:
        resource_graph_client: ResourceGraphClient instance
        tenant_id: Tenant ID string
        tenant_label: Human-readable label for the tenant (e.g., "Tenant A")
    
    Returns:
        List of resource dictionaries
    """
    print(f"\n🔍 Querying {tenant_label} ({tenant_id})...")
    resources_data = []
    
    try:
        # Define the KQL query - comprehensive resource inventory with key metadata
        query = """
        Resources
        | project 
            id,
            name,
            type,
            location,
            resourceGroup,
            subscriptionId,
            tags,
            sku = tostring(sku.name),
            kind,
            managedBy,
            properties,
            zones = tostring(zones),
            identity = tostring(identity.type),
            createdTime,
            changedTime
        | order by subscriptionId, resourceGroup, name asc
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
        page_count = 0
        subscription_ids_found = set()

        print(f"  📊 Processing results...")

        while True:
            page_count += 1
            response = resource_graph_client.resources(request)
            
            # Process results
            if response.data:
                for resource in response.data:
                    # Add tenant identifier
                    resource['tenant_id'] = tenant_id
                    resource['tenant_label'] = tenant_label
                    
                    # Track unique subscriptions
                    subscription_ids_found.add(resource.get('subscriptionId'))
                    
                    # Add extraction timestamp
                    resource['extracted_at'] = datetime.utcnow().isoformat()
                    
                    # Convert complex types to JSON strings IMMEDIATELY
                    # This ensures consistent types before DataFrame creation
                    if 'tags' in resource and resource['tags']:
                        resource['tags'] = json.dumps(resource['tags'])
                    if 'properties' in resource and resource['properties']:
                        resource['properties'] = json.dumps(resource['properties'])
                    
                    resources_data.append(resource)
            
            print(f"    📄 Page {page_count}: Retrieved {len(response.data) if response.data else 0} resources (Total: {len(resources_data)})")
            
            # Check if there are more results
            if response.skip_token:
                request.options.skip_token = response.skip_token
            else:
                break

        print(f"  ✅ Retrieved {len(resources_data)} resources from {tenant_label} across {page_count} pages")
        print(f"  📊 Found resources in {len(subscription_ids_found)} subscriptions")
        
        # Show resource type breakdown for this tenant
        if resources_data:
            type_counts = {}
            for resource in resources_data:
                res_type = resource.get('type', 'Unknown')
                type_counts[res_type] = type_counts.get(res_type, 0) + 1
            
            print(f"  🏷️  Top 5 resource types in {tenant_label}:")
            for res_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"    - {res_type}: {count}")
        
        return resources_data
        
    except Exception as e:
        print(f"  ❌ Error retrieving resources from {tenant_label}: {e}")
        raise

# Retrieve resources from both tenants
print("=" * 70)
print("🚀 RETRIEVING RESOURCES FROM BOTH TENANTS")
print("=" * 70)

tenant_a_resources = get_resources_from_tenant(resource_graph_client_a, a_tenant_id, "Tenant A")
tenant_b_resources = get_resources_from_tenant(resource_graph_client_b, b_tenant_id, "Tenant B")

# Combine resources from both tenants
all_resources = tenant_a_resources + tenant_b_resources

print(f"\n{'=' * 70}")
print(f"📊 EXTRACTION SUMMARY")
print(f"{'=' * 70}")
print(f"  Tenant A: {len(tenant_a_resources)} resources")
print(f"  Tenant B: {len(tenant_b_resources)} resources")
print(f"  📈 Total: {len(all_resources)} resources")
print(f"{'=' * 70}")

# CELL ********************

# Create Polars DataFrame with proper data cleaning

if not all_resources:
    print("⚠️  No resources found across both tenants. Creating empty DataFrame with schema...")
    # Create empty DataFrame with expected schema
    df = pl.DataFrame({
        "tenant_id": [],
        "tenant_label": [],
        "id": [],
        "name": [],
        "type": [],
        "location": [],
        "resourceGroup": [],
        "subscriptionId": [],
        "tags": [],
        "sku": [],
        "kind": [],
        "managedBy": [],
        "properties": [],
        "zones": [],
        "identity": [],
        "createdTime": [],
        "changedTime": [],
        "extracted_at": []
    })
else:
    print(f"📊 Creating DataFrame with {len(all_resources)} resources...")
    # Additional data cleaning for any remaining complex types
    for resource in all_resources:
        for key, value in resource.items():
            # Convert any remaining dicts or lists to JSON strings
            if isinstance(value, (dict, list)):
                if value:  # Non-empty
                    resource[key] = json.dumps(value)
                else:  # Empty
                    resource[key] = None
    
    df = pl.DataFrame(all_resources)

# Cast columns with proper data types to avoid Null type issues
string_columns = [
    "tenant_id", "tenant_label", "id", "name", "type", "location", 
    "resourceGroup", "subscriptionId", "tags", "sku", "kind", 
    "managedBy", "properties", "zones", "identity", "createdTime", 
    "changedTime", "extracted_at"
]

for col in string_columns:
    if col in df.columns:
        df = df.with_columns(pl.col(col).cast(pl.Utf8))

print(f"✅ Created DataFrame with {df.height} rows and {df.width} columns")

if df.height > 0:
    print(f"\n📋 Columns: {', '.join(df.columns)}")
    
    print(f"\n📊 Resources by tenant:")
    tenant_summary = df.group_by("tenant_label").agg(pl.count().alias("count")).sort("tenant_label")
    print(tenant_summary)
    
    print(f"\n🏷️  Resource type breakdown (top 10):")
    type_breakdown = df.group_by("type").agg(pl.count().alias("count")).sort("count", descending=True).head(10)
    print(type_breakdown)
    
    print(f"\n🌍 Location breakdown by tenant:")
    location_breakdown = df.group_by(["tenant_label", "location"]).agg(pl.count().alias("count")).sort(["tenant_label", "count"], descending=[False, True])
    print(location_breakdown.head(15))
    
    print(f"\n📄 Sample data (first 5 rows):")
    print(df.select(["tenant_label", "name", "type", "location", "resourceGroup", "subscriptionId"]).head(5))
else:
    print(f"\n📄 Empty dataset - no resources found across both tenants")

# CELL ********************

# Write DataFrame to FinOpsHub Delta Lake table

print(f"💾 Writing {df.height} multi-tenant resources to Delta Lake...")
print(f"📍 Target path: {resources_delta_table_path}")

try:
    df.write_delta(
        resources_delta_table_path,
        mode='overwrite',
        delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
    )
    
    print(f"✅ Successfully wrote {df.height} resource records to Delta Lake")
    
    # Verify the write by reading back the count
    try:
        dt = DeltaTable(resources_delta_table_path)
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
print("=" * 70)
print("📝 VERIFICATION AND REGISTRATION")
print("=" * 70)

try:
    # For abfss:// paths, add storage_options for Fabric integration
    if resources_delta_table_path.startswith("abfss://"):
        storage_options = {
            "bearer_token": notebookutils.credentials.getToken("storage"),
            "use_fabric_endpoint": "true"
        }
        delta_table = DeltaTable(resources_delta_table_path, storage_options=storage_options)
    else:
        delta_table = DeltaTable(resources_delta_table_path)
    
    print(f"\n✅ Delta table verified:")
    print(f"   Version: {delta_table.version()}")
    print(f"   Files: {len(delta_table.files())}")
    
    # Register table in Fabric metastore for SQL queries
    print("\n📝 Registering table in Fabric metastore...")
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS Resources_MultiTenant
        USING DELTA
        LOCATION '{resources_delta_table_path}'
    """)
    print("✅ Table 'Resources_MultiTenant' registered in metastore")
    
    # Verify we can query it
    row_count = spark.sql("SELECT COUNT(*) as count FROM Resources_MultiTenant").collect()[0]['count']
    print(f"\n✅ Table is queryable! Row count: {row_count}")
    
    if row_count > 0:
        # Show sample query results with tenant breakdown
        print("\n📊 Sample data by tenant and type:")
        spark.sql("""
            SELECT tenant_label, type, location, COUNT(*) as count
            FROM Resources_MultiTenant
            GROUP BY tenant_label, type, location
            ORDER BY tenant_label, count DESC
            LIMIT 15
        """).show(truncate=False)
        
        # Show tenant distribution summary
        print("\n📈 Tenant distribution summary:")
        spark.sql("""
            SELECT 
                tenant_label,
                COUNT(*) as total_resources,
                COUNT(DISTINCT subscriptionId) as subscriptions,
                COUNT(DISTINCT type) as resource_types,
                COUNT(DISTINCT location) as locations
            FROM Resources_MultiTenant
            GROUP BY tenant_label
            ORDER BY tenant_label
        """).show(truncate=False)
    
except Exception as e:
    print(f"\n❌ Error during verification: {e}")
    raise

# CELL ********************

print("🎉 Multi-tenant Azure Resource Graph extraction completed successfully!")
print(f"📊 Summary:")
print(f"  - Total resources processed: {len(all_resources)}")
print(f"  - Tenant A resources: {len(tenant_a_resources)}")
print(f"  - Tenant B resources: {len(tenant_b_resources)}")
print(f"  - Delta table path: {resources_delta_table_path}")
print(f"  - Table name in metastore: Resources_MultiTenant")
print(f"  - Extraction timestamp: {datetime.utcnow().isoformat()}")

if df.height > 0:
    print(f"\n📈 Key statistics:")
    # Get tenant breakdown
    tenant_stats = df.group_by("tenant_label").agg([
        pl.count().alias("resources"),
        pl.col("subscriptionId").n_unique().alias("subscriptions"),
        pl.col("type").n_unique().alias("resource_types"),
        pl.col("location").n_unique().alias("locations")
    ]).sort("tenant_label")
    
    for row in tenant_stats.iter_rows(named=True):
        print(f"  {row['tenant_label']}:")
        print(f"    - Resources: {row['resources']}")
        print(f"    - Subscriptions: {row['subscriptions']}")
        print(f"    - Resource types: {row['resource_types']}")
        print(f"    - Locations: {row['locations']}")
    
    # Check for resources with tags across both tenants
    tagged_resources = df.filter(pl.col("tags").is_not_null() & (pl.col("tags") != "null") & (pl.col("tags") != "{}")).height
    print(f"\n🏷️  Resources with tags: {tagged_resources} ({tagged_resources/df.height*100:.1f}%)")
else:
    print(f"\n📊 No resources found - this may indicate:")
    print(f"  - Service principals have no subscription access")
    print(f"  - All accessible subscriptions are empty")
    print(f"  - Authentication or permission issues")

print(f"\n{'=' * 70}")
print(f"✅ NOTEBOOK COMPLETE")
print(f"{'=' * 70}")