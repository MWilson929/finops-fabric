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

# # finops_bronze_arg_topology
#
# **Purpose**: Lands Batch 1 configured Azure network topology from Azure Resource Graph as source-shaped `bronze.arg_topology_*` tables, across all configured tenants. These are the inputs the silver edge-generation layer turns into graph-ready relationship tables.
#
# **Domain**: finops
# **Schema**: bronze
#
# **Inputs**:
# - Azure Resource Graph (`POST /providers/Microsoft.ResourceGraph/resources`) per tenant, one focused KQL query per topology relationship family
# - The query catalogue is `finops_topology.arg.TOPOLOGY_QUERIES` (Batch 1: vnet subnets, vnet peerings, network interfaces, public IPs, vm nics, vm disks, nsg associations, private endpoint nics, private endpoint targets)
#
# **Output**: one `bronze.arg_topology_*` table per query (full-snapshot overwrite per run)
#
# **Parameters** (pipeline via Variable Library):
# - `tenants` (string, "" = all configured; or comma-separated prefixes e.g. "a,b")
# - `queries` (string, "" = whole catalogue; or comma-separated query names to run a subset)
#
# **Trigger**: scheduled pipeline alongside the other ARG inventory extracts (configured topology is a point-in-time snapshot; cadence is not safety-critical the way the 60-day usage window is).
#
# ---
#
# Built on **finops-core** (ARG auth + `$skipToken` paging via `finops_core.arm.paginate_resource_graph`, Delta writes) and **finops-topology** (the declarative KQL catalogue + generic runner). This notebook is a thin orchestrator: per tenant, run every catalogue query, stamp run metadata, and write each result to its own bronze table. No ARM/SDK calls — Resource Graph only. No silver edge generation or Fabric Graph here.
#
# Each query's `schema` is the table contract: `run_arg_query` conforms every tenant's result to it, so an empty or sparse tenant still produces a correctly-typed table and the per-table schema is stable across tenants and reruns.

# CELL ********************

%%configure -f
{
    "vCores": 4
}

# CELL ********************

# Install finops-core + finops-topology from the Azure DevOps Artifact feed
# (PAT resolved from Key Vault), then azure-identity from public PyPI.
_lib = notebookutils.variableLibrary.getLibrary("VariableLib")
_feed_pat = notebookutils.credentials.getSecret(_lib.key_vault_url, _lib.ado_feed_pat_secret_name)
get_ipython().run_line_magic(
    "pip",
    "install finops-core finops-topology "
    f"--index-url=https://feed:{_feed_pat}@pkgs.dev.azure.com/"
    f"{_lib.ado_organization}/{_lib.ado_project}/_packaging/{_lib.ado_artifactory_feed}/pypi/simple/",
)
del _feed_pat

%pip install azure-identity --quiet

# CELL ********************

import logging
from datetime import datetime, timezone

import polars as pl
from azure.identity import ClientSecretCredential

from finops_core import get_secret, get_var, load_variable_library, write_delta
from finops_topology.arg import TOPOLOGY_QUERIES, resource_graph_client, run_arg_query, stamp

logger = logging.getLogger(__name__)

# PARAMETERS CELL ********************

tenants = ""   # "" = all configured tenant prefixes; or "a" / "a,b"
queries = ""   # "" = whole catalogue; or comma-separated query names

# CELL ********************

# ## 1. Configuration
#
# Config-driven tenancy (same pattern as the other multi-tenant bronze notebooks): every tenant prefix with populated Variable Library entries is included; placeholders are skipped; the `tenants` parameter filters. The `queries` parameter optionally restricts the catalogue to a subset of query names.

# CELL ********************

TENANT_PREFIXES = ["a", "b"]
PLACEHOLDER_GUID = "00000000-0000-0000-0000-000000000000"

VariableLib = load_variable_library("VariableLib")
key_vault_url = get_var(VariableLib, "key_vault_url")
finopshub_root_path = get_var(VariableLib, "finopshub_root_path")
bronze_root = f"{finopshub_root_path.rstrip('/')}/bronze"

# Resolve the query set from the catalogue.
catalogue = {q.name: q for q in TOPOLOGY_QUERIES}
requested_queries = [q.strip() for q in queries.split(",") if q.strip()]
unknown_queries = set(requested_queries) - set(catalogue)
if unknown_queries:
    raise ValueError(f"Unknown query name(s) {sorted(unknown_queries)}. Known: {sorted(catalogue)}")
queries_in_scope = [catalogue[name] for name in requested_queries] if requested_queries else TOPOLOGY_QUERIES

# Resolve the tenant set.
requested_prefixes = [p.strip().lower() for p in tenants.split(",") if p.strip()]
unknown = set(requested_prefixes) - set(TENANT_PREFIXES)
if unknown:
    raise ValueError(f"Unknown tenant prefix(es) {sorted(unknown)}. Known: {TENANT_PREFIXES}")

tenant_configs = []
for prefix in TENANT_PREFIXES:
    tenant_id = get_var(VariableLib, f"{prefix}_tenant_id", "")
    client_id = get_var(VariableLib, f"{prefix}_client_id", "")
    secret_name = get_var(VariableLib, f"{prefix}_secret_name", "")

    configured = all([tenant_id, client_id, secret_name]) and tenant_id != PLACEHOLDER_GUID
    if not configured:
        logger.info("Tenant '%s' not configured in Variable Library - skipping", prefix)
        continue
    if requested_prefixes and prefix not in requested_prefixes:
        continue
    tenant_configs.append({
        "prefix": prefix,
        "label": f"Tenant {prefix.upper()}",
        "tenant_id": tenant_id,
        "client_id": client_id,
        "secret_name": secret_name,
    })

if not tenant_configs:
    raise ValueError(f"No configured tenants match request '{tenants}'")

logger.info(
    "Tenants in scope: %s | queries: %s",
    [c["label"] for c in tenant_configs],
    [q.name for q in queries_in_scope],
)

# CELL ********************

# ## 2. Extract — run the catalogue per tenant
#
# One ARG client per tenant (ARG sits on the ARM token/scope, so `resource_graph_client` is an ARM-authenticated REST client with shared retry/throttle handling). For each query, every tenant's conformed result is stamped with run metadata and collected; tables are written in the next cell. Omitting a subscription scope queries the credential's full accessible estate, matching `finops_bronze_arg_resources`.

# CELL ********************

def tenant_arg_client(cfg):
    credential = ClientSecretCredential(
        tenant_id=cfg["tenant_id"],
        client_id=cfg["client_id"],
        client_secret=get_secret(key_vault_url, cfg["secret_name"]),
    )
    return resource_graph_client(credential)

extracted_at = datetime.now(timezone.utc)
batch_id = extracted_at.strftime("%Y%m%dT%H%M%SZ")
snapshot_date = extracted_at.date()

# query name -> list of per-tenant frames
frames_by_query: dict[str, list[pl.DataFrame]] = {q.name: [] for q in queries_in_scope}

for cfg in tenant_configs:
    client = tenant_arg_client(cfg)
    logger.info("%s: running %d topology queries", cfg["label"], len(queries_in_scope))

    for query in queries_in_scope:
        df = run_arg_query(client, query)
        df = stamp(
            df,
            tenant_id=cfg["tenant_id"],
            tenant_label=cfg["label"],
            batch_id=batch_id,
            extracted_at=extracted_at,
            snapshot_date=snapshot_date,
        )
        frames_by_query[query.name].append(df)
        logger.info("  %s: %d rows", query.name, df.height)

# CELL ********************

# ## 3. Write — one `bronze.arg_topology_*` table per query
#
# Full-snapshot overwrite per run (same convention as `Resources_MultiTenant`): the bronze table reflects the latest ARG snapshot across all in-scope tenants. `finops_core.write_delta` handles schema merge; empty queries still write a correctly-typed table because the runner conformed them to the query schema. Each table is registered in the metastore for SQL access.

# CELL ********************

written = {}
for query in queries_in_scope:
    frames = frames_by_query[query.name]
    combined = pl.concat(frames, how="vertical") if frames else pl.DataFrame(schema=query.schema)
    table_path = f"{bronze_root}/{query.name}"

    write_delta(combined, table_path, mode="overwrite", skip_empty=False)
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {query.name} USING DELTA LOCATION '{table_path}'"
    )
    written[query.name] = combined.height
    logger.info("Wrote %d rows to bronze.%s", combined.height, query.name)

logger.info("Batch %s complete: %s", batch_id, written)

# CELL ********************

# ## 4. Validation
#
# Per-table row counts, per-tenant breakdown, and a sample. Endpoint completeness and orphan checks belong to the silver edge layer, which joins these extracts to the node tables; here we confirm the snapshot landed and is non-degenerate.

# CELL ********************

summary_rows = []
for query in queries_in_scope:
    frames = frames_by_query[query.name]
    combined = pl.concat(frames, how="vertical") if frames else pl.DataFrame(schema=query.schema)
    summary_rows.append({
        "table": query.name,
        "rows": combined.height,
        "tenants": combined["tenant_label"].n_unique() if combined.height else 0,
        "columns": combined.width,
    })

summary = pl.DataFrame(summary_rows).sort("table")
display(summary)

if summary.filter(pl.col("rows") > 0).is_empty():
    raise RuntimeError(
        "Every topology query returned zero rows across all tenants — "
        "check service-principal Resource Graph access and that the estate has network resources"
    )

# Show a per-tenant breakdown and a sample for the richest table.
busiest = summary.sort("rows", descending=True).row(0, named=True)["table"]
busiest_df = pl.concat(frames_by_query[busiest], how="vertical")
logger.info("Sample from the busiest table: bronze.%s", busiest)
display(
    busiest_df.group_by("tenant_label").agg(pl.len().alias("rows")).sort("tenant_label")
)
display(busiest_df.head(5))
