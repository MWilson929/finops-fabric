# Fabric Testing Suite - Consolidated Scripts

This directory contains the consolidated testing scripts for Microsoft Fabric CI/CD deployments.

## Scripts Overview

### 🛠️ fabric_debug_tool.py
**Quick diagnostic tool for troubleshooting Fabric workspace deployments.**

```bash
# Debug configuration files and environment variables only
python scripts/fabric_debug_tool.py --config-only

# Debug workspace contents for specific environment
python scripts/fabric_debug_tool.py --environment dev

# Install dependencies and debug
python scripts/fabric_debug_tool.py --environment dev --install-deps
```

**Use Cases:**
- 🐛 Quick debugging during development
- 🔍 "What's in my workspace?" checks
- 📋 Comparing repo contents vs. deployed items
- 🚀 Initial deployment troubleshooting
- 🔧 Configuration file validation

### 🧪 fabric_testing_suite.py
**Comprehensive testing framework with multiple modes.**

```bash
# Deployment validation (validates successful deployment)
python scripts/fabric_testing_suite.py --mode validation --environment dev

# Integration tests (lightweight, suitable for CI/CD)
python scripts/fabric_testing_suite.py --mode integration --environment dev --quick

# Comprehensive integration tests
python scripts/fabric_testing_suite.py --mode integration --environment test

# Health monitoring (comprehensive health checks)
python scripts/fabric_testing_suite.py --mode health --environment prod
```

## Testing Modes

### 🔍 **Validation Mode**
- **Purpose**: Validate successful deployment of Fabric items
- **Tests**: Workspace access, item deployment, item health, API performance, smoke test
- **Use in**: Post-deployment validation in CI/CD pipelines
- **Threshold**: 80% success rate required

### 🧪 **Integration Mode**
- **Purpose**: Integration testing after deployment
- **Quick Mode**: 3 essential tests (100% required to pass)
- **Comprehensive Mode**: 5 tests including accessibility and performance (80% threshold)
- **Use in**: CI/CD pipeline integration testing

### 🏥 **Health Mode**
- **Purpose**: Comprehensive operational health monitoring  
- **Tests**: 7 comprehensive health checks including security patterns and consistency
- **Use in**: Production monitoring, operational health assessment
- **Threshold**: 85% success rate required

## Pipeline Integration

The Azure DevOps pipeline (`azure-pipelines.yml`) has been updated to use these consolidated scripts:

```yaml
# DEV: Quick validation + integration
- fabric_testing_suite.py --mode validation --environment dev
- fabric_testing_suite.py --mode integration --environment dev --quick

# TEST: Full validation + integration  
- fabric_testing_suite.py --mode validation --environment test
- fabric_testing_suite.py --mode integration --environment test

# PROD: Full validation + integration + health monitoring
- fabric_testing_suite.py --mode validation --environment prod
- fabric_testing_suite.py --mode integration --environment prod
- fabric_testing_suite.py --mode health --environment prod
```

## Migration from Old Scripts

| Old Script | New Equivalent | Notes |
|------------|----------------|-------|
| `debug_workspace.py` | `fabric_debug_tool.py` | Enhanced with config-only mode |
| `fabric_deployment_validator.py` | `fabric_testing_suite.py --mode validation` | Same functionality |
| `fabric_integration_tests.py` | `fabric_testing_suite.py --mode integration` | Added quick mode |
| `fabric_health_monitor.py` | `fabric_testing_suite.py --mode health` | Same functionality |

## Benefits of Consolidation

- ✅ **Eliminated 90% code overlap** between similar testing scripts
- ✅ **Unified testing framework** with clear mode separation
- ✅ **Consistent CLI interface** across all testing functions
- ✅ **Easier maintenance** with shared utility functions
- ✅ **Better organization** - debug vs. testing clearly separated
- ✅ **Pipeline simplification** with single testing suite script

## Dependencies

Both scripts require:
- `fabric-cicd` library
- `azure-identity` 
- `pyyaml`
- `requests`

Install with: `pip install fabric-cicd azure-identity pyyaml requests`

Or use the `--install-deps` flag on the debug tool for automatic installation.