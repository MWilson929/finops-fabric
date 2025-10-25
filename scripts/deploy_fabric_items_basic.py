#!/usr/bin/env python3
"""
Basic Fabric deployment script without experimental features
Uses individual item deployment instead of config-based deployment
"""

import os
import sys
import argparse
import json
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

def deploy_notebooks(workspace_id, environment, credential):
    """Deploy notebooks individually"""
    from fabric_cicd import create_notebook, update_notebook
    
    notebooks_dir = Path("notebooks")
    if not notebooks_dir.exists():
        print("📝 No notebooks directory found, skipping notebook deployment")
        return True
    
    print(f"📝 Deploying notebooks to workspace {workspace_id}")
    
    try:
        for notebook_path in notebooks_dir.glob("*.ipynb"):
            print(f"   📓 Processing notebook: {notebook_path.name}")
            
            # Read notebook content
            with open(notebook_path, 'r', encoding='utf-8') as f:
                notebook_content = f.read()
            
            notebook_name = notebook_path.stem
            
            # Try to update first, create if not exists
            try:
                update_notebook(
                    workspace_id=workspace_id,
                    notebook_name=notebook_name,
                    notebook_content=notebook_content,
                    token_credential=credential
                )
                print(f"   ✅ Updated notebook: {notebook_name}")
                
            except Exception as update_error:
                # If update fails, try to create
                if "not found" in str(update_error).lower():
                    create_notebook(
                        workspace_id=workspace_id,
                        notebook_name=notebook_name,
                        notebook_content=notebook_content,
                        token_credential=credential
                    )
                    print(f"   ✅ Created notebook: {notebook_name}")
                else:
                    raise update_error
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to deploy notebooks: {e}")
        return False

def deploy_lakehouses(workspace_id, environment, credential):
    """Deploy lakehouses individually"""
    from fabric_cicd import create_lakehouse
    
    lakehouses_dir = Path("lakehouses")
    if not lakehouses_dir.exists():
        print("🏠 No lakehouses directory found, skipping lakehouse deployment")
        return True
    
    print(f"🏠 Deploying lakehouses to workspace {workspace_id}")
    
    try:
        for lakehouse_dir in lakehouses_dir.iterdir():
            if lakehouse_dir.is_dir() and lakehouse_dir.name.endswith(".Lakehouse"):
                lakehouse_name = lakehouse_dir.name.replace(".Lakehouse", "")
                print(f"   🏠 Processing lakehouse: {lakehouse_name}")
                
                # Check if lakehouse already exists, create if not
                try:
                    create_lakehouse(
                        workspace_id=workspace_id,
                        lakehouse_name=lakehouse_name,
                        token_credential=credential
                    )
                    print(f"   ✅ Created lakehouse: {lakehouse_name}")
                    
                except Exception as create_error:
                    if "already exists" in str(create_error).lower():
                        print(f"   ℹ️ Lakehouse already exists: {lakehouse_name}")
                    else:
                        raise create_error
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to deploy lakehouses: {e}")
        return False

def load_workspace_config(environment):
    """Load workspace configuration for environment"""
    config_files = ['fabric-config.yml', 'fabric-config-minimal.yml']
    
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"📋 Loading configuration from {config_file}")
            
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Extract workspace ID for environment
            if 'workspaces' in config and environment in config['workspaces']:
                workspace_id = config['workspaces'][environment]
                print(f"🎯 Target workspace for {environment}: {workspace_id}")
                return workspace_id
            
            # Try alternative config structure
            if 'environments' in config and environment in config['environments']:
                env_config = config['environments'][environment]
                if 'workspace_id' in env_config:
                    workspace_id = env_config['workspace_id']
                    print(f"🎯 Target workspace for {environment}: {workspace_id}")
                    return workspace_id
    
    # Fallback to environment variable
    env_var = f"FABRIC_WORKSPACE_ID_{environment.upper()}"
    workspace_id = os.environ.get(env_var)
    if workspace_id:
        print(f"🎯 Using workspace ID from environment variable {env_var}: {workspace_id}")
        return workspace_id
    
    print(f"❌ Could not find workspace ID for environment: {environment}")
    return None

def deploy_fabric_items_basic(environment, dry_run=False):
    """Deploy Fabric items using individual item deployment (no experimental features)"""
    
    # Import fabric-cicd after ensuring it's installed
    try:
        import fabric_cicd
        from azure.identity import DefaultAzureCredential, ClientSecretCredential
        
        # Display fabric-cicd version for debugging (if available)
        try:
            version = getattr(fabric_cicd, '__version__', 'version not available')
            print(f"📦 fabric-cicd imported successfully, version: {version}")
        except:
            print(f"📦 fabric-cicd imported successfully")
        
    except ImportError as e:
        print(f"❌ Failed to import fabric-cicd: {e}")
        return False
    
    print(f"🚀 Starting Basic Fabric deployment to {environment.upper()} environment")
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
            return True
        
        # Deploy individual item types
        success = True
        
        # Deploy lakehouses first (other items might depend on them)
        if not deploy_lakehouses(workspace_id, environment, credential):
            success = False
        
        # Deploy notebooks
        if not deploy_notebooks(workspace_id, environment, credential):
            success = False
        
        if success:
            print(f"✅ Basic deployment to {environment.upper()} completed successfully!")
        else:
            print(f"❌ Basic deployment to {environment.upper()} completed with errors!")
        
        return success
        
    except Exception as e:
        print(f"❌ Basic deployment failed: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Deploy Fabric items using basic individual deployment')
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
    success = deploy_fabric_items_basic(args.environment, args.dry_run)
    
    if not success:
        sys.exit(1)
    
    print("🎉 Deployment completed!")

if __name__ == '__main__':
    main()