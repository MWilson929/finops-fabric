#!/usr/bin/env python3
"""
Generic Microsoft Fabric Deployment Validator
Validates successful deployment of Fabric items to any workspace.
Works with any Fabric item types and deployment patterns.
"""

import requests
import os
import sys
import argparse
import subprocess
import time
import json
import yaml
from datetime import datetime
from pathlib import Path


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


def load_workspace_config(environment, config_file_path):
    """Load workspace configuration from fabric-config.yml"""
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        workspace_id_ref = config.get('core', {}).get('workspace_id', {}).get(environment.upper())
        
        if workspace_id_ref and workspace_id_ref.startswith('$ENV:'):
            env_var = workspace_id_ref[5:]  # Remove '$ENV:' prefix
            workspace_id = os.environ.get(env_var)
            return workspace_id
        
        return workspace_id_ref
    
    except Exception as e:
        print(f"❌ Error loading workspace config: {e}")
        return None


def get_expected_item_types(config_file_path):
    """Get expected item types from configuration"""
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return config.get('core', {}).get('item_types_in_scope', [])
    
    except Exception:
        return ['Notebook', 'Lakehouse']  # Default types


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
            return True, workspace_info
        elif response.status_code == 404:
            print(f"  ❌ Workspace not found: {workspace_id}")
            return False, None
        else:
            print(f"  ❌ Workspace access failed: HTTP {response.status_code}")
            return False, None
    
    except requests.RequestException as e:
        print(f"  ❌ Workspace validation error: {e}")
        return False, None


def validate_deployed_items(workspace_id, headers, expected_types, environment):
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
        
        # Validate expected types are present
        validation_results = []
        
        for expected_type in expected_types:
            count = item_counts.get(expected_type, 0)
            if count > 0:
                print(f"  ✅ {expected_type}: {count} items found")
                validation_results.append(True)
            else:
                print(f"  ⚠️  {expected_type}: No items found")
                validation_results.append(False)
        
        # Check for proper naming conventions (environment-specific items)
        if environment != 'prod':
            env_items = [item for item in items if environment.upper() in item.get('displayName', '')]
            if env_items:
                print(f"  ✅ Environment-specific items: {len(env_items)} items with {environment.upper()} naming")
            else:
                print(f"  ⚠️  No environment-specific naming found for {environment}")
        
        return len(items) > 0 and any(validation_results)
    
    except requests.RequestException as e:
        print(f"  ❌ Error validating deployed items: {e}")
        return False


def validate_item_health(workspace_id, headers):
    """Validate health of deployed items"""
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            return False
        
        items = response.json().get('value', [])
        
        print(f"  🔍 Checking item health...")
        
        healthy_count = 0
        total_count = len(items)
        
        for item in items:
            item_id = item.get('id')
            item_name = item.get('displayName', 'Unknown')
            item_type = item.get('type', 'Unknown')
            
            # Basic health check - item details accessible
            try:
                def_response = requests.get(
                    f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{item_id}',
                    headers=headers,
                    timeout=15
                )
                
                if def_response.status_code == 200:
                    print(f"    ✅ {item_type} '{item_name}': Healthy")
                    healthy_count += 1
                else:
                    print(f"    ⚠️  {item_type} '{item_name}': Health check failed (HTTP {def_response.status_code})")
            
            except requests.RequestException:
                print(f"    ⚠️  {item_type} '{item_name}': Health check timeout")
        
        health_percentage = (healthy_count / total_count * 100) if total_count > 0 else 0
        print(f"  📊 Healthy items: {healthy_count}/{total_count} ({health_percentage:.1f}%)")
        
        return health_percentage >= 75  # 75% health threshold
    
    except Exception as e:
        print(f"  ❌ Error during health validation: {e}")
        return False


def validate_api_connectivity(workspace_id, headers):
    """Validate Fabric API connectivity and performance"""
    print(f"  🔗 Testing API connectivity and performance...")
    
    api_tests = [
        ('Fabric API Root', 'https://api.fabric.microsoft.com/v1/workspaces', 5.0),
        ('Workspace Access', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}', 5.0),
        ('Items Listing', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items', 10.0)
    ]
    
    all_passed = True
    
    for test_name, url, timeout_threshold in api_tests:
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=30)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                if response_time <= timeout_threshold:
                    print(f"    ✅ {test_name}: {response_time:.2f}s (OK)")
                else:
                    print(f"    ⚠️  {test_name}: {response_time:.2f}s (slow)")
            else:
                print(f"    ❌ {test_name}: HTTP {response.status_code}")
                all_passed = False
        
        except requests.RequestException as e:
            print(f"    ❌ {test_name}: Failed ({str(e)[:50]}...)")
            all_passed = False
    
    return all_passed


def run_deployment_smoke_test(workspace_id, headers, expected_types):
    """Run comprehensive deployment smoke test"""
    print(f"  🔬 Running deployment smoke test...")
    
    try:
        # Get all workspace items
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"    ❌ Cannot access workspace items")
            return False
        
        items = response.json().get('value', [])
        
        # Test 1: Item count validation
        if len(items) > 0:
            print(f"    ✅ Items present: {len(items)} items deployed")
        else:
            print(f"    ❌ No items found in workspace")
            return False
        
        # Test 2: Expected types present
        found_types = set(item.get('type') for item in items)
        expected_types_set = set(expected_types)
        
        if expected_types_set.issubset(found_types):
            print(f"    ✅ Expected types present: {', '.join(expected_types)}")
        else:
            missing_types = expected_types_set - found_types
            print(f"    ⚠️  Missing expected types: {', '.join(missing_types)}")
        
        # Test 3: Item accessibility
        accessible_items = 0
        for item in items[:5]:  # Test first 5 items
            item_id = item.get('id')
            try:
                item_response = requests.get(
                    f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{item_id}',
                    headers=headers,
                    timeout=10
                )
                if item_response.status_code == 200:
                    accessible_items += 1
            except:
                pass
        
        accessibility_rate = accessible_items / min(len(items), 5)
        if accessibility_rate >= 0.8:
            print(f"    ✅ Item accessibility: {accessible_items}/5 test items accessible")
        else:
            print(f"    ⚠️  Item accessibility: Only {accessible_items}/5 test items accessible")
        
        return len(items) > 0 and len(found_types & expected_types_set) > 0
    
    except Exception as e:
        print(f"    ❌ Smoke test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Validate generic Fabric deployment')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment')
    parser.add_argument('--config', default='fabric-config.yml',
                       help='Configuration file path (default: fabric-config.yml)')
    
    args = parser.parse_args()
    
    print(f"🔍 Validating Fabric deployment to {args.environment.upper()} environment")
    print("=" * 65)
    
    # Load configuration
    config_file_path = Path(args.config)
    if not config_file_path.exists():
        print(f"❌ Configuration file not found: {config_file_path}")
        sys.exit(1)
    
    workspace_id = load_workspace_config(args.environment, config_file_path)
    expected_types = get_expected_item_types(config_file_path)
    
    if not workspace_id:
        print(f"❌ Workspace ID not configured for {args.environment} environment")
        sys.exit(1)
    
    print(f"📍 Target workspace: {workspace_id[:8]}...{workspace_id[-4:]}")
    print(f"📋 Expected item types: {', '.join(expected_types)}")
    
    # Get authentication token
    print(f"\n🔐 Obtaining Fabric authentication token...")
    token = get_fabric_token()
    
    if not token:
        print(f"❌ Failed to obtain authentication token")
        sys.exit(1)
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print(f"✅ Authentication successful")
    
    # Run validation tests
    validation_results = []
    
    print(f"\n🧪 Running validation test suite...")
    print("-" * 50)
    
    # Test 1: Workspace accessibility
    print(f"1️⃣  Workspace accessibility test")
    result1, workspace_info = validate_workspace_access(workspace_id, headers)
    validation_results.append(result1)
    
    workspace_name = workspace_info.get('displayName', 'Unknown') if workspace_info else 'Unknown'
    
    # Test 2: Deployed items validation
    print(f"\n2️⃣  Deployed items validation")
    result2 = validate_deployed_items(workspace_id, headers, expected_types, args.environment)
    validation_results.append(result2)
    
    # Test 3: Item health validation
    print(f"\n3️⃣  Item health validation")
    result3 = validate_item_health(workspace_id, headers)
    validation_results.append(result3)
    
    # Test 4: API connectivity validation
    print(f"\n4️⃣  API connectivity validation")
    result4 = validate_api_connectivity(workspace_id, headers)
    validation_results.append(result4)
    
    # Test 5: Deployment smoke test
    print(f"\n5️⃣  Deployment smoke test")
    result5 = run_deployment_smoke_test(workspace_id, headers, expected_types)
    validation_results.append(result5)
    
    # Results summary
    passed_tests = sum(validation_results)
    total_tests = len(validation_results)
    success_rate = (passed_tests / total_tests) * 100
    
    print(f"\n📊 Validation Results")
    print("=" * 35)
    print(f"Environment: {args.environment.upper()}")
    print(f"Workspace: {workspace_name}")
    print(f"Tests passed: {passed_tests}/{total_tests}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Validation time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success_rate >= 80:  # 80% success rate required
        print(f"\n✅ DEPLOYMENT VALIDATION PASSED!")
        print(f"🎉 {args.environment.upper()} environment is ready for use")
        sys.exit(0)
    else:
        print(f"\n❌ DEPLOYMENT VALIDATION FAILED")
        print(f"⚠️  Success rate {success_rate:.1f}% below threshold (80%)")
        print(f"🛑 {args.environment.upper()} deployment may have issues")
        sys.exit(1)


if __name__ == "__main__":
    main()