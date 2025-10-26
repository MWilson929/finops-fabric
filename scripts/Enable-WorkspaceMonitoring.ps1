# Fabric Workspace Monitoring Setup - PowerShell Script
# Enables EventHouse-based monitoring for FinOps Hub workspace

param(
    [Parameter(Mandatory=$true)]
    [string]$TenantId,
    
    [Parameter(Mandatory=$true)]
    [string]$ClientId,
    
    [Parameter(Mandatory=$true)]
    [string]$ClientSecret,
    
    [Parameter(Mandatory=$false)]
    [string]$WorkspaceName = "Fabric Development",
    
    [Parameter(Mandatory=$false)]
    [string]$EventhouseName = "FinOpsMonitoring"
)

Write-Host "🔧 Fabric Workspace Monitoring Setup" -ForegroundColor Cyan
Write-Host "=" * 50 -ForegroundColor Cyan

# Install required modules if not present
$requiredModules = @('Az.Accounts', 'Az.Resources')
foreach ($module in $requiredModules) {
    if (!(Get-Module -ListAvailable -Name $module)) {
        Write-Host "📦 Installing module: $module" -ForegroundColor Yellow
        Install-Module -Name $module -Force -AllowClobber
    }
}

try {
    # Authenticate with Azure using Service Principal
    Write-Host "🔐 Authenticating with Azure..." -ForegroundColor Yellow
    
    $securePassword = ConvertTo-SecureString $ClientSecret -AsPlainText -Force
    $credential = New-Object System.Management.Automation.PSCredential($ClientId, $securePassword)
    
    Connect-AzAccount -ServicePrincipal -Credential $credential -TenantId $TenantId | Out-Null
    
    # Get access token for Fabric API
    $context = Get-AzContext
    $token = [Microsoft.Azure.Commands.Common.Authentication.AzureSession]::Instance.AuthenticationFactory.Authenticate($context.Account, $context.Environment, $TenantId, $null, "https://api.fabric.microsoft.com/", $null).AccessToken
    
    $headers = @{
        'Authorization' = "Bearer $token"
        'Content-Type' = 'application/json'
    }
    
    Write-Host "✅ Successfully authenticated with Fabric API" -ForegroundColor Green
    
    # Get workspace ID
    Write-Host "🔍 Finding workspace: $WorkspaceName" -ForegroundColor Yellow
    
    $workspacesResponse = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/workspaces" -Headers $headers -Method GET
    $workspace = $workspacesResponse.value | Where-Object { $_.displayName -eq $WorkspaceName }
    
    if (-not $workspace) {
        Write-Host "❌ Workspace '$WorkspaceName' not found" -ForegroundColor Red
        exit 1
    }
    
    $workspaceId = $workspace.id
    Write-Host "✅ Found workspace ID: $workspaceId" -ForegroundColor Green
    
    # Get EventHouse ID
    Write-Host "📊 Finding EventHouse: $EventhouseName" -ForegroundColor Yellow
    
    $itemsResponse = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items?type=Eventhouse" -Headers $headers -Method GET
    $eventhouse = $itemsResponse.value | Where-Object { $_.displayName -eq $EventhouseName }
    
    if (-not $eventhouse) {
        Write-Host "❌ EventHouse '$EventhouseName' not found in workspace" -ForegroundColor Red
        Write-Host "⚠️  Please deploy the EventHouse first using your CI/CD pipeline" -ForegroundColor Yellow
        exit 1
    }
    
    $eventhouseId = $eventhouse.id
    Write-Host "✅ Found EventHouse ID: $eventhouseId" -ForegroundColor Green
    
    # Enable workspace monitoring
    Write-Host "⚙️  Enabling workspace monitoring with EventHouse..." -ForegroundColor Yellow
    
    $monitoringConfig = @{
        isEnabled = $true
        eventHouse = @{
            id = $eventhouseId
            name = $EventhouseName
        }
        auditingEnabled = $true
        metricsEnabled = $true
        activityLogsEnabled = $true
    } | ConvertTo-Json -Depth 3
    
    $monitoringResponse = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/monitoring" -Headers $headers -Method PUT -Body $monitoringConfig
    
    Write-Host "✅ Workspace monitoring enabled successfully" -ForegroundColor Green
    
    # Verify monitoring status
    Write-Host "🔍 Verifying monitoring configuration..." -ForegroundColor Yellow
    
    $statusResponse = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/monitoring" -Headers $headers -Method GET
    
    Write-Host "📊 Monitoring Status:" -ForegroundColor Cyan
    Write-Host "   Enabled: $($statusResponse.isEnabled)" -ForegroundColor White
    Write-Host "   EventHouse ID: $($statusResponse.eventHouse.id)" -ForegroundColor White
    Write-Host "   Auditing: $($statusResponse.auditingEnabled)" -ForegroundColor White
    Write-Host "   Metrics: $($statusResponse.metricsEnabled)" -ForegroundColor White
    
    Write-Host "`n🎯 Next Steps:" -ForegroundColor Cyan
    Write-Host "   • Monitor activity logs in EventHouse: $EventhouseName" -ForegroundColor White
    Write-Host "   • Query monitoring data using KQL in Fabric" -ForegroundColor White
    Write-Host "   • Set up alerts and dashboards for FinOps metrics" -ForegroundColor White
    Write-Host "   • Review workspace performance and usage patterns" -ForegroundColor White
    
    Write-Host "`n📚 Useful KQL Queries for FinOps Hub:" -ForegroundColor Cyan
    Write-Host @"
   // Notebook execution performance
   FabricActivityEvents
   | where ActivityName == "NotebookExecution"
   | summarize AvgDuration=avg(Duration), Count=count() by NotebookName
   
   // Data pipeline success rates  
   FabricActivityEvents
   | where ActivityName == "PipelineExecution"
   | summarize SuccessRate=avg(case(Status=="Success", 1.0, 0.0)) by PipelineName
   
   // Semantic model query performance
   FabricActivityEvents  
   | where ActivityName == "SemanticModelQuery"
   | summarize AvgQueryTime=avg(Duration) by SemanticModel
"@ -ForegroundColor Gray
    
}
catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n✅ Fabric workspace monitoring setup completed successfully!" -ForegroundColor Green