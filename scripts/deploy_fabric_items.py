#!/usr/bin/env python3
"""
Microsoft Fabric CI/CD General Deployment Script
Uses the official fabric-cicd library for robust deployment across environments
"""

import os
import sys
import argparse
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
    
    missing_vars = []
    env_vars = required_vars.get(environment.lower(), [])
    
    for var in env_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables for {environment}:")
        for var in missing_vars:
            print(f"   - {var}")
        return False
    
    print(f"✅ All required environment variables present for {environment}")
    return True

def deploy_fabric_items(environment, config_file_path, dry_run=False):
    """Deploy Fabric items using configuration-based deployment"""
    
    # Import fabric-cicd after ensuring it's installed
    try:
        from fabric_cicd import deploy_with_config
        from azure.identity import DefaultAzureCredential
    except ImportError as e:
        print(f"❌ Failed to import fabric-cicd: {e}")
        return False
    
    print(f"🚀 Starting Fabric deployment to {environment.upper()} environment")
    print("=" * 60)
    
    try:
        # Use DefaultAzureCredential for authentication
        credential = DefaultAzureCredential()
        
        if dry_run:
            print("🔍 DRY RUN MODE - No actual deployment will occur")
            print(f"   Config file: {config_file_path}")
            print(f"   Environment: {environment}")
            return True
        
        # Deploy using configuration file
        deploy_with_config(
            config_file_path=config_file_path,
            environment=environment.upper(),
            token_credential=credential
        )
        
        print(f"✅ Deployment to {environment.upper()} completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Deployment failed: {str(e)}")
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