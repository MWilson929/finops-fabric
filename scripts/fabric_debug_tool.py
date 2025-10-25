#!/usr/bin/env python3
"""
Microsoft Fabric Debug Tool
Quick diagnostic tool for troubleshooting Fabric workspace deployments.
Focused on debugging and workspace inspection.
"""

import os
import sys
import argparse
import yaml
import requests
import subprocess
from pathlib import Path


def install_fabric_cicd():
    """Install fabric-cicd library if missing"""
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


def get_fabric_token():
    """Get access token for Fabric API"""
    try:
        result = subprocess.run([
            'az', 'account', 'get-access-token', 
            '--resource', 'https://analysis.windows.net/powerbi/api',
            '--query', 'accessToken', '-o', 'tsv'
        ], capture_output=True, text=True, timeout=30)
        
        return result.stdout.strip() if result.returncode == 0 else None
    except:
        return None


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
                            print(f"       Available workspace environment variables:")
                            for key in sorted(os.environ.keys()):
                                if 'WORKSPACE' in key.upper():
                                    print(f"         {key}={os.environ[key]}")
                    else:
                        # Direct workspace ID
                        print(f"✅ Target workspace for {environment}: {workspace_ref}")
                        return workspace_ref
    
    print(f"❌ Could not find workspace ID for environment: {environment}")
    return None


def debug_workspace_contents(environment):
    """Debug workspace contents and compare with repository"""
    
    print(f"🔍 Debugging Fabric workspace for {environment.upper()} environment")
    print("=" * 60)
    
    try:
        # Load workspace configuration
        workspace_id = load_workspace_config(environment)
        if not workspace_id:
            return False
        
        # Get authentication token
        token = get_fabric_token()
        if not token:
            print("❌ Failed to obtain authentication token")
            return False
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        print(f"🏗️ Connecting to workspace: {workspace_id}")
        
        # List workspace items using Fabric REST API
        try:
            url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items"
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                items = response.json().get('value', [])
                print(f"\n📋 Found {len(items)} item(s) in workspace:")
                
                if items:
                    for item in items:
                        item_type = item.get('type', 'Unknown')
                        item_name = item.get('displayName', 'Unknown')
                        item_id = item.get('id', 'Unknown')
                        print(f"   🔸 {item_type}: {item_name}")
                        print(f"      ID: {item_id}")
                
                # Analyze item distribution
                item_counts = {}
                for item in items:
                    item_type = item.get('type', 'Unknown')
                    item_counts[item_type] = item_counts.get(item_type, 0) + 1
                
                print(f"\n📊 Item Summary:")
                for item_type, count in sorted(item_counts.items()):
                    print(f"   {item_type}: {count}")
                
            elif response.status_code == 404:
                print(f"❌ Workspace not found: {workspace_id}")
                return False
            else:
                print(f"❌ Failed to list workspace items: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as api_error:
            print(f"❌ Failed to access Fabric API: {api_error}")
            return False
        
        # Compare with repository contents
        print(f"\n🔍 Repository Contents Comparison:")
        repo_dir = os.getcwd()
        print(f"   Working directory: {repo_dir}")
        
        # Check for notebooks
        notebooks_dir = os.path.join(repo_dir, "notebooks")
        if os.path.exists(notebooks_dir):
            notebook_folders = [d for d in Path(notebooks_dir).iterdir() if d.is_dir() and d.name.endswith('.Notebook')]
            print(f"   📓 Found {len(notebook_folders)} notebook folder(s) in repo:")
            for nb in notebook_folders:
                print(f"      - {nb.name}")
        else:
            print(f"   ❌ Notebooks directory not found: {notebooks_dir}")
        
        # Check for lakehouses
        lakehouses_dir = os.path.join(repo_dir, "lakehouses")
        if os.path.exists(lakehouses_dir):
            lakehouse_folders = [d for d in Path(lakehouses_dir).iterdir() if d.is_dir() and d.name.endswith('.Lakehouse')]
            print(f"   🏠 Found {len(lakehouse_folders)} lakehouse folder(s) in repo:")
            for lh in lakehouse_folders:
                print(f"      - {lh.name}")
        else:
            print(f"   ❌ Lakehouses directory not found: {lakehouses_dir}")
        
        # Check for other item types
        for item_type in ['reports', 'dataflows', 'datapipelines', 'semanticmodels']:
            item_dir = os.path.join(repo_dir, item_type)
            if os.path.exists(item_dir):
                items_in_dir = [d for d in Path(item_dir).iterdir() if d.is_dir()]
                if items_in_dir:
                    print(f"   📊 Found {len(items_in_dir)} {item_type} folder(s) in repo:")
                    for item in items_in_dir:
                        print(f"      - {item.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Workspace debug failed: {str(e)}")
        return False


def debug_configuration():
    """Debug configuration files and environment variables"""
    print(f"🔧 Debugging Configuration")
    print("=" * 40)
    
    # Check configuration files
    config_files = ['fabric-config.yml', 'parameter.yml', 'azure-pipelines.yml']
    
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"✅ Found: {config_file}")
            try:
                with open(config_file, 'r') as f:
                    content = yaml.safe_load(f)
                print(f"   Valid YAML structure")
                
                # Show key sections for fabric-config.yml
                if config_file == 'fabric-config.yml':
                    if 'core' in content:
                        workspace_ids = content['core'].get('workspace_id', {})
                        print(f"   Workspace environments: {list(workspace_ids.keys())}")
                        
                        item_types = content['core'].get('item_types_in_scope', [])
                        print(f"   Item types in scope: {item_types}")
                        
            except Exception as e:
                print(f"   ❌ Error reading {config_file}: {e}")
        else:
            print(f"❌ Missing: {config_file}")
    
    # Check environment variables
    print(f"\n🌍 Environment Variables:")
    workspace_vars = [key for key in os.environ.keys() if 'WORKSPACE' in key.upper()]
    if workspace_vars:
        for var in sorted(workspace_vars):
            value = os.environ[var]
            masked_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else value
            print(f"   {var} = {masked_value}")
    else:
        print(f"   ❌ No workspace-related environment variables found")
    
    # Check Azure CLI
    print(f"\n🔐 Azure CLI Status:")
    try:
        result = subprocess.run(['az', 'account', 'show'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"   ✅ Azure CLI authenticated")
        else:
            print(f"   ❌ Azure CLI not authenticated")
    except:
        print(f"   ❌ Azure CLI not available")


def main():
    parser = argparse.ArgumentParser(description='Debug Fabric workspace and configuration')
    parser.add_argument('--environment', choices=['dev', 'test', 'prod'],
                       help='Target environment (dev, test, prod)')
    parser.add_argument('--config-only', action='store_true',
                       help='Debug configuration files and variables only')
    parser.add_argument('--install-deps', action='store_true',
                       help='Install fabric-cicd library if missing')
    
    args = parser.parse_args()
    
    print(f"🛠️  Microsoft Fabric Debug Tool")
    print("=" * 50)
    
    # Install dependencies if requested
    if args.install_deps:
        if not install_fabric_cicd():
            sys.exit(1)
    
    # Debug configuration
    if args.config_only or not args.environment:
        debug_configuration()
        
        if not args.environment:
            print(f"\n💡 Use --environment [dev|test|prod] to debug workspace contents")
        
        if args.config_only:
            sys.exit(0)
    
    # Debug workspace contents if environment specified
    if args.environment:
        print(f"")  # Add spacing
        success = debug_workspace_contents(args.environment)
        
        if success:
            print(f"\n🎉 Debug completed successfully!")
        else:
            print(f"\n❌ Debug encountered issues")
            sys.exit(1)


if __name__ == '__main__':
    main()