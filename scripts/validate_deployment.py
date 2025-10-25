#!/usr/bin/env python3
"""
Fabric Cost Analysis Deployment Validation Script
Validates successful deployment to Microsoft Fabric workspace.
"""

import requests
import os
import sys
import argparse
import subprocess
import time
import json
from datetime import datetime


def get_fabric_token():
    """Get access token for Fabric API"""
    try:
        result = subprocess.run([
            'az', 'account', 'get-access-token', 
            '--resource', 'https://analysis.windows.net/powerbi/api',
            '--query', 'accessToken', '-o', 'tsv'
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"❌ Failed to get access token: {result.stderr}")
            return None
        
        return result.stdout.strip()
    
    except Exception as e:
        print(f"❌ Error getting access token: {e}")
        return None


def get_environment_config(environment):
    """Get environment-specific configuration"""
    config = {
        'dev': {
            'workspace_id': os.environ.get('DEV_WORKSPACE_ID'),
            'workspace_name': os.environ.get('DEV_WORKSPACE_NAME', 'FCA-Development'),
            'storage_account': os.environ.get('DEV_STORAGE_ACCOUNT')
        },
        'test': {
            'workspace_id': os.environ.get('TEST_WORKSPACE_ID'),
            'workspace_name': os.environ.get('TEST_WORKSPACE_NAME', 'FCA-Test'),
            'storage_account': os.environ.get('TEST_STORAGE_ACCOUNT')
        },
        'prod': {
            'workspace_id': os.environ.get('PROD_WORKSPACE_ID'),
            'workspace_name': os.environ.get('PROD_WORKSPACE_NAME', 'FCA-Production'),
            'storage_account': os.environ.get('PROD_STORAGE_ACCOUNT')
        }
    }
    
    return config.get(environment, {})


def validate_workspace_access(workspace_id, headers):
    """Validate that workspace exists and is accessible"""
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            workspace_info = response.json()
            print(f"  ✅ Workspace accessible: {workspace_info.get('displayName', 'Unknown')}")
            return True
        elif response.status_code == 404:
            print(f"  ❌ Workspace not found: {workspace_id}")
            return False
        else:
            print(f"  ❌ Workspace access failed: HTTP {response.status_code}")
            return False
    
    except requests.RequestException as e:
        print(f"  ❌ Workspace validation error: {e}")
        return False


def validate_deployed_items(workspace_id, headers, environment):
    """Validate that expected items are deployed to workspace"""
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  ❌ Failed to list workspace items: HTTP {response.status_code}")
            return False
        
        items = response.json().get('value', [])
        
        # Count items by type
        item_counts = {}
        for item in items:
            item_type = item.get('type', 'Unknown')
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
        
        print(f"  📊 Deployed items summary:")
        for item_type, count in item_counts.items():
            print(f"    {item_type}: {count}")
        
        # Check for expected notebooks
        notebooks = [item for item in items if item.get('type') == 'Notebook']
        expected_notebooks = ['00_Deploy_FCA', 'Cost_Data_Ingestion', 'FCA_Data_Processing']
        
        if environment != 'prod':
            env_suffix = f"_{environment.upper()}"
            expected_notebooks = [f"{nb}{env_suffix}" for nb in expected_notebooks]
        
        found_notebooks = [item.get('displayName', '') for item in notebooks]
        
        print(f"  📚 Expected notebooks: {len(expected_notebooks)}")
        print(f"  📚 Found notebooks: {len(notebooks)}")
        
        missing_notebooks = [nb for nb in expected_notebooks if nb not in found_notebooks]
        if missing_notebooks:
            print(f"  ⚠️  Missing notebooks: {missing_notebooks}")
        else:
            print(f"  ✅ All expected notebooks found")
        
        # Check for lakehouses
        lakehouses = [item for item in items if item.get('type') == 'Lakehouse']
        if lakehouses:
            print(f"  🏠 Lakehouses found: {len(lakehouses)}")
            for lakehouse in lakehouses:
                print(f"    - {lakehouse.get('displayName', 'Unknown')}")
        else:
            print(f"  ⚠️  No lakehouses found")
        
        return len(notebooks) > 0
    
    except requests.RequestException as e:
        print(f"  ❌ Error validating deployed items: {e}")
        return False


def validate_item_health(workspace_id, headers):
    """Validate health of deployed items"""
    try:
        # Get workspace items
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            return False
        
        items = response.json().get('value', [])
        notebooks = [item for item in items if item.get('type') == 'Notebook']
        
        print(f"  🔍 Checking notebook health...")
        
        healthy_count = 0
        for notebook in notebooks:
            notebook_id = notebook.get('id')
            notebook_name = notebook.get('displayName', 'Unknown')
            
            # Check notebook definition (basic health check)
            try:
                def_response = requests.get(
                    f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{notebook_id}',
                    headers=headers,
                    timeout=15
                )
                
                if def_response.status_code == 200:
                    print(f"    ✅ {notebook_name}: Healthy")
                    healthy_count += 1
                else:
                    print(f"    ⚠️  {notebook_name}: Health check failed (HTTP {def_response.status_code})")
            
            except requests.RequestException:
                print(f"    ⚠️  {notebook_name}: Health check timeout")
        
        print(f"  📊 Healthy notebooks: {healthy_count}/{len(notebooks)}")
        return healthy_count == len(notebooks)
    
    except Exception as e:
        print(f"  ❌ Error during health validation: {e}")
        return False


def run_basic_connectivity_test(workspace_id, headers, environment_config):
    """Run basic connectivity tests"""
    print(f"  🔗 Running connectivity tests...")
    
    # Test Fabric API connectivity
    try:
        response = requests.get(
            'https://api.fabric.microsoft.com/v1/workspaces',
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            print(f"    ✅ Fabric API connectivity: OK")
        else:
            print(f"    ❌ Fabric API connectivity: Failed (HTTP {response.status_code})")
            return False
    
    except requests.RequestException as e:
        print(f"    ❌ Fabric API connectivity: Failed ({e})")
        return False
    
    # Test workspace-specific API access
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Notebook',
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            print(f"    ✅ Workspace API access: OK")
            return True
        else:
            print(f"    ❌ Workspace API access: Failed (HTTP {response.status_code})")
            return False
    
    except requests.RequestException as e:
        print(f"    ❌ Workspace API access: Failed ({e})")
        return False


def main():
    parser = argparse.ArgumentParser(description='Validate Fabric deployment')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment (dev, test, prod)')
    
    args = parser.parse_args()
    
    print(f"🔍 Validating deployment to {args.environment.upper()} environment")
    print("=" * 60)
    
    # Get environment configuration
    env_config = get_environment_config(args.environment)
    workspace_id = env_config.get('workspace_id')
    workspace_name = env_config.get('workspace_name')
    
    if not workspace_id:
        print(f"❌ Workspace ID not configured for {args.environment} environment")
        sys.exit(1)
    
    print(f"📍 Target workspace: {workspace_name} ({workspace_id[:8]}...{workspace_id[-4:]})")
    
    # Get authentication token
    print(f"🔐 Obtaining Fabric authentication token...")
    token = get_fabric_token()
    
    if not token:
        print(f"❌ Failed to obtain authentication token")
        sys.exit(1)
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print(f"✅ Authentication token obtained")
    
    # Run validation tests
    validation_results = []
    
    print(f"\n🧪 Running validation tests...")
    print("-" * 40)
    
    # Test 1: Workspace accessibility
    print(f"1️⃣  Workspace accessibility test")
    result1 = validate_workspace_access(workspace_id, headers)
    validation_results.append(result1)
    
    # Test 2: Deployed items validation
    print(f"\n2️⃣  Deployed items validation")
    result2 = validate_deployed_items(workspace_id, headers, args.environment)
    validation_results.append(result2)
    
    # Test 3: Item health validation
    print(f"\n3️⃣  Item health validation")
    result3 = validate_item_health(workspace_id, headers)
    validation_results.append(result3)
    
    # Test 4: Connectivity validation
    print(f"\n4️⃣  Connectivity validation")
    result4 = run_basic_connectivity_test(workspace_id, headers, env_config)
    validation_results.append(result4)
    
    # Summary
    passed_tests = sum(validation_results)
    total_tests = len(validation_results)
    
    print(f"\n📊 Validation Summary")
    print("=" * 30)
    print(f"Environment: {args.environment.upper()}")
    print(f"Workspace: {workspace_name}")
    print(f"Tests passed: {passed_tests}/{total_tests}")
    print(f"Validation time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if passed_tests == total_tests:
        print(f"✅ All validation tests passed!")
        print(f"🎉 {args.environment.upper()} deployment is healthy and ready for use")
        sys.exit(0)
    else:
        print(f"❌ {total_tests - passed_tests} validation test(s) failed")
        print(f"⚠️  {args.environment.upper()} deployment may have issues")
        sys.exit(1)


if __name__ == "__main__":
    main()