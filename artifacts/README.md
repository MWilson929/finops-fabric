# Fabric Item Structure Guide

This directory explains the folder structure for organizing Microsoft Fabric items in your CI/CD repository. Each folder contains specific Fabric item types that will be deployed using the `fabric-cicd` library.

## 📁 Directory Structure

### Core Directories

```
finops-fabric/
├── artifacts/              # General artifacts and shared resources
├── lakehouses/             # Lakehouse definitions and configurations
├── notebooks/              # Jupyter notebooks (.ipynb files and .Notebook folders)
├── datapipelines/          # Data Pipeline definitions (.DataPipeline folders)
├── dataflows/              # Dataflow definitions (.Dataflow folders)
├── reports/                # Power BI Reports (.Report folders)
├── semanticmodels/         # Semantic Models/Datasets (.SemanticModel folders)
├── environments/           # Spark Environment configurations (.Environment folders)
├── warehouses/             # Data Warehouse definitions (.Warehouse folders)
├── eventhouses/            # Event House definitions for real-time analytics
├── sqldatabases/           # SQL Database definitions
├── dataagents/             # AI Data Agents definitions
├── parameter.yml           # Environment-specific parameter replacements
├── fabric-config.yml       # Fabric CI/CD deployment configuration
└── scripts/                # Deployment and utility scripts
```

### Additional Supported Item Types

The `fabric-cicd` library supports these additional item types (create folders as needed):

- `kqldatabases/` - Kusto Query Language databases  
- `kqlquerysets/` - KQL query collections
- `reflex/` - Reflex applications
- `eventstreams/` - Event streaming definitions
- `kqldashboards/` - KQL dashboards
- `graphqlapis/` - GraphQL API definitions
- `apacheairflowjobs/` - Apache Airflow job definitions
- `mounteddatafactories/` - Mounted Data Factory resources
- `orgapps/` - Organizational applications

## 📋 Item Organization Guidelines

### 1. Naming Conventions

**Fabric Items (Folders):**
- Format: `{ItemName}.{ItemType}`
- Examples: 
  - `MainLakehouse.Lakehouse/`
  - `DataProcessing.DataPipeline/`
  - `SalesReport.Report/`

**Regular Files:**
- Notebooks: `{NotebookName}.ipynb`
- Configuration: Use descriptive names with extensions

### 2. Environment Considerations

**Shared Items:**
- Place items that are identical across environments in their respective folders
- Use parameter replacements in `parameter.yml` for environment-specific values

**Environment-Specific Items:**
- Include environment suffix if needed: `MainLakehouse_DEV.Lakehouse/`
- Consider using deployment filters in `fabric-config.yml`

### 3. Dependencies

**Order of Deployment:**
The `fabric-cicd` library handles dependencies automatically, but consider:
1. **Lakehouses** - Deploy first (data foundation)
2. **Environments** - Deploy early (compute resources)
3. **Notebooks** - Deploy after lakehouses and environments
4. **Data Pipelines** - Deploy after data sources are available
5. **Reports** - Deploy last (depend on data models)

## 🔧 Configuration Files

### parameter.yml
Manages environment-specific replacements:

```yaml
find_replace:
  - find_value: "PLACEHOLDER_STORAGE_ACCOUNT"
    replace_value:
      DEV: "devstorageaccount001"
      TEST: "teststorageaccount001"
      PROD: "prodstorageaccount001"
```

### fabric-config.yml
Controls deployment behavior:

```yaml
core:
  workspace_id:
    DEV: "dev-workspace-guid"
    TEST: "test-workspace-guid"  
    PROD: "prod-workspace-guid"
  repository_directory: "."
  item_types_in_scope:
    - Notebook
    - Lakehouse
    - DataPipeline
```

## 📚 Examples by Item Type

### Notebooks
```
notebooks/
├── DataIngestion.ipynb                    # Simple notebook file
├── DataProcessing.Notebook/               # Notebook as folder
│   ├── notebook-content.py
│   └── .platform
└── AnalysisNotebook.ipynb
```

### Lakehouses
```
lakehouses/
├── MainLakehouse.Lakehouse/
│   ├── .platform
│   └── Tables/                            # Optional: predefined tables
└── StagingLakehouse.Lakehouse/
    └── .platform
```

### Data Pipelines
```
datapipelines/
├── DailyETL.DataPipeline/
│   ├── pipeline-content.json
│   ├── .platform
│   └── .schedules                         # Optional: scheduling
└── StreamProcessing.DataPipeline/
    ├── pipeline-content.json
    └── .platform
```

### Reports
```
reports/
├── SalesDashboard.Report/
│   ├── report.json
│   ├── .platform
│   └── definition.pbir                    # Power BI report definition
└── ExecutiveSummary.Report/
    ├── report.json
    └── .platform
```

## 🚀 Usage Examples

### 1. Adding a New Notebook
```bash
# Option 1: Simple .ipynb file
cp MyAnalysis.ipynb notebooks/

# Option 2: Notebook folder (from Fabric Git integration)
cp -r "MyAnalysis.Notebook" notebooks/
```

### 2. Adding a New Lakehouse
```bash
# Create lakehouse folder structure
mkdir lakehouses/AnalyticsLH.Lakehouse
echo '{"$schema": "..."}' > lakehouses/AnalyticsLH.Lakehouse/.platform
```

### 3. Environment-Specific Configuration
In your notebook or pipeline, use placeholders:
```python
# In notebook cell
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
container_name = "PLACEHOLDER_CONTAINER_NAME"
workspace_id = "PLACEHOLDER_WORKSPACE_ID"
```

These will be replaced during deployment based on `parameter.yml`.

### 4. Dynamic Item References
Reference other items using dynamic replacement:
```python
# This will resolve to the actual lakehouse ID in target environment
lakehouse_id = "$items.Lakehouse.MainLakehouse.$id"
```

## ⚠️ Important Notes

### Parameterization
- Always use placeholders for environment-specific values
- Use dynamic replacement (`$items.*.$id`) for item references
- Test parameter replacement with dry-run deployments

### Security
- Never commit actual connection strings or secrets
- Use environment variables for sensitive data
- Mark Azure DevOps variables as secret

### Source Control Integration
- Use Fabric's Git integration to export items to proper folder structure
- Commit both source files and `.platform` metadata files
- Review changes before committing, especially for binary files

### Testing
- Test deployments in dev environment first
- Validate item dependencies before production deployment
- Use configuration overrides for debugging

## 🔄 Migration from Legacy Structure

If migrating from the previous custom structure:

1. **Move existing notebooks** from `notebooks/` (keeping the same structure)
2. **Create new item type folders** as needed
3. **Update parameter.yml** to replace old placeholder system
4. **Test deployment** in dev environment first
5. **Update pipeline** to use new `deploy_fabric_items.py` script

## 📖 Additional Resources

- [Microsoft Fabric CI/CD Documentation](https://microsoft.github.io/fabric-cicd/latest/)
- [Parameterization Guide](https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/)
- [Configuration Deployment](https://microsoft.github.io/fabric-cicd/latest/how_to/config_deployment/)
- [Item Types Documentation](https://microsoft.github.io/fabric-cicd/latest/how_to/item_types/)

---

**Need Help?** Check the official `fabric-cicd` documentation or raise issues in the Microsoft repository.