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

# Azure Advisor Recommendations Multi-Tenant Notebook
# Retrieves Azure Advisor recommendations from two tenants and combines into one table
# Stores results in Delta Lake format in FinOpsHub lakehouse

%pip install polars deltalake azure-identity azure-keyvault-secrets azure-mgmt-subscription azure-mgmt-advisor --quiet

# CELL ********************

import polars as pl
from deltalake import write_deltalake, DeltaTable
from azure.identity import ClientSecretCredential
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.advisor import AdvisorManagementClient
from datetime import datetime
import json

# CELL ********************

# Get the Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")
key_vault_url = VariableLib.key_vault_url
layer = "bronze"

# Use root path and append specific table name
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
advisor_delta_table_path = f"{finopshub_root_path}/{layer}/AdvisorRecommendations"

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
print(f"  Delta Table Path: {advisor_delta_table_path}")
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

print("🔐 Creating service principal credentials...")

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

# Create subscription clients for both tenants
subscription_client_a = SubscriptionClient(sp_credential_a)
subscription_client_b = SubscriptionClient(sp_credential_b)

print("✓ Successfully created credentials and clients for both tenants")

# CELL ********************

# Function to retrieve advisor recommendations from a tenant
def get_advisor_recommendations_from_tenant(sp_credential, subscription_client, tenant_id, tenant_label):
    """
    Retrieve advisor recommendations from a specific tenant.
    
    Args:
        sp_credential: Service principal credential
        subscription_client: SubscriptionClient instance
        tenant_id: Tenant ID string
        tenant_label: Human-readable label for the tenant (e.g., "Tenant a")
    
    Returns:
        List of recommendation dictionaries
    """
    print(f"\n🔍 Querying {tenant_label} ({tenant_id})...")
    recommendations_data = []
    
    try:
        # Get all subscriptions for this tenant
        subscriptions = list(subscription_client.subscriptions.list())
        print(f"  📋 Processing {len(subscriptions)} subscriptions for Advisor recommendations...")

        # Iterate through each subscription
        for subscription in subscriptions:
            try:
                # Create Advisor client for this subscription
                advisor_client = AdvisorManagementClient(
                    credential=sp_credential,
                    subscription_id=subscription.subscription_id
                )
                
                print(f"    Checking subscription: {subscription.display_name}")
                
                # Get recommendations for this subscription
                recommendations = advisor_client.recommendations.list()
                subscription_rec_count = 0
                
                # Process each recommendation
                for rec in recommendations:
                    rec_dict = {
                        # Add tenant identifier
                        "tenant_id": tenant_id,
                        "tenant_label": tenant_label,
                        
                        # Subscription info
                        "subscription_id": subscription.subscription_id,
                        "subscription_name": subscription.display_name,
                        
                        # Recommendation core info
                        "recommendation_id": rec.id,
                        "recommendation_name": rec.name,
                        "category": rec.category,
                        "impact": rec.impact,
                        
                        # Description fields
                        "problem": rec.short_description.problem if rec.short_description else None,
                        "solution": rec.short_description.solution if rec.short_description else None,
                        
                        # Affected resource
                        "impacted_field": rec.impacted_field,
                        "impacted_value": rec.impacted_value,
                        
                        # Resource details
                        "resource_type": rec.type,
                        "resource_group": rec.resource_metadata.resource_id.split('/')[4] if rec.resource_metadata and rec.resource_metadata.resource_id and len(rec.resource_metadata.resource_id.split('/')) > 4 else None,
                        "resource_id": rec.resource_metadata.resource_id if rec.resource_metadata else None,
                        
                        # Additional metadata
                        "risk": rec.risk if hasattr(rec, 'risk') else None,
                        "last_updated": rec.last_updated.isoformat() if rec.last_updated else None,
                        "suppression_ids": json.dumps(rec.suppression_ids) if rec.suppression_ids else None,
                        
                        # Extended properties (as JSON string)
                        "extended_properties": json.dumps(rec.extended_properties) if rec.extended_properties else None,
                        
                        # Extraction metadata
                        "extracted_at": datetime.utcnow().isoformat()
                    }
                    
                    recommendations_data.append(rec_dict)
                    subscription_rec_count += 1
                
                if subscription_rec_count > 0:
                    print(f"      ✓ Found {subscription_rec_count} recommendations")
                else:
                    print(f"      • No recommendations found")
            
            except Exception as e:
                print(f"      ⚠️  Could not retrieve recommendations for {subscription.display_name}: {str(e)}")
                continue
        
        print(f"  ✅ Retrieved {len(recommendations_data)} total recommendations from {tenant_label}")
        return recommendations_data
        
    except Exception as e:
        print(f"  ❌ Error retrieving recommendations from {tenant_label}: {e}")
        raise

# Retrieve advisor recommendations from both tenants
print("=" * 70)
print("🎯 RETRIEVING ADVISOR RECOMMENDATIONS FROM BOTH TENANTS")
print("=" * 70)

tenant_a_recommendations = get_advisor_recommendations_from_tenant(sp_credential_a, subscription_client_a, a_tenant_id, "Tenant a")
tenant_b_recommendations = get_advisor_recommendations_from_tenant(sp_credential_b, subscription_client_b, b_tenant_id, "Tenant b")

# Combine recommendations from both tenants
all_recommendations = tenant_a_recommendations + tenant_b_recommendations

print(f"\n{'=' * 70}")
print(f"📊 EXTRACTION SUMMARY")
print(f"{'=' * 70}")
print(f"  Tenant a: {len(tenant_a_recommendations)} recommendations")
print(f"  Tenant b: {len(tenant_b_recommendations)} recommendations") 
print(f"  📈 Total: {len(all_recommendations)} recommendations")
print(f"{'=' * 70}")

# CELL ********************

# Create Polars DataFrame and validate data structure

if not all_recommendations:
    print("⚠️  No recommendations found across both tenants. Creating empty DataFrame...")
    # Create empty DataFrame with expected schema
    df = pl.DataFrame({
        "tenant_id": [],
        "tenant_label": [],
        "subscription_id": [],
        "subscription_name": [],
        "recommendation_id": [],
        "recommendation_name": [],
        "category": [],
        "impact": [],
        "problem": [],
        "solution": [],
        "impacted_field": [],
        "impacted_value": [],
        "resource_type": [],
        "resource_group": [],
        "resource_id": [],
        "risk": [],
        "last_updated": [],
        "suppression_ids": [],
        "extended_properties": [],
        "extracted_at": []
    })
else:
    print(f"📊 Creating DataFrame with {len(all_recommendations)} recommendations...")
    df = pl.DataFrame(all_recommendations)

# Cast columns with proper data types to avoid Null type issues
df = df.with_columns([
    pl.col("tenant_id").cast(pl.Utf8),
    pl.col("tenant_label").cast(pl.Utf8),
    pl.col("subscription_id").cast(pl.Utf8),
    pl.col("subscription_name").cast(pl.Utf8),
    pl.col("recommendation_id").cast(pl.Utf8),
    pl.col("recommendation_name").cast(pl.Utf8),
    pl.col("category").cast(pl.Utf8),
    pl.col("impact").cast(pl.Utf8),
    pl.col("problem").cast(pl.Utf8),
    pl.col("solution").cast(pl.Utf8),
    pl.col("impacted_field").cast(pl.Utf8),
    pl.col("impacted_value").cast(pl.Utf8),
    pl.col("resource_type").cast(pl.Utf8),
    pl.col("resource_group").cast(pl.Utf8),
    pl.col("resource_id").cast(pl.Utf8),
    pl.col("risk").cast(pl.Utf8),
    pl.col("last_updated").cast(pl.Utf8),
    pl.col("suppression_ids").cast(pl.Utf8),
    pl.col("extended_properties").cast(pl.Utf8),
    pl.col("extracted_at").cast(pl.Utf8)
])

print(f"✅ DataFrame created with {df.height} rows and {df.width} columns")

if df.height > 0:
    print(f"\n📋 Schema:")
    for col_name, dtype in zip(df.columns, df.dtypes):
        print(f"  {col_name}: {dtype}")
    
    print(f"\n📈 Recommendations by tenant:")
    tenant_summary = df.group_by("tenant_label").agg(pl.count().alias("count")).sort("tenant_label")
    print(tenant_summary)
    
    print(f"\n📊 Recommendations by category:")
    if "category" in df.columns:
        category_summary = df.group_by("category").agg(pl.count().alias("count")).sort("count", descending=True)
        print(category_summary)
    
    print(f"\n📄 Sample data (first 5 rows):")
    df.head(5)
else:
    print(f"\n📄 Empty dataset - no recommendations to display")

# CELL ********************

# Write DataFrame to FinOpsHub Delta Lake table

print(f"💾 Writing data to Delta Lake table: {advisor_delta_table_path}")

try:
    df.write_delta(
        advisor_delta_table_path,
        mode='overwrite',
        delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
    )
    
    print(f"✅ Successfully wrote {df.height} advisor recommendation records to Delta Lake")
    print(f"📍 Table location: {advisor_delta_table_path}")
    
    # Verify the write by reading back the count
    try:
        dt = DeltaTable(advisor_delta_table_path)
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

print("🎉 Azure Advisor Recommendations data extraction completed successfully!")
print(f"📊 Summary:")
print(f"  - Total recommendations processed: {len(all_recommendations)}")
print(f"  - Tenant a recommendations: {len(tenant_a_recommendations)}")  
print(f"  - Tenant b recommendations: {len(tenant_b_recommendations)}")
print(f"  - Delta table path: {advisor_delta_table_path}")
print(f"  - Extraction timestamp: {datetime.utcnow().isoformat()}")

if df.height > 0:
    print(f"\n📈 Recommendation categories found:")
    if "category" in df.columns:
        categories = df.select("category").unique().sort("category").to_pandas()["category"].tolist()
        for category in categories:
            count = df.filter(pl.col("category") == category).height
            print(f"  - {category}: {count} recommendations")
else:
    print(f"\n📊 No recommendations found - this may indicate:")
    print(f"  - All resources are optimally configured")
    print(f"  - Service principals need additional permissions")
    print(f"  - No subscriptions accessible in the configured tenants")