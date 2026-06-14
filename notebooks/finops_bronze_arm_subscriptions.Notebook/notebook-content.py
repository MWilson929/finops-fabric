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

# Azure Subscriptions Notebook
# Retrieves Azure Subscriptions using Azure Management SDK
# Stores results in Delta Lake format in FinOpsHub lakehouse

%pip install polars deltalake azure-identity azure-keyvault-secrets azure-mgmt-subscription azure-mgmt-resource --quiet

# CELL ********************

import polars as pl
from deltalake import write_deltalake, DeltaTable
from azure.identity import ClientSecretCredential
from azure.mgmt.subscription import SubscriptionClient
from datetime import datetime
import json

# CELL ********************

# Get the Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")
key_vault_url = VariableLib.key_vault_url
secret_name = VariableLib.secret_name

# Use root path and append specific table name
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
subscriptions_delta_table_path = f"{finopshub_root_path}/Subscriptions"

# Get non-sensitive configuration from Variable Library
tenant_id = VariableLib.tenant_id
client_id = VariableLib.client_id

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL: {key_vault_url}")
print(f"  Secret Name: {secret_name}")
print(f"  Delta Table Path: {subscriptions_delta_table_path}")
print(f"  Tenant ID: {tenant_id}")
print(f"  Client ID: {client_id}")

# CELL ********************

# Create credential using the service principal

# Validate that we have required configuration
if not all([tenant_id, client_id, key_vault_url, secret_name]):
    raise ValueError("Missing required configuration from Variable Library")

# Create credential - retrieve secret inline without storing in a variable
sp_credential = ClientSecretCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=notebookutils.credentials.getSecret(key_vault_url, secret_name)  
)

# Create subscription client
subscription_client = SubscriptionClient(sp_credential)

# CELL ********************

# Retrieve all subscriptions using Python SDK

subscriptions_data = []

# Get the subscription iterator (handles pagination automatically)
subscription_iterator = subscription_client.subscriptions.list()

print("🔍 Retrieving Azure subscriptions...")

# Iterate through subscriptions
for subscription in subscription_iterator:
    # Extract subscription data using SDK attributes
    sub_dict = {
        # Core subscription info
        "subscription_id": subscription.subscription_id,
        "subscription_name": subscription.display_name,
        "id": subscription.id,  # Full resource ID
        "state": subscription.state,
        "authorization_source": subscription.authorization_source,
        
        # Subscription policies (flattened)
        "policy_location_placement_id": None,
        "policy_quota_id": None,
        "policy_spending_limit": None,
        
        # Additional properties (as JSON string if present)
        "additional_properties": json.dumps(subscription.additional_properties) if subscription.additional_properties else None,
        
        # Metadata
        "extracted_at": datetime.utcnow().isoformat()
    }
    
    # Extract policy information if available
    if subscription.subscription_policies:
        policies = subscription.subscription_policies
        sub_dict["policy_location_placement_id"] = getattr(policies, 'location_placement_id', None)
        sub_dict["policy_quota_id"] = getattr(policies, 'quota_id', None)
        sub_dict["policy_spending_limit"] = getattr(policies, 'spending_limit', None)
    
    subscriptions_data.append(sub_dict)

print(f"✓ Successfully retrieved {len(subscriptions_data)} subscriptions")

# Display subscription names for verification
if subscriptions_data:
    print(f"\n📋 Found subscriptions:")
    for sub in subscriptions_data:
        print(f"  - {sub['subscription_name']} ({sub['subscription_id']})")

# CELL ********************

# Create Polars DataFrame and validate data structure

print("📊 Creating DataFrame...")

df = pl.DataFrame(subscriptions_data)

# Cast columns with proper data types to avoid Null type issues
df = df.with_columns([
    pl.col("policy_location_placement_id").cast(pl.Utf8),
    pl.col("policy_quota_id").cast(pl.Utf8),
    pl.col("policy_spending_limit").cast(pl.Utf8),
    pl.col("additional_properties").cast(pl.Utf8)
])

print(f"✓ DataFrame created with {df.height} rows and {df.width} columns")
print(f"\n📋 Schema:")
print(df.schema)

# Show sample data
print(f"\n📄 Sample data:")
df.head()

# CELL ********************

# Write DataFrame to FinOpsHub Delta Lake table

print(f"💾 Writing data to Delta Lake table: {subscriptions_delta_table_path}")

try:
    df.write_delta(
        subscriptions_delta_table_path,
        mode='overwrite',
        delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
    )
    
    print(f"✅ Successfully wrote {df.height} subscription records to Delta Lake")
    print(f"📍 Table location: {subscriptions_delta_table_path}")
    
    # Verify the write by reading back the count
    try:
        dt = DeltaTable(subscriptions_delta_table_path)
        record_count = dt.to_pandas().shape[0]
        print(f"🔍 Verification: {record_count} records in Delta table")
    except Exception as verify_error:
        print(f"⚠️  Could not verify write (table may still be valid): {verify_error}")

except Exception as write_error:
    print(f"❌ Error writing to Delta Lake: {write_error}")
    raise

# CELL ********************

print("🎉 Azure Subscriptions data extraction completed successfully!")
print(f"📊 Summary:")
print(f"  - Subscriptions processed: {len(subscriptions_data)}")
print(f"  - Delta table path: {subscriptions_delta_table_path}")
print(f"  - Extraction timestamp: {datetime.utcnow().isoformat()}")