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

# Azure DevOps Pipeline Work Items Notebook
# Retrieves pipeline runs and their associated work items to enable correlation with Azure resources
# Supports deployment tracking and cost attribution through pipeline-to-work item mappings

%pip install polars deltalake requests azure-identity --quiet

# CELL ********************

import polars as pl
from deltalake import write_deltalake, DeltaTable
import requests
import json
from datetime import datetime, timedelta
from azure.identity import ClientSecretCredential
import notebookutils
from typing import Dict, List, Any
import time

print("✓ Imports successful")

# CELL ********************

# Load Variable Library configuration
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")

# Service Principal configuration (matches other notebooks)
tenant_id = VariableLib.tenant_id
client_id = VariableLib.client_id
secret_name = VariableLib.secret_name
key_vault_url = VariableLib.key_vault_url

# Azure DevOps configuration
ado_organization = VariableLib.ado_organization
ado_project = VariableLib.ado_project

# Storage configuration
finopshub_root_path = VariableLib.finopshub_root_path
layer = "bronze"
pipeline_workitems_delta_path = f"{finopshub_root_path}/{layer}/AzureDevOps_PipelineWorkItems"

# Processing configuration
LOOKBACK_DAYS = 90  # How many days back to look for pipeline runs

print("✓ Configuration loaded successfully")
print(f"  Organization: {ado_organization}")
print(f"  Project: {ado_project}")
print(f"  Lookback: {LOOKBACK_DAYS} days")
print(f"  Delta Path: {pipeline_workitems_delta_path}")

# CELL ********************

# Authenticate with Service Principal for Azure DevOps
print("🔐 Authenticating with Service Principal for Azure DevOps...")

# Get client secret from Key Vault
client_secret = notebookutils.credentials.getSecret(key_vault_url, secret_name)

# Create Service Principal credential
sp_credential = ClientSecretCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=client_secret
)

# Get access token for Azure DevOps
AZURE_DEVOPS_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"
token = sp_credential.get_token(AZURE_DEVOPS_SCOPE)

# Create authentication headers for Azure DevOps
auth_headers = {
    'Authorization': f'Bearer {token.token}',
    'Content-Type': 'application/json'
}

print("✅ Successfully authenticated with Azure AD for Azure DevOps")

# CELL ********************

# List all pipelines in the project
def list_pipelines(organization: str, project: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    """List all pipelines in the project with metadata"""
    pipelines_url = f"https://dev.azure.com/{organization}/{project}/_apis/pipelines?api-version=7.1"
    
    response = requests.get(pipelines_url, headers=headers)
    response.raise_for_status()
    
    result = response.json()
    pipelines = result.get('value', [])
    
    pipeline_list = []
    for pipeline in pipelines:
        pipeline_list.append({
            'pipeline_id': pipeline.get('id'),
            'pipeline_name': pipeline.get('name'),
            'pipeline_folder': pipeline.get('folder', '')
        })
    
    return pipeline_list

print("📋 Listing pipelines in project...")
pipelines = list_pipelines(ado_organization, ado_project, auth_headers)
print(f"✅ Found {len(pipelines)} pipelines")

if pipelines:
    print("\n📊 Sample pipelines:")
    for p in pipelines[:5]:
        folder = f" ({p['pipeline_folder']})" if p['pipeline_folder'] else ""
        print(f"  - {p['pipeline_name']}{folder} (ID: {p['pipeline_id']})")
    if len(pipelines) > 5:
        print(f"  ... and {len(pipelines) - 5} more")

# CELL ********************

# Get pipeline runs for a specific pipeline
def get_pipeline_runs(organization: str, project: str, headers: Dict[str, str],
                     pipeline_id: int, days_back: int = 90) -> List[Dict[str, Any]]:
    """Get recent pipeline runs with metadata and filtering"""
    # Calculate date threshold
    min_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat() + 'Z'
    
    runs_url = f"https://dev.azure.com/{organization}/{project}/_apis/pipelines/{pipeline_id}/runs?api-version=7.1"
    
    try:
        response = requests.get(runs_url, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        all_runs = result.get('value', [])
        
        # Filter by date and collect metadata
        runs = []
        for run in all_runs:
            created_date = run.get('createdDate', '')
            if created_date >= min_date:
                runs.append({
                    'pipeline_id': pipeline_id,
                    'run_id': run.get('id'),
                    'run_name': run.get('name'),
                    'state': run.get('state'),
                    'result': run.get('result'),
                    'created_date': created_date,
                    'finished_date': run.get('finishedDate'),
                    'url': run.get('url')
                })
        
        return runs
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return []  # Pipeline may not exist or no runs
        raise

print(f"\n🔄 Querying pipeline runs from last {LOOKBACK_DAYS} days...")
print("=" * 70)

all_runs = []
processed_count = 0
pipelines_with_runs = 0

for idx, pipeline in enumerate(pipelines, 1):
    pipeline_id = pipeline['pipeline_id']
    pipeline_name = pipeline['pipeline_name']
    
    runs = get_pipeline_runs(ado_organization, ado_project, auth_headers, 
                            pipeline_id, LOOKBACK_DAYS)
    
    if runs:
        pipelines_with_runs += 1
        # Add pipeline metadata to each run
        for run in runs:
            run['pipeline_name'] = pipeline_name
            run['pipeline_folder'] = pipeline['pipeline_folder']
        all_runs.extend(runs)
    
    processed_count += 1
    if processed_count % 25 == 0:
        print(f"  📈 Progress: {processed_count}/{len(pipelines)} pipelines processed")
    
    # Rate limiting to respect Azure DevOps API limits
    if processed_count % 50 == 0:
        time.sleep(1)

print("=" * 70)
print(f"✅ Pipeline run discovery completed:")
print(f"  📊 Total pipeline runs found: {len(all_runs)}")
print(f"  🏗️  Pipelines with runs: {pipelines_with_runs}/{len(pipelines)}")
print(f"  📅 Date range: Last {LOOKBACK_DAYS} days")

# CELL ********************

# Get work items associated with pipeline runs
def get_run_work_items(organization: str, project: str, headers: Dict[str, str],
                      pipeline_id: int, run_id: int) -> List[Dict[str, Any]]:
    """Get work items associated with a pipeline run through commits, PRs, and manual links"""
    # Use Build API (pipelines are builds under the hood)
    workitems_url = f"https://dev.azure.com/{organization}/{project}/_apis/build/builds/{run_id}/workitems?api-version=7.1"
    
    try:
        response = requests.get(workitems_url, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        work_items = result.get('value', [])
        
        work_item_list = []
        for wi in work_items:
            work_item_list.append({
                'work_item_id': int(wi.get('id')),
                'work_item_url': wi.get('url')
            })
        
        return work_item_list
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return []  # No work items associated
        raise

print("\n🔗 Retrieving work item associations for pipeline runs...")
print("=" * 70)

pipeline_workitem_mappings = []
runs_with_workitems = 0
total_associations = 0
processed_runs = 0

for idx, run in enumerate(all_runs, 1):
    pipeline_id = run['pipeline_id']
    run_id = run['run_id']
    
    work_items = get_run_work_items(ado_organization, ado_project, auth_headers,
                                   pipeline_id, run_id)
    
    processed_runs += 1
    
    if work_items:
        runs_with_workitems += 1
        total_associations += len(work_items)
        
        # Create mapping records for each work item association
        for wi in work_items:
            mapping = {
                'pipeline_run_id': str(run_id),  # Key for joining with Azure resource tags
                'pipeline_id': pipeline_id,
                'pipeline_name': run['pipeline_name'],
                'pipeline_folder': run['pipeline_folder'],
                'run_name': run['run_name'],
                'run_state': run['state'],
                'run_result': run['result'],
                'run_created_date': run['created_date'],
                'run_finished_date': run['finished_date'],
                'work_item_id': wi['work_item_id'],
                'work_item_url': wi['work_item_url'],
                'extracted_at': datetime.utcnow().isoformat()
            }
            pipeline_workitem_mappings.append(mapping)
    
    if processed_runs % 100 == 0:
        print(f"  📈 Progress: {processed_runs}/{len(all_runs)} runs processed")
    
    # Rate limiting for API stability
    if processed_runs % 50 == 0:
        time.sleep(1)

print("=" * 70)
print(f"✅ Work item association discovery completed:")
print(f"  🔗 Total work item associations: {total_associations}")
print(f"  ✅ Runs with work items: {runs_with_workitems}/{len(all_runs)}")
print(f"  ❌ Runs without work items: {len(all_runs) - runs_with_workitems}")

# CELL ********************

# Convert to Polars DataFrame and analyze
print("\n📊 Creating pipeline-work item mapping DataFrame...")

if pipeline_workitem_mappings:
    df = pl.DataFrame(pipeline_workitem_mappings)
    
    # Ensure correct data types for joins and analysis
    df = df.with_columns([
        pl.col('pipeline_run_id').cast(pl.Utf8),
        pl.col('pipeline_id').cast(pl.Int64),
        pl.col('work_item_id').cast(pl.Int64)
    ])
    
    print(f"✅ DataFrame created with {len(df)} association records")
    print(f"📋 Columns: {', '.join(df.columns)}")
    
    # Comprehensive statistics
    print(f"\n📈 Pipeline-Work Item Mapping Statistics:")
    print(f"  🔄 Unique pipeline runs: {df['pipeline_run_id'].n_unique()}")
    print(f"  🏗️  Unique pipelines: {df['pipeline_id'].n_unique()}")
    print(f"  📋 Unique work items: {df['work_item_id'].n_unique()}")
    print(f"  🔗 Total associations: {len(df)}")
    
    # Top pipelines by work item associations
    print(f"\n🏆 Top pipelines by work item associations:")
    top_pipelines = (
        df.group_by(['pipeline_name', 'pipeline_folder'])
        .agg([
            pl.count().alias('association_count'),
            pl.col('work_item_id').n_unique().alias('unique_work_items')
        ])
        .sort('association_count', descending=True)
        .head(10)
    )
    print(top_pipelines)
    
    # Success rate analysis
    print(f"\n📊 Pipeline run results:")
    result_summary = (
        df.group_by('run_result')
        .agg([
            pl.count().alias('runs'),
            pl.col('work_item_id').n_unique().alias('unique_work_items')
        ])
        .sort('runs', descending=True)
    )
    print(result_summary)
    
    print(f"\n📋 Sample mappings:")
    sample_cols = ['pipeline_run_id', 'pipeline_name', 'work_item_id', 'run_result', 'run_created_date']
    print(df.select(sample_cols).head(5))
    
else:
    print("⚠️  No work item associations found")
    print("📝 This could indicate:")
    print("   • Pipelines don't reference work items in commits or PRs")
    print("   • No pipelines have run in the last {LOOKBACK_DAYS} days")
    print("   • Work items are not being linked to development work")
    print("   • Different work item linking practices in use")
    
    # Create empty DataFrame with expected schema
    df = pl.DataFrame({
        'pipeline_run_id': [],
        'pipeline_id': [],
        'pipeline_name': [],
        'pipeline_folder': [],
        'run_name': [],
        'run_state': [],
        'run_result': [],
        'run_created_date': [],
        'run_finished_date': [],
        'work_item_id': [],
        'work_item_url': [],
        'extracted_at': []
    })

# CELL ********************

# Write to Delta Lake and register in metastore
print("\n💾 Writing pipeline-work item mappings to Delta Lake...")

try:
    if df.height > 0:
        print(f"📊 Writing {len(df)} association records to Delta Lake...")
        print(f"📍 Target path: {pipeline_workitems_delta_path}")
        
        df.write_delta(
            pipeline_workitems_delta_path,
            mode='overwrite',
            delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
        )
        
        print(f"✅ Successfully wrote {len(df)} records to Delta Lake")
        
        # Verify the write
        try:
            dt = DeltaTable(pipeline_workitems_delta_path)
            record_count = dt.to_pandas().shape[0]
            print(f"🔍 Verification: {record_count} records in Delta table")
        except Exception as verify_error:
            print(f"⚠️  Could not verify write: {verify_error}")
        
    else:
        print("📝 Creating empty Delta table with expected schema...")
        df.write_delta(
            pipeline_workitems_delta_path,
            mode='overwrite',
            delta_write_options={'schema_mode': 'merge', 'engine': 'rust'}
        )
        print("✅ Empty table created successfully")

except Exception as write_error:
    print(f"❌ Error writing to Delta Lake: {write_error}")
    raise

# CELL ********************

# Register table in Fabric metastore for SQL queries
print("\n📝 Registering table in Fabric metastore...")

try:
    # Register table in metastore for SQL access
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS ADO_PipelineWorkItems
        USING DELTA
        LOCATION '{pipeline_workitems_delta_path}'
    """)
    print("✅ Table 'ADO_PipelineWorkItems' registered in metastore")
    
    # Verify table is queryable
    row_count = spark.sql("SELECT COUNT(*) as count FROM ADO_PipelineWorkItems").collect()[0]['count']
    print(f"✅ Table is queryable! Row count: {row_count}")
    
    if row_count > 0:
        print("\n🔗 Sample pipeline-work item correlations:")
        spark.sql("""
            SELECT 
                pipeline_name,
                COUNT(DISTINCT pipeline_run_id) as pipeline_runs,
                COUNT(DISTINCT work_item_id) as unique_work_items,
                COUNT(*) as total_associations
            FROM ADO_PipelineWorkItems
            GROUP BY pipeline_name
            ORDER BY total_associations DESC
            LIMIT 10
        """).show(truncate=False)
        
        print("\n📊 Association patterns by run result:")
        spark.sql("""
            SELECT 
                run_result,
                COUNT(DISTINCT pipeline_run_id) as runs,
                COUNT(DISTINCT work_item_id) as work_items,
                COUNT(*) as associations
            FROM ADO_PipelineWorkItems
            GROUP BY run_result
            ORDER BY associations DESC
        """).show(truncate=False)

except Exception as e:
    print(f"❌ Error during metastore registration: {e}")
    raise

# CELL ********************

print("\n" + "=" * 70)
print("🔗 AZURE DEVOPS PIPELINE-WORK ITEM MAPPING COMPLETE")
print("=" * 70)

print(f"\n📊 Extraction Summary:")
print(f"  📋 Pipelines discovered: {len(pipelines)}")
print(f"  🔄 Pipeline runs analyzed: {len(all_runs)}")
print(f"  🔗 Work item associations found: {len(pipeline_workitem_mappings)}")
print(f"  📅 Date range: Last {LOOKBACK_DAYS} days")
print(f"  📍 Delta table path: {pipeline_workitems_delta_path}")
print(f"  🗂️  Metastore table: ADO_PipelineWorkItems")
print(f"  ⏰ Extraction timestamp: {datetime.utcnow().isoformat()}")

if len(pipeline_workitem_mappings) > 0:
    unique_pipelines = df['pipeline_id'].n_unique()
    unique_runs = df['pipeline_run_id'].n_unique()
    unique_workitems = df['work_item_id'].n_unique()
    
    print(f"\n🎯 Key Metrics:")
    print(f"  🏗️  Unique pipelines with work items: {unique_pipelines}")
    print(f"  🔄 Unique runs with work items: {unique_runs}")
    print(f"  📋 Unique work items referenced: {unique_workitems}")
    print(f"  📈 Average work items per run: {len(pipeline_workitem_mappings) / unique_runs:.2f}")
    
    print(f"\n🔗 Integration Instructions:")
    print(f"  💡 Join with Azure resources using 'pipeline_run_id' tag")
    print(f"  📋 Join with work items using 'work_item_id'")
    print(f"  🎯 Enable resource → pipeline → work item traceability")
    print(f"  💰 Support cost attribution to development work")

else:
    print(f"\n📝 No associations found - consider:")
    print(f"  📋 Ensure commit messages reference work items (#1234)")
    print(f"  🔄 Link pull requests to work items")
    print(f"  🏗️  Verify pipelines are running and deploying resources")
    print(f"  🔗 Check Azure DevOps work item linking practices")

print(f"\n🚀 Next Steps:")
print(f"  1. 🏷️  Tag Azure resources with pipeline run IDs in deployment scripts")
print(f"  2. 📊 Create ADO_WorkItems notebook for work item details")
print(f"  3. 🔄 Schedule daily runs to maintain current mappings")
print(f"  4. 📈 Build dashboards joining resources → pipelines → work items")
print(f"  5. 💰 Enable cost attribution and deployment tracking")

print(f"\n{'=' * 70}")
print(f"✅ PIPELINE-WORK ITEM MAPPING EXTRACTION COMPLETE")
print(f"{'=' * 70}")