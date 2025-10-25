#!/usr/bin/env python3
"""
Microsoft Fabric CI/CD General Deployment Script
Uses the official fabric-cicd library for robust deployment across environments
"""

import os
import sys
import argparse
import yaml
from pathlib import Path

def install_fabric_cicd():
    """Install the fabric-cicd library if not already available"""
    try:
        import fabric_cicd
        print("✅ fabric-cicd library is available")
        return True
    except ImportError:
        print("📦 Installing fabric-cicd library...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "fabric-cicd"])
            print("✅ fabric-cicd library installed successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to install fabric-cicd library: {e}")
            return False

def validate_environment_variables(environment):
    """Validate required environment variables are present"""
    required_vars = {
        'dev': [
            'DEV_WORKSPACE_ID',
            'DEV_SUBSCRIPTION_ID'
        ],
        'test': [
            'TEST_WORKSPACE_ID', 
            'TEST_SUBSCRIPTION_ID'
        ],
        'prod': [
            'PROD_WORKSPACE_ID',
            'PROD_SUBSCRIPTION_ID'
        ]
    }
    
    # Authentication variables (recommended for CI/CD)
    auth_vars = [
        'AZURE_CLIENT_ID',
        'AZURE_CLIENT_SECRET', 
        'AZURE_TENANT_ID'
    ]
    
    missing_vars = []
    missing_auth_vars = []
    
    # Check environment-specific variables
    env_vars = required_vars.get(environment.lower(), [])
    for var in env_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    # Check authentication variables
    for var in auth_vars:
        if not os.environ.get(var):
            missing_auth_vars.append(var)
    
    # Report missing variables
    if missing_vars:
        print(f"❌ Missing required environment variables for {environment}:")
        for var in missing_vars:
            print(f"   - {var}")
        return False
    
    if missing_auth_vars:
        print(f"⚠️  Missing authentication variables (will use DefaultAzureCredential):")
        for var in missing_auth_vars:
            print(f"   - {var}")
        print("   💡 For CI/CD pipelines, it's recommended to set these variables")
    else:
        print("✅ All authentication variables present")
    
    print(f"✅ All required environment variables present for {environment}")
    return True

def load_workspace_config(environment, config_file_path):
    """Load workspace configuration for environment from config file"""
    try:
        with open(config_file_path, 'r') as f:
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
                    return workspace_ref
        
        # Try simple workspaces structure
        if 'workspaces' in config and environment in config['workspaces']:
            workspace_id = config['workspaces'][environment]
            print(f"   Found in workspaces: {workspace_id}")
            return workspace_id
        
        # Try alternative environments structure
        if 'environments' in config and environment in config['environments']:
            env_config = config['environments'][environment]
            if 'workspace_id' in env_config:
                workspace_id = env_config['workspace_id']
                print(f"   Found in environments: {workspace_id}")
                return workspace_id
        
        print(f"   ❌ Could not find workspace ID for {environment}")
        return None
        
    except Exception as e:
        print(f"❌ Failed to load workspace config: {e}")
        return None

def deploy_fabric_items(environment, config_file_path, dry_run=False):
    """Deploy Fabric items using configuration-based deployment"""
    
    # Import fabric-cicd after ensuring it's installed
    try:
        import fabric_cicd
        from fabric_cicd import deploy_with_config
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
    
    print(f"🚀 Starting Fabric deployment to {environment.upper()} environment")
    print("=" * 60)
    
    try:
        # Determine authentication method based on available environment variables
        client_id = os.environ.get('AZURE_CLIENT_ID')
        client_secret = os.environ.get('AZURE_CLIENT_SECRET')
        tenant_id = os.environ.get('AZURE_TENANT_ID')
        
        if client_id and client_secret and tenant_id:
            print("🔐 Using Service Principal authentication")
            print(f"   Client ID: {client_id[:8]}..." if len(client_id) > 8 else client_id)
            print(f"   Tenant ID: {tenant_id[:8]}..." if len(tenant_id) > 8 else tenant_id)
            
            # Validate tenant ID format (should be a GUID)
            import re
            guid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            if not re.match(guid_pattern, tenant_id, re.IGNORECASE):
                print(f"❌ Invalid tenant ID format: {tenant_id}")
                print("   Tenant ID must be a valid GUID (e.g., 12345678-1234-1234-1234-123456789abc)")
                print("   You can find your tenant ID here: https://learn.microsoft.com/partner-center/find-ids-and-domain-names")
                return False
            
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        else:
            print("🔐 Using DefaultAzureCredential (Managed Identity or other)")
            if not client_id:
                print("   Missing AZURE_CLIENT_ID environment variable")
            if not client_secret:
                print("   Missing AZURE_CLIENT_SECRET environment variable")
            if not tenant_id:
                print("   Missing AZURE_TENANT_ID environment variable")
            print("   Falling back to DefaultAzureCredential...")
            credential = DefaultAzureCredential()
        
        # Enable experimental features using proper fabric-cicd API
        try:
            from fabric_cicd import append_feature_flag
            append_feature_flag("enable_experimental_features")
            append_feature_flag("enable_config_deploy") 
            append_feature_flag("enable_lakehouse_unpublish")
            append_feature_flag("enable_warehouse_unpublish")
            append_feature_flag("enable_environment_variable_replacement")
            append_feature_flag("enable_exclude_folder")
            append_feature_flag("disable_print_identity")
            print("🧪 Feature flags configured using append_feature_flag:")
            print("   ✅ enable_experimental_features")
            print("   ✅ enable_config_deploy")
            print("   ✅ enable_lakehouse_unpublish") 
            print("   ✅ enable_warehouse_unpublish")
            print("   ✅ enable_environment_variable_replacement")
            print("   ✅ enable_exclude_folder")
            print("   ✅ disable_print_identity")
        except ImportError:
            print("❌ ERROR: append_feature_flag not available. Please update fabric-cicd library.")
            return False
        
        if dry_run:
            print("🔍 DRY RUN MODE - No actual deployment will occur")
            print(f"   Config file: {config_file_path}")
            print(f"   Environment: {environment}")
            return True
        
        # Try experimental config-based deployment first
        print(f"📦 Attempting experimental config-based deployment...")
        
        try:
            # Create a temporary config file with resolved workspace IDs
            import tempfile
            import shutil
            
            # Get workspace ID for current environment
            workspace_id = load_workspace_config(environment, config_file_path)
            if not workspace_id:
                print(f"❌ Could not resolve workspace ID for {environment}")
                raise Exception(f"Workspace ID not found for environment: {environment}")
            
            print(f"🔍 Searching for workspace ID for environment: {environment}")
            print(f"   Found workspace reference: $ENV:DEV_WORKSPACE_ID")
            
            # Load and modify config
            with open(config_file_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
            
            # Replace environment variable references with actual values
            config_content = config_content.replace('$ENV:DEV_WORKSPACE_ID', workspace_id)
            
            # Create temporary config file
            temp_config_fd, temp_config_path = tempfile.mkstemp(suffix='.yml', text=True)
            try:
                with os.fdopen(temp_config_fd, 'w', encoding='utf-8') as f:
                    f.write(config_content)
                
                print(f"📋 Created temporary config with resolved workspace IDs")
                
                # Deploy using configuration file (experimental)
                deploy_with_config(
                    config_file_path=temp_config_path,
                    environment=environment.upper(),
                    token_credential=credential
                )
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_config_path)
                    print(f"🧹 Cleaned up temporary config file")
                except:
                    pass
            
            print(f"✅ Config-based deployment to {environment.upper()} completed successfully!")
            return True
            
        except Exception as config_error:
            print(f"❌ Config-based deployment failed: {str(config_error)}")
            raise config_error
        
    except Exception as e:
        print(f"❌ Deployment failed: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        
        if "experimental" in str(e).lower():
            print("   💡 This is an experimental features issue. Try:")
            print("      - Upgrading fabric-cicd: pip install --upgrade fabric-cicd")
            print("      - Using alternative deployment method")
            print("      - Checking fabric-cicd documentation for latest config format")
        elif "tenant" in str(e).lower():
            print("   💡 This appears to be a tenant ID issue. Please check:")
            print("      - Ensure your tenant ID is correct in your variable group")
            print("      - Verify the tenant ID is in GUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)")
            print("      - Confirm your service principal exists in the correct tenant")
        
        return False

def main():
    parser = argparse.ArgumentParser(description='Deploy Fabric items using Microsoft fabric-cicd library')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment (dev, test, prod)')
    parser.add_argument('--config-file', 
                       default='fabric-config.yml',
                       help='Path to fabric configuration file (default: fabric-config.yml)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Validate configuration without deploying')
    parser.add_argument('--install-deps', action='store_true',
                       help='Install fabric-cicd library if missing')
    
    args = parser.parse_args()
    
    # Install dependencies if requested
    if args.install_deps:
        if not install_fabric_cicd():
            sys.exit(1)
    
    # Validate config file exists
    config_path = Path(args.config_file)
    if not config_path.exists():
        print(f"❌ Configuration file not found: {args.config_file}")
        sys.exit(1)
    
    # Validate environment variables
    if not validate_environment_variables(args.environment):
        sys.exit(1)
    
    # Display configuration summary
    print(f"📋 Deployment Configuration:")
    print(f"   Environment: {args.environment.upper()}")
    print(f"   Config File: {config_path.absolute()}")
    print(f"   Dry Run: {args.dry_run}")
    print()
    
    # Perform deployment
    success = deploy_fabric_items(
        environment=args.environment,
        config_file_path=str(config_path.absolute()),
        dry_run=args.dry_run
    )
    
    if success:
        print(f"🎉 Operation completed successfully!")
        sys.exit(0)
    else:
        print(f"💥 Operation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()