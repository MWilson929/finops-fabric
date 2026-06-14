# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "PLACEHOLDER_LAKEHOUSE_ID",
# META       "default_lakehouse_name": "FinOpsHub",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
# META     }
# META   }
# META }

# CELL ********************

# # FOCUS Cost Forecasting — Trey Research (StatsForecast / Polars)
#
# Forecasts daily Azure cost per subscription, aligned to a Sept–Aug financial year. Pure-Polars Python notebook using **StatsForecast (MSTL + AutoARIMA)** for forecasting.
#
# ## Why this stack
#
# - **Polars** — handles the heavy 50M+ row aggregation on a single node (lazy/streaming, fast)
# - **StatsForecast** — Polars-native library, fits all subscriptions in one call (no manual loop), AutoARIMA picks the best order per series automatically, MSTL handles weekly + yearly seasonality
# - **deltalake** — write Delta tables to the lakehouse
#
# ## Pipeline
#
# 1. Read FOCUS table, aggregate to daily totals per subscription (Polars)
# 2. Write daily actuals to its own Delta table
# 3. Fit MSTL+AutoARIMA across all subscriptions in a single call, forecast through end of next FY
# 4. Write forecasts to a separate Delta table
# 5. Create a unified SQL view for Power BI consumption
#
# ## Financial Year Definition
#
# FY2026 = 1 September 2025 → 31 August 2026

# CELL ********************

# ## 0. Node Sizing
#
# `%%configure` must be the first cell. Medium (8 vCores) is the default for 50M rows; bump to 16 if you hit memory pressure on >100M rows.

# CELL ********************

%%configure -f
{
    "vCores": 8
}

# CELL ********************

# ## 1. Parameters

# PARAMETERS CELL ********************

# ---- Source tables ----
LAKEHOUSE_NAME    = "FinOpsHub"
SOURCE_TABLE      = "focus_cost"          # input FOCUS table
ACTUALS_TABLE     = "focus_actuals_daily" # output: daily aggregated actuals
FORECAST_TABLE    = "focus_forecast_daily" # output: forecast
UNIFIED_VIEW_NAME = "vw_focus_actuals_and_forecast"

# ---- Column references ----
DATE_COL = "ChargePeriodStart"   # daily charges in FOCUS
COST_COL = "BilledCost"          # or 'EffectiveCost' — pick one, stay consistent
SUBSCRIPTION_COL = "SubAccountId"

# ---- Forecast configuration ----
HORIZON_DAYS = 365  # forecast through end of next FY

# ---- FY boundaries (Sept 1 - Aug 31) ----
import datetime
TODAY = datetime.date.today()
FY_START_MONTH = 9
FY_START_DAY = 1

# CELL ********************

# ## 2. Read and Aggregate

# CELL ********************

import polars as pl
import pandas as pd
from datetime import datetime, timedelta
import notebookutils.mssparkutils as mssparkutils
from deltalake import DeltaTable

# ---- Connect to lakehouse ----
spark.sql(f"USE CATALOG hive_metastore")
spark.sql(f"USE SCHEMA default")  # adjust schema as needed

# ---- Read FOCUS table (lazy Polars with streaming) ----
print(f"Reading {SOURCE_TABLE}...")
lf = pl.scan_delta(
    f"abfss://Lakehouse@onelake.dfs.fabric.microsoft.com/Workspaces/PLACEHOLDER_WORKSPACE_ID/Lakehouses/{LAKEHOUSE_NAME}/Tables/{SOURCE_TABLE}"
)

# ---- Aggregate to daily cost per subscription ----
daily_actuals = lf.group_by(
    pl.col(DATE_COL).cast(pl.Date).alias("ds"),
    pl.col(SUBSCRIPTION_COL).alias("unique_id")
).agg(
    pl.col(COST_COL).sum().alias("y")
).sort(["unique_id", "ds"]).collect(streaming=True)

print(f"Aggregated to {len(daily_actuals)} daily records across {daily_actuals['unique_id'].n_unique()} subscriptions")
print(f"Date range: {daily_actuals['ds'].min()} to {daily_actuals['ds'].max()}")
display(daily_actuals.head())

# CELL ********************

# ## 3. Write Daily Actuals to Delta

# CELL ********************

# ---- Write actuals table ----
abfss_path = f"abfss://Lakehouse@onelake.dfs.fabric.microsoft.com/Workspaces/PLACEHOLDER_WORKSPACE_ID/Lakehouses/{LAKEHOUSE_NAME}/Tables/{ACTUALS_TABLE}"

daily_actuals.write_delta(
    abfss_path,
    mode="overwrite",
    engine="rust"
)

print(f"Written {len(daily_actuals)} rows to {ACTUALS_TABLE}")

# CELL ********************

# ## 4. Fit StatsForecast (MSTL + AutoARIMA)

# CELL ********************

from statsforecast import StatsForecast
from statsforecast.models import MSTL, AutoARIMA, SeasonalNaive

# ---- Instantiate models ----
# MSTL decomposes into trend + multiple seasonalities (weekly + yearly)
# AutoARIMA fits the residuals
models = [
    MSTL(season_length=7, trend_forecaster=AutoARIMA(max_p=3, max_q=3, max_d=1)),
    SeasonalNaive(season_length=7)  # baseline
]

# ---- Convert to pandas for StatsForecast (it doesn't consume Polars directly yet) ----
df_sf = daily_actuals.to_pandas()

# ---- Fit ----
print(f"Fitting StatsForecast across {df_sf['unique_id'].nunique()} series...")
sf = StatsForecast(models=models, freq='D')
sf.fit(df_sf)

print("Fit complete.")

# CELL ********************

# ## 5. Generate Forecasts

# CELL ********************

# ---- Forecast ----
print(f"Generating {HORIZON_DAYS}-day forecast...")
forecast_df = sf.forecast(horizon=HORIZON_DAYS)

# ---- Convert back to Polars and reshape ----
forecast_df = forecast_df.reset_index()
forecast_pl = pl.from_pandas(forecast_df)

# Rename MSTL output column to 'yhat' for consistency
forecast_pl = forecast_pl.rename({"MSTL": "yhat"})

# Add metadata
forecast_pl = forecast_pl.with_columns(
    pl.lit("MSTL-AutoARIMA").alias("model_id"),
    pl.lit(datetime.now()).alias("forecast_generated_at")
)

print(f"Generated {len(forecast_pl)} forecast records")
display(forecast_pl.head())

# CELL ********************

# ## 6. Write Forecast to Delta

# CELL ********************

# ---- Write forecast table ----
forecast_abfss_path = f"abfss://Lakehouse@onelake.dfs.fabric.microsoft.com/Workspaces/PLACEHOLDER_WORKSPACE_ID/Lakehouses/{LAKEHOUSE_NAME}/Tables/{FORECAST_TABLE}"

forecast_pl.write_delta(
    forecast_abfss_path,
    mode="overwrite",
    engine="rust"
)

print(f"Written {len(forecast_pl)} rows to {FORECAST_TABLE}")

# CELL ********************

# ## 7. Create Unified SQL View

# CELL ********************

# ---- SQL view combining actuals and forecast ----
view_sql = f"""
CREATE OR REPLACE VIEW {UNIFIED_VIEW_NAME} AS

-- ACTUALS
SELECT
    ds AS date,
    unique_id AS subscription_id,
    y AS cost,
    'actual' AS record_type,
    NULL AS model_id,
    NULL AS forecast_generated_at
FROM {ACTUALS_TABLE}

UNION ALL

-- FORECAST
SELECT
    ds AS date,
    unique_id AS subscription_id,
    yhat AS cost,
    'forecast' AS record_type,
    model_id,
    forecast_generated_at
FROM {FORECAST_TABLE}

ORDER BY unique_id, date
"""

# Execute via Spark SQL
spark.sql(view_sql)
print(f"Created view: {UNIFIED_VIEW_NAME}")
print("\nView SQL:")
print(view_sql)

# CELL ********************

# ## 8. Validation and Diagnostics

# CELL ********************

# ---- Sanity checks ----
print("=== VALIDATION ===")
print(f"Actuals: {len(daily_actuals)} rows")
print(f"Forecast: {len(forecast_pl)} rows")
print(f"Subscriptions: {daily_actuals['unique_id'].n_unique()} unique")
print(f"Actuals date range: {daily_actuals['ds'].min()} to {daily_actuals['ds'].max()}")
print(f"Forecast date range: {forecast_pl['ds'].min()} to {forecast_pl['ds'].max()}")
print(f"\nForecast quality (point estimate, no intervals yet):")
print(forecast_pl.select(["unique_id", "yhat"]).group_by("unique_id").agg(pl.col("yhat").mean()).head())
