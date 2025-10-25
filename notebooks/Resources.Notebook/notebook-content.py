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

# Azure Resource Graph Notebook
# Queries Azure Resource Graph for resource inventory across all accessible subscriptions
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
secret_name = VariableLib.secret_name
layer = "bronze"

# Use root path and append specific table name
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
resources_delta_table_path = f"{finopshub_root_path}/{layer}/Resources"

# Get non-sensitive configuration from Variable Library
tenant_id = VariableLib.tenant_id
client_id = VariableLib.client_id

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL: {key_vault_url}")
print(f"  Secret Name: {secret_name}")
print(f"  Delta Table Path: {resources_delta_table_path}")
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

# Query Azure Resource Graph for all resources
print("🔍 Querying Azure Resource Graph for all resources across all accessible subscriptions...")

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
resources_data = []
page_count = 0
subscription_ids_found = set()
resource_types_found = set()

print("📊 Processing results...")

while True:
    page_count += 1
    response = resource_graph_client.resources(request)
    
    # Process results
    if response.data:
        for resource in response.data:
            # Track unique subscriptions and resource types
            subscription_ids_found.add(resource.get('subscriptionId'))
            resource_types_found.add(resource.get('type'))
            
            # Add extraction timestamp
            resource['extracted_at'] = datetime.utcnow().isoformat()
            
            # Convert complex types to JSON strings for proper storage
            if 'tags' in resource and resource['tags']:
                resource['tags'] = json.dumps(resource['tags'])
            if 'properties' in resource and resource['properties']:
                resource['properties'] = json.dumps(resource['properties'])
            
            resources_data.append(resource)
    
    print(f"  📄 Page {page_count}: Retrieved {len(response.data)} resources (Total: {len(resources_data)})")
    
    # Check if there are more results
    if response.skip_token:
        request.options.skip_token = response.skip_token
    else:
        break

print(f"\n✅ Successfully retrieved {len(resources_data)} total resources across {page_count} pages")
print(f"📊 Found resources in {len(subscription_ids_found)} subscriptions")
print(f"🏷️  Discovered {len(resource_types_found)} unique resource types")

# Show top 10 most common resource types
if resources_data:
    type_counts = {}
    for resource in resources_data:
        res_type = resource.get('type', 'Unknown')
        type_counts[res_type] = type_counts.get(res_type, 0) + 1
    
    print(f"\n📈 Top 10 resource types:")
    for res_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  - {res_type}: {count}")

# CELL ********************

# Create Polars DataFrame with proper data cleaning

if not resources_data:
    print("⚠️  No resources found. Creating empty DataFrame with schema...")
    # Create empty DataFrame with expected schema
    df = pl.DataFrame({
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
    print("🧹 Cleaning data before DataFrame creation...")
    # Clean data - convert ALL remaining dict/complex types to strings
    for resource in resources_data:
        for key, value in resource.items():
            # Convert any remaining dicts (including empty {}) to JSON string or None
            if isinstance(value, dict):
                if len(value) > 0:
                    resource[key] = json.dumps(value)
                else:
                    resource[key] = None
            # Convert any lists to JSON strings
            elif isinstance(value, list):
                if len(value) > 0:
                    resource[key] = json.dumps(value)
                else:
                    resource[key] = None

    print("✓ Data cleaned successfully")

    # Create Polars DataFrame - now all values should be simple types
    df = pl.DataFrame(resources_data)

# Cast columns to proper string types to avoid Null type issues
string_columns = [
    "id", "name", "type", "location", "resourceGroup", "subscriptionId",
    "tags", "sku", "kind", "managedBy", "properties", "zones", "identity",
    "createdTime", "changedTime", "extracted_at"
]

for col in string_columns:
    if col in df.columns:
        df = df.with_columns(pl.col(col).cast(pl.Utf8))

print(f"✅ Created DataFrame with {df.height} rows and {df.width} columns")

if df.height > 0:
    print(f"\n📋 Columns: {', '.join(df.columns)}")
    
    print(f"\n📊 Resource type breakdown (top 10):")
    type_breakdown = df.group_by("type").agg(pl.count().alias("count")).sort("count", descending=True).head(10)
    print(type_breakdown)
    
    print(f"\n🌍 Location distribution (top 10):")
    location_breakdown = df.group_by("location").agg(pl.count().alias("count")).sort("count", descending=True).head(10)
    print(location_breakdown)
    
    print(f"\n📁 Subscription distribution:")
    subscription_breakdown = df.group_by("subscriptionId").agg(pl.count().alias("count")).sort("count", descending=True)
    print(subscription_breakdown)
    
    print(f"\n📄 Sample data (first 5 rows):")
    print(df.select(["name", "type", "location", "resourceGroup", "subscriptionId"]).head(5))
else:
    print(f"\n📄 Empty dataset - no resources found")

# CELL ********************

# Write DataFrame to FinOpsHub Delta Lake table

print(f"💾 Writing {df.height} resources to Delta Lake...")
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

print("🎉 Azure Resource Graph inventory extraction completed successfully!")
print(f"📊 Summary:")
print(f"  - Total resources processed: {len(resources_data)}")
print(f"  - Unique subscriptions: {len(subscription_ids_found)}")
print(f"  - Unique resource types: {len(resource_types_found)}")
print(f"  - Delta table path: {resources_delta_table_path}")
print(f"  - Extraction timestamp: {datetime.utcnow().isoformat()}")

if df.height > 0:
    print(f"\n📈 Key statistics:")
    print(f"  - Most common resource type: {df.group_by('type').agg(pl.count().alias('count')).sort('count', descending=True).head(1)}")
    print(f"  - Most used location: {df.group_by('location').agg(pl.count().alias('count')).sort('count', descending=True).head(1)}")
    
    # Check for resources with tags
    tagged_resources = df.filter(pl.col("tags").is_not_null() & (pl.col("tags") != "null")).height
    print(f"  - Resources with tags: {tagged_resources} ({tagged_resources/df.height*100:.1f}%)")
else:
    print(f"\n📊 No resources found - this may indicate:")
    print(f"  - Service principal has no subscriptions access")
    print(f"  - All accessible subscriptions are empty")
    print(f"  - Authentication or permission issues")