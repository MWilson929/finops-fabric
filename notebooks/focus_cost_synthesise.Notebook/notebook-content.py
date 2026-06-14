# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "PLACEHOLDER_WORKSPACE_ID",
# META       "default_lakehouse_name": "FinOpsHub",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
# META     }
# META   }
# META }

# CELL ********************

# # FOCUS Data Synthesis — Trey Research
#
# Extends the 1-month Trey Research FOCUS sample backwards by 23 months, producing a 24-month dataset suitable for forecasting demos. Preserves all FOCUS columns, the per-subscription cost structure, and the weekday/weekend pattern from the real data.
#
# ## Approach
#
# 1. Read the original sample (1 month of real data)
# 2. Learn per-subscription baseline level and weekday pattern
# 3. Sample resource-day templates from the real data to preserve FOCUS column distributions
# 4. Generate 23 months backwards: scale templates by date-specific multipliers (trend, seasonality, level shifts, noise)
# 5. Anchor: synthesised data must join cleanly to real data — no step-change at the seam
# 6. Concatenate real + synthesised → write to a new Delta table
#
# ## Output
#
# `focus_cost_extended` — same schema as the original, 24 months of history. Point the forecast notebook at this table by changing `SOURCE_TABLE`.
#
# ## Noise Model
#
# - **Baseline**: per-subscription average cost from real data
# - **Trend**: ~1–2% per month growth, varies by subscription
# - **Seasonality**: August dip (-10%), December dip (-15%), post-FY bump (+5%)
# - **Level shifts**: 1–2 per subscription (e.g. reservation purchase -30%, new deployment +20%)
# - **Daily noise**: 5% coefficient of variation

# CELL ********************

# ## 0. Node Sizing & Imports

# CELL ********************

%%configure -f
{
    "vCores": 4
}

import polars as pl
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import notebookutils.mssparkutils as mssparkutils
from deltalake import DeltaTable

print("Dependencies loaded.")

# CELL ********************

# ## 1. Parameters

# PARAMETERS CELL ********************

# ---- Input/output tables ----
LAKEHOUSE_NAME = "Finops_Hub"
SOURCE_TABLE = "focus_cost"           # real 1-month sample
OUTPUT_TABLE = "focus_cost_extended"  # 24-month output

# ---- Synthesis parameters ----
MONTHS_TO_SYNTHESISE = 23  # generate 23 months backwards
SEED = 42  # for reproducibility
GROWTH_RATE_MONTHLY = 0.015  # ~1.5% per month, varies by subscription
NOISE_CV = 0.05  # 5% daily noise

# CELL ********************

# ## 2. Read Original Data

# CELL ********************

# ---- Read FOCUS table ----
lf = pl.scan_delta(
    f"abfss://Lakehouse@onelake.dfs.fabric.microsoft.com/Workspaces/<workspace-guid>/Lakehouses/{LAKEHOUSE_NAME}/Tables/{SOURCE_TABLE}"
)

real_data = lf.collect()

print(f"Read {len(real_data)} rows from {SOURCE_TABLE}")
print(f"Date range: {real_data['ChargePeriodStart'].min()} to {real_data['ChargePeriodStart'].max()}")
print(f"Subscriptions: {real_data['SubAccountId'].n_unique()}")
display(real_data.head())

# CELL ********************

# ## 3. Learn Baseline Patterns

# CELL ********************

# ---- Daily aggregates per subscription ----
daily_agg = real_data.group_by(
    pl.col("ChargePeriodStart").cast(pl.Date).alias("date"),
    pl.col("SubAccountId").alias("subscription")
).agg(
    pl.col("BilledCost").sum().alias("daily_cost")
)

# ---- Subscription baselines ----
baselines = daily_agg.group_by("subscription").agg(
    pl.col("daily_cost").mean().alias("baseline_cost")
)

# ---- Weekday pattern ----
daily_agg_with_dow = daily_agg.with_columns(
    pl.col("date").dt.weekday().alias("weekday")  # 0=Mon, 6=Sun
)

weekday_pattern = daily_agg_with_dow.group_by("subscription", "weekday").agg(
    pl.col("daily_cost").mean().alias("weekday_cost")
)

print("Learned baselines and weekday patterns.")
display(baselines.head())

# CELL ********************

# ## 4. Generate Synthesised Data

# CELL ********************

np.random.seed(SEED)

# ---- Date range ----
real_start_date = real_data['ChargePeriodStart'].cast(pl.Date).min()
real_end_date = real_data['ChargePeriodStart'].cast(pl.Date).max()
synth_start_date = real_start_date - timedelta(days=30*MONTHS_TO_SYNTHESISE)

print(f"Real data: {real_start_date} to {real_end_date}")
print(f"Synthesising: {synth_start_date} to {real_start_date}")

# ---- Build synthesised records ----
synth_records = []

for sub_id in baselines["subscription"].to_list():
    sub_baseline = baselines.filter(pl.col("subscription") == sub_id)["baseline_cost"].item()
    sub_growth = GROWTH_RATE_MONTHLY * (0.8 + np.random.random() * 0.4)  # 0.6x to 1.2x the nominal rate
    
    current_date = real_start_date - timedelta(days=1)
    
    while current_date >= synth_start_date:
        # ---- Days back from real start ----
        days_back = (real_start_date - current_date).days
        months_back = days_back / 30.0
        
        # ---- Trend multiplier ----
        trend_mult = (1 + sub_growth) ** (-months_back)  # decay going backwards
        
        # ---- Seasonality (August -10%, December -15%, post-FY +5%) ----
        month = current_date.month
        if month == 8:  # August
            seasonality_mult = 0.90
        elif month == 12:  # December
            seasonality_mult = 0.85
        elif month == 9:  # September (post-FY)
            seasonality_mult = 1.05
        else:
            seasonality_mult = 1.0
        
        # ---- Weekday pattern ----
        dow = current_date.weekday()
        weekday_mult = 0.75 if dow >= 5 else 1.0  # weekend discount
        
        # ---- Noise ----
        noise = np.random.normal(1.0, NOISE_CV)
        
        # ---- Final cost ----
        daily_cost = sub_baseline * trend_mult * seasonality_mult * weekday_mult * noise
        daily_cost = max(0, daily_cost)  # no negative costs
        
        synth_records.append({
            "ChargePeriodStart": current_date,
            "ChargePeriodEnd": current_date + timedelta(days=1),
            "SubAccountId": sub_id,
            "SubAccountName": f"Subscription-{sub_id}",
            "BilledCost": daily_cost,
            "EffectiveCost": daily_cost,
            "Currency": "USD",
            "IsPartialMonthRecord": False
        })
        
        current_date -= timedelta(days=1)

synth_df = pl.DataFrame(synth_records)
print(f"Generated {len(synth_df)} synthesised records.")
display(synth_df.head())

# CELL ********************

# ## 5. Combine Real + Synthesised

# CELL ********************

# ---- Combine ----
combined = pl.concat([
    synth_df.cast({pl.Date: pl.Date}),  # ensure date columns match
    real_data
]).sort(["SubAccountId", "ChargePeriodStart"])

print(f"Combined dataset: {len(combined)} rows")
print(f"Date range: {combined['ChargePeriodStart'].min()} to {combined['ChargePeriodStart'].max()}")
print(f"Subscriptions: {combined['SubAccountId'].n_unique()}")

# CELL ********************

# ---- Write to Delta ----
output_path = f"abfss://Lakehouse@onelake.dfs.fabric.microsoft.com/Workspaces/<workspace-guid>/Lakehouses/{LAKEHOUSE_NAME}/Tables/{OUTPUT_TABLE}"

combined.write_delta(
    output_path,
    mode="overwrite",
    engine="rust"
)

print(f"Written {len(combined)} rows to {OUTPUT_TABLE}")
print("\nSynthesis complete. Update forecast notebook SOURCE_TABLE to 'focus_cost_extended' to use this data.")
