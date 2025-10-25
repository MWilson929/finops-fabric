# Fabric Cost Analysis CI/CD Pipeline

A comprehensive Azure DevOps CI/CD pipeline for deploying Microsoft Fabric Cost Analysis (FCA) solutions across multiple environments with automated testing, validation, and deployment.

## 🚀 Quick Start

### Prerequisites
- Azure DevOps organization and project
- Microsoft Fabric capacity and workspaces (Dev, Test, Prod)
- Azure subscription with appropriate permissions
- Cost Management exports configured

### Setup Steps

1. **Clone this repository**
   ```bash
   git clone <repository-url>
   cd FabricCICD
   ```

2. **Configure Azure service principal**
   ```bash
   az ad sp create-for-rbac --name "fabric-cicd-sp" --role contributor --scopes /subscriptions/{subscription-id}
   ```

3. **Set up Azure DevOps**
   - Create service connection with service principal credentials
   - Create variable groups for each environment
   - Set up environments with appropriate approvals

4. **Deploy pipeline**
   - Commit code to trigger first pipeline run
   - Monitor deployment across Dev → Test → Prod

## 📁 Repository Structure

```
FabricCICD/
├── azure-pipelines.yml          # Main CI/CD pipeline
├── config/                      # Configuration files
│   ├── environments.yaml        # Environment-specific settings
│   └── deployment_order.json    # Deployment sequence
├── notebooks/                   # Fabric notebooks
│   ├── 00_Deploy_FCA.ipynb     # Main deployment notebook
│   ├── cost-ingestion.ipynb    # Cost data ingestion
│   └── data-processing.ipynb   # Data transformation
├── scripts/                     # Deployment automation
│   ├── configure_notebooks.py  # Environment configuration
│   ├── deploy_to_fabric.sh     # Fabric deployment
│   ├── validate_deployment.py  # Deployment validation
│   ├── run_integration_tests.py # Integration testing
│   └── production_health_check.py # Production validation
├── docs/                        # Documentation
└── README.md                    # This file
```

## 🔄 Pipeline Workflow

### Stages

1. **Build & Validate** 
   - Validates notebook syntax and structure
   - Validates configuration files
   - Creates deployment artifacts

2. **Deploy to Development**
   - Configures notebooks for dev environment
   - Deploys to dev workspace
   - Runs basic validation tests

3. **Deploy to Test** *(main branch only)*
   - Configures notebooks for test environment  
   - Deploys to test workspace
   - Runs comprehensive integration tests

4. **Deploy to Production** *(requires approval)*
   - Configures notebooks for production environment
   - Deploys to production workspace
   - Runs production health checks

### Trigger Conditions

- **Push to main**: Full Dev → Test → Prod deployment
- **Push to develop**: Dev deployment only  
- **Pull requests**: Validation and build only
- **Path filters**: Only triggers on notebook/config changes

## ⚙️ Configuration

### Environment Variables

Each environment requires these variable groups in Azure DevOps:

#### fabric-dev-variables
```yaml
dev-storage-account: "devstorageaccount001"
dev-workspace-id: "12345678-1234-1234-1234-123456789012"  
dev-workspace-name: "FCA-Development"
dev-container-name: "msexports"
```

#### fabric-test-variables  
```yaml
test-storage-account: "teststorageaccount001"
test-workspace-id: "12345678-1234-1234-1234-123456789013"
test-workspace-name: "FCA-Test"  
test-container-name: "msexports"
```

#### fabric-prod-variables
```yaml
prod-storage-account: "prodstorageaccount001"
prod-workspace-id: "12345678-1234-1234-1234-123456789014"
prod-workspace-name: "FCA-Production"
prod-container-name: "msexports"
```

### Notebook Configuration

Update your notebooks with placeholders that the pipeline will replace:

```python
# Example notebook cell:
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
workspace_id = "PLACEHOLDER_WORKSPACE_ID"  
container_name = "PLACEHOLDER_CONTAINER_NAME"

# Cost export path
read_path = f"abfss://{container_name}@{storage_account}.dfs.core.windows.net/focuscost/"
```

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

#### "fab command not found"
- Ensure ms-fabric-cli is installed in pipeline
- Check PATH configuration in deployment scripts

#### "Workspace not found"  
- Verify workspace IDs in variable groups
- Confirm service principal has workspace access

#### "Authentication failed"
- Check service connection configuration
- Verify Fabric API permissions are enabled

#### Pipeline timeout
- Increase timeout values in azure-pipelines.yml
- Optimize notebook deployment order

### Debug Commands

```bash
# Test Fabric CLI locally
fab --version
fab auth login

# Validate workspace access
fab get /WorkspaceName.Workspace

# Check deployment status
fab api -X get workspaces/{workspace-id}/items
```

## 📈 Advanced Features

### Multi-Region Deployment
- Add region-specific variable groups
- Configure geo-distributed workspaces  
- Implement cross-region replication

### Custom Validation
- Extend validation scripts for business rules
- Add data quality checks
- Implement cost threshold alerts

### Integration Options
- Azure Monitor integration for alerts
- Teams/Slack notifications
- JIRA/ServiceNow integration for approvals

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
- [ ] Automated cost optimization recommendations  
- [ ] Advanced monitoring dashboards
- [ ] Custom approval workflows
- [ ] Performance optimization tools

### v3.0 Features  
- [ ] GitOps integration
- [ ] Infrastructure as Code templates
- [ ] Advanced security scanning
- [ ] Automated rollback mechanisms
- [ ] Cross-cloud deployment support

---

**Made with ❤️ for the Fabric community**