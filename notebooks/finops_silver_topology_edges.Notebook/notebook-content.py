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

# # finops_silver_topology_edges
#
# **Purpose**: Builds the Batch 1 graph-ready silver `topology_edge_*` tables from the bronze `arg_topology_*` extracts. Each edge table is one relationship type with the common ADR-0004 edge schema (stable `edge_id`, normalized endpoints, evidence/confidence, lifecycle timestamps), ready for Power BI bridge use, later Fabric Graph projection, and LLM reasoning.
#
# **Domain**: finops
# **Schema**: silver
#
# **Inputs**: bronze `arg_topology_*` tables produced by `finops_bronze_arg_topology`
#
# **Output**: one `silver.topology_edge_*` table per relationship (11 in Batch 1), full-snapshot overwrite per run
#
# **Parameters** (pipeline via Variable Library):
# - `edges` (string, "" = all Batch 1 edges; or comma-separated edge table names to build a subset)
#
# **Trigger**: scheduled pipeline immediately after `finops_bronze_arg_topology`.
#
# ---
#
# Built on **finops-topology**: the edge schema, the declarative `EDGE_SPECS`, and the generic `build_edge` transform live in the package and are unit-tested; this notebook is a thin orchestrator — read each bronze extract, build each edge, write each silver table, validate. No ARM/ARG calls here (configured topology is derived from the bronze snapshot). Endpoint IDs preserve original case to match node-table keys; the `*_normalized` columns and `edge_id` use lowercased IDs. Rows with null/empty endpoints are dropped and each table is deduped by `edge_id`.
#
# Deferred (later batches): load balancer, application gateway, firewall, NSG-rule evaluation, gold path tables, observed traffic, identity/RBAC, and Fabric Graph deployment.

# CELL ********************

%%configure -f
{
    "vCores": 4
}

# CELL ********************

# Install finops-core + finops-topology from the Azure DevOps Artifact feed
# (PAT resolved from Key Vault).
_lib = notebookutils.variableLibrary.getLibrary("VariableLib")
_feed_pat = notebookutils.credentials.getSecret(_lib.key_vault_url, _lib.ado_feed_pat_secret_name)
get_ipython().run_line_magic(
    "pip",
    "install finops-core finops-topology "
    f"--index-url=https://feed:{_feed_pat}@pkgs.dev.azure.com/"
    f"{_lib.ado_organization}/{_lib.ado_project}/_packaging/{_lib.ado_artifactory_feed}/pypi/simple/",
)
del _feed_pat

# CELL ********************

import logging
from datetime import datetime, timezone

import polars as pl

from finops_core import get_var, load_variable_library, write_delta
from finops_topology.edges import EDGE_SPECS, build_edge, validate_edge

logger = logging.getLogger(__name__)

# PARAMETERS CELL ********************

edges = ""   # "" = all Batch 1 edges; or comma-separated topology_edge_* names

# CELL ********************

# ## 1. Configuration
#
# Resolve the lakehouse paths and the edge set. The `edges` parameter optionally restricts the build to a subset of edge table names.

# CELL ********************

VariableLib = load_variable_library("VariableLib")
finopshub_root_path = get_var(VariableLib, "finopshub_root_path")
bronze_root = f"{finopshub_root_path.rstrip('/')}/bronze"
silver_root = f"{finopshub_root_path.rstrip('/')}/silver"

specs_by_name = {s.name: s for s in EDGE_SPECS}
requested = [e.strip() for e in edges.split(",") if e.strip()]
unknown = set(requested) - set(specs_by_name)
if unknown:
    raise ValueError(f"Unknown edge name(s) {sorted(unknown)}. Known: {sorted(specs_by_name)}")
specs_in_scope = [specs_by_name[name] for name in requested] if requested else EDGE_SPECS

observed_at = datetime.now(timezone.utc)
batch_id = observed_at.strftime("%Y%m%dT%H%M%SZ")

logger.info("Building %d edge tables: %s", len(specs_in_scope), [s.name for s in specs_in_scope])

# CELL ********************

# ## 2. Read bronze extracts
#
# Read each bronze `arg_topology_*` table once (several edges share a source, e.g. `arg_topology_network_interfaces` feeds the NIC→VM, NIC→subnet, and NIC→public-IP edges). A missing bronze table is tolerated — its edges build to empty and are reported in validation rather than failing the run.

# CELL ********************

needed_datasets = sorted({s.source_dataset for s in specs_in_scope})
bronze_frames = {}
for dataset in needed_datasets:
    path = f"{bronze_root}/{dataset}"
    try:
        bronze_frames[dataset] = pl.read_delta(path)
        logger.info("Read bronze.%s: %d rows", dataset, bronze_frames[dataset].height)
    except Exception as exc:  # table not yet produced — build its edges empty
        logger.warning("Could not read bronze.%s (%s) — its edges will be empty", dataset, exc)
        bronze_frames[dataset] = pl.DataFrame()

# CELL ********************

# ## 3. Build and write silver edge tables
#
# `build_edge` applies the full edge contract (normalize, stable `edge_id`, drop null endpoints, stamp provenance/lifecycle, dedupe). Full-snapshot overwrite per run; `edge_id` is stable, so the same relationship keeps its identity across reruns. Each table is registered in the metastore for SQL access.

# CELL ********************

edge_frames = {}
for spec in specs_in_scope:
    edge_df = build_edge(
        bronze_frames[spec.source_dataset],
        spec,
        batch_id=batch_id,
        observed_at=observed_at,
    )
    table_path = f"{silver_root}/{spec.name}"
    write_delta(edge_df, table_path, mode="overwrite", skip_empty=False)
    spark.sql(f"CREATE TABLE IF NOT EXISTS {spec.name} USING DELTA LOCATION '{table_path}'")
    edge_frames[spec.name] = edge_df
    logger.info("Wrote %d edges to silver.%s", edge_df.height, spec.name)

logger.info("Batch %s complete", batch_id)

# CELL ********************

# ## 4. Validation
#
# Per-edge invariants: row count, null endpoints (must be zero), duplicate `edge_id` (must be zero). `build_edge` guarantees the last two; the run fails if any table violates them. Orphan checks against node tables belong to a later step once the canonical node sources are confirmed.

# CELL ********************

report_rows = []
violations = []
for spec in specs_in_scope:
    metrics = validate_edge(edge_frames[spec.name])
    report_rows.append({"edge_table": spec.name, **metrics})
    if metrics["null_source_id"] or metrics["null_target_id"] or metrics["duplicate_edge_id"]:
        violations.append(spec.name)

report = pl.DataFrame(report_rows).sort("edge_table")
display(report)

if violations:
    raise RuntimeError(f"Edge invariant violation(s) in: {violations}")

total_edges = int(report["rows"].sum())
logger.info("Total edges across %d tables: %d", len(specs_in_scope), total_edges)
if total_edges == 0:
    logger.warning(
        "All edge tables are empty — confirm finops_bronze_arg_topology has run and "
        "the estate has network resources"
    )

# Sample from the richest edge table for a quick eyeball.
busiest = report.sort("rows", descending=True).row(0, named=True)["edge_table"]
if edge_frames[busiest].height:
    logger.info("Sample from the richest edge table: silver.%s", busiest)
    display(
        edge_frames[busiest]
        .select(
            "source_label", "source_id", "relationship_type",
            "target_label", "target_id", "confidence", "properties_json",
        )
        .head(5)
    )
