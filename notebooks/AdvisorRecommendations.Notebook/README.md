# Azure Advisor Recommendations Notebook

## Overview

This Microsoft Fabric notebook extracts Azure Advisor recommendations from multiple Azure tenants and stores the combined data in a Delta Lake table for centralized FinOps analysis.

## Features

- **Multi-Tenant Support**: Connects to two separate Azure tenants using service principal authentication
- **Comprehensive Data Collection**: Retrieves all Advisor recommendation categories (Cost, Security, Reliability, Operational Excellence, Performance)
- **Rich Metadata**: Captures detailed recommendation information including:
  - Tenant and subscription identifiers
  - Recommendation category, impact level, and risk assessment
  - Problem descriptions and suggested solutions
  - Affected resource information and metadata
  - Suppression status and extended properties
- **Delta Lake Storage**: Stores results in structured Delta format for analytics and reporting
- **Error Handling**: Graceful handling of authentication errors and inaccessible subscriptions

## Data Sources

The notebook connects to **two Azure tenants** configured in the Variable Library:
- **Tenant A**: Primary tenant with service principal credentials
- **Tenant B**: Secondary tenant with service principal credentials

## Prerequisites

### Variable Library Configuration

The notebook requires the following variables in `VariableLib`:

**Tenant A Configuration:**
- `a_tenant_id`: Azure AD Tenant ID for the first tenant
- `a_client_id`: Application (client) ID of the service principal for Tenant A
- `a_secret_name`: Key Vault secret name containing the client secret for Tenant A

**Tenant B Configuration:**
- `b_tenant_id`: Azure AD Tenant ID for the second tenant
- `b_client_id`: Application (client) ID of the service principal for Tenant B
- `b_secret_name`: Key Vault secret name containing the client secret for Tenant B

**Shared Configuration:**
- `key_vault_url`: URL of the Azure Key Vault containing service principal secrets
- `finopshub_root_path`: Root path for FinOpsHub Delta Lake tables

### Service Principal Permissions

Each service principal must have the following permissions:
- **Reader** role on all subscriptions to access
- **Advisor Reader** role (if available) for enhanced Advisor access
- Minimum permissions to list subscriptions and read Advisor recommendations

### Azure Key Vault Access

- Service principals' client secrets stored in Azure Key Vault
- Fabric workspace identity must have **Get** permissions on the Key Vault secrets

## Output Schema

The notebook creates a Delta table with the following schema:

| Column | Type | Description |
|--------|------|-------------|
| `tenant_id` | string | Azure AD Tenant ID |
| `tenant_label` | string | Human-readable tenant identifier (e.g., "Tenant A") |
| `subscription_id` | string | Azure subscription ID |
| `subscription_name` | string | Display name of the subscription |
| `recommendation_id` | string | Unique Advisor recommendation identifier |
| `recommendation_name` | string | Name/title of the recommendation |
| `category` | string | Recommendation category (Cost, Security, etc.) |
| `impact` | string | Impact level (High, Medium, Low) |
| `problem` | string | Description of the identified problem |
| `solution` | string | Recommended solution or action |
| `impacted_field` | string | Field or attribute that is impacted |
| `impacted_value` | string | Value of the impacted field |
| `resource_type` | string | Type of the affected Azure resource |
| `resource_group` | string | Resource group name containing the resource |
| `resource_id` | string | Full Azure resource ID |
| `risk` | string | Risk level associated with the recommendation |
| `last_updated` | string | ISO timestamp of when the recommendation was last updated |
| `suppression_ids` | string | JSON array of any suppression rule IDs |
| `extended_properties` | string | JSON object with additional recommendation metadata |
| `extracted_at` | string | ISO timestamp of when the data was extracted |

## Delta Lake Table Location

Data is written to: `{finopshub_root_path}/bronze/AdvisorRecommendations`

The table uses **overwrite** mode, replacing all data on each execution to ensure freshness.

## Usage

1. **Configure Variable Library**: Ensure all required variables are set in `VariableLib`
2. **Set Up Key Vault**: Store service principal secrets in Azure Key Vault
3. **Grant Permissions**: Assign appropriate roles to service principals in both tenants
4. **Run Notebook**: Execute all cells to extract and store Advisor recommendations

## Error Handling

The notebook includes robust error handling:
- **Authentication Failures**: Validates credentials before proceeding
- **Permission Issues**: Continues processing other subscriptions if one fails
- **Empty Results**: Creates proper schema even when no recommendations are found
- **API Limits**: Handles rate limiting and temporary service issues

## Monitoring and Validation

The notebook provides comprehensive logging:
- Progress indicators for each tenant and subscription
- Summary statistics by tenant and category
- Data validation and verification of Delta Lake writes
- Error reporting for failed operations

## Sample Output

```
🎯 RETRIEVING ADVISOR RECOMMENDATIONS FROM BOTH TENANTS
══════════════════════════════════════════════════════════════════════

🔍 Querying Tenant A (12345678-1234-1234-1234-123456789012)...
  📋 Processing 3 subscriptions for Advisor recommendations...
    Checking subscription: Production Environment
      ✓ Found 15 recommendations
    Checking subscription: Development Environment  
      ✓ Found 8 recommendations
  ✅ Retrieved 23 total recommendations from Tenant A

🔍 Querying Tenant B (87654321-4321-4321-4321-210987654321)...
  📋 Processing 2 subscriptions for Advisor recommendations...
    Checking subscription: Corporate IT
      ✓ Found 12 recommendations  
  ✅ Retrieved 12 total recommendations from Tenant B

══════════════════════════════════════════════════════════════════════
📊 EXTRACTION SUMMARY
══════════════════════════════════════════════════════════════════════
  Tenant A: 23 recommendations
  Tenant B: 12 recommendations
  📈 Total: 35 recommendations
══════════════════════════════════════════════════════════════════════
```

## Integration with FinOps Processes

This data feeds into broader FinOps analytics workflows:
- **Cost Optimization**: Identifies cost-saving opportunities across all tenants
- **Security Compliance**: Tracks security recommendations and remediation status
- **Performance Monitoring**: Highlights performance optimization opportunities
- **Governance Reporting**: Provides centralized view of recommendation compliance

The centralized data enables cross-tenant analysis and consistent reporting across the organization's Azure footprint.