# Migration Guide: From Custom Fabric CI/CD to Microsoft fabric-cicd Library

This guide explains how to migrate your existing Fabric Cost Analysis CI/CD pipeline to use the official Microsoft `fabric-cicd` library for general-purpose Fabric deployments.

## 🎯 Migration Overview

### What's Changed

| **Before (Custom Implementation)** | **After (Microsoft fabric-cicd)** |
|---|---|
| Custom Fabric CLI scripts | Official `fabric-cicd` Python library |
| Manual placeholder replacement | Built-in parameterization system |
| Bash deployment scripts | Python-based deployment with config files |
| Cost Analysis specific | General-purpose for all Fabric items |
| Limited item type support | 20+ supported Fabric item types |

### Key Benefits

✅ **Robust Parameterization**: Advanced find/replace with regex, dynamic values, and environment variables  
✅ **Comprehensive Item Support**: Notebooks, Lakehouses, Pipelines, Reports, Semantic Models, and more  
✅ **Dependency Management**: Automatic handling of item dependencies  
✅ **Official Support**: Maintained by Microsoft with regular updates  
✅ **Advanced Features**: Configuration-based deployment, validation, and rollback capabilities  

## 🚀 Step-by-Step Migration

### Step 1: Install New Dependencies

Update your pipeline to use the new library:

```yaml
- script: |
    python -m pip install --upgrade pip
    pip install fabric-cicd
    pip install azure-identity
    pip install pyyaml
  displayName: 'Install Fabric CI/CD Dependencies'
```

### Step 2: Create Parameter Configuration

**Replace:** `scripts/configure_notebooks.py`  
**With:** `parameter.yml`

```yaml
find_replace:
  - find_value: "PLACEHOLDER_STORAGE_ACCOUNT"
    replace_value:
      DEV: "devstorageaccount001"
      TEST: "teststorageaccount001"
      PROD: "prodstorageaccount001"
      
  - find_value: "PLACEHOLDER_WORKSPACE_ID"
    replace_value:
      _ALL_: "$workspace.$id"  # Dynamic replacement
```

### Step 3: Create Deployment Configuration

**Create:** `fabric-config.yml`

```yaml
core:
  workspace_id:
    DEV: "$ENV:DEV_WORKSPACE_ID"
    TEST: "$ENV:TEST_WORKSPACE_ID"  
    PROD: "$ENV:PROD_WORKSPACE_ID"
    
  repository_directory: "."
  
  item_types_in_scope:
    - Notebook
    - Lakehouse
    - DataPipeline
    - Dataflow
    - Report
    - SemanticModel
    
  parameter: "parameter.yml"

publish:
  exclude_regex: "^(TEMP_|DEBUG_|DRAFT_).*"
  skip:
    DEV: false
    TEST: false 
    PROD: false
```

### Step 4: Replace Deployment Script

**Replace:** `scripts/deploy_to_fabric.sh`  
**With:** `scripts/deploy_fabric_items.py`

```python
from fabric_cicd import deploy_with_config
from azure.identity import DefaultAzureCredential

def deploy_fabric_items(environment, config_file_path):
    credential = DefaultAzureCredential()
    
    deploy_with_config(
        config_file_path=config_file_path,
        environment=environment.upper(),
        token_credential=credential
    )
```

### Step 5: Update Pipeline Tasks

**Before:**
```yaml
- task: AzureCLI@2
  displayName: 'Deploy to Fabric Dev Workspace'
  inputs:
    azureSubscription: '$(azureServiceConnection)'
    scriptType: 'bash'
    scriptPath: '$(Pipeline.Workspace)/scripts/deploy_to_fabric.sh'
```

**After:**
```yaml
- task: PythonScript@0
  displayName: 'Deploy Fabric Items to Dev Environment'
  inputs:
    scriptSource: 'filePath'
    scriptPath: '$(Pipeline.Workspace)/scripts/deploy_fabric_items.py'
    arguments: '--environment dev --config-file fabric-config.yml'
```

### Step 6: Organize Item Structure

Create folders for different Fabric item types:

```
FabricCICD/
├── notebooks/           # Existing notebooks (keep structure)
├── lakehouses/          # New: Lakehouse definitions
├── datapipelines/       # New: Data Pipeline definitions  
├── dataflows/           # New: Dataflow definitions
├── reports/             # New: Power BI Reports
├── semanticmodels/      # New: Semantic Models
├── environments/        # New: Spark Environments
├── warehouses/          # New: Data Warehouses
├── parameter.yml        # New: Parameter configuration
├── fabric-config.yml    # New: Deployment configuration
└── scripts/
    └── deploy_fabric_items.py  # New: Python deployment script
```

### Step 7: Update Parameterization

**Before (in notebooks):**
```python
# Old placeholder system
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
workspace_id = "PLACEHOLDER_WORKSPACE_ID"
```

**After (enhanced parameterization):**
```python
# Same placeholders, but more powerful replacement
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
workspace_id = "PLACEHOLDER_WORKSPACE_ID"  # Can use $workspace.$id for dynamic
lakehouse_id = "$items.Lakehouse.MainLakehouse.$id"  # Dynamic item reference
```

### Step 8: Update Environment Variables

Ensure your Azure DevOps variable groups include:

```yaml
# fabric-dev-variables
DEV_WORKSPACE_ID: "your-dev-workspace-id"
DEV_SUBSCRIPTION_ID: "your-dev-subscription-id"
DEV_STORAGE_ACCOUNT: "devstorageaccount001"

# fabric-test-variables  
TEST_WORKSPACE_ID: "your-test-workspace-id"
TEST_SUBSCRIPTION_ID: "your-test-subscription-id"
TEST_STORAGE_ACCOUNT: "teststorageaccount001"

# fabric-prod-variables
PROD_WORKSPACE_ID: "your-prod-workspace-id" 
PROD_SUBSCRIPTION_ID: "your-prod-subscription-id"
PROD_STORAGE_ACCOUNT: "prodstorageaccount001"
```

## ✅ Validation Checklist

### Pre-Migration
- [ ] Backup existing pipeline configuration
- [ ] Document current parameter mappings
- [ ] Test fabric-cicd library installation locally
- [ ] Review all notebook placeholders

### During Migration  
- [ ] Create `parameter.yml` with all current placeholders
- [ ] Create `fabric-config.yml` with workspace mappings
- [ ] Update pipeline to use new Python script
- [ ] Test deployment in DEV environment first

### Post-Migration
- [ ] Validate all notebooks deploy correctly
- [ ] Confirm parameter replacement works
- [ ] Test full DEV → TEST → PROD pipeline
- [ ] Document new deployment process
- [ ] Train team on new approach

## 🔧 Troubleshooting

### Common Migration Issues

**Issue**: "fabric-cicd module not found"
```bash
# Solution: Install in pipeline
pip install fabric-cicd
```

**Issue**: "Invalid parameter.yml format" 
```yaml
# Solution: Check YAML syntax and indentation
find_replace:
  - find_value: "old_value"  # Note the dash and proper indentation
    replace_value:
      DEV: "new_value"
```

**Issue**: "Workspace not found"
```yaml
# Solution: Verify workspace IDs in variable groups
DEV_WORKSPACE_ID: "correct-workspace-guid"
```

**Issue**: "Authentication failed"
```python
# Solution: Ensure proper service principal configuration
credential = DefaultAzureCredential()
```

### Advanced Features

**Dynamic Item References:**
```yaml
find_replace:
  - find_value: "hardcoded-lakehouse-id"
    replace_value:
      _ALL_: "$items.Lakehouse.MainLakehouse.$id"
```

**Regex Pattern Matching:**
```yaml
find_replace:
  - find_value: \#\s*META\s+"default_lakehouse":\s*"([0-9a-fA-F-]+)"
    replace_value:
      _ALL_: "$items.Lakehouse.MainLakehouse.$id"
    is_regex: "true"
```

**Environment Variable Integration:**
```yaml
find_replace:
  - find_value: "PLACEHOLDER_CONNECTION_STRING"
    replace_value:
      DEV: "$ENV:DEV_CONNECTION_STRING"
      PROD: "$ENV:PROD_CONNECTION_STRING"
```

## 📚 Resources

- **Microsoft fabric-cicd Documentation**: https://microsoft.github.io/fabric-cicd/latest/
- **Parameterization Guide**: https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/
- **Configuration Deployment**: https://microsoft.github.io/fabric-cicd/latest/how_to/config_deployment/
- **GitHub Repository**: https://github.com/microsoft/fabric-cicd

## 🎉 Next Steps

After migration, consider these enhancements:

1. **Expand Item Types**: Add Dataflows, Reports, Semantic Models
2. **Advanced Parameterization**: Use regex patterns and dynamic references  
3. **Environment-Specific Configurations**: Different item sets per environment
4. **Automated Testing**: Add validation and testing steps
5. **Monitoring**: Implement deployment success tracking

---

**Need Help?** Check the official documentation or reach out to the team for assistance with the migration process.