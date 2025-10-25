#!/usr/bin/env python3
"""
Fabric Cost Analysis Notebook Configuration Script (Improved Debug Version)
Configures notebooks with environment-specific values for deployment.
"""

import json
import os
import argparse
import yaml
import sys
import traceback
from pathlib import Path


def load_environment_config(config_file_path):
    """Load environment configuration from YAML file"""
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load environment configuration: {e}")
        sys.exit(1)


def get_environment_variables(environment):
    """Get environment-specific variables from Azure DevOps environment variables"""
    # Map environment names to mapped environment variables from ADO pipeline
    env_vars = {
        'dev': {
            'storage_account': os.environ.get('DEV_STORAGE_ACCOUNT', ''),
            'workspace_id': os.environ.get('DEV_WORKSPACE_ID', ''),
            'container_name': os.environ.get('DEV_CONTAINER_NAME', 'costexport'),
            'workspace_name': os.environ.get('DEV_WORKSPACE_NAME', 'Finops Dev'),
            'subscription_id': os.environ.get('DEV_SUBSCRIPTION_ID', '')
        },
        'test': {
            'storage_account': os.environ.get('TEST_STORAGE_ACCOUNT', ''),
            'workspace_id': os.environ.get('TEST_WORKSPACE_ID', ''),
            'container_name': os.environ.get('TEST_CONTAINER_NAME', 'costexport'),
            'workspace_name': os.environ.get('TEST_WORKSPACE_NAME', 'Finops Test'),
            'subscription_id': os.environ.get('TEST_SUBSCRIPTION_ID', '')
        },
        'prod': {
            'storage_account': os.environ.get('PROD_STORAGE_ACCOUNT', ''),
            'workspace_id': os.environ.get('PROD_WORKSPACE_ID', ''),
            'container_name': os.environ.get('PROD_CONTAINER_NAME', 'costexport'),
            'workspace_name': os.environ.get('PROD_WORKSPACE_NAME', 'Finops Prod'),
            'subscription_id': os.environ.get('PROD_SUBSCRIPTION_ID', '')
        }
    }
    
    return env_vars.get(environment, {})


def update_notebook_for_environment(notebook_path, environment_config):
    """Update notebook with environment-specific configurations"""
    
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to read notebook {notebook_path}: {e}")
        return False
    
    # Update cells with environment-specific values
    updates_made = 0
    for cell in notebook.get('cells', []):
        if cell.get('cell_type') == 'code':
            source_lines = cell.get('source', [])
            
            # Convert source to string for processing
            if isinstance(source_lines, list):
                source = ''.join(source_lines)
            else:
                source = str(source_lines)
            
            # Replace placeholders with environment values
            replacements = {
                'PLACEHOLDER_STORAGE_ACCOUNT': environment_config.get('storage_account', ''),
                'PLACEHOLDER_WORKSPACE_ID': environment_config.get('workspace_id', ''),
                'PLACEHOLDER_CONTAINER_NAME': environment_config.get('container_name', 'costexport'),
                'PLACEHOLDER_WORKSPACE_NAME': environment_config.get('workspace_name', ''),
                'PLACEHOLDER_SUBSCRIPTION_ID': environment_config.get('subscription_id', '')
            }
            
            original_source = source
            for placeholder, value in replacements.items():
                if placeholder in source:
                    source = source.replace(placeholder, value)
                    print(f"    ✓ Replaced {placeholder}")
                    updates_made += 1
            
            # Convert back to list format for notebook
            if source != original_source:
                if isinstance(source_lines, list):
                    # Split back into lines maintaining original format
                    cell['source'] = source.split('\n')
                    # Fix line endings
                    for i in range(len(cell['source']) - 1):
                        if not cell['source'][i].endswith('\n'):
                            cell['source'][i] += '\n'
                else:
                    cell['source'] = source
    
    # Save updated notebook
    try:
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=2, ensure_ascii=False)
        print(f"    📝 {updates_made} replacements made, notebook saved")
        return True
    except Exception as e:
        print(f"ERROR: Failed to save notebook {notebook_path}: {e}")
        return False


def main():
    try:
        print("🚀 Starting Fabric Notebook Configuration Script")
        print(f"🐍 Python version: {sys.version}")
        print(f"📂 Current working directory: {os.getcwd()}")
        
        parser = argparse.ArgumentParser(description='Configure notebooks for Fabric deployment')
        parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                            help='Target environment (dev/test/prod)')
        parser.add_argument('--artifact-path', required=True,
                            help='Path to deployment artifacts')
        parser.add_argument('--config-file', default='config/environments.yaml',
                            help='Path to environment configuration file')
        
        args = parser.parse_args()
        
        print(f"\n🔧 Configuration:")
        print(f"   Environment: {args.environment}")
        print(f"   Artifact path: {args.artifact_path}")
        print(f"   Config file: {args.config_file}")
        
        # Debug: Check if artifact path exists
        if not os.path.exists(args.artifact_path):
            print(f"\n❌ ERROR: Artifact path does not exist: {args.artifact_path}")
            print(f"📂 Available items in current directory:")
            try:
                for item in os.listdir('.'):
                    item_type = "📁" if os.path.isdir(item) else "📄"
                    print(f"   {item_type} {item}")
            except Exception as e:
                print(f"   Error listing directory: {e}")
            sys.exit(1)
        
        # Get environment variables
        print(f"\n🔍 Reading environment variables for '{args.environment}'...")
        env_vars = get_environment_variables(args.environment)
        
        # Debug: Print what we found
        print(f"📋 Environment variables:")
        for key, value in env_vars.items():
            if value:
                # Mask sensitive values
                if key in ['storage_account', 'workspace_id', 'subscription_id'] and len(value) > 8:
                    masked_value = value[:4] + "..." + value[-4:]
                else:
                    masked_value = value
                print(f"   ✅ {key}: {masked_value}")
            else:
                print(f"   ❌ {key}: <empty or missing>")
        
        # Load additional config from file if provided
        config_path = os.path.join(args.artifact_path, args.config_file)
        env_config = {}
        
        if os.path.exists(config_path):
            print(f"\n📋 Loading configuration from: {config_path}")
            try:
                config = load_environment_config(config_path)
                env_config = config.get('environments', {}).get(args.environment, {})
                print(f"   ✅ Loaded YAML configuration")
            except Exception as e:
                print(f"   ⚠️  Failed to load YAML config: {e}")
        else:
            print(f"\n⚠️  Config file not found: {config_path}")
        
        # Merge configurations (env vars take precedence)
        env_config.update({k: v for k, v in env_vars.items() if v})
        
        # Validate required configuration
        required_fields = ['storage_account', 'workspace_id', 'workspace_name']
        missing_fields = [field for field in required_fields if not env_config.get(field)]
        
        if missing_fields:
            print(f"\n❌ ERROR: Missing required configuration:")
            for field in missing_fields:
                expected_env_var = f"{args.environment.upper()}_{field.upper()}"
                print(f"   - {field} (expected env var: {expected_env_var})")
            
            print(f"\n💡 Troubleshooting:")
            print(f"   1. Check Azure DevOps variable groups are created")
            print(f"   2. Verify pipeline maps variables correctly:")
            print(f"      env:")
            for field in required_fields:
                env_var = f"{args.environment.upper()}_{field.upper().replace('-', '_')}"
                ado_var = f"{args.environment}-{field.replace('_', '-')}"
                print(f"        {env_var}: $({ado_var})")
            sys.exit(1)
        
        print(f"\n✅ Final configuration for '{args.environment}':")
        for key, value in env_config.items():
            if key in ['workspace_id', 'storage_account', 'subscription_id'] and value and len(value) > 8:
                print(f"   {key}: {value[:4]}...{value[-4:]}")
            else:
                print(f"   {key}: {value}")
        
        # Find notebooks
        notebooks_dir = os.path.join(args.artifact_path, 'notebooks')
        if not os.path.exists(notebooks_dir):
            print(f"\n⚠️  Notebooks directory not found: {notebooks_dir}")
            print(f"🔍 Searching entire artifact path: {args.artifact_path}")
            notebooks_dir = args.artifact_path
        
        print(f"\n📂 Searching for notebooks in: {notebooks_dir}")
        
        # Process notebooks
        success_count = 0
        total_count = 0
        
        for root, dirs, files in os.walk(notebooks_dir):
            for file in files:
                if file.endswith('.ipynb'):
                    notebook_path = os.path.join(root, file)
                    total_count += 1
                    
                    print(f"\n📓 Processing: {file}")
                    print(f"   Path: {notebook_path}")
                    
                    if update_notebook_for_environment(notebook_path, env_config):
                        success_count += 1
                    else:
                        print(f"   ❌ Failed to process {file}")
        
        # Summary
        print(f"\n📊 SUMMARY:")
        print(f"   📁 Directory searched: {notebooks_dir}")
        print(f"   📓 Notebooks found: {total_count}")
        print(f"   ✅ Successfully processed: {success_count}")
        print(f"   ❌ Failed: {total_count - success_count}")
        
        if total_count == 0:
            print(f"\n⚠️  No notebooks found - this might be expected if:")
            print(f"   - You haven't added notebooks to the repository yet")
            print(f"   - Notebooks are in a different location")
            print(f"   - This is just the configuration validation step")
            print(f"\n✅ Configuration script completed successfully (no notebooks to process)")
            sys.exit(0)
        elif success_count == total_count:
            print(f"\n🎉 All notebooks configured successfully!")
            sys.exit(0)
        else:
            print(f"\n💥 Some notebooks failed - check errors above")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n💥 FATAL ERROR: {e}")
        print(f"\n🔍 Full traceback:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()