# Fabric CI/CD Setup Guide

This guide provides step-by-step instructions for setting up the complete Fabric Cost Analysis CI/CD pipeline.

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Azure subscription with Owner or Contributor access
- [ ] Azure DevOps organization and project
- [ ] Microsoft Fabric capacity provisioned
- [ ] Three Fabric workspaces (Dev, Test, Prod)
- [ ] Azure CLI installed locally
- [ ] Git repository access

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

### 1.3 Grant Workspace Access

For each workspace (Dev, Test, Prod):
1. Go to **Workspace Settings** → **Access**
2. Add service principal with **Admin** permissions

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
  dev-storage-account: your-dev-storage-account
  dev-workspace-id: your-dev-workspace-id
  dev-workspace-name: Finops Dev
  dev-container-name: msexports
  dev-fabric-capacity: your-dev-capacity-name
```

#### fabric-test-variables
```yaml
Variables:
  test-storage-account: your-test-storage-account
  test-workspace-id: your-test-workspace-id
  test-workspace-name: Finops Test
  test-container-name: msexports
  test-fabric-capacity: your-test-capacity-name
```

#### fabric-prod-variables
```yaml
Variables:
  prod-storage-account: your-prod-storage-account
  prod-workspace-id: your-prod-workspace-id
  prod-workspace-name: Finops Prod
  prod-container-name: msexports
  prod-fabric-capacity: your-prod-capacity-name
```

**Security Note:** Mark storage account and workspace details as **Secret** if they contain sensitive information.

### 2.3 Create Environments

1. Go to **Pipelines** → **Environments**
2. Create three environments:

#### Development
- **Name:** `Development`
- **Approvals:** None required
- **Checks:** None

#### Test  
- **Name:** `Test`
- **Approvals:** Add your team leads
- **Checks:** Optional - add required reviewers

#### Production
- **Name:** `Production` 
- **Approvals:** Add business owners and change board
- **Checks:** Add business hours restriction if needed

## Step 3: Cost Management Export Setup

### 3.1 Create Cost Export

1. Navigate to **Azure Portal** → **Cost Management**
2. Go to **Exports** → **Create**
3. Configure export settings:
   - **Export type:** Daily export of month-to-date costs
   - **Format:** FOCUS (FinOps Open Cost and Usage Specification)
   - **Storage account:** Use the accounts from your variable groups
   - **Container:** `msexports`
   - **Path:** `focuscost/`

### 3.2 Verify Export Path Structure

Ensure your exports create this structure:
```
msexports/
└── focuscost/
    ├── 20241201-20241231/
    │   └── focus_2024-12-01_2024-12-31_*.csv
    ├── 20241101-20241130/
    │   └── focus_2024-11-01_2024-11-30_*.csv
    └── 20241001-20241031/
        └── focus_2024-10-01_2024-10-31_*.csv
```

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

### 4.2 Update Configuration Files

Edit `config/environments.yaml` with your specific values:

```yaml
environments:
  dev:
    storage_account: "your-dev-storage-account"
    workspace_id: "your-dev-workspace-id"
    workspace_name: "Finops Dev"
    container_name: "msexports"
    fabric_capacity: "your-dev-capacity"
    
  test:
    storage_account: "your-test-storage-account" 
    workspace_id: "your-test-workspace-id"
    workspace_name: "Finops Test"
    container_name: "msexports"
    fabric_capacity: "your-test-capacity"
    
  prod:
    storage_account: "your-prod-storage-account"
    workspace_id: "your-prod-workspace-id" 
    workspace_name: "Finops Prod"
    container_name: "msexports"
    fabric_capacity: "your-prod-capacity"
```

### 4.3 Update Notebook Placeholders

In your notebooks, replace hardcoded values with placeholders:

```python
# Replace this:
storage_account = "mystorageaccount001"

# With this:
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
```

Common placeholders to use:
- `PLACEHOLDER_STORAGE_ACCOUNT`
- `PLACEHOLDER_WORKSPACE_ID`
- `PLACEHOLDER_WORKSPACE_NAME`
- `PLACEHOLDER_CONTAINER_NAME`
- `PLACEHOLDER_FABRIC_CAPACITY`

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