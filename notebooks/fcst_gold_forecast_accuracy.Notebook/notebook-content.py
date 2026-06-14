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

# # fcst_gold_forecast_accuracy
#
# **Purpose**: Walk-forward backtest of the hierarchical forecast — scores MinT vs BottomUp vs raw MSTL per hierarchy level and horizon, persisting accuracy history.
#
# **Domain**: fcst
# **Schema**: gold
#
# **Inputs**:
# - `focus_cost` (Delta table — pre-dates LAKEHOUSE_TABLES.md; update `SOURCE_TABLE` when it migrates to `silver.focusazure_normalised`)
#
# **Output**: `gold.forecast_accuracy` (appends per run date; same-day reruns replace)
#
# **Parameters** (in-notebook constants now; move to Variable Library on promotion):
# - `WORKSPACE_GUID` (string)
# - `BT_HORIZON_DAYS` (int, 182), `N_WINDOWS` (int, 6), `STEP_SIZE_DAYS` (int, 28)
#
# **Trigger**: ad-hoc (monthly pipeline on promotion)
#
# ---
#
# Walk-forward scheme: pretend it's a past cutoff date, fit on everything before it, forecast `BT_HORIZON_DAYS` ahead, score against the held-back actuals. Slide the cutoff forward `STEP_SIZE_DAYS`, repeat `N_WINDOWS` times. Every window is reconciled the same way as the live notebook (`fcst_gold_forecast_reconciled`), so the comparison covers `MSTL` (raw), `MSTL/BottomUp`, and `MSTL/MinTrace_method-mint_shrink`.
#
# Outputs: accuracy by hierarchy level (MAPE/RMSE + WAPE), a horizon-degradation curve (WAPE by days-ahead bucket), and the persisted `gold.forecast_accuracy` history that drift detection (roadmap item 9) will consume.
#
# Defaults vs history: with ~24 months, 6 windows × 28-day steps × 182-day horizon leaves the earliest window ~12 months of training data. Shorten `BT_HORIZON_DAYS` or `N_WINDOWS` if history is thinner.

# CELL ********************

# ## 0. Node Sizing and Libraries
#
# Cross-validation refits every window (`N_WINDOWS` × ~600 series) — the heaviest notebook in the set. Start at 8 vCores; bump to 16 if window fits crawl.
#
# Polars and delta-rs are in the Fabric runtime; the Nixtla libraries are not — inline install for now, ADO artifact feed via the environment definition on promotion.

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

import pandas as pd
import polars as pl
from hierarchicalforecast.core import HierarchicalReconciliation
from hierarchicalforecast.evaluation import evaluate
from hierarchicalforecast.methods import BottomUp, MinTrace
from hierarchicalforecast.utils import aggregate
from statsforecast import StatsForecast
from statsforecast.models import MSTL, AutoARIMA
from utilsforecast.losses import mape, rmse

logger = logging.getLogger(__name__)

# CELL ********************

# ## 1. Parameters
#
# Source/hierarchy parameters mirror `focus_cost_forecast_hierarchical.ipynb` — keep them in sync.

# CELL ********************

# ---- Source / output tables ----
LAKEHOUSE_NAME = "Finops_Hub"
SOURCE_TABLE   = "focus_cost"          # legacy name; silver.focusazure_normalised post-migration
SCHEMA_NAME    = "gold"
METRICS_TABLE  = "forecast_accuracy"   # gold.forecast_accuracy

# ---- Column references (FOCUS spec PascalCase at source; gold outputs are snake_case) ----
DATE_COL = "ChargePeriodStart"
COST_COL = "BilledCost"
TAGS_COL = "Tags"
SERVICEID_TAG_KEY = "Service_ID"  # {division}/{platform}/{workload}/{component}

# ---- Hierarchy ----
LEVELS      = ["division", "platform", "workload", "component"]
TOTAL_LABEL = "total"
UNTAGGED    = "Untagged"
UNTAGGED_ID = "/".join([UNTAGGED] * len(LEVELS))
SPEC = [[TOTAL_LABEL] + LEVELS[:i] for i in range(len(LEVELS) + 1)]

# ---- Backtest configuration ----
BT_HORIZON_DAYS = 182   # how far ahead each window forecasts
N_WINDOWS       = 6     # number of walk-forward windows
STEP_SIZE_DAYS  = 28    # cutoff spacing (4 weeks keeps weekly seasonality aligned)

# days-ahead buckets for the degradation curve
HORIZON_BUCKETS = [(1, 28, "01-28d"), (29, 91, "29-91d"), (92, 182, "92-182d")]

# ---- Lakehouse paths ----
WORKSPACE_GUID = "<workspace-guid>"
TABLES_ROOT = f"abfss://Lakehouse@onelake.dfs.fabric.microsoft.com/Workspaces/{WORKSPACE_GUID}/Lakehouses/{LAKEHOUSE_NAME}/Tables"
GOLD_ROOT = f"{TABLES_ROOT}/{SCHEMA_NAME}"

# CELL ********************

# ## 2. Read, Extract Service_ID, Build Hierarchy
#
# Identical data prep to the live notebook: Tags JSON → `Service_ID` (malformed → Untagged), zero-fill from each component's first appearance, `aggregate()` builds every level's series.

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

Y_df, S_df, tags = aggregate(
    df=base.select(["ds", "y", TOTAL_LABEL] + LEVELS).to_pandas(),
    spec=SPEC,
)

n_days = base["ds"].n_unique()
needed = BT_HORIZON_DAYS + (N_WINDOWS - 1) * STEP_SIZE_DAYS
logger.info(
    "%d series across %d levels, %d days of history; backtest consumes %d trailing days, earliest window trains on ~%d",
    Y_df["unique_id"].nunique(), len(tags), n_days, needed, n_days - needed,
)

# CELL ********************

# ## 3. Walk-Forward Cross-Validation
#
# One `cross_validation()` call handles all windows and all series. Output has a `cutoff` column (last training date of each window) plus the actual `y` for every held-out day. `fitted=True` retains per-window insample fitted values — MinT needs each window's residuals computed **only from that window's training data** (no leakage from the held-out period).

# CELL ********************

models = [
    MSTL(season_length=7, trend_forecaster=AutoARIMA(max_p=3, max_q=3, max_d=1)),
]

sf = StatsForecast(models=models, freq="D", n_jobs=-1)

logger.info("Cross-validating: %d windows x %d-day horizon, step %d", N_WINDOWS, BT_HORIZON_DAYS, STEP_SIZE_DAYS)
cv_df = sf.cross_validation(
    df=Y_df,
    h=BT_HORIZON_DAYS,
    n_windows=N_WINDOWS,
    step_size=STEP_SIZE_DAYS,
    fitted=True,
)
cv_fitted_df = sf.cross_validation_fitted_values()

cutoffs = sorted(cv_df["cutoff"].unique())
logger.info("%d holdout records across cutoffs: %s", len(cv_df), [str(c)[:10] for c in cutoffs])

# CELL ********************

# ## 4. Reconcile Each Window
#
# `reconcile()` has no concept of cutoffs, so each window is reconciled separately with its own insample fitted values, then stitched back together with the `cutoff` column reattached.

# CELL ********************

hrec = HierarchicalReconciliation(reconcilers=[
    BottomUp(),
    MinTrace(method="mint_shrink", nonnegative=True),
])

rec_windows = []
for cutoff in cutoffs:
    y_hat_w = cv_df.loc[cv_df["cutoff"] == cutoff].drop(columns=["cutoff", "y"])
    y_fitted_w = cv_fitted_df.loc[cv_fitted_df["cutoff"] == cutoff].drop(columns=["cutoff"])
    rec_w = hrec.reconcile(Y_hat_df=y_hat_w, Y_df=y_fitted_w, S_df=S_df, tags=tags)
    rec_w["cutoff"] = cutoff
    rec_windows.append(rec_w)
    logger.info("Reconciled window %s", str(cutoff)[:10])

rec_df = pd.concat(rec_windows, ignore_index=True)

# reattach held-out actuals
rec_df = rec_df.merge(
    cv_df[["unique_id", "ds", "cutoff", "y"]],
    on=["unique_id", "ds", "cutoff"],
    how="left",
)

MODEL_COLS = [c for c in rec_df.columns if c not in ("unique_id", "ds", "cutoff", "y")]
logger.info("Models under test: %s", MODEL_COLS)

# CELL ********************

# ## 5. Accuracy by Hierarchy Level
#
# `evaluate()` scores each hierarchy level separately (pooled across windows). **Read MAPE only at total/division levels** — component-level series have genuine zero-cost days where MAPE is undefined/explosive; WAPE in the next section is the metric to trust down the tree.

# CELL ********************

eval_df = evaluate(
    df=rec_df.drop(columns=["cutoff"]),
    metrics=[mape, rmse],
    tags=tags,
)

display(eval_df)

# CELL ********************

# ## 6. WAPE by Level + Horizon Degradation Curve
#
# WAPE = Σ|error| / Σ|actual| — robust to zero-cost days, weighted toward the spend that matters. The degradation curve buckets days-ahead to show where each model's credibility runs out (this is what should set expectations for the 365-day live forecast).

# CELL ********************

LEVEL_BY_DEPTH = {i: name for i, name in enumerate([TOTAL_LABEL] + LEVELS)}

long = (
    pl.from_pandas(rec_df)
    .unpivot(
        index=["unique_id", "ds", "cutoff", "y"],
        on=MODEL_COLS,
        variable_name="model_id",
        value_name="yhat",
    )
    .with_columns(
        pl.col("unique_id").str.count_matches("/")
          .replace_strict(LEVEL_BY_DEPTH, return_dtype=pl.Utf8).alias("level"),
        (pl.col("ds") - pl.col("cutoff")).dt.total_days().alias("days_ahead"),
    )
)

bucket_expr = pl.lit(None, dtype=pl.Utf8)
for lo, hi, label in reversed(HORIZON_BUCKETS):
    bucket_expr = (
        pl.when(pl.col("days_ahead").is_between(lo, hi))
        .then(pl.lit(label))
        .otherwise(bucket_expr)
    )
long = long.with_columns(bucket_expr.alias("horizon_bucket"))

wape = (pl.col("yhat") - pl.col("y")).abs().sum() / pl.col("y").abs().sum()

wape_by_level = (
    long.group_by(["level", "model_id"])
    .agg(wape.alias("wape"))
    .sort(["level", "wape"])
)
display(wape_by_level.pivot(values="wape", index="level", on="model_id"))

degradation = (
    long.group_by(["level", "model_id", "horizon_bucket"])
    .agg(wape.alias("wape"))
    .sort(["level", "model_id", "horizon_bucket"])
)
display(
    degradation.filter(pl.col("level").is_in([TOTAL_LABEL, "division"]))
    .pivot(values="wape", index=["level", "model_id"], on="horizon_bucket")
)

# CELL ********************

# ## 7. Persist Metrics — `gold.forecast_accuracy`
#
# One long-format record per (level, model, metric, horizon bucket), stamped with `run_date` and the backtest configuration. The write replaces same-`run_date` rows (idempotent rerun) while accumulating history across dates — that history is what drift detection (roadmap item 9) will consume.

# CELL ********************

run_date = datetime.now().date()
run_meta = [
    pl.lit(run_date).alias("run_date"),
    pl.lit(BT_HORIZON_DAYS).alias("bt_horizon_days"),
    pl.lit(N_WINDOWS).alias("n_windows"),
    pl.lit(STEP_SIZE_DAYS).alias("step_size_days"),
]

metrics_pl = pl.concat([
    wape_by_level.with_columns(
        pl.lit(None, dtype=pl.Utf8).alias("horizon_bucket"),
        pl.lit("wape").alias("metric"),
        pl.col("wape").alias("value"),
    ).select(["level", "model_id", "metric", "horizon_bucket", "value"]),
    degradation.with_columns(
        pl.lit("wape").alias("metric"),
        pl.col("wape").alias("value"),
    ).select(["level", "model_id", "metric", "horizon_bucket", "value"]),
]).with_columns(run_meta)

metrics_pl.write_delta(
    f"{GOLD_ROOT}/{METRICS_TABLE}",
    mode="overwrite",
    engine="rust",
    delta_write_options={"predicate": f"run_date = '{run_date}'"},
)

logger.info("Wrote %d metric rows to %s.%s for run_date %s", len(metrics_pl), SCHEMA_NAME, METRICS_TABLE, run_date)

# CELL ********************

# ## 8. Verdict
#
# Headline comparison: which model wins at each level, judged on WAPE. If MinTrace wins at aggregate levels without losing at component level, adopt it as the published model in `focus_cost_forecast_hierarchical.ipynb`.

# CELL ********************

winners = (
    wape_by_level.sort("wape")
    .group_by("level", maintain_order=True)
    .first()
)
display(winners)
