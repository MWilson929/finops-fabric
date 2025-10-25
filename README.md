# Microsoft Fabric CI/CD Pipeline

A comprehensive Azure DevOps CI/CD pipeline for deploying Microsoft Fabric items (notebooks, lakehouses, data pipelines, reports, etc.) across multiple environments with automated testing, validation, and deployment.

## 🚀 Quick Start

### Prerequisites
- Azure DevOps organization and project
- Microsoft Fabric capacity and workspaces (Dev, Test, Prod)
- Azure subscription with appropriate permissions
- Service principal with Fabric API access

### Setup Steps

🚀 **New to this pipeline?** Follow the **[First-Time Setup Guide](FIRST_TIME_SETUP.md)** for complete step-by-step instructions.

**Quick Setup Summary:**

1. **Create Service Principal & Configure Fabric Access**
   ```bash
   az ad sp create-for-rbac --name "fabric-cicd-sp" --role contributor --scopes /subscriptions/{subscription-id}
   ```

2. **Set up Azure DevOps**
   - Create service connection with service principal credentials
   - Create variable groups for each environment (DEV, TEST, PROD)
   - Set up environments with appropriate approvals

3. **Configure Your Repository**
   - Update `parameter.yml` with environment-specific values
   - Update `fabric-config.yml` with workspace IDs
   - Add your Fabric items to appropriate folders

4. **Deploy Pipeline**
   - Commit Fabric items to trigger first pipeline run
   - Monitor deployment across Dev → Test → Prod

📖 **Detailed Instructions**: See [FIRST_TIME_SETUP.md](FIRST_TIME_SETUP.md) for comprehensive setup guidance.

## 📁 Repository Structure

```
FabricCICD/
├── azure-pipelines.yml          # Main CI/CD pipeline
├── parameter.yml                # Environment-specific parameter replacements
├── fabric-config.yml            # Fabric deployment configuration
├── notebooks/                   # Jupyter notebooks and .Notebook folders
├── lakehouses/                  # Lakehouse definitions (.Lakehouse folders)
├── datapipelines/               # Data Pipeline definitions (.DataPipeline folders)
├── dataflows/                   # Dataflow definitions (.Dataflow folders)
├── reports/                     # Power BI Reports (.Report folders)
├── semanticmodels/              # Semantic Models (.SemanticModel folders)
├── environments/                # Spark Environment configurations (.Environment folders)
├── warehouses/                  # Data Warehouse definitions (.Warehouse folders)
├── scripts/                     # Deployment automation
│   └── deploy_fabric_items.py  # Main deployment script using fabric-cicd library
├── docs/                        # Documentation
├── artifacts/                   # General artifacts and shared resources
└── README.md                   # This file
```

## 🔄 Pipeline Workflow

### Stages

1. **Build & Validate** 
   - Validates Fabric item syntax and structure
   - Validates configuration files (parameter.yml, fabric-config.yml)
   - Creates deployment artifacts

2. **Deploy to Development**
   - Applies environment-specific parameters
   - Deploys all Fabric items to dev workspace
   - Runs basic validation tests

3. **Deploy to Test** *(main branch only)*
   - Applies test environment parameters  
   - Deploys to test workspace
   - Runs comprehensive integration tests

4. **Deploy to Production** *(requires approval)*
   - Applies production environment parameters
   - Deploys to production workspace
   - Runs production health checks

### Trigger Conditions

- **Push to main**: Full Dev → Test → Prod deployment (default)
- **Push to develop**: Dev deployment only  
- **Pull requests**: Validation and build only
- **Path filters**: Only triggers on Fabric item/config changes

## 🎯 Environment Deployment Control

### Method 1: Manual Pipeline Parameters (Recommended)

When running the pipeline manually, you can control which environments to deploy to:

1. **Go to Azure DevOps → Pipelines → [Your Pipeline] → Run Pipeline**
2. **Choose deployment options:**
   - ✅ **Deploy to Development**: Individual environment checkbox
   - ✅ **Deploy to Test**: Individual environment checkbox  
   - ✅ **Deploy to Production**: Individual environment checkbox
   - **Target Environment**: Override dropdown with preset combinations
     - `auto` - Use branch-based rules (default)
     - `dev-only` - Deploy to Development only
     - `test-only` - Deploy to Test only (requires Dev success)
     - `prod-only` - Deploy to Production only (requires Test success)
     - `dev-test` - Deploy to Dev and Test
     - `dev-prod` - Deploy to Dev and Production  
     - `test-prod` - Deploy to Test and Production
     - `all` - Deploy to all environments

**Example Use Cases:**
```yaml
# Hotfix to production only (after manual validation)
Target Environment: "prod-only"

# Feature testing (skip production)  
Target Environment: "dev-test"

# Emergency rollback (specific environment)
Deploy to Development: false
Deploy to Test: false
Deploy to Production: true
```

### Method 2: Branch-Based Automatic Deployment

The pipeline automatically determines deployments based on the source branch:

```yaml
# Deployment Rules:
main branch:     → DEV → TEST → PROD (full pipeline)
develop branch:  → DEV only
feature/* branch: → DEV only  
hotfix/* branch: → DEV → TEST → PROD
```

### Method 3: Configuration-Based Control

Use `fabric-config.yml` to control deployment behavior:

```yaml
publish:
  skip:
    DEV: false    # Always deploy to dev
    TEST: false   # Deploy to test (if stage runs)
    PROD: false   # Deploy to prod (if stage runs)

# Environment-specific exclusions
exclude_regex: "^(TEMP_|DEBUG_|DRAFT_).*"
folder_exclude_regex: "^(temp|debug|drafts)/"
```

### Method 4: Environment Approvals

Configure environment-specific approvals in Azure DevOps:

1. **Go to Environments → [Environment Name] → Approvals and Checks**
2. **Add approval requirements:**
   - **Dev**: No approval (automatic)
   - **Test**: Team lead approval required
   - **Prod**: Business owner + change board approval

### Method 5: Variable Group Overrides

Control deployment by modifying variable groups:

```yaml
# In fabric-dev-variables (example)
DEPLOYMENT_ENABLED: "true"   # Set to "false" to skip deployment
DEPLOYMENT_MODE: "full"      # Options: full, validation-only, rollback
```

## ⚙️ Configuration

### Environment Variables

Each environment requires these variable groups in Azure DevOps:

#### fabric-dev-variables
```yaml
DEV_WORKSPACE_ID: "12345678-1234-1234-1234-123456789012"  
DEV_WORKSPACE_NAME: "Fabric Development"
DEV_SUBSCRIPTION_ID: "12345678-1234-1234-1234-123456789abc"
DEV_STORAGE_ACCOUNT: "devstorageaccount001"
DEV_CONTAINER_NAME: "data"
```

#### fabric-test-variables  
```yaml
TEST_WORKSPACE_ID: "12345678-1234-1234-1234-123456789013"
TEST_WORKSPACE_NAME: "Fabric Test"  
TEST_SUBSCRIPTION_ID: "12345678-1234-1234-1234-123456789def"
TEST_STORAGE_ACCOUNT: "teststorageaccount001"
TEST_CONTAINER_NAME: "data"
```

#### fabric-prod-variables
```yaml
PROD_WORKSPACE_ID: "12345678-1234-1234-1234-123456789014"
PROD_WORKSPACE_NAME: "Fabric Production"
PROD_SUBSCRIPTION_ID: "12345678-1234-1234-1234-123456789ghi"
PROD_STORAGE_ACCOUNT: "prodstorageaccount001"
PROD_CONTAINER_NAME: "data"
```

### Parameter Configuration

Configure your Fabric items with placeholders that the pipeline will replace:

**In notebooks:**
```python
# Example notebook cell:
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
workspace_id = "PLACEHOLDER_WORKSPACE_ID"  
container_name = "PLACEHOLDER_CONTAINER_NAME"
lakehouse_id = "$items.Lakehouse.MainLakehouse.$id"  # Dynamic reference

# Data path example
data_path = f"abfss://{container_name}@{storage_account}.dfs.core.windows.net/data/"
```

**In data pipelines (JSON):**
```json
{
  "properties": {
    "activities": [{
      "typeProperties": {
        "source": {
          "datasetSettings": {
            "externalReferences": {
              "connection": "PLACEHOLDER_CONNECTION_ID"
            }
          }
        }
      }
    }]
  }
}

## 🔒 Security

### Service Principal Permissions
- **Azure**: Contributor role on subscription
- **Fabric**: Service principal enabled for Fabric APIs
- **Workspaces**: Admin access to all target workspaces

### Variable Security
- Mark sensitive variables as **Secret** in Azure DevOps
- Restrict variable group access to specific pipelines
- Use separate service principals per environment if needed

### Environment Protection
- **Dev**: No approvals required
- **Test**: Team lead approval required  
- **Prod**: Business owner + change board approval required

## 📊 Monitoring & Validation

### Automated Testing
- **Syntax validation**: JSON structure and Python syntax
- **Configuration validation**: YAML and environment settings
- **Deployment validation**: Workspace access and item deployment
- **Integration tests**: End-to-end workflow validation
- **Health checks**: Production readiness assessment

### Key Metrics Tracked
- Deployment success/failure rates
- Test coverage and pass rates
- Performance baselines
- Security compliance
- Change frequency and lead time

## 🛠️ Troubleshooting

### Common Issues

#### "fabric-cicd library not found"
- Ensure fabric-cicd is installed in pipeline
- Check pip installation in deployment script

#### "Workspace not found"  
- Verify workspace IDs in variable groups
- Confirm service principal has workspace access

#### "Authentication failed"
- Check service connection configuration
- Verify Fabric API permissions are enabled

#### "Parameter replacement failed"
- Check parameter.yml syntax and formatting
- Verify environment variable mappings

#### Pipeline timeout
- Increase timeout values in azure-pipelines.yml
- Optimize Fabric item deployment order

### Debug Commands

```python
# Test fabric-cicd library locally
pip install fabric-cicd
python -c "import fabric_cicd; print('Library installed successfully')"

# Validate configuration files
python -c "import yaml; yaml.safe_load(open('parameter.yml')); print('Parameter file valid')"
python -c "import yaml; yaml.safe_load(open('fabric-config.yml')); print('Config file valid')"

# Test deployment (dry run)
python scripts/deploy_fabric_items.py --environment dev --dry-run
```

## 📈 Advanced Features

### Multi-Region Deployment
- Add region-specific variable groups
- Configure geo-distributed workspaces  
- Implement cross-region replication

### Custom Validation
- Extend validation scripts for business rules
- Add data quality checks
- Implement deployment health checks

### Integration Options
- Azure Monitor integration for alerts
- Teams/Slack notifications for deployment status
- JIRA/ServiceNow integration for approvals
- Power BI reports for deployment metrics

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Workflow
- Use develop branch for active development
- Create PRs against main branch
- Ensure all tests pass before merging
- Follow semantic versioning for releases

## 📚 Documentation

- **Setup Guide**: Detailed configuration instructions
- **API Reference**: Fabric API usage patterns  
- **Best Practices**: Deployment and security guidelines
- **Troubleshooting**: Common issues and solutions

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- **Issues**: Use GitHub Issues for bug reports
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check the `/docs` folder for detailed guides
- **Contact**: [Your contact information]

## 🎯 Roadmap

### v2.0 Features
- [ ] Multi-tenant deployment support
- [ ] Advanced item dependency management  
- [ ] Deployment rollback mechanisms
- [ ] Custom approval workflows
- [ ] Performance optimization tools

### v3.0 Features  
- [ ] GitOps integration with Fabric Git
- [ ] Infrastructure as Code templates
- [ ] Advanced security scanning
- [ ] Automated testing frameworks
- [ ] Cross-workspace deployment support

---

**🚀 Ready to deploy your Fabric items with confidence!**

- **🆕 First-time setup**: [FIRST_TIME_SETUP.md](FIRST_TIME_SETUP.md)
- ** Official docs**: [Microsoft fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/)
- **🛠️ Fabric documentation**: [Microsoft Fabric](https://docs.microsoft.com/en-us/fabric/)

**Made with ❤️ for the Fabric community**