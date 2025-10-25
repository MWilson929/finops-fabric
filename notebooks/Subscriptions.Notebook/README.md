# Subscriptions Notebook

## Overview
This notebook retrieves Azure subscription information using the Azure Management SDK and stores the data in Delta Lake format within the FinOpsHub lakehouse.

## Purpose
- Extract subscription metadata for FinOps cost analysis
- Provide subscription context for cost allocation and reporting
- Maintain historical subscription information for compliance and auditing

## Data Sources
- **Azure Management API**: Subscription information via Azure SDK
- **Authentication**: Service Principal credentials stored in Azure Key Vault

## Data Output
- **Target**: FinOpsHub lakehouse `/Tables/Subscriptions` Delta table
- **Format**: Delta Lake with schema evolution support
- **Mode**: Overwrite (full refresh of subscription data)

## Schema
The notebook extracts the following subscription information:

| Column | Type | Description |
|--------|------|-------------|
| `subscription_id` | string | Unique subscription identifier |
| `subscription_name` | string | Display name of the subscription |
| `id` | string | Full Azure resource ID |
| `state` | string | Subscription state (Enabled, Disabled, etc.) |
| `authorization_source` | string | Authorization source |
| `policy_location_placement_id` | string | Location placement policy ID |
| `policy_quota_id` | string | Quota policy ID |
| `policy_spending_limit` | string | Spending limit policy |
| `additional_properties` | string | Additional properties as JSON |
| `extracted_at` | string | ISO timestamp of data extraction |

## Dependencies
- **Python Packages**: 
  - `polars` - DataFrame processing
  - `deltalake` - Delta Lake integration
  - `azure-identity` - Azure authentication
  - `azure-keyvault-secrets` - Key Vault access
  - `azure-mgmt-subscription` - Subscription management
  - `azure-mgmt-resource` - Resource management

- **Variable Library**: `VariableLib`
  - `key_vault_url` - Azure Key Vault URL
  - `secret_name` - Service Principal secret name
  - `finopshub_root_path` - FinOpsHub lakehouse root path
  - `tenant_id` - Azure tenant ID
  - `client_id` - Service Principal client ID

## Configuration Requirements
1. **Service Principal**: Must have `Reader` permissions on target subscriptions
2. **Key Vault**: Service Principal secret must be accessible
3. **Lakehouse**: FinOpsHub lakehouse must be attached to workspace
4. **Variable Library**: All required variables must be configured

## Usage
1. Ensure Variable Library (`VariableLib`) is configured with required values
2. Run all cells in sequence
3. Monitor output for successful subscription retrieval and Delta Lake write
4. Verify data in FinOpsHub lakehouse `/Tables/Subscriptions`

## Scheduling
- **Frequency**: Daily or weekly refresh recommended
- **Timing**: Can run anytime (subscription metadata changes infrequently)
- **Duration**: Typically completes in 1-2 minutes for most tenants

## Troubleshooting
- **Authentication Errors**: Verify Service Principal credentials and Key Vault access
- **Permission Errors**: Ensure Service Principal has `Reader` role on subscriptions
- **Delta Write Errors**: Check FinOpsHub lakehouse connectivity and permissions
- **Variable Library Errors**: Verify all required variables are configured in VariableLib

## Integration with FinOps
This notebook provides foundational subscription data used by other FinOps processes:
- Cost allocation and chargeback reporting
- Subscription governance and compliance monitoring  
- Multi-subscription cost analysis and optimization