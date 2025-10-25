#!/usr/bin/env python3
"""
Generic Microsoft Fabric Health Monitor
Comprehensive health checking for any Fabric workspace deployment.
Monitors performance, availability, and operational health.
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


def check_workspace_health(workspace_id, headers):
    """Check overall workspace health and accessibility"""
    print("  🏥 Checking workspace health...")
    
    try:
        start_time = time.time()
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        response_time = time.time() - start_time
        
        if response.status_code != 200:
            print(f"    ❌ Workspace inaccessible: HTTP {response.status_code}")
            return False
        
        workspace_info = response.json()
        workspace_name = workspace_info.get('displayName', 'Unknown')
        workspace_type = workspace_info.get('type', 'Unknown')
        
        print(f"    ✅ Workspace accessible: {workspace_name}")
        print(f"    📊 Workspace type: {workspace_type}")
        print(f"    ⚡ Response time: {response_time:.2f}s")
        
        return response_time < 10  # 10 second threshold
    
    except Exception as e:
        print(f"    ❌ Workspace health check failed: {e}")
        return False


def check_items_inventory_health(workspace_id, headers):
    """Check health of workspace items inventory"""
    print("  📦 Checking items inventory health...")
    
    try:
        start_time = time.time()
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        response_time = time.time() - start_time
        
        if response.status_code != 200:
            print(f"    ❌ Items inventory check failed: HTTP {response.status_code}")
            return False
        
        items = response.json().get('value', [])
        
        # Analyze item distribution
        item_types = {}
        for item in items:
            item_type = item.get('type', 'Unknown')
            item_types[item_type] = item_types.get(item_type, 0) + 1
        
        print(f"    📊 Total items: {len(items)}")
        print(f"    ⚡ Inventory response time: {response_time:.2f}s")
        
        for item_type, count in sorted(item_types.items()):
            print(f"      - {item_type}: {count}")
        
        # Health indicators
        if len(items) == 0:
            print(f"    ⚠️  Empty workspace - no items deployed")
            return False
        elif response_time > 15:
            print(f"    ⚠️  Slow inventory response ({response_time:.2f}s)")
            return False
        else:
            print(f"    ✅ Items inventory healthy")
            return True
    
    except Exception as e:
        print(f"    ❌ Items inventory health check failed: {e}")
        return False


def check_individual_item_health(workspace_id, headers):
    """Check health of individual items"""
    print("  🔍 Checking individual item health...")
    
    try:
        # Get all items
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"    ❌ Cannot access items for health check")
            return False
        
        items = response.json().get('value', [])
        
        if not items:
            print(f"    ⚠️  No items to check")
            return True
        
        healthy_items = 0
        slow_items = 0
        error_items = 0
        
        # Sample up to 10 items for detailed health check
        sample_items = items[:10]
        
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
                        print(f"    ✅ {item_type} '{item_name}': Healthy ({response_time:.2f}s)")
                        healthy_items += 1
                    else:
                        print(f"    ⚠️  {item_type} '{item_name}': Slow ({response_time:.2f}s)")
                        slow_items += 1
                else:
                    print(f"    ❌ {item_type} '{item_name}': Error (HTTP {item_response.status_code})")
                    error_items += 1
            
            except requests.RequestException:
                print(f"    ❌ {item_type} '{item_name}': Timeout/Error")
                error_items += 1
        
        total_checked = len(sample_items)
        health_percentage = (healthy_items / total_checked * 100) if total_checked > 0 else 0
        
        print(f"    📊 Health summary ({total_checked} items checked):")
        print(f"      Healthy: {healthy_items}")
        print(f"      Slow: {slow_items}")  
        print(f"      Errors: {error_items}")
        print(f"      Health rate: {health_percentage:.1f}%")
        
        return health_percentage >= 70  # 70% health threshold
    
    except Exception as e:
        print(f"    ❌ Individual item health check failed: {e}")
        return False


def check_api_performance_baseline(workspace_id, headers):
    """Check API performance baseline"""
    print("  ⚡ Checking API performance baseline...")
    
    performance_tests = [
        ('Workspace Info', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}', 5.0),
        ('Items List', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items', 10.0),
        ('Notebooks Filter', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Notebook', 8.0),
        ('Lakehouses Filter', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Lakehouse', 8.0)
    ]
    
    performance_results = []
    
    for test_name, url, threshold in performance_tests:
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=30)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                if response_time <= threshold:
                    print(f"    ✅ {test_name}: {response_time:.2f}s (good)")
                    performance_results.append(True)
                elif response_time <= threshold * 2:
                    print(f"    ⚠️  {test_name}: {response_time:.2f}s (acceptable)")
                    performance_results.append(True)
                else:
                    print(f"    ❌ {test_name}: {response_time:.2f}s (slow)")
                    performance_results.append(False)
            else:
                print(f"    ❌ {test_name}: HTTP {response.status_code}")
                performance_results.append(False)
                
        except requests.RequestException as e:
            print(f"    ❌ {test_name}: Failed ({str(e)[:30]}...)")
            performance_results.append(False)
    
    performance_score = sum(performance_results) / len(performance_results) * 100
    print(f"    📊 Performance score: {performance_score:.1f}%")
    
    return performance_score >= 75  # 75% performance threshold


def check_deployment_consistency(workspace_id, headers, config_file_path):
    """Check deployment consistency against configuration"""
    print("  🔄 Checking deployment consistency...")
    
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
            
            # Calculate consistency score
            matching_types = len(expected_types_set & actual_types)
            consistency_score = (matching_types / len(expected_types_set) * 100) if expected_types_set else 100
        
        print(f"    📊 Configuration consistency: {consistency_score:.1f}%")
        
        return consistency_score >= 80  # 80% consistency threshold
    
    except Exception as e:
        print(f"    ❌ Deployment consistency check failed: {e}")
        return False


def check_security_and_access_patterns(workspace_id, headers):
    """Check basic security and access patterns"""
    print("  🔒 Checking security and access patterns...")
    
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
        
        workspace_info = response.json()
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
            
            # Check for proper item naming (no obvious dev/test patterns in prod)
            suspicious_items = []
            for item in items:
                item_name = item.get('displayName', '').upper()
                if any(pattern in item_name for pattern in ['TEST', 'DEBUG', 'TEMP', 'DRAFT']):
                    suspicious_items.append(item.get('displayName'))
            
            if suspicious_items:
                print(f"    ⚠️  Items with suspicious naming: {len(suspicious_items)}")
                for name in suspicious_items[:3]:  # Show first 3
                    print(f"      - {name}")
            else:
                print(f"    ✅ Item naming follows conventions")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Security check failed: {e}")
        return False


def generate_health_summary(workspace_id, headers, environment, config_file_path):
    """Generate comprehensive health summary"""
    print("  📋 Generating health summary...")
    
    try:
        # Collect workspace info
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
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'environment': environment.upper(),
            'workspace': {
                'id': workspace_id,
                'name': workspace_info.get('displayName', 'Unknown'),
                'type': workspace_info.get('type', 'Unknown')
            },
            'inventory': {
                'total_items': len(items),
                'item_types': item_counts
            }
        }
        
        print(f"    📊 Health Summary:")
        print(f"      Environment: {summary['environment']}")
        print(f"      Workspace: {summary['workspace']['name']}")
        print(f"      Total Items: {summary['inventory']['total_items']}")
        print(f"      Item Breakdown:")
        for item_type, count in item_counts.items():
            print(f"        - {item_type}: {count}")
        print(f"      Health Check Time: {summary['timestamp']}")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Health summary generation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Run comprehensive Fabric health check')
    parser.add_argument('--environment', required=True, choices=['dev', 'test', 'prod'],
                       help='Target environment')
    parser.add_argument('--config', default='fabric-config.yml',
                       help='Configuration file path (default: fabric-config.yml)')
    
    args = parser.parse_args()
    
    print(f"🏥 Running Fabric Health Check for {args.environment.upper()} environment")
    print("=" * 70)
    
    # Load configuration
    config_file_path = Path(args.config)
    if not config_file_path.exists():
        print(f"❌ Configuration file not found: {config_file_path}")
        sys.exit(1)
    
    workspace_id = load_workspace_config(args.environment, config_file_path)
    
    if not workspace_id:
        print(f"❌ Workspace ID not configured for {args.environment} environment")
        sys.exit(1)
    
    print(f"📍 Target workspace: {workspace_id[:8]}...{workspace_id[-4:]}")
    
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
    
    # Run health check suite
    health_results = []
    
    print(f"\n🏥 Running comprehensive health check suite...")
    print("-" * 60)
    
    # Health Check 1: Workspace Health
    print(f"1️⃣  Workspace health check")
    result1 = check_workspace_health(workspace_id, headers)
    health_results.append(result1)
    
    # Health Check 2: Items Inventory Health
    print(f"\n2️⃣  Items inventory health check")
    result2 = check_items_inventory_health(workspace_id, headers)
    health_results.append(result2)
    
    # Health Check 3: Individual Item Health
    print(f"\n3️⃣  Individual item health check")
    result3 = check_individual_item_health(workspace_id, headers)
    health_results.append(result3)
    
    # Health Check 4: API Performance Baseline
    print(f"\n4️⃣  API performance baseline check")
    result4 = check_api_performance_baseline(workspace_id, headers)
    health_results.append(result4)
    
    # Health Check 5: Deployment Consistency
    print(f"\n5️⃣  Deployment consistency check")
    result5 = check_deployment_consistency(workspace_id, headers, config_file_path)
    health_results.append(result5)
    
    # Health Check 6: Security and Access Patterns
    print(f"\n6️⃣  Security and access patterns check")
    result6 = check_security_and_access_patterns(workspace_id, headers)
    health_results.append(result6)
    
    # Health Check 7: Health Summary Generation
    print(f"\n7️⃣  Health summary generation")
    result7 = generate_health_summary(workspace_id, headers, args.environment, config_file_path)
    health_results.append(result7)
    
    # Final health assessment
    passed_checks = sum(health_results)
    total_checks = len(health_results)
    health_score = (passed_checks / total_checks) * 100
    
    print(f"\n🏥 Health Check Results")
    print("=" * 40)
    print(f"Environment: {args.environment.upper()}")
    print(f"Health checks passed: {passed_checks}/{total_checks}")
    print(f"Health score: {health_score:.1f}%")
    print(f"Assessment time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Determine health status
    if health_score >= 90:
        status = "EXCELLENT"
        emoji = "🎉"
        exit_code = 0
    elif health_score >= 80:
        status = "GOOD"
        emoji = "✅"
        exit_code = 0
    elif health_score >= 70:
        status = "ACCEPTABLE"
        emoji = "⚠️"
        exit_code = 0
    else:
        status = "POOR"
        emoji = "❌"
        exit_code = 1
    
    print(f"\n{emoji} HEALTH STATUS: {status} ({health_score:.1f}%)")
    
    if exit_code == 0:
        print(f"🎯 {args.environment.upper()} environment is healthy and operational")
    else:
        print(f"🛑 {args.environment.upper()} environment needs attention")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()