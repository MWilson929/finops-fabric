# Microsoft Fabric CI/CD Setup Guide

This guide provides step-by-step instructions for setting up a complete Microsoft Fabric CI/CD pipeline for deploying any Fabric items (notebooks, lakehouses, data pipelines, reports, etc.) across multiple environments.

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Azure subscription with Owner or Contributor access
- [ ] Azure DevOps organization and project
- [ ] Microsoft Fabric capacity provisioned
- [ ] Three Fabric workspaces (Dev, Test, Prod)
- [ ] Azure CLI installed locally
- [ ] Git repository access
- [ ] Python 3.9+ for local testing

## Step 1: Azure Service Principal Setup

### 1.1 Create Service Principal

```bash
# Create service principal
az ad sp create-for-rbac --name "fabric-cicd-sp" \
  --role contributor \
  --scopes /subscriptions/{your-subscription-id}
```

**Save the output:** You'll need the `appId`, `password`, and `tenant` values.

### 1.2 Enable Fabric API Access

1. Navigate to **Microsoft Fabric Admin Portal** → **Tenant Settings**
2. Enable **"Service principals can use Fabric APIs"**
3. Add your service principal to the allowed list
4. Enable **"Allow service principals to use read-only admin APIs"**

### 1.3 Grant Workspace Access

For each workspace (Dev, Test, Prod):
1. Go to **Workspace Settings** → **Access**
2. Add service principal with **Admin** permissions
3. Note down the workspace ID (found in workspace URL or settings)

## Step 2: Azure DevOps Configuration

### 2.1 Create Service Connection

1. In Azure DevOps, go to **Project Settings** → **Service Connections**
2. Click **"New service connection"** → **"Azure Resource Manager"**
3. Choose **"Service principal (manual)"**
4. Enter service principal details from Step 1.1
5. Name it: `fabric-service-connection`

### 2.2 Create Variable Groups

Create three variable groups with these exact names:

#### fabric-dev-variables
```yaml
Variables:
  DEV_WORKSPACE_ID: your-dev-workspace-id
  DEV_WORKSPACE_NAME: Fabric Development
  DEV_SUBSCRIPTION_ID: your-dev-subscription-id
  DEV_STORAGE_ACCOUNT: your-dev-storage-account
  DEV_CONTAINER_NAME: data
  DEV_FABRIC_CAPACITY: your-dev-capacity-name
```

#### fabric-test-variables
```yaml
Variables:
  TEST_WORKSPACE_ID: your-test-workspace-id
  TEST_WORKSPACE_NAME: Fabric Test
  TEST_SUBSCRIPTION_ID: your-test-subscription-id
  TEST_STORAGE_ACCOUNT: your-test-storage-account
  TEST_CONTAINER_NAME: data
  TEST_FABRIC_CAPACITY: your-test-capacity-name
```

#### fabric-prod-variables
```yaml
Variables:
  PROD_WORKSPACE_ID: your-prod-workspace-id
  PROD_WORKSPACE_NAME: Fabric Production
  PROD_SUBSCRIPTION_ID: your-prod-subscription-id
  PROD_STORAGE_ACCOUNT: your-prod-storage-account
  PROD_CONTAINER_NAME: data
  PROD_FABRIC_CAPACITY: your-prod-capacity-name
```

**Security Note:** Mark storage account and workspace details as **Secret** if they contain sensitive information.

### 2.3 Create Environments

1. Go to **Pipelines** → **Environments**
2. Create three environments:

#### fabric-dev
- **Name:** `fabric-dev`
- **Approvals:** None required
- **Checks:** None

#### fabric-test  
- **Name:** `fabric-test`
- **Approvals:** Add your team leads
- **Checks:** Optional - add required reviewers

#### fabric-prod
- **Name:** `fabric-prod` 
- **Approvals:** Add business owners and change board
- **Checks:** Add business hours restriction if needed

## Step 3: First-Time Setup Instructions

### 3.1 Create Your Fabric Items

Start by creating your Fabric items in the Development workspace:

1. **Create a Lakehouse** (recommended first item):
   ```
   Name: MainLakehouse
   Purpose: Primary data storage for your solution
   ```

2. **Create Notebooks** for data processing:
   ```
   Name: DataProcessing.ipynb
   Purpose: Main data processing logic
   ```

3. **Create Data Pipelines** (if needed):
   ```
   Name: DataIngestion
   Purpose: Automated data ingestion processes
   ```

### 3.2 Export Items to Git Integration

1. In your Development workspace, go to **Workspace Settings** → **Git Integration**
2. Connect to your repository
3. Initialize Git integration
4. This will create the proper folder structure in your repository

## Step 4: Repository Configuration

### 4.1 Clone and Setup Repository

```bash
# Clone the repository
git clone <your-repository-url>
cd FabricCICD

# Create main and develop branches
git checkout -b develop
git push origin develop
git checkout main
```

### 4.2 Update Parameter Configuration

Edit `parameter.yml` with your environment-specific values:

```yaml
find_replace:
  - find_value: "PLACEHOLDER_STORAGE_ACCOUNT"
    replace_value:
      DEV: "your-dev-storage-account"
      TEST: "your-test-storage-account"
      PROD: "your-prod-storage-account"
      
  - find_value: "PLACEHOLDER_WORKSPACE_ID"
    replace_value:
      _ALL_: "$workspace.$id"  # Dynamic workspace ID resolution
      
  - find_value: "PLACEHOLDER_CONTAINER_NAME"
    replace_value:
      DEV: "data"
      TEST: "data"
      PROD: "data"
```

### 4.3 Update Fabric Item Placeholders

In your Fabric items, use placeholders that will be replaced during deployment:

**In notebooks:**
```python
# Replace hardcoded values with placeholders:
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
workspace_id = "PLACEHOLDER_WORKSPACE_ID"
container_name = "PLACEHOLDER_CONTAINER_NAME"
lakehouse_id = "$items.Lakehouse.MainLakehouse.$id"  # Dynamic reference
```

**In data pipelines:**
```json
{
  "typeProperties": {
    "source": {
      "datasetSettings": {
        "externalReferences": {
          "connection": "PLACEHOLDER_CONNECTION_ID"
        }
      }
    }
  }
}
```

Common placeholders to use:
- `PLACEHOLDER_STORAGE_ACCOUNT`
- `PLACEHOLDER_WORKSPACE_ID`
- `PLACEHOLDER_CONTAINER_NAME`
- `PLACEHOLDER_CONNECTION_ID`
- `$items.{ItemType}.{ItemName}.$id` (dynamic references)

## Step 5: Pipeline Deployment

### 5.1 Create Pipeline

1. In Azure DevOps, go to **Pipelines** → **New Pipeline**
2. Choose **"Azure Repos Git"** (or your source)
3. Select your repository
4. Choose **"Existing Azure Pipelines YAML file"**
5. Select `/azure-pipelines.yml`
6. Click **"Run"**

### 5.2 First Pipeline Run

The first run will likely fail - this is expected. Common first-run issues:

1. **Service connection permissions**: Grant pipeline access to service connection
2. **Variable group access**: Grant pipeline access to all variable groups  
3. **Environment permissions**: Grant pipeline access to environments

## Step 6: Validation and Testing

### 6.1 Test Development Deployment

1. Create a small change in develop branch
2. Push to trigger dev-only pipeline
3. Verify deployment in development workspace
4. Check pipeline logs for any issues

### 6.2 Test Full Pipeline

1. Create PR from develop to main
2. Merge after PR validation passes
3. Monitor full pipeline execution
4. Verify deployment in all environments

### 6.3 Validation Checklist

- [ ] Pipeline triggers correctly on branch pushes
- [ ] Development deployment works
- [ ] Test deployment requires approval
- [ ] Production deployment requires approval  
- [ ] Notebooks are properly configured for each environment
- [ ] Health checks pass in each environment
- [ ] Integration tests pass

## Step 7: Operational Procedures

### 7.1 Daily Operations

**Development Team:**
- Push feature branches to develop
- Create PRs for main branch deployment
- Monitor pipeline execution
- Respond to pipeline failures

**Operations Team:**
- Approve test environment deployments
- Monitor production health checks
- Manage environment access and permissions

### 7.2 Change Management

**Normal Changes:**
1. Develop in feature branches
2. Merge to develop for dev testing
3. Create PR to main for promotion
4. Pipeline handles automated deployment

**Emergency Changes:**
1. Create hotfix branch from main
2. Apply minimal required changes
3. Fast-track through approvals
4. Monitor post-deployment carefully

### 7.3 Troubleshooting

**Pipeline Failures:**
1. Check pipeline logs for specific errors
2. Verify service principal permissions
3. Confirm workspace access
4. Validate configuration files

**Deployment Issues:**
1. Check Fabric workspace for deployment status
2. Verify notebook execution in target environment
3. Review health check results
4. Compare configurations between environments

## Step 8: Security and Compliance

### 8.1 Security Hardening

- [ ] Enable branch protection on main branch
- [ ] Require PR reviews before merging
- [ ] Enable vulnerability scanning on repository
- [ ] Rotate service principal credentials quarterly
- [ ] Audit environment access regularly

### 8.2 Compliance Requirements

- [ ] Document all environment changes
- [ ] Maintain change approval records
- [ ] Implement data governance policies
- [ ] Enable audit logging in Fabric workspaces
- [ ] Regular security assessments

## Support and Maintenance

### Monthly Tasks
- [ ] Review pipeline performance metrics
- [ ] Update service principal credentials if needed
- [ ] Audit environment access permissions
- [ ] Review and update documentation

### Quarterly Tasks  
- [ ] Rotate service principal secrets
- [ ] Review and update security policies
- [ ] Performance optimization review
- [ ] Disaster recovery testing

### Annual Tasks
- [ ] Complete security audit
- [ ] Update compliance documentation
- [ ] Review and update procedures
- [ ] Business continuity plan review

## Getting Help

**Pipeline Issues:**
- Check Azure DevOps pipeline logs
- Review service connection status
- Verify variable group configurations

**Fabric Issues:**
- Check Fabric workspace activity logs
- Verify service principal permissions
- Review notebook execution history

**Configuration Issues:**
- Validate YAML syntax in config files
- Check placeholder replacement in notebooks
- Verify environment-specific settings

**Contact:**
- DevOps Team: [devops-team-email]
- Fabric Admins: [fabric-admin-email]  
- Security Team: [security-team-email]

---

This completes your Fabric CI/CD setup. The pipeline should now automatically handle deployments across your environments with proper validation and approvals.