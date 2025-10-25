#!/usr/bin/env python3
"""
Standard Fabric deployment script using fabric-cicd library
Uses the standard FabricWorkspace approach instead of experimental config files
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
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
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
                            print(f"   Resolved from environment variable {env_var}: {workspace_id}")
                            return workspace_id
                        else:
                            print(f"   ❌ Environment variable {env_var} not found")
                    else:
                        # Direct workspace ID
                        print(f"🎯 Target workspace for {environment}: {workspace_ref}")
                        return workspace_ref
            
            # Try simple workspaces structure
            if 'workspaces' in config and environment in config['workspaces']:
                workspace_id = config['workspaces'][environment]
                print(f"🎯 Target workspace for {environment}: {workspace_id}")
                return workspace_id
            
            # Try alternative environments structure
            if 'environments' in config and environment in config['environments']:
                env_config = config['environments'][environment]
                if 'workspace_id' in env_config:
                    workspace_id = env_config['workspace_id']
                    print(f"🎯 Target workspace for {environment}: {workspace_id}")
                    return workspace_id
    
    # Fallback to direct environment variable
    env_var = f"{environment.upper()}_WORKSPACE_ID"
    workspace_id = os.environ.get(env_var)
    if workspace_id:
        print(f"🎯 Using direct environment variable {env_var}: {workspace_id}")
        return workspace_id
    
    # Last resort - FABRIC_WORKSPACE_ID format
    env_var_alt = f"FABRIC_WORKSPACE_ID_{environment.upper()}"
    workspace_id = os.environ.get(env_var_alt)
    if workspace_id:
        print(f"🎯 Using alternative environment variable {env_var_alt}: {workspace_id}")
        return workspace_id
    
    print(f"❌ Could not find workspace ID for environment: {environment}")
    return None

def deploy_fabric_items_standard(environment, dry_run=False):
    """Deploy Fabric items using standard fabric-cicd library approach"""
    
    # Import fabric-cicd after ensuring it's installed
    try:
        from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items
        from azure.identity import DefaultAzureCredential, ClientSecretCredential
        
        print(f"📦 fabric-cicd imported successfully")
        
    except ImportError as e:
        print(f"❌ Failed to import fabric-cicd: {e}")
        return False
    
    print(f"🚀 Starting Standard Fabric deployment to {environment.upper()} environment")
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
        
        if dry_run:
            print("🔍 DRY RUN MODE - No actual deployment will occur")
            print(f"   Target workspace: {workspace_id}")
            print(f"   Environment: {environment}")
            print(f"   Repository directory: {os.getcwd()}")
            return True
        
        # Check what items exist in repository before deployment  
        # Use current directory, but should be called from repository root
        repo_dir = os.getcwd()
        print(f"🔍 Repository scan:")
        print(f"   Working directory: {repo_dir}")
        
        # Try to find repository root if we're not in it
        potential_repo_dirs = [
            repo_dir,
            os.path.dirname(repo_dir),  # Parent directory
            "/home/vsts/work/1/fca-deployment-package"  # Known artifact path
        ]
        
        actual_repo_dir = repo_dir
        for test_dir in potential_repo_dirs:
            if os.path.exists(os.path.join(test_dir, "notebooks")) or os.path.exists(os.path.join(test_dir, "lakehouses")):
                actual_repo_dir = test_dir
                print(f"   📁 Found repository structure in: {actual_repo_dir}")
                break
        
        repo_dir = actual_repo_dir
        
        # Check for notebooks
        notebooks_dir = os.path.join(repo_dir, "notebooks")
        if os.path.exists(notebooks_dir):
            notebooks = list(Path(notebooks_dir).glob("*.ipynb"))
            print(f"   Found {len(notebooks)} notebook(s): {[nb.name for nb in notebooks]}")
        else:
            print(f"   ❌ Notebooks directory not found: {notebooks_dir}")
        
        # Check for lakehouses
        lakehouses_dir = os.path.join(repo_dir, "lakehouses")
        if os.path.exists(lakehouses_dir):
            lakehouses = [d for d in Path(lakehouses_dir).iterdir() if d.is_dir()]
            print(f"   Found {len(lakehouses)} lakehouse(s): {[lh.name for lh in lakehouses]}")
        else:
            print(f"   ❌ Lakehouses directory not found: {lakehouses_dir}")
        
        # Initialize the FabricWorkspace object
        print(f"🏗️ Initializing Fabric workspace...")
        print(f"   Workspace ID: {workspace_id}")
        print(f"   Repository directory: {repo_dir}")
        print(f"   Item types in scope: ['Notebook', 'Lakehouse']")
        
        target_workspace = FabricWorkspace(
            workspace_id=workspace_id,
            repository_directory=repo_dir,
            item_type_in_scope=["Notebook", "Lakehouse"],
            token_credential=credential
        )
        
        # Publish all items in scope
        print(f"📦 Publishing items to workspace...")
        print(f"   This will deploy all Notebooks and Lakehouses found in the repository")
        
        try:
            result = publish_all_items(target_workspace)
            print(f"   ✅ Publish operation completed: {result}")
        except Exception as pub_error:
            print(f"   ❌ Publish operation failed: {pub_error}")
            raise pub_error
        
        # Unpublish orphan items
        print(f"🧹 Cleaning up orphan items...")
        print(f"   This will remove items in workspace not found in repository")
        
        try:
            result = unpublish_all_orphan_items(target_workspace)
            print(f"   ✅ Cleanup operation completed: {result}")
        except Exception as cleanup_error:
            print(f"   ❌ Cleanup operation failed: {cleanup_error}")
            # Don't fail deployment if cleanup fails
            print(f"   ⚠️  Continuing despite cleanup failure...")
        
        print(f"✅ Standard deployment to {environment.upper()} completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Standard deployment failed: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Deploy Fabric items using standard fabric-cicd library')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment (dev, test, prod)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Validate configuration without deploying')
    parser.add_argument('--install-deps', action='store_true',
                       help='Install fabric-cicd library if missing')
    
    args = parser.parse_args()
    
    # Install dependencies if requested
    if args.install_deps:
        if not install_fabric_cicd():
            sys.exit(1)
    
    # Run deployment
    success = deploy_fabric_items_standard(args.environment, args.dry_run)
    
    if not success:
        sys.exit(1)
    
    print("🎉 Deployment completed!")

if __name__ == '__main__':
    main()