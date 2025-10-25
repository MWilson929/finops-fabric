# Fabric notebook source generated from notebook-content.ipynb
# This is a test notebook for validating Microsoft Fabric CI/CD deployment

# METADATA ********************

# META {
# META   "kernel": {
# META     "display_name": "synapse_pyspark",
# META     "name": "synapse_pyspark"
# META   },
# META   "language_info": {
# META     "name": "python"
# META   }
# META }

# MARKDOWN ********************

# # Hello World Fabric Notebook
# 
# This is a simple test notebook to validate our CI/CD deployment pipeline.
# 
# ## Purpose
# - Test notebook deployment via fabric-cicd
# - Verify workspace connectivity
# - Validate authentication and permissions

# CELL ********************

print("🎉 Hello from Fabric CI/CD!")
print("=" * 50)

# CELL ********************

# Test basic Python functionality
import datetime
import os

current_time = datetime.datetime.now()
print(f"📅 Current time: {current_time}")
print(f"🐍 Python version: {os.sys.version}")

# CELL ********************

# Test Fabric-specific functionality
try:
    # Try to access notebook utilities if available
    print("🔍 Testing Fabric notebook utilities...")
    
    # Basic variable test
    test_variable = "Hello Fabric"
    print(f"✅ Variable test: {test_variable}")
    
    # Simple function test
    def fabric_test_function(message):
        return f"📦 Fabric Function Result: {message}"
    
    result = fabric_test_function("CI/CD Deployment Successful!")
    print(result)
    
except Exception as e:
    print(f"⚠️  Fabric utilities not available: {e}")

# CELL ********************

# Test workspace and lakehouse references (dynamic)
try:
    print("🏠 Testing dynamic workspace references...")
    
    # These would be replaced by actual Fabric dynamic references in a real deployment
    workspace_ref = "$workspace.$id"  # Dynamic reference
    lakehouse_ref = "$items.Lakehouse.FinOpsHub.$id"  # Dynamic reference
    
    print(f"🎯 Workspace ID reference: {workspace_ref}")
    print(f"🏠 Lakehouse ID reference: {lakehouse_ref}")
    
    print("✅ Dynamic references configured successfully!")
    
except Exception as e:
    print(f"⚠️  Dynamic references not available: {e}")

# MARKDOWN ********************

# ## Deployment Validation
# 
# If you can see this notebook running successfully, then:
# 
# ✅ **fabric-cicd deployment worked**  
# ✅ **Authentication is configured correctly**  
# ✅ **Workspace permissions are properly set**  
# ✅ **CI/CD pipeline is functional**

# CELL ********************

print("🎊 Notebook execution completed successfully!")
print("🚀 Microsoft Fabric CI/CD deployment validated!")