# 🚀 First-Time Setup for Microsoft Fabric CI/CD

This guide walks you through setting up your first Microsoft Fabric CI/CD pipeline from scratch.

## 📋 Prerequisites

Before you begin, ensure you have:

- [ ] **Azure Subscription** with Owner/Contributor access
- [ ] **Azure DevOps Organization** and project
- [ ] **Microsoft Fabric Capacity** provisioned (F64 or higher recommended)
- [ ] **Three Fabric Workspaces** created (Development, Test, Production)
- [ ] **Git Repository** (Azure Repos, GitHub, etc.)
- [ ] **Python 3.9+** installed locally for testing

## 🏗️ Step-by-Step Setup

### Step 1: Create Service Principal

```powershell
# Login to Azure
az login

# Create service principal
az ad sp create-for-rbac --name "fabric-cicd-sp" \
  --role "Contributor" \
  --scopes "/subscriptions/{your-subscription-id}"

# Save the output - you'll need appId, password, and tenant
```

### Step 2: Configure Fabric Permissions

1. **Enable Service Principal Access:**
   - Go to **Fabric Admin Portal** → **Tenant Settings**
   - Enable **"Service principals can use Fabric APIs"**
   - Add your service principal to the **"Specific service principals"** list

2. **Grant Workspace Access:**
   - For each workspace (Dev, Test, Prod):
     - Go to **Workspace Settings** → **Manage Access**
     - Add service principal with **Admin** role

### Step 3: Set Up Azure DevOps

#### 3.1 Create Service Connection

1. In Azure DevOps: **Project Settings** → **Service Connections**
2. Click **"New service connection"** → **"Azure Resource Manager"**
3. Choose **"Service principal (manual)"**
4. Enter details from Step 1:
   - **Subscription ID**: Your Azure subscription
   - **Service Principal ID**: The `appId` from Step 1
   - **Service Principal Key**: The `password` from Step 1
   - **Tenant ID**: The `tenant` from Step 1
5. **Connection name**: `fabric-service-connection`
6. **Grant access permission to all pipelines**: ✅ Check this

#### 3.2 Create Variable Groups

Create these three variable groups with **exactly** these names:

**fabric-dev-variables:**
```
DEV_WORKSPACE_ID = your-dev-workspace-id-guid
DEV_WORKSPACE_NAME = Fabric Development  
DEV_SUBSCRIPTION_ID = your-subscription-id
DEV_STORAGE_ACCOUNT = devstorageaccount001
DEV_CONTAINER_NAME = data
```

**fabric-test-variables:**
```
TEST_WORKSPACE_ID = your-test-workspace-id-guid
TEST_WORKSPACE_NAME = Fabric Test
TEST_SUBSCRIPTION_ID = your-subscription-id
TEST_STORAGE_ACCOUNT = teststorageaccount001
TEST_CONTAINER_NAME = data
```

**fabric-prod-variables:**
```
PROD_WORKSPACE_ID = your-prod-workspace-id-guid
PROD_WORKSPACE_NAME = Fabric Production
PROD_SUBSCRIPTION_ID = your-subscription-id
PROD_STORAGE_ACCOUNT = prodstorageaccount001
PROD_CONTAINER_NAME = data
```

**Important:** Mark sensitive variables (workspace IDs, subscription IDs) as **Secret**.

#### 3.3 Create Environments

Create three environments in **Pipelines** → **Environments**:

1. **fabric-dev** - No approvals required
2. **fabric-test** - Add team lead approvals
3. **fabric-prod** - Add business owner approvals + business hours restrictions

### Step 4: Initialize Your Repository

#### 4.1 Clone the Repository Template

```powershell
# Clone this repository template
git clone https://github.com/your-org/FabricCICD.git
cd FabricCICD

# Create and switch to develop branch
git checkout -b develop
git push origin develop
```

#### 4.2 Create Your First Fabric Items

**Option A: Create items manually in Development workspace, then export to Git**

1. In your **Development** workspace:
   - Create a Lakehouse: "MainLakehouse"
   - Create a Notebook: "DataProcessing"
   
2. Set up **Git Integration** in the workspace:
   - Go to **Workspace Settings** → **Git Integration**
   - Connect to your repository
   - Select the `develop` branch
   - Initialize and commit

**Option B: Create items directly in the repository structure**

Create the folder structure:
```powershell
# Create Fabric item folders
mkdir lakehouses/MainLakehouse.Lakehouse
mkdir notebooks
mkdir datapipelines
mkdir dataflows
mkdir reports
mkdir semanticmodels
mkdir environments
mkdir warehouses
```

#### 4.3 Configure Parameters

Update `parameter.yml` with your actual values:

```yaml
find_replace:
  # Storage accounts for each environment
  - find_value: "PLACEHOLDER_STORAGE_ACCOUNT"
    replace_value:
      DEV: "devstorageaccount001"
      TEST: "teststorageaccount001"
      PROD: "prodstorageaccount001"
      
  # Dynamic workspace ID resolution
  - find_value: "PLACEHOLDER_WORKSPACE_ID"
    replace_value:
      _ALL_: "$workspace.$id"
      
  # Container names
  - find_value: "PLACEHOLDER_CONTAINER_NAME"
    replace_value:
      DEV: "data"
      TEST: "data"  
      PROD: "data"

  # Dynamic lakehouse references
  - find_value: "PLACEHOLDER_LAKEHOUSE_ID"
    replace_value:
      _ALL_: "$items.Lakehouse.MainLakehouse.$id"
```

#### 4.4 Update Fabric Configuration

Edit `fabric-config.yml` to match your workspace setup:

```yaml
core:
  workspace_id:
    DEV: "$ENV:DEV_WORKSPACE_ID"
    TEST: "$ENV:TEST_WORKSPACE_ID"
    PROD: "$ENV:PROD_WORKSPACE_ID"
    
  workspace:
    DEV: "Fabric Development"
    TEST: "Fabric Test"
    PROD: "Fabric Production"
    
  repository_directory: "."
  
  item_types_in_scope:
    - Notebook
    - Lakehouse
    - DataPipeline
    - Dataflow
    - Report
    - SemanticModel
    - Environment
    - Warehouse
    
  parameter: "parameter.yml"

publish:
  exclude_regex: "^(TEMP_|DEBUG_|DRAFT_).*"
  skip:
    DEV: false
    TEST: false
    PROD: false

features:
  - enable_experimental_features
  - enable_config_deploy
  - enable_environment_variable_replacement
```

### Step 5: Create Your First Pipeline

#### 5.1 Set Up Pipeline

1. In Azure DevOps: **Pipelines** → **New Pipeline**
2. Choose **"Azure Repos Git"** (or your Git provider)
3. Select your repository
4. Choose **"Existing Azure Pipelines YAML file"**
5. Select `/azure-pipelines.yml`
6. Click **"Save and run"**

#### 5.2 Grant Pipeline Permissions

The first run will likely fail with permission errors. Grant these permissions:

1. **Service Connection Access:**
   - Go to **Project Settings** → **Service Connections**
   - Select `fabric-service-connection`
   - Go to **Security** → Grant access to your pipeline

2. **Variable Group Access:**
   - Go to **Library** → Select each variable group
   - Go to **Security** → Grant access to your pipeline

3. **Environment Access:**
   - Go to **Environments** → Select each environment
   - Go to **Security** → Grant access to your pipeline

### Step 6: Test Your First Deployment

#### 6.1 Create Test Content

Add a simple notebook to test:

```python
# File: notebooks/TestNotebook.ipynb
{
  "cells": [
    {
      "cell_type": "code",
      "source": [
        "# Test notebook with parameters\n",
        "storage_account = \"PLACEHOLDER_STORAGE_ACCOUNT\"\n",
        "workspace_id = \"PLACEHOLDER_WORKSPACE_ID\"\n",
        "print(f\"Storage Account: {storage_account}\")\n",
        "print(f\"Workspace ID: {workspace_id}\")"
      ]
    }
  ]
}
```

#### 6.2 Commit and Push

```powershell
# Add your changes
git add .
git commit -m "Initial Fabric CI/CD setup with test notebook"
git push origin develop
```

#### 6.3 Monitor Pipeline

1. Go to **Pipelines** in Azure DevOps
2. Watch the pipeline run
3. Check that deployment succeeds in **DEV** environment
4. Verify the test notebook appears in your Development workspace

#### 6.4 Test Full Pipeline

```powershell
# Create PR to main branch to trigger full pipeline
git checkout -b feature/test-deployment
git push origin feature/test-deployment

# Create PR from feature/test-deployment to main
# This will trigger DEV → TEST → PROD deployment
```

## ✅ Validation Checklist

After setup, verify:

- [ ] Service principal has Fabric API access
- [ ] All three workspaces grant Admin access to service principal
- [ ] Azure DevOps variable groups are created with correct values
- [ ] Pipeline runs successfully in DEV environment
- [ ] Test notebook deploys with correct parameter replacements
- [ ] Approvals work for TEST and PROD environments
- [ ] Items appear in target workspaces after deployment

## 🛠️ Troubleshooting Common Issues

### "Service principal cannot access Fabric APIs"
- **Solution**: Enable service principal access in Fabric Admin Portal
- **Check**: Tenant Settings → "Service principals can use Fabric APIs"

### "Workspace not found" 
- **Solution**: Verify workspace IDs in variable groups
- **Check**: Copy workspace ID from workspace URL or settings

### "Authentication failed"
- **Solution**: Verify service connection configuration
- **Check**: Service principal credentials and permissions

### "Pipeline permission denied"
- **Solution**: Grant pipeline access to resources
- **Check**: Service connections, variable groups, and environments security

### "Parameter replacement not working"
- **Solution**: Check parameter.yml syntax and formatting
- **Check**: Ensure proper YAML indentation and structure

## 📚 Next Steps

Once your pipeline is working:

1. **Add More Fabric Items**: Lakehouses, Data Pipelines, Reports
2. **Advanced Parameterization**: Use regex patterns and dynamic references
3. **Security Hardening**: Rotate credentials, audit access
4. **Monitoring**: Set up deployment notifications and health checks
5. **Documentation**: Document your specific business processes

## 🆘 Getting Help

- **Pipeline Issues**: Check Azure DevOps pipeline logs
- **Fabric Issues**: Check Fabric workspace activity logs  
- **Configuration**: Review parameter.yml and fabric-config.yml syntax
- **Permissions**: Verify service principal and workspace access

**Support Resources:**
- [Microsoft Fabric CI/CD Documentation](https://microsoft.github.io/fabric-cicd/latest/)
- [Azure DevOps Documentation](https://docs.microsoft.com/en-us/azure/devops/)
- [Microsoft Fabric Documentation](https://docs.microsoft.com/en-us/fabric/)

---

🎉 **Congratulations!** You now have a fully functional Microsoft Fabric CI/CD pipeline that can deploy any Fabric items across multiple environments with proper validation and approvals.