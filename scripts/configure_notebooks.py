#!/usr/bin/env python3
"""
Fabric Cost Analysis Notebook Configuration Script
Configures notebooks with environment-specific values for deployment.
"""

import json
import os
import argparse
import yaml
import sys
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
    """Get environment-specific variables from environment variables"""
    env_vars = {
        'dev': {
            'storage_account': os.environ.get('DEV_STORAGE_ACCOUNT', ''),
            'workspace_id': os.environ.get('DEV_WORKSPACE_ID', ''),
            'container_name': os.environ.get('DEV_CONTAINER_NAME', 'msexports'),
            'workspace_name': os.environ.get('DEV_WORKSPACE_NAME', 'Finops Dev')
        },
        'test': {
            'storage_account': os.environ.get('TEST_STORAGE_ACCOUNT', ''),
            'workspace_id': os.environ.get('TEST_WORKSPACE_ID', ''),
            'container_name': os.environ.get('TEST_CONTAINER_NAME', 'msexports'),
            'workspace_name': os.environ.get('TEST_WORKSPACE_NAME', 'Finops Test')
        },
        'prod': {
            'storage_account': os.environ.get('PROD_STORAGE_ACCOUNT', ''),
            'workspace_id': os.environ.get('PROD_WORKSPACE_ID', ''),
            'container_name': os.environ.get('PROD_CONTAINER_NAME', 'msexports'),
            'workspace_name': os.environ.get('PROD_WORKSPACE_NAME', 'Finops Prod')
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
                'PLACEHOLDER_CONTAINER_NAME': environment_config.get('container_name', 'msexports'),
                'PLACEHOLDER_WORKSPACE_NAME': environment_config.get('workspace_name', ''),
                'PLACEHOLDER_SUBSCRIPTION_ID': environment_config.get('subscription_id', '')
            }
            
            for placeholder, value in replacements.items():
                if placeholder in source:
                    source = source.replace(placeholder, value)
                    print(f"  ✓ Replaced {placeholder} with {value}")
            
            # Convert back to list format for notebook
            cell['source'] = source.split('\n') if source else []
    
    # Write updated notebook
    try:
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Updated notebook for environment: {notebook_path}")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to write updated notebook {notebook_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Configure Fabric notebooks for specific environment')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment (dev, test, prod)')
    parser.add_argument('--artifact-path', required=True,
                       help='Path to the build artifacts containing notebooks')
    parser.add_argument('--config-file', 
                       help='Path to environment configuration file')
    
    args = parser.parse_args()
    
    print(f"🔧 Configuring notebooks for {args.environment.upper()} environment")
    print("=" * 60)
    
    # Get environment configuration
    env_vars = get_environment_variables(args.environment)
    
    # Load additional config from file if provided
    if args.config_file and os.path.exists(args.config_file):
        config = load_environment_config(args.config_file)
        env_config = config.get('environments', {}).get(args.environment, {})
        # Merge with environment variables (env vars take precedence)
        env_config.update({k: v for k, v in env_vars.items() if v})
    else:
        env_config = env_vars
    
    # Validate required configuration
    required_fields = ['storage_account', 'workspace_id', 'workspace_name']
    missing_fields = [field for field in required_fields if not env_config.get(field)]
    
    if missing_fields:
        print(f"ERROR: Missing required configuration fields: {missing_fields}")
        sys.exit(1)
    
    print(f"Configuration for {args.environment}:")
    for key, value in env_config.items():
        if key == 'workspace_id':
            print(f"  {key}: {value[:8]}...{value[-4:]}" if value else f"  {key}: <missing>")
        else:
            print(f"  {key}: {value}")
    
    # Find and process all notebooks
    notebooks_dir = os.path.join(args.artifact_path, 'notebooks')
    if not os.path.exists(notebooks_dir):
        notebooks_dir = args.artifact_path
    
    success_count = 0
    total_count = 0
    
    for root, dirs, files in os.walk(notebooks_dir):
        for file in files:
            if file.endswith('.ipynb'):
                notebook_path = os.path.join(root, file)
                total_count += 1
                
                print(f"\nProcessing notebook: {file}")
                if update_notebook_for_environment(notebook_path, env_config):
                    success_count += 1
                else:
                    print(f"✗ Failed to update {file}")
    
    print(f"\n📊 Configuration Summary:")
    print(f"  Total notebooks processed: {total_count}")
    print(f"  Successfully configured: {success_count}")
    print(f"  Failed: {total_count - success_count}")
    
    if success_count == total_count and total_count > 0:
        print("✅ All notebooks configured successfully!")
        sys.exit(0)
    else:
        print("❌ Some notebooks failed to configure")
        sys.exit(1)


if __name__ == "__main__":
    main()