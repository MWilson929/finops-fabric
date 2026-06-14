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

# # fcst_gold_forecast_changepoints
#
# **Purpose**: Detects structural breaks in cost (PELT on MSTL trend) at every Service_ID hierarchy level and quantifies/classifies each change for Power BI.
#
# **Domain**: fcst
# **Schema**: gold
#
# **Inputs**:
# - `focus_cost` (Delta table — pre-dates LAKEHOUSE_TABLES.md; update `SOURCE_TABLE` when it migrates to `silver.focusazure_normalised`)
#
# **Output**: `gold.forecast_changepoints` (one row per detected change), `gold.forecast_segments` (one row per stable period)
#
# **Parameters** (in-notebook constants now; move to Variable Library on promotion):
# - `WORKSPACE_GUID` (string)
# - `PENALTY` (float, 10), `MIN_SEGMENT_DAYS` (int, 14), `JUMP` (int, 7), `MIN_HISTORY_DAYS` (int, 90)
#
# **Trigger**: ad-hoc (weekly pipeline on promotion)
#
# ---
#
# Per series: **MSTL** strips weekly (and yearly, when ≥2 years of history) seasonality so a Monday spike never registers as a break; **PELT** (`ruptures`) segments the *standardised* trend so one penalty works across series of wildly different cost scales; each break is quantified on **raw cost** (mean daily spend before vs after) and classified `increase` / `decrease` / `launch` / `shutdown` — the lifecycle labels feed roadmap item 10's workload-lifecycle angle.
#
# ## Power BI consumption
#
# Both outputs carry `level` + the four path columns and join to `gold.forecast_input` on `unique_id`. Suggested visuals: actuals line with `changepoint_date` markers sized by `abs_change` (slicers on division/platform); `gold.forecast_segments` as a step-line overlay showing the level cost sat at between breaks; a matrix sorted by `abs_change` descending as the "what just happened" report.
#
# ## Tuning
#
# - `PENALTY` — higher = fewer, bigger breaks. The first knob to raise if output is noisy
# - `MIN_SEGMENT_DAYS` — nothing shorter than this counts as a regime (default a fortnight)
# - `JUMP` — candidate-break grid (default 7, week-aligned; also a big speedup)

# CELL ********************

# ## 0. Node Sizing and Libraries
#
# Polars and delta-rs are in the Fabric runtime; `ruptures`, `statsmodels` and `hierarchicalforecast` are not — inline install for now, ADO artifact feed via the environment definition on promotion.

# CELL ********************

%%configure -f
{
    "vCores": 8
}

# CELL ********************

%pip install -q ruptures statsmodels "hierarchicalforecast>=1.2"

# CELL ********************

import logging
from datetime import datetime

import numpy as np
import polars as pl
import ruptures as rpt
from hierarchicalforecast.utils import aggregate
from statsmodels.tsa.seasonal import MSTL

logger = logging.getLogger(__name__)

# CELL ********************

# ## 1. Parameters
#
# Source/hierarchy parameters mirror `focus_cost_forecast_hierarchical.ipynb` — keep them in sync.

# CELL ********************

# ---- Source / output tables ----
LAKEHOUSE_NAME     = "FinOpsHub"
SOURCE_TABLE       = "focus_cost"             # legacy name; silver.focusazure_normalised post-migration
SCHEMA_NAME        = "gold"
CHANGEPOINTS_TABLE = "forecast_changepoints"  # gold.forecast_changepoints
SEGMENTS_TABLE     = "forecast_segments"      # gold.forecast_segments

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

# ---- Detection configuration ----
PENALTY          = 10    # PELT penalty on standardised trend; raise to report fewer/bigger breaks
MIN_SEGMENT_DAYS = 14    # minimum days between change points
JUMP             = 7     # candidate break grid (week-aligned)
MIN_HISTORY_DAYS = 90    # skip series with less history than this

# launch/shutdown classification: 'after' (or 'before') mean below this share of the other side
LIFECYCLE_RATIO = 0.05

# ---- Lakehouse paths ----
WORKSPACE_GUID = "PLACEHOLDER_WORKSPACE_ID"
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
Y_pl = pl.from_pandas(Y_df).sort(["unique_id", "ds"])

logger.info(
    "%d series across %d levels, %s to %s",
    Y_pl["unique_id"].n_unique(), len(tags), Y_pl["ds"].min(), Y_pl["ds"].max(),
)

# CELL ********************

# ## 3. Detect Change Points (MSTL trend → PELT)
#
# Per series: decompose, standardise the trend, segment with PELT (`rbf` cost — robust to scale/shape), then quantify each break on raw cost. Series that are too short or flat (e.g. all-zero padding) are skipped and counted.

# CELL ********************

changepoint_rows = []
segment_rows = []
skipped = {"too_short": 0, "flat": 0}

for (uid,), grp in Y_pl.group_by("unique_id", maintain_order=True):
    y = grp["y"].to_numpy().astype(float)
    ds = grp["ds"].to_list()
    n = len(y)

    if n < MIN_HISTORY_DAYS:
        skipped["too_short"] += 1
        continue

    # MSTL: weekly always; yearly only with >= 2 full cycles
    periods = [7, 365] if n >= 2 * 365 else [7]
    trend = MSTL(y, periods=periods).fit().trend

    std = trend.std()
    if std == 0 or np.isnan(std):
        skipped["flat"] += 1
        continue
    z = (trend - trend.mean()) / std

    # PELT breakpoints are segment END indices, last == n
    bkps = rpt.Pelt(model="rbf", min_size=MIN_SEGMENT_DAYS, jump=JUMP).fit(z).predict(pen=PENALTY)

    bounds = [0] + bkps  # segment i spans [bounds[i], bounds[i+1])
    seg_means = [float(y[bounds[i]:bounds[i + 1]].mean()) for i in range(len(bounds) - 1)]

    for i in range(len(bounds) - 1):
        segment_rows.append({
            "unique_id": uid,
            "segment_start": ds[bounds[i]],
            "segment_end": ds[bounds[i + 1] - 1],
            "segment_days": bounds[i + 1] - bounds[i],
            "daily_mean_cost": seg_means[i],
        })

    for i in range(1, len(bounds) - 1):  # each interior boundary is a change point
        before, after = seg_means[i - 1], seg_means[i]
        if after < LIFECYCLE_RATIO * before:
            change_type = "shutdown"
        elif before < LIFECYCLE_RATIO * after:
            change_type = "launch"
        elif after > before:
            change_type = "increase"
        else:
            change_type = "decrease"
        changepoint_rows.append({
            "unique_id": uid,
            "changepoint_date": ds[bounds[i]],
            "before_daily_mean": before,
            "after_daily_mean": after,
            "abs_change": abs(after - before),
            "pct_change": (after - before) / before if before != 0 else None,
            "change_type": change_type,
        })

logger.info(
    "Detected %d change points across %d segments; skipped %s",
    len(changepoint_rows), len(segment_rows), skipped,
)

# CELL ********************

# ## 4. Write Lakehouse Tables — `gold.forecast_changepoints`, `gold.forecast_segments`
#
# Full recompute each run → overwrite (idempotent). `detected_at` and the tuning parameters are stamped on every row so consumers can tell which configuration produced a given set of breaks.

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

run_meta = [
    pl.lit(datetime.now()).alias("detected_at"),
    pl.lit(PENALTY).alias("penalty"),
    pl.lit(MIN_SEGMENT_DAYS).alias("min_segment_days"),
]

changepoints_pl = with_hierarchy_cols(pl.from_dicts(changepoint_rows)).with_columns(run_meta)
segments_pl = with_hierarchy_cols(pl.from_dicts(segment_rows)).with_columns(run_meta)

changepoints_pl.write_delta(f"{GOLD_ROOT}/{CHANGEPOINTS_TABLE}", mode="overwrite", engine="rust")
segments_pl.write_delta(f"{GOLD_ROOT}/{SEGMENTS_TABLE}", mode="overwrite", engine="rust")

logger.info("Written %d rows to %s.%s", len(changepoints_pl), SCHEMA_NAME, CHANGEPOINTS_TABLE)
logger.info("Written %d rows to %s.%s", len(segments_pl), SCHEMA_NAME, SEGMENTS_TABLE)

# CELL ********************

# ## 5. Diagnostics — Top Movers
#
# The same view the Power BI report should lead with: biggest structural changes by absolute daily change.

# CELL ********************

display(changepoints_pl.group_by("change_type").len().sort("len", descending=True))

display(
    changepoints_pl
    .sort("abs_change", descending=True)
    .select([
        "changepoint_date", "level", "unique_id", "change_type",
        "before_daily_mean", "after_daily_mean", "abs_change", "pct_change",
    ])
    .head(20)
)
