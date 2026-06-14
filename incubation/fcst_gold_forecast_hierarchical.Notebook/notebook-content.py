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

# # fcst_gold_forecast_reconciled
#
# **Purpose**: Produces coherent daily cost forecasts across the Service_ID hierarchy (MinT-reconciled, with BottomUp baseline), plus the hierarchical daily actuals they are built from.
#
# **Domain**: fcst
# **Schema**: gold
#
# **Inputs**:
# - `focus_cost` (Delta table — pre-dates LAKEHOUSE_TABLES.md; update `SOURCE_TABLE` when it migrates to `silver.focusazure_normalised`)
#
# **Output**: `gold.forecast_input` (actuals, all levels), `gold.forecast_reconciled` (forecasts). `gold.vw_forecast_unified` unions them for Power BI — DDL in `sql/gold_vw_forecast_unified.sql`, deployed separately per LAKEHOUSE_TABLES.md.
#
# **Parameters** (in-notebook constants now; move to Variable Library on promotion):
# - `WORKSPACE_GUID` (string)
# - `HORIZON_DAYS` (int, 365)
#
# **Trigger**: ad-hoc (daily pipeline on promotion, after FOCUS ingestion)
#
# ---
#
# `Service_ID` is a fixed multipart tag: `{division}/{platform}/{workload}/{component}`, read from the FOCUS `Tags` JSON column. Missing/malformed tags go to a synthetic Untagged bucket — totals stay true to billing, and the bucket size doubles as a tagging-hygiene metric.
#
# Every hierarchy level (total → division → platform → workload → component) is forecast directly — aggregates are smoother, so each level gets the best model for its own signal — then `hierarchicalforecast` reconciles the levels so children sum to parents: `MinTrace(mint_shrink)` as the headline method, `BottomUp` kept as the trivially-coherent baseline (distinguished by `model_id`).
#
# > **Consumption note**: output tables contain *every* level. Always filter on `level` (or a specific path column) before summing, otherwise you double-count.

# CELL ********************

# ## 0. Node Sizing and Libraries
#
# `%%configure` must be the first cell. ~300 components → ~500–600 total series across all levels; Medium (8 vCores) is comfortable.
#
# Polars and delta-rs are in the Fabric runtime. `statsforecast`/`hierarchicalforecast` are not — inline install for now; on promotion these come from the ADO artifact feed via the Fabric environment definition.

# CELL ********************

%%configure -f
{
    "vCores": 8
}

# CELL ********************

%pip install -q "statsforecast>=2.0" "hierarchicalforecast>=1.2"

# CELL ********************

import logging
from datetime import datetime

import polars as pl
from hierarchicalforecast.core import HierarchicalReconciliation
from hierarchicalforecast.methods import BottomUp, MinTrace
from hierarchicalforecast.utils import aggregate
from statsforecast import StatsForecast
from statsforecast.models import MSTL, AutoARIMA

logger = logging.getLogger(__name__)

# CELL ********************

# ## 1. Parameters

# CELL ********************

# ---- Source / output tables ----
LAKEHOUSE_NAME = "FinOpsHub"
SOURCE_TABLE   = "focus_cost"            # legacy name; silver.focusazure_normalised post-migration
SCHEMA_NAME    = "gold"
ACTUALS_TABLE  = "forecast_input"        # gold.forecast_input
FORECAST_TABLE = "forecast_reconciled"   # gold.forecast_reconciled

# ---- Column references (FOCUS spec PascalCase at source; gold outputs are snake_case) ----
DATE_COL = "ChargePeriodStart"
COST_COL = "BilledCost"          # or 'EffectiveCost' — pick one, stay consistent
TAGS_COL = "Tags"
SERVICEID_TAG_KEY = "Service_ID" # tag value = {division}/{platform}/{workload}/{component}

# ---- Hierarchy ----
LEVELS      = ["division", "platform", "workload", "component"]
TOTAL_LABEL = "total"
UNTAGGED    = "Untagged"
UNTAGGED_ID = "/".join([UNTAGGED] * len(LEVELS))

# spec for hierarchicalforecast.aggregate: [[total], [total, division], ..., [total, ..., component]]
SPEC = [[TOTAL_LABEL] + LEVELS[:i] for i in range(len(LEVELS) + 1)]

# ---- Forecast configuration ----
HORIZON_DAYS = 365

# ---- Lakehouse paths ----
WORKSPACE_GUID = "PLACEHOLDER_WORKSPACE_ID"
TABLES_ROOT = f"abfss://Lakehouse@onelake.dfs.fabric.microsoft.com/Workspaces/{WORKSPACE_GUID}/Lakehouses/{LAKEHOUSE_NAME}/Tables"
GOLD_ROOT = f"{TABLES_ROOT}/{SCHEMA_NAME}"

# CELL ********************

# ## 2. Read, Extract Service_ID, Aggregate
#
# - `Service_ID` is pulled from the Tags JSON; anything missing or not exactly 4 parts → the Untagged bucket
# - Missing days are zero-filled **from each component's first appearance** (a day with no spend is a real £0; StatsForecast needs regular daily series, and zero-filling before a component existed would drag its trend down)

# CELL ********************

lf = pl.scan_delta(f"{TABLES_ROOT}/{SOURCE_TABLE}")

service_id = pl.col(TAGS_COL).str.json_path_match(f"$.{SERVICEID_TAG_KEY}")
valid = service_id.is_not_null() & (service_id.str.count_matches("/") == len(LEVELS) - 1)

base = (
    lf.with_columns(
        pl.when(valid).then(service_id).otherwise(pl.lit(UNTAGGED_ID)).alias("service_id")
    )
    .group_by(pl.col(DATE_COL).cast(pl.Date).alias("ds"), "service_id")
    .agg(pl.col(COST_COL).sum().alias("y"))
    .collect(streaming=True)
)

untagged_cost = base.filter(pl.col("service_id") == UNTAGGED_ID)["y"].sum()
total_cost = base["y"].sum()
logger.info("Untagged cost share: %.1f%%", 100 * untagged_cost / total_cost)

# ---- Zero-fill: each component's first appearance -> global max date ----
global_max = base["ds"].max()
scaffold = (
    base.group_by("service_id")
    .agg(pl.col("ds").min().alias("start"))
    .with_columns(pl.date_ranges(pl.col("start"), pl.lit(global_max)).alias("ds"))
    .drop("start")
    .explode("ds")
)
base = (
    scaffold.join(base, on=["service_id", "ds"], how="left")
    .with_columns(pl.col("y").fill_null(0.0))
    .with_columns(
        pl.lit(TOTAL_LABEL).alias(TOTAL_LABEL),
        pl.col("service_id").str.split_exact("/", len(LEVELS) - 1).struct.rename_fields(LEVELS).alias("_parts"),
    )
    .unnest("_parts")
)

logger.info(
    "%d daily records, %d components, %s to %s",
    len(base), base["service_id"].n_unique(), base["ds"].min(), base["ds"].max(),
)

# CELL ********************

# ## 3. Build Hierarchy
#
# `aggregate()` builds the series for every level in `SPEC`, joining path parts with `/` (so `unique_id`s look like `total/DivA/PlatX/...`). Returns the long all-levels frame `Y_df`, the summing matrix `S_df`, and the per-level `tags` dict.
#
# Pandas from here through reconciliation (StatsForecast/hierarchicalforecast interface; ~600 series × daily history is small — an accepted pandas exception under NOTEBOOK_STANDARDS).

# CELL ********************

Y_df, S_df, tags = aggregate(
    df=base.select(["ds", "y", TOTAL_LABEL] + LEVELS).to_pandas(),
    spec=SPEC,
)

for level_key, ids in tags.items():
    logger.info("%s: %d series", level_key, len(ids))
logger.info("Total series: %d, rows: %d", Y_df["unique_id"].nunique(), len(Y_df))

# CELL ********************

# ## 4. Write Hierarchical Daily Actuals — `gold.forecast_input`

# CELL ********************

LEVEL_BY_DEPTH = {i: name for i, name in enumerate([TOTAL_LABEL] + LEVELS)}

def with_hierarchy_cols(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.col("unique_id").str.count_matches("/")
              .replace_strict(LEVEL_BY_DEPTH, return_dtype=pl.Utf8).alias("level"),
            pl.col("unique_id").str.split_exact("/", len(LEVELS))
              .struct.rename_fields(["_root"] + LEVELS).alias("_parts"),
        )
        .unnest("_parts")
        .drop("_root")
    )

actuals_pl = with_hierarchy_cols(pl.from_pandas(Y_df))

actuals_pl.write_delta(
    f"{GOLD_ROOT}/{ACTUALS_TABLE}",
    mode="overwrite",
    engine="rust"
)

logger.info("Written %d rows to %s.%s", len(actuals_pl), SCHEMA_NAME, ACTUALS_TABLE)

# CELL ********************

# ## 5. Fit StatsForecast Across All Levels
#
# One `forecast()` call fits every series at every level. `fitted=True` keeps the insample fitted values — MinT(mint_shrink) needs the insample residuals to estimate the error covariance.

# CELL ********************

models = [
    MSTL(season_length=7, trend_forecaster=AutoARIMA(max_p=3, max_q=3, max_d=1)),
]

sf = StatsForecast(models=models, freq="D", n_jobs=-1)

logger.info("Forecasting %d series, %d-day horizon", Y_df["unique_id"].nunique(), HORIZON_DAYS)
Y_hat_df = sf.forecast(df=Y_df, h=HORIZON_DAYS, fitted=True)
Y_fitted_df = sf.forecast_fitted_values()

logger.info("Generated %d base forecast records", len(Y_hat_df))

# CELL ********************

# ## 6. Reconcile (BottomUp + MinTrace mint_shrink)
#
# The independently-fitted level forecasts are not coherent (children don't sum to parents). Reconciliation fixes that:
#
# - **BottomUp** — replace every aggregate with the sum of its components; trivially coherent baseline
# - **MinTrace(mint_shrink, nonnegative=True)** — MinT-optimal blend across levels using the shrunk residual covariance; usually more accurate than either pure approach. Costs can't go negative, hence `nonnegative=True`.
#
# If mint_shrink fails with an ill-conditioning error, bump `mint_shr_ridge` (default 2e-8) or fall back to `method="wls_var"`.

# CELL ********************

reconcilers = [
    BottomUp(),
    MinTrace(method="mint_shrink", nonnegative=True),
]

hrec = HierarchicalReconciliation(reconcilers=reconcilers)
Y_rec_df = hrec.reconcile(Y_hat_df=Y_hat_df, Y_df=Y_fitted_df, S_df=S_df, tags=tags)

logger.info("Reconciled columns: %s", [c for c in Y_rec_df.columns if c not in ("unique_id", "ds")])

# CELL ********************

# ## 7. Write Forecast — `gold.forecast_reconciled`
#
# Long format: one row per (`unique_id`, `ds`, `model_id`). `model_id` distinguishes the raw model (`MSTL`) from each reconciler (`MSTL/BottomUp`, `MSTL/MinTrace_method-mint_shrink`) so Power BI can compare them.

# CELL ********************

rec_pl = pl.from_pandas(Y_rec_df)
value_cols = [c for c in rec_pl.columns if c not in ("unique_id", "ds")]

forecast_pl = (
    rec_pl.unpivot(
        index=["unique_id", "ds"],
        on=value_cols,
        variable_name="model_id",
        value_name="yhat",
    )
    .pipe(with_hierarchy_cols)
    .with_columns(pl.lit(datetime.now()).alias("forecast_generated_at"))
)

forecast_pl.write_delta(
    f"{GOLD_ROOT}/{FORECAST_TABLE}",
    mode="overwrite",
    engine="rust"
)

logger.info("Written %d rows to %s.%s", len(forecast_pl), SCHEMA_NAME, FORECAST_TABLE)

# CELL ********************

# ## 8. Power BI View
#
# `gold.vw_forecast_unified` unions actuals and forecasts with `level` + path columns for drill-down. Per LAKEHOUSE_TABLES.md, plain views are governed by SQL DDL in the repo, not created notebook-side: see **`sql/gold_vw_forecast_unified.sql`** (deploy once / on change). **Always filter on `level` (and for forecasts, `model_id`) before aggregating.**

# CELL ********************

# ## 9. Validation and Diagnostics
#
# The coherence check is the point of this notebook: for each `model_id`, the total forecast minus the sum of component forecasts per day. Raw `MSTL` will show a gap (independent fits); `BottomUp` and `MinTrace` should be ~0 (floating-point noise).

# CELL ********************

logger.info(
    "Actuals: %d rows | Forecast: %d rows | Forecast range %s to %s | Untagged share %.1f%%",
    len(actuals_pl), len(forecast_pl), forecast_pl["ds"].min(), forecast_pl["ds"].max(),
    100 * untagged_cost / total_cost,
)

comp_sum = (
    forecast_pl.filter(pl.col("level") == "component")
    .group_by(["model_id", "ds"])
    .agg(pl.col("yhat").sum().alias("component_sum"))
)
coherence = (
    forecast_pl.filter(pl.col("level") == TOTAL_LABEL)
    .join(comp_sum, on=["model_id", "ds"])
    .with_columns((pl.col("yhat") - pl.col("component_sum")).abs().alias("abs_gap"))
    .group_by("model_id")
    .agg(
        pl.col("abs_gap").max().alias("max_daily_gap"),
        pl.col("abs_gap").mean().alias("mean_daily_gap"),
    )
)
display(coherence)
