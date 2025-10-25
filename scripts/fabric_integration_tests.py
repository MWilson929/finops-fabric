#!/usr/bin/env python3
"""
Generic Fabric Integration Test Runner
Runs focused integration tests after any Fabric deployment.
Lightweight, fast, and suitable for CI/CD pipelines.
"""

import requests
import os
import sys
import argparse
import subprocess
import time
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
        
        return result.stdout.strip() if result.returncode == 0 else None
    except:
        return None


def load_workspace_config(environment, config_file_path):
    """Load workspace configuration from fabric-config.yml"""
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        workspace_id_ref = config.get('core', {}).get('workspace_id', {}).get(environment.upper())
        
        if workspace_id_ref and workspace_id_ref.startswith('$ENV:'):
            env_var = workspace_id_ref[5:]
            workspace_id = os.environ.get(env_var)
            return workspace_id
        
        return workspace_id_ref
    except:
        return None


def get_expected_item_types(config_file_path):
    """Get expected item types from configuration"""
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return config.get('core', {}).get('item_types_in_scope', [])
    except:
        return ['Notebook', 'Lakehouse']


def test_workspace_connectivity(workspace_id, headers):
    """Test basic workspace connectivity"""
    print("  🔗 Testing workspace connectivity...")
    
    try:
        start_time = time.time()
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=15
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            workspace_info = response.json()
            workspace_name = workspace_info.get('displayName', 'Unknown')
            print(f"    ✅ Connected to workspace: {workspace_name} ({response_time:.2f}s)")
            return True
        else:
            print(f"    ❌ Connection failed: HTTP {response.status_code}")
            return False
    
    except Exception as e:
        print(f"    ❌ Connectivity test failed: {str(e)[:50]}...")
        return False


def test_items_deployment(workspace_id, headers, expected_types):
    """Test that expected items are deployed and accessible"""
    print("  📦 Testing items deployment...")
    
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=20
        )
        
        if response.status_code != 200:
            print(f"    ❌ Items listing failed: HTTP {response.status_code}")
            return False
        
        items = response.json().get('value', [])
        
        if not items:
            print(f"    ❌ No items found in workspace")
            return False
        
        # Count items by type
        item_counts = {}
        for item in items:
            item_type = item.get('type', 'Unknown')
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
        
        print(f"    📊 Found {len(items)} items:")
        for item_type, count in sorted(item_counts.items()):
            print(f"      - {item_type}: {count}")
        
        # Check expected types
        found_types = set(item_counts.keys())
        expected_types_set = set(expected_types)
        missing_types = expected_types_set - found_types
        
        if not missing_types:
            print(f"    ✅ All expected item types deployed")
            return True
        else:
            print(f"    ⚠️  Missing item types: {', '.join(missing_types)}")
            # Return true if at least one expected type is found
            return len(found_types & expected_types_set) > 0
    
    except Exception as e:
        print(f"    ❌ Items deployment test failed: {e}")
        return False


def test_item_accessibility(workspace_id, headers):
    """Test accessibility of deployed items"""
    print("  🔍 Testing item accessibility...")
    
    try:
        # Get items list
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=20
        )
        
        if response.status_code != 200:
            print(f"    ❌ Cannot access items for testing")
            return False
        
        items = response.json().get('value', [])
        
        if not items:
            print(f"    ⚠️  No items to test accessibility")
            return True
        
        # Test accessibility of first few items
        test_count = min(3, len(items))
        accessible_count = 0
        
        for i in range(test_count):
            item = items[i]
            item_id = item.get('id')
            item_name = item.get('displayName', 'Unknown')
            item_type = item.get('type', 'Unknown')
            
            try:
                item_response = requests.get(
                    f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{item_id}',
                    headers=headers,
                    timeout=10
                )
                
                if item_response.status_code == 200:
                    print(f"    ✅ {item_type} '{item_name}': Accessible")
                    accessible_count += 1
                else:
                    print(f"    ❌ {item_type} '{item_name}': Not accessible (HTTP {item_response.status_code})")
            
            except:
                print(f"    ❌ {item_type} '{item_name}': Access timeout")
        
        accessibility_rate = accessible_count / test_count
        print(f"    📊 Accessibility rate: {accessible_count}/{test_count} ({accessibility_rate*100:.0f}%)")
        
        return accessibility_rate >= 0.5  # At least 50% accessible
    
    except Exception as e:
        print(f"    ❌ Item accessibility test failed: {e}")
        return False


def test_api_performance(workspace_id, headers):
    """Test API performance with key operations"""
    print("  ⚡ Testing API performance...")
    
    performance_tests = [
        ('Workspace Access', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}'),
        ('Items Listing', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items')
    ]
    
    all_fast = True
    
    for test_name, url in performance_tests:
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=20)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                if response_time <= 10:  # 10 second threshold
                    print(f"    ✅ {test_name}: {response_time:.2f}s (good)")
                elif response_time <= 20:
                    print(f"    ⚠️  {test_name}: {response_time:.2f}s (acceptable)")
                else:
                    print(f"    ❌ {test_name}: {response_time:.2f}s (slow)")
                    all_fast = False
            else:
                print(f"    ❌ {test_name}: HTTP {response.status_code}")
                all_fast = False
        
        except Exception as e:
            print(f"    ❌ {test_name}: Failed")
            all_fast = False
    
    return all_fast


def test_deployment_smoke_test(workspace_id, headers, expected_types, environment):
    """Run quick smoke test of deployment"""
    print("  🔬 Running deployment smoke test...")
    
    try:
        # Basic workspace + items test
        workspace_response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=15
        )
        
        items_response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=20
        )
        
        if workspace_response.status_code != 200:
            print(f"    ❌ Workspace not accessible")
            return False
        
        if items_response.status_code != 200:
            print(f"    ❌ Items not accessible")
            return False
        
        workspace_info = workspace_response.json()
        items = items_response.json().get('value', [])
        
        # Basic validations
        print(f"    ✅ Workspace: {workspace_info.get('displayName', 'Unknown')}")
        print(f"    ✅ Items count: {len(items)}")
        
        if len(items) == 0:
            print(f"    ❌ No items deployed")
            return False
        
        # Check for expected item types
        found_types = set(item.get('type') for item in items)
        expected_set = set(expected_types)
        
        if found_types & expected_set:
            print(f"    ✅ Expected item types present: {', '.join(found_types & expected_set)}")
        else:
            print(f"    ⚠️  No expected item types found")
        
        print(f"    ✅ Smoke test passed")
        return True
    
    except Exception as e:
        print(f"    ❌ Smoke test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Run Fabric integration tests')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment')
    parser.add_argument('--config', default='fabric-config.yml',
                       help='Configuration file path (default: fabric-config.yml)')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick tests only (faster for CI/CD)')
    
    args = parser.parse_args()
    
    test_mode = "QUICK" if args.quick else "COMPREHENSIVE"
    
    print(f"🧪 Running {test_mode} Integration Tests for {args.environment.upper()}")
    print("=" * 70)
    
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
    print(f"📋 Expected types: {', '.join(expected_types)}")
    
    # Get authentication token
    print(f"\n🔐 Obtaining authentication token...")
    token = get_fabric_token()
    
    if not token:
        print(f"❌ Failed to obtain authentication token")
        sys.exit(1)
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print(f"✅ Authentication successful")
    
    # Run integration tests
    test_results = []
    
    print(f"\n🧪 Running integration test suite...")
    print("-" * 50)
    
    # Test 1: Workspace connectivity (always run)
    print(f"1️⃣  Workspace connectivity test")
    result1 = test_workspace_connectivity(workspace_id, headers)
    test_results.append(result1)
    
    # Test 2: Items deployment (always run)
    print(f"\n2️⃣  Items deployment test")
    result2 = test_items_deployment(workspace_id, headers, expected_types)
    test_results.append(result2)
    
    # Test 3: Deployment smoke test (always run)
    print(f"\n3️⃣  Deployment smoke test")
    result3 = test_deployment_smoke_test(workspace_id, headers, expected_types, args.environment)
    test_results.append(result3)
    
    # Additional tests for comprehensive mode
    if not args.quick:
        # Test 4: Item accessibility
        print(f"\n4️⃣  Item accessibility test")
        result4 = test_item_accessibility(workspace_id, headers)
        test_results.append(result4)
        
        # Test 5: API performance
        print(f"\n5️⃣  API performance test")
        result5 = test_api_performance(workspace_id, headers)
        test_results.append(result5)
    
    # Results summary
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    success_rate = (passed_tests / total_tests) * 100
    
    print(f"\n📊 Integration Test Results")
    print("=" * 40)
    print(f"Mode: {test_mode}")
    print(f"Environment: {args.environment.upper()}")
    print(f"Tests passed: {passed_tests}/{total_tests}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Completion time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Determine success threshold based on mode
    threshold = 100 if args.quick else 80  # Quick mode requires all tests to pass
    
    if success_rate >= threshold:
        print(f"\n✅ INTEGRATION TESTS PASSED!")
        print(f"🎉 {args.environment.upper()} deployment is ready for use")
        sys.exit(0)
    else:
        print(f"\n❌ INTEGRATION TESTS FAILED")
        print(f"⚠️  Success rate {success_rate:.1f}% below threshold ({threshold}%)")
        print(f"🛑 {args.environment.upper()} deployment needs attention")
        sys.exit(1)


if __name__ == "__main__":
    main()