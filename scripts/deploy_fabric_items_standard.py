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
        
        # Initialize the FabricWorkspace object
        print(f"🏗️ Initializing Fabric workspace...")
        target_workspace = FabricWorkspace(
            workspace_id=workspace_id,
            repository_directory=os.getcwd(),
            item_type_in_scope=["Notebook", "Lakehouse"],  # Start with supported types
            token_credential=credential
        )
        
        # Publish all items in scope
        print(f"📦 Publishing items to workspace...")
        publish_all_items(target_workspace)
        
        # Unpublish orphan items (items not in repository)
        print(f"🧹 Cleaning up orphan items...")
        unpublish_all_orphan_items(target_workspace)
        
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