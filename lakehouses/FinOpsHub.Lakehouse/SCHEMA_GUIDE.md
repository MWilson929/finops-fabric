# FinOpsHub Lakehouse Schema Guide

## Medallion Architecture Overview

The FinOpsHub lakehouse implements a **medallion architecture** with Bronze, Silver, and Gold layers for optimal data organization and processing efficiency.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   BRONZE    │───▶│   SILVER    │───▶│    GOLD     │
│  Raw Data   │    │ Clean Data  │    │Business Data│
└─────────────┘    └─────────────┘    └─────────────┘
```

## Schema Structure

### 🥉 Bronze Layer (Raw Data Zone)
**Purpose**: Landing zone for all ingested data in its original format

```sql
-- Example table creation for Bronze layer
CREATE TABLE IF NOT EXISTS bronze.raw_cost_data (
    subscription_id STRING,
    resource_group STRING,
    resource_name STRING,
    service_category STRING,
    cost_amount DECIMAL(18,2),
    billing_currency STRING,
    usage_date DATE,
    ingestion_timestamp TIMESTAMP,
    source_system STRING,
    raw_payload STRING  -- Original JSON payload for audit
) 
USING DELTA
PARTITIONED BY (ingestion_date DATE, subscription_id)
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);
```

**Characteristics**:
- ✅ Preserves original data format and structure
- ✅ Immutable - never modify after ingestion
- ✅ Full audit trail with source timestamps
- ✅ Partitioned by ingestion date for efficient processing

### 🥈 Silver Layer (Validated Data Zone)  
**Purpose**: Cleansed, validated, and standardized data ready for analysis

```sql
-- Example table creation for Silver layer
CREATE TABLE IF NOT EXISTS silver.cleansed_cost_data (
    cost_id STRING,  -- Generated unique identifier
    subscription_id STRING,
    resource_group STRING,
    resource_name STRING,
    service_category STRING,
    normalized_cost_amount DECIMAL(18,2),  -- Standardized to USD
    original_currency STRING,
    exchange_rate DECIMAL(10,6),
    usage_date DATE,
    cost_center STRING,  -- Enriched from resource tags
    department STRING,   -- Mapped from cost center
    environment STRING,  -- DEV/TEST/PROD classification
    is_valid BOOLEAN,   -- Data quality flag
    validation_errors ARRAY<STRING>,
    processed_timestamp TIMESTAMP
)
USING DELTA  
PARTITIONED BY (billing_date DATE, resource_group)
TBLPROPERTIES (
    'delta.enableChangeDataFeed' = 'true',
    'delta.columnMapping.mode' = 'name'
);
```

**Transformations Applied**:
- 🔧 Data validation and quality checks
- 🔧 Currency normalization to standard (USD)
- 🔧 Deduplication based on business keys
- 🔧 Tag enrichment and hierarchy mapping
- 🔧 Standardized naming conventions

### 🥇 Gold Layer (Business Data Zone)
**Purpose**: Aggregated, business-ready data optimized for reporting and analytics

```sql  
-- Example table creation for Gold layer
CREATE TABLE IF NOT EXISTS gold.monthly_cost_summary (
    summary_id STRING,
    fiscal_year INT,
    fiscal_month INT,
    department STRING,
    service_category STRING,
    environment STRING,
    region STRING,
    total_cost DECIMAL(18,2),
    budget_allocated DECIMAL(18,2),
    budget_variance DECIMAL(18,2),
    budget_variance_pct DECIMAL(5,2),
    cost_trend_mom DECIMAL(5,2),  -- Month-over-month % change
    resource_count INT,
    avg_daily_cost DECIMAL(18,2),
    peak_daily_cost DECIMAL(18,2),
    cost_optimization_potential DECIMAL(18,2),
    last_updated TIMESTAMP
)
USING DELTA
PARTITIONED BY (fiscal_year, fiscal_month)
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.columnMapping.mode' = 'name'
);
```

**Business Aggregations**:
- 📊 Monthly/quarterly/yearly rollups
- 📊 Department and cost center summaries  
- 📊 Budget vs. actual variance analysis
- 📊 Trend analysis and forecasting metrics
- 📊 Optimization recommendations and KPIs

## Schema Implementation

### 1. Create Schemas in Lakehouse

```sql
-- Create schemas in your FinOpsHub lakehouse
CREATE SCHEMA IF NOT EXISTS bronze 
COMMENT 'Raw data layer - ingested data in original format';

CREATE SCHEMA IF NOT EXISTS silver 
COMMENT 'Cleansed and validated data layer';

CREATE SCHEMA IF NOT EXISTS gold 
COMMENT 'Business-ready aggregated data layer';
```

### 2. Data Pipeline Flow

```python
# Example Bronze to Silver transformation
def bronze_to_silver_transformation():
    # Read from Bronze
    bronze_df = spark.read.table("FinOpsHub.bronze.raw_cost_data")
    
    # Apply transformations
    silver_df = (bronze_df
        .filter(col("cost_amount").isNotNull())  # Remove nulls
        .withColumn("normalized_cost_amount",   # Currency normalization
                   when(col("billing_currency") == "EUR", col("cost_amount") * 1.1)
                   .when(col("billing_currency") == "GBP", col("cost_amount") * 1.3)
                   .otherwise(col("cost_amount")))
        .withColumn("cost_center", get_cost_center_udf(col("resource_group")))
        .withColumn("is_valid", validate_cost_data_udf(struct("*")))
        .withColumn("processed_timestamp", current_timestamp())
    )
    
    # Write to Silver
    (silver_df.write
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable("FinOpsHub.silver.cleansed_cost_data"))

# Example Silver to Gold aggregation  
def silver_to_gold_aggregation():
    # Read from Silver
    silver_df = spark.read.table("FinOpsHub.silver.cleansed_cost_data")
    
    # Create monthly summary
    monthly_summary = (silver_df
        .filter(col("is_valid") == True)
        .groupBy("fiscal_year", "fiscal_month", "department", 
                 "service_category", "environment", "region")
        .agg(
            sum("normalized_cost_amount").alias("total_cost"),
            avg("normalized_cost_amount").alias("avg_daily_cost"),
            max("normalized_cost_amount").alias("peak_daily_cost"),
            countDistinct("resource_name").alias("resource_count")
        )
        .withColumn("last_updated", current_timestamp())
    )
    
    # Write to Gold with merge logic
    monthly_summary.write.mode("overwrite").saveAsTable("FinOpsHub.gold.monthly_cost_summary")
```

### 3. Dynamic References in Notebooks

```python
# Reference the lakehouse using fabric-cicd dynamic replacement
lakehouse_name = "FinOpsHub"
lakehouse_id = "$items.Lakehouse.FinOpsHub.$id"

# Access tables across schemas
bronze_costs = spark.read.table(f"{lakehouse_name}.bronze.raw_cost_data")
silver_costs = spark.read.table(f"{lakehouse_name}.silver.cleansed_cost_data") 
gold_summary = spark.read.table(f"{lakehouse_name}.gold.monthly_cost_summary")
```

## Data Governance and Security

### Access Control by Layer

```python
# Bronze Layer - Restricted Access
# - Data Engineers: Read/Write
# - System Administrators: Read/Write  
# - Data Analysts: Read-only (limited)

# Silver Layer - Analytical Access
# - Data Engineers: Read/Write
# - Data Analysts: Read/Write
# - FinOps Teams: Read/Write
# - Business Users: Read-only

# Gold Layer - Business Access  
# - All Silver layer users: Read/Write
# - Finance Teams: Read/Write
# - Executives: Read-only
# - Report Consumers: Read-only
```

### Data Quality Monitoring

```python
# Bronze layer quality checks
def validate_bronze_data():
    return [
        "COUNT(*) > 0",  # Non-empty check
        "cost_amount IS NOT NULL",  # Required fields
        "usage_date BETWEEN '2020-01-01' AND CURRENT_DATE()",  # Date range
        "LENGTH(subscription_id) = 36"  # GUID format
    ]

# Silver layer quality checks  
def validate_silver_data():
    return [
        "is_valid = true",  # Only valid records
        "normalized_cost_amount >= 0",  # Non-negative costs
        "department IS NOT NULL",  # Enrichment successful
        "cost_center IS NOT NULL"  # Mapping successful
    ]

# Gold layer quality checks
def validate_gold_data():
    return [
        "total_cost = SUM(individual_costs)",  # Aggregation accuracy
        "budget_variance_pct BETWEEN -100 AND 500",  # Reasonable variance
        "resource_count > 0"  # Non-zero resource count
    ]
```

## Performance Optimization

### Partitioning Strategy
- **Bronze**: Partition by `ingestion_date` and `subscription_id`
- **Silver**: Partition by `billing_date` and `resource_group`  
- **Gold**: Partition by `fiscal_year` and `fiscal_month`

### File Optimization
```sql
-- Optimize Bronze tables for write performance
ALTER TABLE bronze.raw_cost_data SET TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Optimize Silver tables for read/write balance
ALTER TABLE silver.cleansed_cost_data SET TBLPROPERTIES (
    'delta.enableChangeDataFeed' = 'true',
    'delta.autoOptimize.optimizeWrite' = 'true'
);

-- Optimize Gold tables for fast queries
ALTER TABLE gold.monthly_cost_summary SET TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported'
);

-- Apply ZORDER optimization for frequently queried columns
OPTIMIZE FinOpsHub.silver.cleansed_cost_data ZORDER BY (department, service_category);
OPTIMIZE FinOpsHub.gold.monthly_cost_summary ZORDER BY (department, fiscal_year);
```

## Usage Examples

### Cost Analysis Query
```sql
-- Cross-layer analysis: Bronze -> Silver -> Gold
WITH cost_trends AS (
  SELECT 
    department,
    fiscal_year,
    fiscal_month, 
    total_cost,
    LAG(total_cost, 1) OVER (PARTITION BY department ORDER BY fiscal_year, fiscal_month) as prev_month_cost
  FROM FinOpsHub.gold.monthly_cost_summary
  WHERE fiscal_year >= 2024
)
SELECT 
  department,
  fiscal_year,
  fiscal_month,
  total_cost,
  ROUND((total_cost - prev_month_cost) / prev_month_cost * 100, 2) as mom_change_pct
FROM cost_trends
WHERE prev_month_cost IS NOT NULL
ORDER BY department, fiscal_year, fiscal_month;
```

### Data Lineage Tracking
```sql
-- Track data lineage from Bronze to Gold
SELECT 
  'bronze.raw_cost_data' as source_table,
  COUNT(*) as record_count,
  MAX(ingestion_timestamp) as latest_ingestion
FROM FinOpsHub.bronze.raw_cost_data
WHERE ingestion_date = CURRENT_DATE()

UNION ALL

SELECT 
  'silver.cleansed_cost_data' as source_table,
  COUNT(*) as record_count, 
  MAX(processed_timestamp) as latest_processing
FROM FinOpsHub.silver.cleansed_cost_data
WHERE processed_timestamp >= CURRENT_DATE()

UNION ALL

SELECT
  'gold.monthly_cost_summary' as source_table,
  COUNT(*) as record_count,
  MAX(last_updated) as latest_update  
FROM FinOpsHub.gold.monthly_cost_summary
WHERE last_updated >= CURRENT_DATE();
```

---

This medallion architecture provides a robust foundation for FinOps data management with clear data lineage, quality controls, and optimized performance for both operational and analytical workloads.