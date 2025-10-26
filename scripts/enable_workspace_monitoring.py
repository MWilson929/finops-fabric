#!/usr/bin/env python3
"""
Fabric Workspace Monitoring Setup Script
Enables workspace monitoring with EventHouse integration for FinOps Hub
"""

import requests
import json
import time
from azure.identity import ClientSecretCredential
from typing import Dict, Optional
import sys
import os

class FabricMonitoringSetup:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        """Initialize Fabric monitoring setup with service principal credentials"""
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.headers = None
        
    def authenticate(self):
        """Authenticate with Fabric using service principal"""
        try:
            credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            
            # Get Fabric API token
            token_response = credential.get_token("https://api.fabric.microsoft.com/.default")
            self.token = token_response.token
            
            self.headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json'
            }
            
            print("✅ Successfully authenticated with Fabric API")
            return True
            
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return False
    
    def get_workspace_id(self, workspace_name: str) -> Optional[str]:
        """Get workspace ID by name"""
        try:
            url = "https://api.fabric.microsoft.com/v1/workspaces"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            workspaces = response.json().get('value', [])
            for workspace in workspaces:
                if workspace.get('displayName') == workspace_name:
                    return workspace.get('id')
            
            print(f"⚠️  Workspace '{workspace_name}' not found")
            return None
            
        except Exception as e:
            print(f"❌ Failed to get workspace ID: {e}")
            return None
    
    def get_eventhouse_id(self, workspace_id: str, eventhouse_name: str) -> Optional[str]:
        """Get EventHouse ID by name within workspace"""
        try:
            url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items"
            params = {"type": "Eventhouse"}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            items = response.json().get('value', [])
            for item in items:
                if item.get('displayName') == eventhouse_name:
                    return item.get('id')
            
            print(f"⚠️  EventHouse '{eventhouse_name}' not found in workspace")
            return None
            
        except Exception as e:
            print(f"❌ Failed to get EventHouse ID: {e}")
            return None
    
    def enable_workspace_monitoring(self, workspace_id: str, eventhouse_id: str) -> bool:
        """Enable workspace monitoring with EventHouse"""
        try:
            url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/monitoring"
            
            monitoring_config = {
                "isEnabled": True,
                "eventHouse": {
                    "id": eventhouse_id,
                    "name": "FinOpsMonitoring"
                },
                "auditingEnabled": True,
                "metricsEnabled": True,
                "activityLogsEnabled": True
            }
            
            response = requests.put(url, headers=self.headers, json=monitoring_config)
            
            if response.status_code in [200, 201]:
                print("✅ Workspace monitoring enabled successfully")
                return True
            else:
                print(f"⚠️  Monitoring setup response: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Failed to enable workspace monitoring: {e}")
            return False
    
    def verify_monitoring_status(self, workspace_id: str) -> Dict:
        """Verify monitoring configuration status"""
        try:
            url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/monitoring"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                config = response.json()
                print(f"📊 Monitoring Status:")
                print(f"   Enabled: {config.get('isEnabled', False)}")
                print(f"   EventHouse ID: {config.get('eventHouse', {}).get('id', 'Not configured')}")
                print(f"   Auditing: {config.get('auditingEnabled', False)}")
                print(f"   Metrics: {config.get('metricsEnabled', False)}")
                return config
            else:
                print(f"⚠️  Could not retrieve monitoring status: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"❌ Failed to verify monitoring status: {e}")
            return {}

def main():
    """Main execution function"""
    print("🔧 Fabric Workspace Monitoring Setup")
    print("=" * 50)
    
    # Get configuration from environment variables
    tenant_id = os.getenv('TENANT_ID')
    client_id = os.getenv('CLIENT_ID')
    client_secret = os.getenv('CLIENT_SECRET')
    workspace_name = os.getenv('WORKSPACE_NAME', 'Fabric Development')
    eventhouse_name = os.getenv('EVENTHOUSE_NAME', 'FinOpsMonitoring')
    
    if not all([tenant_id, client_id, client_secret]):
        print("❌ Missing required environment variables: TENANT_ID, CLIENT_ID, CLIENT_SECRET")
        sys.exit(1)
    
    # Initialize monitoring setup
    setup = FabricMonitoringSetup(tenant_id, client_id, client_secret)
    
    # Authenticate
    if not setup.authenticate():
        sys.exit(1)
    
    # Get workspace ID
    print(f"\n🔍 Finding workspace: {workspace_name}")
    workspace_id = setup.get_workspace_id(workspace_name)
    if not workspace_id:
        sys.exit(1)
    
    print(f"✅ Found workspace ID: {workspace_id}")
    
    # Get EventHouse ID
    print(f"\n📊 Finding EventHouse: {eventhouse_name}")
    eventhouse_id = setup.get_eventhouse_id(workspace_id, eventhouse_name)
    if not eventhouse_id:
        print("⚠️  EventHouse not found - please deploy it first")
        sys.exit(1)
    
    print(f"✅ Found EventHouse ID: {eventhouse_id}")
    
    # Enable monitoring
    print(f"\n⚙️  Enabling workspace monitoring...")
    if setup.enable_workspace_monitoring(workspace_id, eventhouse_id):
        print("✅ Monitoring setup completed successfully")
        
        # Verify configuration
        print(f"\n🔍 Verifying monitoring configuration...")
        setup.verify_monitoring_status(workspace_id)
        
        print(f"\n🎯 Next Steps:")
        print(f"   • Monitor activity logs in EventHouse: {eventhouse_name}")
        print(f"   • Query monitoring data using KQL")
        print(f"   • Set up alerts and dashboards")
        print(f"   • Review workspace performance metrics")
        
    else:
        print("❌ Failed to enable workspace monitoring")
        sys.exit(1)

if __name__ == "__main__":
    main()