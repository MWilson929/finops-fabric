#!/usr/bin/env python3
"""
Microsoft Fabric Testing Suite
Comprehensive testing framework for Fabric deployments.
Supports multiple testing modes: validation, health, integration.
"""

import requests
import os
import sys
import argparse
import subprocess
import time
import json
import yaml
from datetime import datetime, timedelta
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


def test_workspace_access(workspace_id, headers):
    """Test workspace accessibility and get info"""
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            workspace_info = response.json()
            print(f"    ✅ Workspace accessible: {workspace_info.get('displayName', 'Unknown')}")
            return True, workspace_info
        else:
            print(f"    ❌ Workspace access failed: HTTP {response.status_code}")
            return False, None
    except Exception as e:
        print(f"    ❌ Workspace access error: {e}")
        return False, None


def test_items_deployment(workspace_id, headers, expected_types, environment):
    """Test deployed items validation"""
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"    ❌ Failed to list workspace items: HTTP {response.status_code}")
            return False
        
        items = response.json().get('value', [])
        
        # Count items by type
        item_counts = {}
        for item in items:
            item_type = item.get('type', 'Unknown')
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
        
        print(f"    📊 Deployed items summary:")
        for item_type, count in sorted(item_counts.items()):
            print(f"      {item_type}: {count}")
        
        # Validate expected types
        found_types = set(item_counts.keys())
        expected_types_set = set(expected_types)
        missing_types = expected_types_set - found_types
        
        if not missing_types:
            print(f"    ✅ All expected item types deployed: {', '.join(expected_types)}")
        else:
            print(f"    ⚠️  Missing item types: {', '.join(missing_types)}")
        
        return len(items) > 0 and len(found_types & expected_types_set) > 0
    
    except Exception as e:
        print(f"    ❌ Items deployment test failed: {e}")
        return False


def test_item_health(workspace_id, headers, mode='basic'):
    """Test health of individual items"""
    try:
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            return False
        
        items = response.json().get('value', [])
        
        if not items:
            print(f"    ⚠️  No items to test")
            return True
        
        healthy_count = 0
        total_count = len(items)
        
        # Test sample of items based on mode
        if mode == 'quick':
            sample_items = items[:3]  # Test first 3 items
        elif mode == 'comprehensive':
            sample_items = items[:10]  # Test up to 10 items
        else:
            sample_items = items[:5]  # Default: test first 5 items
        
        print(f"    🔍 Testing health of {len(sample_items)} items...")
        
        for item in sample_items:
            item_id = item.get('id')
            item_name = item.get('displayName', 'Unknown')
            item_type = item.get('type', 'Unknown')
            
            try:
                start_time = time.time()
                item_response = requests.get(
                    f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{item_id}',
                    headers=headers,
                    timeout=15
                )
                response_time = time.time() - start_time
                
                if item_response.status_code == 200:
                    if response_time < 5:
                        print(f"      ✅ {item_type} '{item_name}': Healthy ({response_time:.2f}s)")
                    else:
                        print(f"      ⚠️  {item_type} '{item_name}': Slow ({response_time:.2f}s)")
                    healthy_count += 1
                else:
                    print(f"      ❌ {item_type} '{item_name}': Error (HTTP {item_response.status_code})")
            
            except:
                print(f"      ❌ {item_type} '{item_name}': Timeout/Error")
        
        health_percentage = (healthy_count / len(sample_items) * 100) if sample_items else 0
        print(f"    📊 Health rate: {healthy_count}/{len(sample_items)} ({health_percentage:.1f}%)")
        
        return health_percentage >= 75  # 75% health threshold
    
    except Exception as e:
        print(f"    ❌ Item health test failed: {e}")
        return False


def test_api_performance(workspace_id, headers):
    """Test API performance"""
    print(f"    ⚡ Testing API performance...")
    
    performance_tests = [
        ('Workspace Access', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}', 5.0),
        ('Items Listing', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items', 10.0),
        ('Notebooks Filter', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Notebook', 8.0)
    ]
    
    performance_results = []
    
    for test_name, url, threshold in performance_tests:
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=30)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                if response_time <= threshold:
                    print(f"      ✅ {test_name}: {response_time:.2f}s (good)")
                    performance_results.append(True)
                elif response_time <= threshold * 2:
                    print(f"      ⚠️  {test_name}: {response_time:.2f}s (acceptable)")
                    performance_results.append(True)
                else:
                    print(f"      ❌ {test_name}: {response_time:.2f}s (slow)")
                    performance_results.append(False)
            else:
                print(f"      ❌ {test_name}: HTTP {response.status_code}")
                performance_results.append(False)
        except:
            print(f"      ❌ {test_name}: Failed")
            performance_results.append(False)
    
    performance_score = sum(performance_results) / len(performance_results) * 100
    print(f"    📊 Performance score: {performance_score:.1f}%")
    
    return performance_score >= 75


def test_deployment_consistency(workspace_id, headers, config_file_path):
    """Test deployment consistency against configuration"""
    try:
        # Load expected configuration
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        expected_types = config.get('core', {}).get('item_types_in_scope', [])
        
        # Get actual items
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"    ❌ Cannot check deployment consistency")
            return False
        
        items = response.json().get('value', [])
        actual_types = set(item.get('type') for item in items)
        expected_types_set = set(expected_types)
        
        # Check type consistency
        missing_types = expected_types_set - actual_types
        unexpected_types = actual_types - expected_types_set
        
        if not missing_types and not unexpected_types:
            print(f"    ✅ Deployment matches configuration perfectly")
            consistency_score = 100
        else:
            if missing_types:
                print(f"    ⚠️  Missing expected types: {', '.join(missing_types)}")
            if unexpected_types:
                print(f"    ℹ️  Additional types found: {', '.join(unexpected_types)}")
            
            matching_types = len(expected_types_set & actual_types)
            consistency_score = (matching_types / len(expected_types_set) * 100) if expected_types_set else 100
        
        print(f"    📊 Configuration consistency: {consistency_score:.1f}%")
        
        return consistency_score >= 80
    
    except Exception as e:
        print(f"    ❌ Deployment consistency test failed: {e}")
        return False


def test_security_patterns(workspace_id, headers):
    """Test basic security and access patterns"""
    try:
        # Test workspace access level
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"    ❌ Cannot validate workspace access")
            return False
        
        print(f"    ✅ Workspace access validated")
        
        # Test items access
        items_response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if items_response.status_code == 200:
            items = items_response.json().get('value', [])
            print(f"    ✅ Items access validated ({len(items)} items)")
            
            # Check for proper item naming
            suspicious_items = []
            for item in items:
                item_name = item.get('displayName', '').upper()
                if any(pattern in item_name for pattern in ['TEST', 'DEBUG', 'TEMP', 'DRAFT']):
                    suspicious_items.append(item.get('displayName'))
            
            if suspicious_items and len(suspicious_items) > len(items) * 0.3:  # More than 30% suspicious
                print(f"    ⚠️  Many items with suspicious naming: {len(suspicious_items)}")
            elif suspicious_items:
                print(f"    ℹ️  Some items with development naming: {len(suspicious_items)}")
            else:
                print(f"    ✅ Item naming follows conventions")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Security patterns test failed: {e}")
        return False


def run_smoke_test(workspace_id, headers, expected_types, environment):
    """Run quick deployment smoke test"""
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
        workspace_name = workspace_info.get('displayName', 'Unknown')
        print(f"    ✅ Workspace: {workspace_name}")
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


def generate_health_summary(workspace_id, headers, environment, config_file_path):
    """Generate health summary"""
    try:
        workspace_response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        items_response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if workspace_response.status_code != 200 or items_response.status_code != 200:
            print(f"    ❌ Cannot generate health summary")
            return False
        
        workspace_info = workspace_response.json()
        items = items_response.json().get('value', [])
        
        # Generate summary
        item_counts = {}
        for item in items:
            item_type = item.get('type', 'Unknown')
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
        
        print(f"    📊 Health Summary:")
        print(f"      Environment: {environment.upper()}")
        print(f"      Workspace: {workspace_info.get('displayName', 'Unknown')}")
        print(f"      Total Items: {len(items)}")
        print(f"      Item Breakdown:")
        for item_type, count in item_counts.items():
            print(f"        - {item_type}: {count}")
        print(f"      Summary Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Health summary generation failed: {e}")
        return False


def run_validation_mode(workspace_id, headers, expected_types, environment, config_file_path):
    """Run validation mode tests"""
    print(f"🔍 Running VALIDATION mode tests...")
    print("-" * 50)
    
    test_results = []
    
    # Test 1: Workspace accessibility
    print(f"1️⃣  Workspace accessibility test")
    result1, workspace_info = test_workspace_access(workspace_id, headers)
    test_results.append(result1)
    
    # Test 2: Deployed items validation
    print(f"\n2️⃣  Deployed items validation")
    result2 = test_items_deployment(workspace_id, headers, expected_types, environment)
    test_results.append(result2)
    
    # Test 3: Item health validation
    print(f"\n3️⃣  Item health validation")
    result3 = test_item_health(workspace_id, headers, 'basic')
    test_results.append(result3)
    
    # Test 4: API performance test
    print(f"\n4️⃣  API performance validation")
    result4 = test_api_performance(workspace_id, headers)
    test_results.append(result4)
    
    # Test 5: Deployment smoke test
    print(f"\n5️⃣  Deployment smoke test")
    result5 = run_smoke_test(workspace_id, headers, expected_types, environment)
    test_results.append(result5)
    
    return test_results, workspace_info


def run_integration_mode(workspace_id, headers, expected_types, environment, quick_mode=False):
    """Run integration mode tests"""
    mode_label = "QUICK INTEGRATION" if quick_mode else "COMPREHENSIVE INTEGRATION"
    print(f"🧪 Running {mode_label} mode tests...")
    print("-" * 50)
    
    test_results = []
    
    # Test 1: Workspace connectivity (always run)
    print(f"1️⃣  Workspace connectivity test")
    result1, workspace_info = test_workspace_access(workspace_id, headers)
    test_results.append(result1)
    
    # Test 2: Items deployment (always run)
    print(f"\n2️⃣  Items deployment test")
    result2 = test_items_deployment(workspace_id, headers, expected_types, environment)
    test_results.append(result2)
    
    # Test 3: Deployment smoke test (always run)
    print(f"\n3️⃣  Deployment smoke test")
    result3 = run_smoke_test(workspace_id, headers, expected_types, environment)
    test_results.append(result3)
    
    if not quick_mode:
        # Test 4: Item accessibility (comprehensive only)
        print(f"\n4️⃣  Item accessibility test")
        result4 = test_item_health(workspace_id, headers, 'basic')
        test_results.append(result4)
        
        # Test 5: API performance (comprehensive only)
        print(f"\n5️⃣  API performance test")
        result5 = test_api_performance(workspace_id, headers)
        test_results.append(result5)
    
    return test_results, workspace_info


def run_health_mode(workspace_id, headers, expected_types, environment, config_file_path):
    """Run health monitoring mode tests"""
    print(f"🏥 Running HEALTH MONITORING mode tests...")
    print("-" * 50)
    
    test_results = []
    
    # Test 1: Workspace health
    print(f"1️⃣  Workspace health check")
    result1, workspace_info = test_workspace_access(workspace_id, headers)
    test_results.append(result1)
    
    # Test 2: Items inventory health
    print(f"\n2️⃣  Items inventory health")
    result2 = test_items_deployment(workspace_id, headers, expected_types, environment)
    test_results.append(result2)
    
    # Test 3: Individual item health
    print(f"\n3️⃣  Individual item health check")
    result3 = test_item_health(workspace_id, headers, 'comprehensive')
    test_results.append(result3)
    
    # Test 4: API performance baseline
    print(f"\n4️⃣  API performance baseline")
    result4 = test_api_performance(workspace_id, headers)
    test_results.append(result4)
    
    # Test 5: Deployment consistency
    print(f"\n5️⃣  Deployment consistency check")
    result5 = test_deployment_consistency(workspace_id, headers, config_file_path)
    test_results.append(result5)
    
    # Test 6: Security patterns
    print(f"\n6️⃣  Security and access patterns")
    result6 = test_security_patterns(workspace_id, headers)
    test_results.append(result6)
    
    # Test 7: Health summary
    print(f"\n7️⃣  Health summary generation")
    result7 = generate_health_summary(workspace_id, headers, environment, config_file_path)
    test_results.append(result7)
    
    return test_results, workspace_info


def main():
    parser = argparse.ArgumentParser(description='Fabric Testing Suite - Comprehensive testing framework')
    parser.add_argument('--mode', required=True, choices=['validation', 'integration', 'health'],
                       help='Testing mode: validation (deployment validation), integration (integration tests), health (health monitoring)')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment')
    parser.add_argument('--config', default='fabric-config.yml',
                       help='Configuration file path (default: fabric-config.yml)')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick tests only (for integration mode)')
    
    args = parser.parse_args()
    
    mode_names = {
        'validation': 'DEPLOYMENT VALIDATION',
        'integration': 'INTEGRATION TESTS',
        'health': 'HEALTH MONITORING'
    }
    
    print(f"🎯 Microsoft Fabric Testing Suite")
    print(f"📋 Mode: {mode_names[args.mode]} for {args.environment.upper()}")
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
    
    # Run tests based on mode
    print(f"\n")
    
    if args.mode == 'validation':
        test_results, workspace_info = run_validation_mode(workspace_id, headers, expected_types, args.environment, config_file_path)
    elif args.mode == 'integration':
        test_results, workspace_info = run_integration_mode(workspace_id, headers, expected_types, args.environment, args.quick)
    elif args.mode == 'health':
        test_results, workspace_info = run_health_mode(workspace_id, headers, expected_types, args.environment, config_file_path)
    
    # Results summary
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    success_rate = (passed_tests / total_tests) * 100
    
    workspace_name = workspace_info.get('displayName', 'Unknown') if workspace_info else 'Unknown'
    
    print(f"\n📊 Test Results Summary")
    print("=" * 40)
    print(f"Mode: {mode_names[args.mode]}")
    print(f"Environment: {args.environment.upper()}")
    print(f"Workspace: {workspace_name}")
    print(f"Tests passed: {passed_tests}/{total_tests}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Completion time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Determine success threshold based on mode
    if args.mode == 'integration' and args.quick:
        threshold = 100  # Quick integration requires all tests to pass
    elif args.mode == 'health':
        threshold = 85   # Health monitoring requires high threshold
    else:
        threshold = 80   # Standard threshold for validation and comprehensive integration
    
    # Final assessment
    if success_rate >= threshold:
        print(f"\n✅ {mode_names[args.mode]} PASSED!")
        print(f"🎉 {args.environment.upper()} environment is operational")
        sys.exit(0)
    else:
        print(f"\n❌ {mode_names[args.mode]} FAILED")
        print(f"⚠️  Success rate {success_rate:.1f}% below threshold ({threshold}%)")
        print(f"🛑 {args.environment.upper()} environment needs attention")
        sys.exit(1)


if __name__ == "__main__":
    main()