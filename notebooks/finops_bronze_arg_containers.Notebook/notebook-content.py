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

# Azure Resource Graph Multi-Tenant ResourceContainers Bronze Layer
# Queries Azure Resource Graph for resource containers from two tenants and combines into one table
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

# Bronze layer path - raw data from Azure Resource Graph
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
bronze_resourcecontainers_path = f"{finopshub_root_path}/Bronze/ResourceContainers"

# Get configuration for Tenant a
a_tenant_id = VariableLib.a_tenant_id
a_client_id = VariableLib.a_client_id
a_secret_name = VariableLib.a_secret_name

# Get configuration for Tenant b
b_tenant_id = VariableLib.b_tenant_id
b_client_id = VariableLib.b_client_id
b_secret_name = VariableLib.b_secret_name

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL: {key_vault_url}")
print(f"  Bronze Table Path: {bronze_resourcecontainers_path}")
print(f"\n  Tenant a:")
print(f"    Tenant ID: {a_tenant_id}")
print(f"    Client ID: {a_client_id}")
print(f"    Secret Name: {a_secret_name}")
print(f"\n  Tenant b:")
print(f"    Tenant ID: {b_tenant_id}")
print(f"    Client ID: {b_client_id}")
print(f"    Secret Name: {b_secret_name}")

# CELL ********************

# Create credentials for both tenants

# Validate that we have required configuration for both tenants
if not all([a_tenant_id, a_client_id, a_secret_name, key_vault_url]):
    raise ValueError("Missing required configuration for Tenant a from Variable Library")

if not all([b_tenant_id, b_client_id, b_secret_name, key_vault_url]):
    raise ValueError("Missing required configuration for Tenant b from Variable Library")

# Create credential for Tenant a
sp_credential_a = ClientSecretCredential(
    tenant_id=a_tenant_id,
    client_id=a_client_id,
    client_secret=notebookutils.credentials.getSecret(key_vault_url, a_secret_name)
)

# Create credential for Tenant b
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

# Function to retrieve containers from a tenant using Azure Resource Graph
def get_containers_from_tenant(resource_graph_client, tenant_id, tenant_label):
    """
    Retrieve resource containers from a specific tenant using Azure Resource Graph.
    Uses the same logic as the original ResourceContainers_Bronze notebook.
    """
    print(f"\nQuerying {tenant_label} ({tenant_id}) for all resource containers...")
    print("This includes: Management Groups, Subscriptions, and Resource Groups\n")
    
    # Define the KQL query - NO WHERE clause to get ALL container types (same as original)
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
        managedBy
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

    # Execute query and handle pagination (same logic as original)
    containers_data = []
    page_count = 0
    type_counts = {}

    while True:
        page_count += 1
        response = resource_graph_client.resources(request)
        
        # Process results
        if response.data:
            for container in response.data:
                # Add tenant identifiers for multi-tenant tracking
                container['tenant_id'] = tenant_id
                container['tenant_label'] = tenant_label
                
                # Track type counts
                container_type = container.get('type', 'unknown')
                type_counts[container_type] = type_counts.get(container_type, 0) + 1
                
                # Add extraction timestamp
                container['extracted_at'] = datetime.utcnow().isoformat()
                
                # Convert complex types to JSON strings (Layer 1 cleaning - same as original)
                if 'tags' in container and container['tags']:
                    container['tags'] = json.dumps(container['tags'])
                if 'properties' in container and container['properties']:
                    container['properties'] = json.dumps(container['properties'])
                
                containers_data.append(container)
        
        print(f"  Page {page_count}: Retrieved {len(response.data)} containers (Total: {len(containers_data)})")
        
        # Check if there are more results
        if response.skip_token:
            request.options.skip_token = response.skip_token
        else:
            break

    print(f"\n✓ Successfully retrieved {len(containers_data)} total containers from {tenant_label} across {page_count} pages")
    print(f"\n📊 Container types breakdown for {tenant_label}:")
    for container_type, count in sorted(type_counts.items()):
        print(f"  {container_type}: {count}")
        
    return containers_data

# Retrieve containers from both tenants
print("=" * 70)
print("RETRIEVING RESOURCE CONTAINERS FROM BOTH TENANTS")
print("=" * 70)

tenant_a_containers = get_containers_from_tenant(resource_graph_client_a, a_tenant_id, "Tenant a")
tenant_b_containers = get_containers_from_tenant(resource_graph_client_b, b_tenant_id, "Tenant b")

# Combine containers from both tenants
all_containers = tenant_a_containers + tenant_b_containers

print(f"\n{'=' * 70}")
print(f"SUMMARY")
print(f"{'=' * 70}")
print(f"  Tenant a: {len(tenant_a_containers)} containers")
print(f"  Tenant b: {len(tenant_b_containers)} containers")
print(f"  Total: {len(all_containers)} containers")
print(f"{'=' * 70}")

# CELL ********************

# Clean data - convert ALL remaining dict/complex types to strings (Layer 2 cleaning)
print("\nCleaning data before DataFrame creation...")
for container in all_containers:
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

print("✓ Data cleaned")

# Create Polars DataFrame - now all values should be simple types
df = pl.DataFrame(all_containers)

print(f"\n✓ Created DataFrame with {len(df)} rows and {len(df.columns)} columns")
print(f"\nColumns: {df.columns}")
print(f"\nContainers by tenant:")
print(df.group_by("tenant_label").agg(pl.count().alias("count")).sort("tenant_label"))
print(f"\nContainer types in DataFrame:")
print(df.group_by("type").agg(pl.count().alias("count")).sort("count", descending=True))

df.head()

# CELL ********************

# Write DataFrame to Bronze layer
print(f"\nWriting {len(df)} resource containers to Bronze layer...")

df.write_delta(
    bronze_resourcecontainers_path,
    mode='overwrite',
    delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
)

print("✓ Successfully wrote data to Bronze Delta Lake table")

# CELL ********************

# Verify and register table in metastore
print("\n" + "="*70)
print("VERIFICATION AND REGISTRATION")
print("="*70)

from deltalake import DeltaTable

try:
    # For abfss:// paths, add storage_options
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
        CREATE TABLE IF NOT EXISTS Bronze_ResourceContainers_MultiTenant
        USING DELTA
        LOCATION '{bronze_resourcecontainers_path}'
    """)
    print("✅ Table 'Bronze_ResourceContainers_MultiTenant' registered in metastore")
    
    # Verify we can query it
    row_count = spark.sql("SELECT COUNT(*) as count FROM Bronze_ResourceContainers_MultiTenant").collect()[0]['count']
    print(f"\n✅ Table is queryable! Row count: {row_count}")
    
    # Show breakdown by tenant and type
    print("\n📊 Container breakdown by tenant and type:")
    spark.sql("""
        SELECT tenant_label, type, COUNT(*) as count
        FROM Bronze_ResourceContainers_MultiTenant
        GROUP BY tenant_label, type
        ORDER BY tenant_label, count DESC
    """).show(truncate=False)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    raise

print("\n" + "="*70)
print("✅ MULTI-TENANT RESOURCECONTAINERS BRONZE LAYER INGESTION COMPLETE")
print("="*70)
print("\nNext step: Run ResourceContainers_Silver notebook to split into typed tables")
print("Combined data from both tenants is now available for further processing")
