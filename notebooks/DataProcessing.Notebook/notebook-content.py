# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "PLACEHOLDER_LAKEHOUSE_ID",
# META       "default_lakehouse_name": "MainLakehouse",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
# META     },
# META     "environment": {
# META       "environmentId": "PLACEHOLDER_ENVIRONMENT_ID",
# META       "workspaceId": "PLACEHOLDER_WORKSPACE_ID"
# META     }
# META   }
# META }

# CELL ********************

# Example Data Processing Notebook
# This notebook demonstrates parameterized configuration for different environments

# Environment-specific configurations (will be replaced during deployment)
storage_account = "PLACEHOLDER_STORAGE_ACCOUNT"
container_name = "PLACEHOLDER_CONTAINER_NAME"
subscription_id = "PLACEHOLDER_SUBSCRIPTION_ID"
data_path = "PLACEHOLDER_DATA_PATH"

# Dynamic workspace and lakehouse references
workspace_id = "PLACEHOLDER_WORKSPACE_ID"
lakehouse_id = "PLACEHOLDER_LAKEHOUSE_ID"

print(f"Connecting to storage account: {storage_account}")
print(f"Using container: {container_name}")
print(f"Data path: {data_path}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Construct connection string for ADLS Gen2
connection_string = f"abfss://{container_name}@{storage_account}.dfs.core.windows.net/{data_path}"
print(f"Connection string: {connection_string}")

# Read data from the configured path
try:
    df = spark.read.option("header", "true").csv(connection_string)
    print(f"Successfully read {df.count()} rows from {connection_string}")
    df.show(5)
except Exception as e:
    print(f"Error reading data: {e}")

# METADATA ********************

# META {
# META   "language": "python", 
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Write processed data to lakehouse
try:
    # Process the data (example transformation)
    processed_df = df.withColumn("processed_timestamp", current_timestamp())
    
    # Write to lakehouse table
    processed_df.write \
        .mode("overwrite") \
        .option("overwriteSchema", "true") \
        .saveAsTable("processed_data")
    
    print("✅ Data processing completed successfully")
    
except Exception as e:
    print(f"❌ Error processing data: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark" 
# META }