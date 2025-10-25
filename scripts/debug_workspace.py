#!/usr/bin/env python3
"""
Debug script to check Fabric workspace contents and verify deployment
"""

import os
import sys
import argparse
import yaml
from pathlib import Path

def install_fabric_cicd():
    """Install fabric-cicd library"""
    import subprocess
    
    print("📦 Installing fabric-cicd library...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '--upgrade', 'fabric-cicd', 'azure-identity', 'pyyaml'
        ], capture_output=True, text=True, check=True)
        
        print("✅ fabric-cicd installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install fabric-cicd: {e}")
        return False

def load_workspace_config(environment):
    """Load workspace configuration for environment"""
    config_files = ['fabric-config.yml', 'fabric-config-minimal.yml']
    
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"📋 Loading configuration from {config_file}")
            
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            print(f"🔍 Searching for workspace ID for environment: {environment}")
            
            # Try fabric-config.yml structure: core.workspace_id.ENV
            if 'core' in config and 'workspace_id' in config['core']:
                workspace_mapping = config['core']['workspace_id']
                if environment.upper() in workspace_mapping:
                    workspace_ref = workspace_mapping[environment.upper()]
                    print(f"   Found workspace reference: {workspace_ref}")
                    
                    # Handle environment variable references like "$ENV:DEV_WORKSPACE_ID"
                    if workspace_ref.startswith('$ENV:'):
                        env_var = workspace_ref[5:]  # Remove "$ENV:" prefix
                        workspace_id = os.environ.get(env_var)
                        if workspace_id:
                            print(f"   ✅ Resolved from environment variable {env_var}: {workspace_id}")
                            return workspace_id
                        else:
                            print(f"   ❌ Environment variable {env_var} not found")
                            print(f"       Available environment variables:")
                            for key in sorted(os.environ.keys()):
                                if 'WORKSPACE' in key.upper():
                                    print(f"         {key}={os.environ[key]}")
                    else:
                        # Direct workspace ID
                        print(f"✅ Target workspace for {environment}: {workspace_ref}")
                        return workspace_ref
    
    print(f"❌ Could not find workspace ID for environment: {environment}")
    return None

def check_workspace_contents(environment):
    """Check what's actually in the Fabric workspace"""
    
    # Import fabric-cicd after ensuring it's installed
    try:
        from fabric_cicd import FabricWorkspace
        from azure.identity import DefaultAzureCredential, ClientSecretCredential
        
        print(f"📦 fabric-cicd imported successfully")
        
    except ImportError as e:
        print(f"❌ Failed to import fabric-cicd: {e}")
        return False
    
    print(f"🔍 Checking Fabric workspace contents for {environment.upper()} environment")
    print("=" * 60)
    
    try:
        # Load workspace configuration
        workspace_id = load_workspace_config(environment)
        if not workspace_id:
            return False
        
        # Setup authentication
        client_id = os.environ.get('AZURE_CLIENT_ID')
        client_secret = os.environ.get('AZURE_CLIENT_SECRET')
        tenant_id = os.environ.get('AZURE_TENANT_ID')
        
        if client_id and client_secret and tenant_id:
            print("🔐 Using Service Principal authentication")
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        else:
            print("🔐 Using DefaultAzureCredential")
            credential = DefaultAzureCredential()
        
        print(f"🏗️ Connecting to workspace: {workspace_id}")
        
        # Try to list items in the workspace using Fabric REST API
        try:
            import requests
            from azure.core.credentials import TokenCredential
            
            # Get access token
            token = credential.get_token("https://analysis.windows.net/powerbi/api/.default")
            
            # List workspace items
            headers = {
                'Authorization': f'Bearer {token.token}',
                'Content-Type': 'application/json'
            }
            
            url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                items = response.json().get('value', [])
                print(f"\n📋 Found {len(items)} item(s) in workspace:")
                
                for item in items:
                    item_type = item.get('type', 'Unknown')
                    item_name = item.get('displayName', 'Unknown')
                    item_id = item.get('id', 'Unknown')
                    print(f"   🔸 {item_type}: {item_name} (ID: {item_id})")
                
                # Filter for our item types
                notebooks = [item for item in items if item.get('type') == 'Notebook']
                lakehouses = [item for item in items if item.get('type') == 'Lakehouse']
                
                print(f"\n📊 Item Summary:")
                print(f"   📓 Notebooks: {len(notebooks)}")
                print(f"   🏠 Lakehouses: {len(lakehouses)}")
                
                if notebooks:
                    print(f"   Notebook names: {[nb.get('displayName') for nb in notebooks]}")
                if lakehouses:
                    print(f"   Lakehouse names: {[lh.get('displayName') for lh in lakehouses]}")
                
            else:
                print(f"❌ Failed to list workspace items: {response.status_code}")
                print(f"   Response: {response.text}")
                
        except Exception as api_error:
            print(f"❌ Failed to access Fabric API: {api_error}")
        
        print(f"\n🔍 Repository Contents Check:")
        repo_dir = os.getcwd()
        print(f"   Working directory: {repo_dir}")
        
        # Check for notebooks
        notebooks_dir = os.path.join(repo_dir, "notebooks")
        if os.path.exists(notebooks_dir):
            notebooks = list(Path(notebooks_dir).glob("*.ipynb"))
            print(f"   📓 Found {len(notebooks)} notebook(s) in repo: {[nb.name for nb in notebooks]}")
        else:
            print(f"   ❌ Notebooks directory not found: {notebooks_dir}")
        
        # Check for lakehouses
        lakehouses_dir = os.path.join(repo_dir, "lakehouses")
        if os.path.exists(lakehouses_dir):
            lakehouses = [d for d in Path(lakehouses_dir).iterdir() if d.is_dir()]
            print(f"   🏠 Found {len(lakehouses)} lakehouse(s) in repo: {[lh.name for lh in lakehouses]}")
        else:
            print(f"   ❌ Lakehouses directory not found: {lakehouses_dir}")
        
        return True
        
    except Exception as e:
        print(f"❌ Workspace check failed: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Debug Fabric workspace contents')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment (dev, test, prod)')
    parser.add_argument('--install-deps', action='store_true',
                       help='Install fabric-cicd library if missing')
    
    args = parser.parse_args()
    
    # Install dependencies if requested
    if args.install_deps:
        if not install_fabric_cicd():
            sys.exit(1)
    
    # Check workspace contents
    success = check_workspace_contents(args.environment)
    
    if not success:
        sys.exit(1)
    
    print("\n🎉 Workspace check completed!")

if __name__ == '__main__':
    main()