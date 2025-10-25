#!/usr/bin/env python3
"""
Production Health Check for Fabric Cost Analysis
Performs comprehensive health checks for production deployment.
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
        
        return result.stdout.strip() if result.returncode == 0 else None
    except:
        return None


def get_environment_config(environment):
    """Get environment-specific configuration"""
    config = {
        'prod': {
            'workspace_id': os.environ.get('PROD_WORKSPACE_ID'),
            'workspace_name': os.environ.get('PROD_WORKSPACE_NAME', 'Finops Prod'),
            'storage_account': os.environ.get('PROD_STORAGE_ACCOUNT')
        }
    }
    
    return config.get(environment, {})


def check_production_readiness(workspace_id, headers):
    """Check production readiness indicators"""
    print("  🎯 Checking production readiness...")
    
    try:
        # Get workspace information
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Cannot access production workspace")
            return False
        
        workspace_info = response.json()
        print(f"    ✅ Production workspace: {workspace_info.get('displayName')}")
        
        # Get all items
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Cannot list production items")
            return False
        
        items = response.json().get('value', [])
        
        # Check for required production components
        required_components = {
            'Lakehouse': {'count': 0, 'required': 1, 'names': []},
            'Notebook': {'count': 0, 'required': 3, 'names': []},
            'SemanticModel': {'count': 0, 'required': 1, 'names': []},
            'Report': {'count': 0, 'required': 1, 'names': []}
        }
        
        for item in items:
            item_type = item.get('type')
            item_name = item.get('displayName', 'Unknown')
            
            if item_type in required_components:
                required_components[item_type]['count'] += 1
                required_components[item_type]['names'].append(item_name)
        
        print("    📊 Production component inventory:")
        all_requirements_met = True
        
        for component, info in required_components.items():
            count = info['count']
            required = info['required']
            
            if count >= required:
                print(f"      ✅ {component}: {count}/{required} (sufficient)")
            else:
                print(f"      ❌ {component}: {count}/{required} (insufficient)")
                all_requirements_met = False
        
        return all_requirements_met
    
    except Exception as e:
        print(f"    ❌ Production readiness check failed: {e}")
        return False


def check_security_configuration(workspace_id, headers):
    """Check security configuration for production"""
    print("  🔒 Checking security configuration...")
    
    try:
        # Basic security checks
        
        # 1. Check workspace access
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Workspace access validation failed")
            return False
        
        print("    ✅ Workspace access validated")
        
        # 2. Check for proper item naming (no dev/test suffixes)
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            items = response.json().get('value', [])
            dev_test_items = []
            
            for item in items:
                item_name = item.get('displayName', '')
                if any(suffix in item_name.upper() for suffix in ['_DEV', '_TEST', '_STAGING']):
                    dev_test_items.append(item_name)
            
            if dev_test_items:
                print(f"    ⚠️  Found items with dev/test naming: {dev_test_items}")
                print("    ⚠️  Consider renaming for production clarity")
            else:
                print("    ✅ Item naming follows production conventions")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Security configuration check failed: {e}")
        return False


def check_data_pipeline_health(workspace_id, headers):
    """Check data pipeline health and configuration"""
    print("  🔄 Checking data pipeline health...")
    
    try:
        # Get lakehouses
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Lakehouse',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            print("    ❌ Cannot access lakehouses")
            return False
        
        lakehouses = response.json().get('value', [])
        
        if not lakehouses:
            print("    ❌ No lakehouses found")
            return False
        
        # Check primary lakehouse
        fca_lakehouse = None
        for lakehouse in lakehouses:
            if 'FCA' in lakehouse.get('displayName', '').upper():
                fca_lakehouse = lakehouse
                break
        
        if not fca_lakehouse:
            print("    ❌ FCA lakehouse not found")
            return False
        
        lakehouse_id = fca_lakehouse.get('id')
        lakehouse_name = fca_lakehouse.get('displayName')
        
        print(f"    ✅ Primary lakehouse found: {lakehouse_name}")
        
        # Test lakehouse accessibility
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/lakehouses/{lakehouse_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            print("    ✅ Lakehouse is accessible")
        else:
            print(f"    ⚠️  Lakehouse access issue: HTTP {response.status_code}")
        
        # Check notebooks
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Notebook',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            notebooks = response.json().get('value', [])
            print(f"    ✅ Found {len(notebooks)} notebooks")
            
            # Check for key notebooks
            key_notebooks = ['Deploy_FCA', 'Cost_Data_Ingestion', 'Init_FCA_Lakehouse_Tables']
            found_key_notebooks = []
            
            for notebook in notebooks:
                notebook_name = notebook.get('displayName', '')
                for key in key_notebooks:
                    if key in notebook_name:
                        found_key_notebooks.append(notebook_name)
                        break
            
            if len(found_key_notebooks) >= 2:
                print(f"    ✅ Essential notebooks present: {len(found_key_notebooks)}")
            else:
                print(f"    ⚠️  Missing essential notebooks: {found_key_notebooks}")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Data pipeline health check failed: {e}")
        return False


def check_performance_baseline(workspace_id, headers):
    """Check performance baseline for production workloads"""
    print("  ⚡ Checking performance baseline...")
    
    try:
        # Test API response times
        api_tests = [
            ('Workspace Info', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}'),
            ('Items List', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items'),
            ('Lakehouses', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Lakehouse'),
            ('Notebooks', f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=Notebook')
        ]
        
        performance_results = []
        
        for test_name, url in api_tests:
            start_time = time.time()
            
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    status = "✅" if response_time < 5 else "⚠️" 
                    print(f"    {status} {test_name}: {response_time:.2f}s")
                    performance_results.append(response_time < 10)  # 10s threshold
                else:
                    print(f"    ❌ {test_name}: HTTP {response.status_code}")
                    performance_results.append(False)
                    
            except Exception as e:
                print(f"    ❌ {test_name}: Timeout or error")
                performance_results.append(False)
        
        # Calculate performance score
        performance_score = sum(performance_results) / len(performance_results) * 100
        
        if performance_score >= 75:
            print(f"    ✅ Performance baseline: {performance_score:.0f}% (acceptable)")
            return True
        else:
            print(f"    ⚠️  Performance baseline: {performance_score:.0f}% (may need optimization)")
            return False
    
    except Exception as e:
        print(f"    ❌ Performance baseline check failed: {e}")
        return False


def check_monitoring_and_alerting(workspace_id, headers):
    """Check monitoring and alerting capabilities"""
    print("  📊 Checking monitoring capabilities...")
    
    try:
        # Basic monitoring readiness checks
        
        # 1. Workspace accessibility for monitoring
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            print("    ✅ Workspace accessible for monitoring")
        else:
            print("    ❌ Workspace monitoring access failed")
            return False
        
        # 2. Items enumeration for monitoring
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            items = response.json().get('value', [])
            print(f"    ✅ Can enumerate {len(items)} items for monitoring")
        else:
            print("    ❌ Items enumeration for monitoring failed")
            return False
        
        # 3. Check for semantic models (needed for usage monitoring)
        semantic_models = [item for item in items if item.get('type') == 'SemanticModel']
        reports = [item for item in items if item.get('type') == 'Report']
        
        if semantic_models:
            print(f"    ✅ Found {len(semantic_models)} semantic models for usage monitoring")
        else:
            print("    ⚠️  No semantic models found - usage monitoring may be limited")
        
        if reports:
            print(f"    ✅ Found {len(reports)} reports for access monitoring")
        else:
            print("    ⚠️  No reports found - access monitoring may be limited")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Monitoring capabilities check failed: {e}")
        return False


def generate_production_summary(workspace_id, headers, env_config):
    """Generate production deployment summary"""
    print("  📋 Generating production summary...")
    
    try:
        # Get workspace details
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            return False
        
        workspace_info = response.json()
        
        # Get items summary
        response = requests.get(
            f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items',
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            return False
        
        items = response.json().get('value', [])
        
        # Generate summary
        summary = {
            'deployment_time': datetime.now().isoformat(),
            'workspace': {
                'id': workspace_id,
                'name': workspace_info.get('displayName'),
                'type': workspace_info.get('type', 'Unknown')
            },
            'components': {
                'total_items': len(items),
                'lakehouses': len([i for i in items if i.get('type') == 'Lakehouse']),
                'notebooks': len([i for i in items if i.get('type') == 'Notebook']),
                'semantic_models': len([i for i in items if i.get('type') == 'SemanticModel']),
                'reports': len([i for i in items if i.get('type') == 'Report'])
            }
        }
        
        print("    📊 Production Deployment Summary:")
        print(f"      Workspace: {summary['workspace']['name']}")
        print(f"      Total Items: {summary['components']['total_items']}")
        print(f"      Lakehouses: {summary['components']['lakehouses']}")
        print(f"      Notebooks: {summary['components']['notebooks']}")
        print(f"      Semantic Models: {summary['components']['semantic_models']}")
        print(f"      Reports: {summary['components']['reports']}")
        print(f"      Deployment Time: {summary['deployment_time']}")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Summary generation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Run production health check')
    parser.add_argument('--environment', required=True, choices=['prod'],
                       help='Target environment (prod only)')
    
    args = parser.parse_args()
    
    print(f"🏥 Running production health check")
    print("=" * 50)
    
    # Get environment configuration
    env_config = get_environment_config(args.environment)
    workspace_id = env_config.get('workspace_id')
    workspace_name = env_config.get('workspace_name')
    
    if not workspace_id:
        print(f"❌ Production workspace ID not configured")
        sys.exit(1)
    
    print(f"📍 Production workspace: {workspace_name}")
    print(f"🆔 Workspace ID: {workspace_id[:8]}...{workspace_id[-4:]}")
    
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
    
    # Run production health checks
    health_results = []
    
    print(f"\n🏥 Running production health check suite...")
    print("-" * 60)
    
    # Check 1: Production readiness
    print(f"1️⃣  Production readiness check")
    result1 = check_production_readiness(workspace_id, headers)
    health_results.append(result1)
    
    # Check 2: Security configuration
    print(f"\n2️⃣  Security configuration check")
    result2 = check_security_configuration(workspace_id, headers)
    health_results.append(result2)
    
    # Check 3: Data pipeline health
    print(f"\n3️⃣  Data pipeline health check")
    result3 = check_data_pipeline_health(workspace_id, headers)
    health_results.append(result3)
    
    # Check 4: Performance baseline
    print(f"\n4️⃣  Performance baseline check")
    result4 = check_performance_baseline(workspace_id, headers)
    health_results.append(result4)
    
    # Check 5: Monitoring capabilities
    print(f"\n5️⃣  Monitoring capabilities check")
    result5 = check_monitoring_and_alerting(workspace_id, headers)
    health_results.append(result5)
    
    # Check 6: Production summary
    print(f"\n6️⃣  Production deployment summary")
    result6 = generate_production_summary(workspace_id, headers, env_config)
    health_results.append(result6)
    
    # Final health assessment
    passed_checks = sum(health_results)
    total_checks = len(health_results)
    health_score = (passed_checks / total_checks) * 100
    
    print(f"\n🏥 Production Health Check Results")
    print("=" * 50)
    print(f"Environment: PRODUCTION")
    print(f"Workspace: {workspace_name}")
    print(f"Health checks passed: {passed_checks}/{total_checks}")
    print(f"Health score: {health_score:.1f}%")
    print(f"Assessment time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if health_score >= 85:  # High bar for production
        print(f"✅ PRODUCTION HEALTH CHECK PASSED!")
        print(f"🎉 Production environment is healthy and ready for business use")
        print(f"🚀 Fabric Cost Analysis is now live in production")
        sys.exit(0)
    else:
        print(f"❌ PRODUCTION HEALTH CHECK FAILED")
        print(f"⚠️  Health score {health_score:.1f}% is below production threshold (85%)")
        print(f"🛑 Production environment may not be ready for business use")
        sys.exit(1)


if __name__ == "__main__":
    main()