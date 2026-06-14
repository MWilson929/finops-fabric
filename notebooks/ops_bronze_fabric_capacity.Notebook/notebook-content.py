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

# # ops_bronze_fabric_capacity
#
# **Purpose**: Ingests Capacity Unit consumption by workspace/item/operation/day from the Fabric Capacity Metrics app's semantic model into the FinOps Hub (control SVC-FAB 1.2).
#
# **Domain**: ops
# **Schema**: bronze
#
# **Inputs**:
# - "Fabric Capacity Metrics" semantic model (consolidated app install, owned by the FinOps service account per SVC-FAB 1.1), queried via sempy DAX
#
# **Output**: `bronze.monitoring_capacity`
#
# **Parameters** (pipeline via Variable Library):
# - `metrics_workspace` (string, "" = resolve from Variable Library)
# - `lookback_days` (int, 14 — the source's full retention window)
#
# **Trigger**: daily pipeline — **mandatory cadence**: the metrics model retains 14 days, so gaps beyond that are permanently unrecoverable (SVC-FAB 1.2)
#
# ---
#
# **Identity**: runs as the FinOps service principal, which needs Viewer + Build on the metrics app's semantic model and the tenant settings permitting SP XMLA/API access. The app itself refreshes under the FinOps *service account* (interactive-OAuth connector — SPs cannot refresh it); this notebook only reads.
#
# **Schema contract**: the metrics app's internal model is *not a public API* and changes between app versions. `EXPECTED_SCHEMA` below was **calibrated 2026-06-12 against a live app install** (via DAX `INFO` functions over executeQueries) — fact table `Metrics By Item Operation And Day`, friendly-cased columns. Section 3 re-validates the contract against the live model on every run and fails with a printed diff before extracting. On an app upgrade: read the diff, adjust `EXPECTED_SCHEMA`/`DAX_QUERIES`/`RENAME`, bump `PINNED_APP_VERSION`.
#
# Extraction is deliberately **relationship-agnostic**: the fact is scraped on its own ID columns and the three small dimensions (`Capacities`, `Workspaces`, `Items`) are scraped separately and joined in Polars — no assumptions about the model's internal relationship keys.

# CELL ********************

%%configure -f
{
    "vCores": 4
}

# CELL ********************

# Install finops-core from the Azure DevOps Artifact feed (PAT resolved from Key Vault).
# sempy, polars and delta-rs are in the Fabric runtime.
_lib = notebookutils.variableLibrary.getLibrary("VariableLib")
_feed_pat = notebookutils.credentials.getSecret(_lib.key_vault_url, _lib.ado_feed_pat_secret_name)
get_ipython().run_line_magic(
    "pip",
    "install finops-core "
    f"--index-url=https://feed:{_feed_pat}@pkgs.dev.azure.com/"
    f"{_lib.ado_organization}/{_lib.ado_project}/_packaging/{_lib.ado_artifactory_feed}/pypi/simple/",
)
del _feed_pat

# CELL ********************

import logging
import re
from datetime import datetime, timezone

import polars as pl
import sempy.fabric as fabric

from finops_core import get_var, load_variable_library, write_delta

logger = logging.getLogger(__name__)

# PARAMETERS CELL ********************

metrics_workspace = ""   # "" = take from Variable Library (finops platform workspace)
lookback_days = 14       # source retention; no point asking for more

# CELL ********************

# ## 1. Configuration
#
# `EXPECTED_SCHEMA`, `DAX_QUERIES` and `RENAME` are the version-pinned contract with the metrics app's internal model. Section 3 enforces it. Update them together when the app is upgraded.

# CELL ********************

VariableLib = load_variable_library("VariableLib")
finopshub_root_path = get_var(VariableLib, "finopshub_root_path")
if not metrics_workspace:
    metrics_workspace = get_var(VariableLib, "capacity_metrics_workspace")

capacity_table_path = f"{finopshub_root_path.rstrip('/')}/bronze/monitoring_capacity"

METRICS_DATASET = "Fabric Capacity Metrics"
FACT = "Metrics By Item Operation And Day"
PINNED_APP_VERSION = "calibrated-2026-06-12"  # bump deliberately after each app upgrade recalibration

EXPECTED_SCHEMA = {
    "Capacities": ["Capacity Id", "Capacity name", "SKU", "Region", "State"],
    "Workspaces": ["Workspace Id", "Workspace name"],
    "Items": ["Item Id", "Item name", "Item kind", "Billable type"],
    FACT: [
        "Capacity Id", "Workspace Id", "Item Id", "Operation name", "Date",
        "CU (s)", "Duration (s)", "Operations", "Throttling (min)",
        "Successful operations", "Failed operations", "Rejected operations",
    ],
}

DAX_QUERIES = {
    "fact": f"""
EVALUATE
SUMMARIZECOLUMNS(
    '{FACT}'[Capacity Id],
    '{FACT}'[Workspace Id],
    '{FACT}'[Item Id],
    '{FACT}'[Operation name],
    '{FACT}'[Date],
    FILTER(VALUES('{FACT}'[Date]), '{FACT}'[Date] >= TODAY() - {{lookback_days}}),
    "cu_seconds", SUM('{FACT}'[CU (s)]),
    "duration_seconds", SUM('{FACT}'[Duration (s)]),
    "operation_count", SUM('{FACT}'[Operations]),
    "throttling_minutes", SUM('{FACT}'[Throttling (min)]),
    "successful_operations", SUM('{FACT}'[Successful operations]),
    "failed_operations", SUM('{FACT}'[Failed operations]),
    "rejected_operations", SUM('{FACT}'[Rejected operations])
)
""",
    "capacities": """
EVALUATE
SELECTCOLUMNS(Capacities,
    "Capacity Id", Capacities[Capacity Id],
    "capacity_name", Capacities[Capacity name],
    "capacity_sku", Capacities[SKU],
    "capacity_region", Capacities[Region],
    "capacity_state", Capacities[State])
""",
    "workspaces": """
EVALUATE
SELECTCOLUMNS(Workspaces,
    "Workspace Id", Workspaces[Workspace Id],
    "workspace_name", Workspaces[Workspace name])
""",
    "items": """
EVALUATE
SELECTCOLUMNS(Items,
    "Item Id", Items[Item Id],
    "item_name", Items[Item name],
    "item_kind", Items[Item kind],
    "billable_type", Items[Billable type])
""",
}

# friendly scraped names -> house snake_case
RENAME = {
    "Capacity Id": "capacity_id",
    "Workspace Id": "workspace_id",
    "Item Id": "item_id",
    "Operation name": "operation_name",
    "Date": "usage_date",
}

def normalise_columns(pdf):
    """sempy returns 'Table[Col]' or '[alias]' headers; reduce to the bracket content, then RENAME."""
    pdf.columns = [re.sub(r"^.*\[([^\]]+)\]$", r"\1", c) for c in pdf.columns]
    return pdf.rename(columns=RENAME)

logger.info("Metrics source: '%s' in workspace '%s'", METRICS_DATASET, metrics_workspace)

# CELL ********************

# ## 2. Locate the Semantic Model

# CELL ********************

datasets = fabric.list_datasets(workspace=metrics_workspace)
if METRICS_DATASET not in set(datasets["Dataset Name"]):
    raise RuntimeError(
        f"Semantic model '{METRICS_DATASET}' not found in workspace '{metrics_workspace}'. "
        f"Models present: {sorted(datasets['Dataset Name'])}"
    )
logger.info("Found semantic model '%s'", METRICS_DATASET)

# CELL ********************

# ## 3. Validate the Model Contract
#
# Compares `EXPECTED_SCHEMA` against the live model and fails with a full diff before any extraction — an app upgrade becomes an explicit, fixable failure instead of silent corruption.

# CELL ********************

live_tables = set(fabric.list_tables(dataset=METRICS_DATASET, workspace=metrics_workspace)["Name"])

problems = []
for table, expected_cols in EXPECTED_SCHEMA.items():
    if table not in live_tables:
        problems.append(f"missing table: {table}")
        continue
    live_cols = set(
        fabric.list_columns(dataset=METRICS_DATASET, table=table, workspace=metrics_workspace)["Column Name"]
    )
    for col in expected_cols:
        if col not in live_cols:
            problems.append(f"missing column: {table}[{col}] (live columns: {sorted(live_cols)})")

if problems:
    logger.error("Model contract violated. Live tables: %s", sorted(live_tables))
    raise RuntimeError(
        "Capacity Metrics model does not match EXPECTED_SCHEMA (app upgraded?). "
        f"Pinned: {PINNED_APP_VERSION}. Problems: " + "; ".join(problems)
    )
logger.info("Model contract OK against %s", PINNED_APP_VERSION)

# CELL ********************

# ## 4. Extract and Join
#
# Fact on its own ID columns; dimensions separately; joins in Polars. `Items` can carry multiple snapshots per item (it has a `Timestamp`), so it's deduplicated on `item_id` before joining.

# CELL ********************

ingestion_ts = datetime.now(timezone.utc)
snapshot_date = ingestion_ts.date()

def scrape(name):
    dax = DAX_QUERIES[name].format(lookback_days=lookback_days)
    pdf = normalise_columns(fabric.evaluate_dax(dataset=METRICS_DATASET, dax_string=dax, workspace=metrics_workspace))
    logger.info("%s: %d rows", name, len(pdf))
    return pl.from_pandas(pdf)

fact = scrape("fact")
if fact.is_empty():
    raise RuntimeError("Fact extraction returned zero rows — check the app's refresh and the SP's Build permission")

capacities = scrape("capacities").unique(subset=["capacity_id"])
workspaces = scrape("workspaces").unique(subset=["workspace_id"])
items = scrape("items").unique(subset=["item_id"])

df = (
    fact
    .join(capacities, on="capacity_id", how="left")
    .join(workspaces, on="workspace_id", how="left")
    .join(items, on="item_id", how="left")
    .with_columns(
        pl.col("usage_date").cast(pl.Date),
        pl.lit(ingestion_ts).alias("ingestion_timestamp"),
        pl.lit(f"{METRICS_DATASET} ({PINNED_APP_VERSION}) in {metrics_workspace}").alias("source_file"),
        pl.lit(snapshot_date).alias("snapshot_date"),
    )
)

logger.info(
    "Scraped %d fact rows: %d capacities, %d workspaces, %s to %s",
    len(df), df["capacity_id"].n_unique(), df["workspace_id"].n_unique(),
    df["usage_date"].min(), df["usage_date"].max(),
)

# CELL ********************

# ## 5. Freshness Gate
#
# The scrape can only be as fresh as the app's last refresh. If the newest usage date is stale, the app's refresh (owned by the service account) is broken — fail before writing so the pipeline alerts while the 14-day window still covers the gap.

# CELL ********************

MAX_STALENESS_DAYS = 2  # metrics data lags up to ~1 day; beyond 2 means the app refresh is broken

newest = df["usage_date"].max()
staleness = (snapshot_date - newest).days
if staleness > MAX_STALENESS_DAYS:
    raise RuntimeError(
        f"Metrics data is {staleness} days stale (newest usage_date {newest}). "
        "The Capacity Metrics app refresh is likely broken — fix within the 14-day window or data is lost."
    )
logger.info("Freshness OK: newest usage_date %s (%d day(s) behind)", newest, staleness)

# CELL ********************

# ## 6. Write Snapshot — `bronze.monitoring_capacity`
#
# Snapshot-append with same-day replace (idempotent rerun). Overlapping 14-day windows are kept deliberately: restatements between snapshots are visible, and silver dedupes to the latest snapshot per (capacity, item, operation, day).

# CELL ********************

write_delta(
    df,
    capacity_table_path,
    replace_where=f"snapshot_date = '{snapshot_date}'",
    partition_by=["snapshot_date"],
)
logger.info("Written %d rows to bronze.monitoring_capacity, snapshot_date=%s", len(df), snapshot_date)

# CELL ********************

# ## 7. Continuity Check
#
# Per capacity: the previous snapshots' newest usage_date and this snapshot's oldest must overlap or abut. A gap means days fell out of the 14-day window unobserved — permanently unrecoverable, so the run fails loudly for the pipeline to alert on (SVC-FAB 1.2 evidence).

# CELL ********************

existing = pl.scan_delta(capacity_table_path).filter(pl.col("snapshot_date") < snapshot_date)
prior = existing.group_by("capacity_id").agg(pl.col("usage_date").max().alias("prior_max")).collect()

if prior.is_empty():
    logger.info("First snapshot — no continuity to check")
else:
    current = df.group_by("capacity_id").agg(pl.col("usage_date").min().alias("new_min"))
    gaps = (
        prior.join(current, on="capacity_id", how="inner")
        .with_columns((pl.col("new_min") - pl.col("prior_max")).dt.total_days().alias("gap_days"))
        .filter(pl.col("gap_days") > 1)
    )
    if gaps.is_empty():
        logger.info("Continuity OK across %d previously-seen capacities", len(prior))
    else:
        display(gaps)
        raise RuntimeError(
            f"Capacity telemetry continuity broken for {len(gaps)} capacity(ies) — "
            "days have aged out of the 14-day window unobserved; investigate run cadence"
        )

display(
    df.group_by(["capacity_name", "usage_date"]).agg(pl.col("cu_seconds").sum().alias("cu_seconds"))
    .sort(["capacity_name", "usage_date"])
    .head(20)
)
