# Parameter Configuration Guide

This document explains how to use the `parameter.yml` file to manage environment-specific configurations for Microsoft Fabric CI/CD deployments.

## Overview

The `parameter.yml` file enables automatic find/replace operations during deployment, allowing you to use different storage accounts, containers, and connection IDs across environments (DEV, TEST, PROD) while maintaining a single set of Fabric item definitions.

## ADLS Gen2 Shortcuts Configuration

### Required Azure DevOps Variables

For each environment, set the following variables in your Azure DevOps Variable Groups:

#### DEV Environment Variables
- `DEV_STORAGE_ACCOUNT_NAME`: Name of your development storage account (e.g., "devstorageaccount001")
- `DEV_CONTAINER_NAME`: Container name for development (e.g., "costexport")
- `DEV_CONNECTION_ID`: Fabric connection ID for DEV ADLS Gen2 connection

#### TEST Environment Variables
- `TEST_STORAGE_ACCOUNT_NAME`: Name of your test storage account (e.g., "teststorageaccount001")
- `TEST_CONTAINER_NAME`: Container name for test (e.g., "costexport")
- `TEST_CONNECTION_ID`: Fabric connection ID for TEST ADLS Gen2 connection

#### PROD Environment Variables
- `PROD_STORAGE_ACCOUNT_NAME`: Name of your production storage account (e.g., "prodstorageaccount001")
- `PROD_CONTAINER_NAME`: Container name for production (e.g., "costexport")
- `PROD_CONNECTION_ID`: Fabric connection ID for PROD ADLS Gen2 connection

### How It Works

1. **Lakehouse Shortcuts**: The `shortcuts.metadata.json` file contains placeholders:
   ```json
   {
     "connectionId": "PLACEHOLDER_CONNECTION_ID",
     "location": "https://PLACEHOLDER_STORAGE_ACCOUNT.dfs.core.windows.net",
     "subpath": "/PLACEHOLDER_CONTAINER_NAME"
   }
   ```

2. **Parameter Replacement**: During deployment, the fabric-cicd library reads `parameter.yml` and replaces:
   - `PLACEHOLDER_STORAGE_ACCOUNT` → Environment-specific storage account name
   - `PLACEHOLDER_CONTAINER_NAME` → Environment-specific container name
   - `PLACEHOLDER_CONNECTION_ID` → Environment-specific connection ID

3. **Environment Selection**: The replacement values are chosen based on the deployment environment:
   - DEV deployment uses `$ENV:DEV_STORAGE_ACCOUNT_NAME`
   - TEST deployment uses `$ENV:TEST_STORAGE_ACCOUNT_NAME`
   - PROD deployment uses `$ENV:PROD_STORAGE_ACCOUNT_NAME`

## Example Configuration

### Example DEV Variables
```
DEV_STORAGE_ACCOUNT_NAME = "2trickcostexportdev"
DEV_CONTAINER_NAME = "costexport"
DEV_CONNECTION_ID = "ac9d047e-1e22-404f-ab2c-3a3a71e90273"
```

### Example TEST Variables
```
TEST_STORAGE_ACCOUNT_NAME = "2trickcostexporttest"
TEST_CONTAINER_NAME = "costexport"
TEST_CONNECTION_ID = "bc9d047e-1e22-404f-ab2c-3a3a71e90274"
```

### Example PROD Variables
```
PROD_STORAGE_ACCOUNT_NAME = "2trickcostexport"
PROD_CONTAINER_NAME = "costexport"
PROD_CONNECTION_ID = "cc9d047e-1e22-404f-ab2c-3a3a71e90275"
```

## Dynamic Replacements

The parameter file also includes dynamic replacements that don't require environment variables:

- `PLACEHOLDER_WORKSPACE_ID` → Automatically replaced with the target workspace ID
- Notebook lakehouse references → Automatically replaced with deployed lakehouse IDs

## Adding New Parameters

To add new environment-specific parameters:

1. **Add placeholder in your Fabric item** (e.g., in JSON files, notebook code, etc.)
2. **Add replacement rule to parameter.yml**:
   ```yaml
   - find_value: "YOUR_PLACEHOLDER"
     replace_value:
       DEV: "$ENV:DEV_YOUR_VALUE"
       TEST: "$ENV:TEST_YOUR_VALUE"
       PROD: "$ENV:PROD_YOUR_VALUE"
   ```
3. **Set environment variables** in Azure DevOps Variable Groups

## Validation

After deployment, verify that placeholders have been replaced:

1. Check deployed lakehouse shortcuts in Fabric workspace
2. Verify storage account names and connection IDs match expected values
3. Test shortcut connectivity to ensure proper configuration

## Troubleshooting

### Common Issues

1. **Placeholders not replaced**: 
   - Verify parameter.yml is in repository root
   - Check environment variable names match exactly
   - Ensure deployment script copies parameter.yml to temporary directory

2. **Connection failures**:
   - Verify connection IDs exist in target workspace
   - Check storage account permissions
   - Validate container names and paths

3. **Variable resolution errors**:
   - Confirm variables are set in correct Variable Group
   - Check variable group is linked to pipeline
   - Verify variable names use correct environment prefix

### Debug Steps

1. Check deployment logs for parameter replacement messages
2. Verify temporary directory contains parameter.yml
3. Validate Azure DevOps variables are accessible
4. Test connection IDs manually in Fabric workspace