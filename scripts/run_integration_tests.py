#!/usr/bin/env python3
"""
Fabric Cost Analysis Integration Tests
Runs comprehensive integration tests after deployment.
"""

import requests
import os
import sys
import argparse
import subprocess
import time
import json
from datetime import datetime, timedelta


def get_fabric_token():
    """Get access token for Fabric API"""
    try:
        result = subprocess.run([
            'az', 'account', 'get-access-token', 
            '--resource', 'https://analysis.windows.net/powerbi/api',
            '--query', 'accessToken', '-o', 'tsv'
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return None
        
        return result.stdout.strip()
    except:
        return None


def get_environment_config(environment):
    """Get environment-specific configuration"""
    config = {
        'dev': {
            'workspace_id': os.environ.get('DEV_WORKSPACE_ID'),
            'workspace_name': os.environ.get('DEV_WORKSPACE_NAME', 'Finops Dev')
        },
        'test': {
            'workspace_id': os.environ.get('TEST_WORKSPACE_ID'),
            'workspace_name': os.environ.get('TEST_WORKSPACE_NAME', 'Finops Test')
        },
        'prod': {
            'workspace_id': os.environ.get('PROD_WORKSPACE_ID'),
            'workspace_name': os.environ.get('PROD_WORKSPACE_NAME', 'Finops Prod')
        }
    }
    
    return config.get(environment, {})


def test_lakehouse_connectivity(workspace_id, headers):
    """Test lakehouse connectivity and basic operations"""
    print("  🏠 Testing lakehouse connectivity...")
    
    try:
        # Get all lakehouses in workspace
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Lakehouse',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Failed to list lakehouses")
            return False
        
        lakehouses = response.json().get('value', [])
        
        if not lakehouses:
            print("    ⚠️  No lakehouses found")
            return False
        
        fca_lakehouse = None
        for lakehouse in lakehouses:
            if 'FCA' in lakehouse.get('displayName', ''):
                fca_lakehouse = lakehouse
                break
        
        if not fca_lakehouse:
            print("    ❌ FCA lakehouse not found")
            return False
        
        lakehouse_id = fca_lakehouse.get('id')
        lakehouse_name = fca_lakehouse.get('displayName')
        
        print(f"    ✅ Found FCA lakehouse: {lakehouse_name}")
        
        # Test lakehouse properties access
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/lakehouses/{lakehouse_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            print("    ✅ Lakehouse properties accessible")
            return True
        else:
            print(f"    ❌ Lakehouse properties access failed: HTTP {response.status_code}")
            return False
    
    except Exception as e:
        print(f"    ❌ Lakehouse connectivity test failed: {e}")
        return False


def test_notebook_execution_readiness(workspace_id, headers, environment):
    """Test that notebooks are ready for execution"""
    print("  📚 Testing notebook execution readiness...")
    
    try:
        # Get notebooks
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Notebook',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Failed to list notebooks")
            return False
        
        notebooks = response.json().get('value', [])
        
        if not notebooks:
            print("    ❌ No notebooks found")
            return False
        
        # Test key notebooks
        key_notebooks = ['Deploy_FCA', 'Cost_Data_Ingestion']
        if environment != 'prod':
            key_notebooks = [f"{nb}_{environment.upper()}" for nb in key_notebooks]
        
        found_notebooks = []
        for notebook in notebooks:
            notebook_name = notebook.get('displayName', '')
            if any(key in notebook_name for key in key_notebooks):
                found_notebooks.append(notebook_name)
        
        print(f"    📊 Key notebooks found: {len(found_notebooks)}")
        for notebook in found_notebooks:
            print(f"      - {notebook}")
        
        if len(found_notebooks) >= len(key_notebooks) / 2:  # At least half found
            print("    ✅ Sufficient notebooks for testing")
            return True
        else:
            print("    ❌ Insufficient key notebooks found")
            return False
    
    except Exception as e:
        print(f"    ❌ Notebook readiness test failed: {e}")
        return False


def test_data_pipeline_components(workspace_id, headers):
    """Test data pipeline components"""
    print("  🔄 Testing data pipeline components...")
    
    try:
        # Get all items to check for pipeline components
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Failed to list workspace items")
            return False
        
        items = response.json().get('value', [])
        
        # Check for essential components
        component_counts = {
            'Lakehouse': 0,
            'Notebook': 0,
            'SemanticModel': 0,
            'Report': 0
        }
        
        for item in items:
            item_type = item.get('type')
            if item_type in component_counts:
                component_counts[item_type] += 1
        
        print("    📊 Component inventory:")
        all_components_present = True
        
        for component, count in component_counts.items():
            if component == 'Lakehouse' and count >= 1:
                print(f"      ✅ {component}: {count}")
            elif component == 'Notebook' and count >= 2:
                print(f"      ✅ {component}: {count}")
            elif component in ['SemanticModel', 'Report'] and count >= 0:
                print(f"      ✅ {component}: {count}")
            else:
                print(f"      ⚠️  {component}: {count} (may be insufficient)")
        
        # Minimum viable pipeline check
        has_lakehouse = component_counts['Lakehouse'] >= 1
        has_notebooks = component_counts['Notebook'] >= 1
        
        if has_lakehouse and has_notebooks:
            print("    ✅ Essential pipeline components present")
            return True
        else:
            print("    ❌ Missing essential pipeline components")
            return False
    
    except Exception as e:
        print(f"    ❌ Pipeline components test failed: {e}")
        return False


def test_workspace_permissions(workspace_id, headers):
    """Test workspace permissions and access levels"""
    print("  🔐 Testing workspace permissions...")
    
    try:
        # Test workspace details access
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Workspace access denied")
            return False
        
        workspace_info = response.json()
        workspace_name = workspace_info.get('displayName', 'Unknown')
        
        print(f"    ✅ Workspace access: {workspace_name}")
        
        # Test items listing (requires read permissions)
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            items_count = len(response.json().get('value', []))
            print(f"    ✅ Items listing: {items_count} items accessible")
        else:
            print(f"    ⚠️  Items listing: Limited access (HTTP {response.status_code})")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Permissions test failed: {e}")
        return False


def test_api_performance(workspace_id, headers):
    """Test API performance and response times"""
    print("  ⚡ Testing API performance...")
    
    try:
        # Test workspace API response time
        start_time = time.time()
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200 and response_time < 10:
            print(f"    ✅ Workspace API response: {response_time:.2f}s")
        else:
            print(f"    ⚠️  Workspace API response: {response_time:.2f}s (slow)")
        
        # Test items listing response time
        start_time = time.time()
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200 and response_time < 15:
            print(f"    ✅ Items API response: {response_time:.2f}s")
            return True
        else:
            print(f"    ⚠️  Items API response: {response_time:.2f}s (slow)")
            return response.status_code == 200
    
    except Exception as e:
        print(f"    ❌ Performance test failed: {e}")
        return False


def run_end_to_end_smoke_test(workspace_id, headers, environment):
    """Run end-to-end smoke test"""
    print("  🔬 Running end-to-end smoke test...")
    
    try:
        # Simulate a basic cost analysis workflow
        print("    1. Checking workspace readiness...")
        
        # Get workspace items
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Workspace not ready")
            return False
        
        items = response.json().get('value', [])
        lakehouses = [item for item in items if item.get('type') == 'Lakehouse']
        notebooks = [item for item in items if item.get('type') == 'Notebook']
        
        print(f"    2. Validating components ({len(lakehouses)} lakehouses, {len(notebooks)} notebooks)...")
        
        if not lakehouses:
            print("    ❌ No lakehouses found for data storage")
            return False
        
        if not notebooks:
            print("    ❌ No notebooks found for data processing")
            return False
        
        print("    3. Checking deployment naming conventions...")
        
        # Check naming conventions
        expected_suffix = "" if environment == "prod" else f"_{environment.upper()}"
        properly_named_items = 0
        
        for item in items:
            item_name = item.get('displayName', '')
            if environment == 'prod':
                properly_named_items += 1
            elif item_name.endswith(expected_suffix):
                properly_named_items += 1
        
        if properly_named_items >= len(items) * 0.8:  # 80% properly named
            print(f"    ✅ Naming conventions: {properly_named_items}/{len(items)} items properly named")
        else:
            print(f"    ⚠️  Naming conventions: Only {properly_named_items}/{len(items)} items properly named")
        
        print("    4. Smoke test completed successfully")
        return True
    
    except Exception as e:
        print(f"    ❌ Smoke test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Run integration tests for Fabric deployment')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment (dev, test, prod)')
    
    args = parser.parse_args()
    
    print(f"🧪 Running integration tests for {args.environment.upper()} environment")
    print("=" * 70)
    
    # Get environment configuration
    env_config = get_environment_config(args.environment)
    workspace_id = env_config.get('workspace_id')
    workspace_name = env_config.get('workspace_name')
    
    if not workspace_id:
        print(f"❌ Workspace ID not configured for {args.environment} environment")
        sys.exit(1)
    
    print(f"📍 Target workspace: {workspace_name} ({workspace_id[:8]}...{workspace_id[-4:]})")
    
    # Get authentication token
    print(f"🔐 Obtaining authentication token...")
    token = get_fabric_token()
    
    if not token:
        print(f"❌ Failed to obtain authentication token")
        sys.exit(1)
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # Run integration tests
    test_results = []
    
    print(f"\n🧪 Running integration test suite...")
    print("-" * 50)
    
    # Test 1: Lakehouse connectivity
    print(f"1️⃣  Lakehouse connectivity test")
    result1 = test_lakehouse_connectivity(workspace_id, headers)
    test_results.append(result1)
    
    # Test 2: Notebook readiness
    print(f"\n2️⃣  Notebook execution readiness test")
    result2 = test_notebook_execution_readiness(workspace_id, headers, args.environment)
    test_results.append(result2)
    
    # Test 3: Data pipeline components
    print(f"\n3️⃣  Data pipeline components test")
    result3 = test_data_pipeline_components(workspace_id, headers)
    test_results.append(result3)
    
    # Test 4: Workspace permissions
    print(f"\n4️⃣  Workspace permissions test")
    result4 = test_workspace_permissions(workspace_id, headers)
    test_results.append(result4)
    
    # Test 5: API performance
    print(f"\n5️⃣  API performance test")
    result5 = test_api_performance(workspace_id, headers)
    test_results.append(result5)
    
    # Test 6: End-to-end smoke test
    print(f"\n6️⃣  End-to-end smoke test")
    result6 = run_end_to_end_smoke_test(workspace_id, headers, args.environment)
    test_results.append(result6)
    
    # Results summary
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    success_rate = (passed_tests / total_tests) * 100
    
    print(f"\n📊 Integration Test Results")
    print("=" * 40)
    print(f"Environment: {args.environment.upper()}")
    print(f"Workspace: {workspace_name}")
    print(f"Tests passed: {passed_tests}/{total_tests}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Test completion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success_rate >= 80:  # 80% pass rate required
        print(f"✅ Integration tests passed!")
        print(f"🎉 {args.environment.upper()} environment is ready for cost analysis workloads")
        sys.exit(0)
    else:
        print(f"❌ Integration tests failed (success rate: {success_rate:.1f}%)")
        print(f"⚠️  {args.environment.upper()} environment may not be ready for production use")
        sys.exit(1)


if __name__ == "__main__":
    main()