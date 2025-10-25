# Microsoft Fabric CI/CD Authentication Troubleshooting Guide

## Issue: Invalid Tenant ID Error

The error `Invalid tenant ID provided` typically occurs when the Azure authentication configuration is incorrect. Here's how to fix it:

## 🔍 **Step 1: Verify Tenant ID Format**

Your tenant ID must be a valid GUID in this format:
```
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### Find Your Tenant ID:
1. **Azure Portal Method**:
   - Go to [Azure Portal](https://portal.azure.com)
   - Navigate to "Azure Active Directory" > "Overview"
   - Copy the "Tenant ID" value

2. **PowerShell Method**:
   ```powershell
   Connect-AzAccount
   Get-AzContext | Select-Object -ExpandProperty Tenant
   ```

3. **Azure CLI Method**:
   ```bash
   az account show --query tenantId --output tsv
   ```

## 🔧 **Step 2: Update Your Azure DevOps Variable Groups**

You need to configure three variable groups with the correct authentication values:

### Variable Group: `fabric-dev-variables`
```yaml
Variables:
- dev-workspace-id: "your-dev-workspace-guid"
- dev-subscription-id: "your-subscription-guid"  
- dev-storage-account: "your-dev-storage-account"
- dev-container-name: "your-dev-container"
- servicePrincipalId: "your-service-principal-client-id"
- servicePrincipalKey: "your-service-principal-secret"  # Mark as SECRET
- tenantId: "your-tenant-id-guid"
```

### Variable Group: `fabric-test-variables`
```yaml
Variables:
- test-workspace-id: "your-test-workspace-guid"
- test-subscription-id: "your-subscription-guid"
- test-storage-account: "your-test-storage-account"  
- test-container-name: "your-test-container"
- servicePrincipalId: "your-service-principal-client-id"
- servicePrincipalKey: "your-service-principal-secret"  # Mark as SECRET
- tenantId: "your-tenant-id-guid"
```

### Variable Group: `fabric-prod-variables`
```yaml
Variables:
- prod-workspace-id: "your-prod-workspace-guid"
- prod-subscription-id: "your-subscription-guid"
- prod-storage-account: "your-prod-storage-account"
- prod-container-name: "your-prod-container"  
- servicePrincipalId: "your-service-principal-client-id"
- servicePrincipalKey: "your-service-principal-secret"  # Mark as SECRET
- tenantId: "your-tenant-id-guid"
```

## 🔐 **Step 3: Create/Verify Service Principal**

If you don't have a service principal, create one:

```bash
# Create service principal
az ad sp create-for-rbac --name "fabric-cicd-sp" --role contributor --scopes /subscriptions/{subscription-id}

# Output will include:
{
  "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",      # This is your Client ID
  "displayName": "fabric-cicd-sp",
  "password": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",        # This is your Client Secret
  "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"      # This is your Tenant ID
}
```

Grant Fabric permissions:
```bash
# Add Fabric Admin role (or appropriate permissions)
az role assignment create --assignee {appId} --role "Fabric Administrator" --scope /subscriptions/{subscription-id}
```

## 🔄 **Step 4: Update Azure DevOps Variable Groups**

1. Go to Azure DevOps > Your Project > Pipelines > Library
2. Edit each variable group (`fabric-dev-variables`, `fabric-test-variables`, `fabric-prod-variables`)
3. Update/add these variables:
   - `servicePrincipalId` = Service Principal App ID (Client ID)
   - `servicePrincipalKey` = Service Principal Password (Client Secret) - **Mark as SECRET**
   - `tenantId` = Your Azure Tenant ID

## 🧪 **Step 5: Test the Configuration**

### Manual Test Script
Create a test script to validate your configuration:

```python
# test_auth.py
import os
from azure.identity import ClientSecretCredential

# Get values from environment or replace with actual values
client_id = os.environ.get('AZURE_CLIENT_ID', 'your-client-id-here')
client_secret = os.environ.get('AZURE_CLIENT_SECRET', 'your-client-secret-here')  
tenant_id = os.environ.get('AZURE_TENANT_ID', 'your-tenant-id-here')

print(f"Testing authentication with:")
print(f"Client ID: {client_id}")
print(f"Tenant ID: {tenant_id}")

try:
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id, 
        client_secret=client_secret
    )
    
    # Test getting a token
    token = credential.get_token('https://api.fabric.microsoft.com/.default')
    print("✅ Authentication successful!")
    print(f"Token expires: {token.expires_on}")
    
except Exception as e:
    print(f"❌ Authentication failed: {e}")
```

## 📋 **Step 6: Common Issues and Solutions**

### Issue: "AADSTS70011: Invalid client secret"
**Solution**: Regenerate the service principal secret:
```bash
az ad sp credential reset --id {service-principal-app-id}
```

### Issue: "AADSTS700016: Application not found"  
**Solution**: Verify the service principal exists and the client ID is correct:
```bash
az ad sp show --id {service-principal-app-id}
```

### Issue: "AADSTS90002: Tenant not found"
**Solution**: Verify your tenant ID:
```bash
az account show --query tenantId --output tsv
```

### Issue: "Insufficient permissions"
**Solution**: Grant proper Fabric permissions to your service principal:
- Fabric Administrator role
- Contributor role on subscription
- Workspace access in Fabric

## 🔄 **Step 7: Re-run Your Pipeline**

After updating the variable groups:

1. Go to Azure DevOps > Pipelines
2. Find your pipeline 
3. Click "Run pipeline"
4. Select your deployment parameters
5. Monitor the "Deploy Fabric Items to Dev Environment" step

## 📞 **Additional Resources**

- [Find Azure Tenant ID](https://learn.microsoft.com/partner-center/find-ids-and-domain-names)
- [Azure Service Principal Creation](https://docs.microsoft.com/azure/active-directory/develop/howto-create-service-principal-portal)
- [Microsoft Fabric Authentication](https://learn.microsoft.com/fabric/security/security-authentication)
- [Azure DevOps Variable Groups](https://docs.microsoft.com/azure/devops/pipelines/library/variable-groups)

---

**💡 Pro Tip**: Always use Azure DevOps variable groups with secret variables for sensitive authentication information rather than hardcoding values in your pipeline YAML.