"""
Hosting Directory — Fabric User Data Function
=============================================

Serves the build pipeline path. The directory UX (Power App) connects to
Fabric SQL directly — dropdowns bind to the lookup tables, Power Fx builds the
ServiceID, and integrity is enforced by database constraints (see
directory_schema.sql). This UDF provides the callable endpoint the pipeline
uses to validate a ServiceID and render its tag block.

  - resolve_service_id : returns whether a ServiceID exists (lookup, no writes)
  - render_bicep_tags  : validates the ServiceID resolves and the environment
                         is allowed, then returns the Bicep tag block. Unknown
                         ServiceID returns a handled error; the function never
                         creates a ServiceID.

SDK ref: https://learn.microsoft.com/en-us/fabric/data-engineering/user-data-functions/python-programming-model

RECONCILE BEFORE DEPLOY:
  - CONNECTION_ALIAS = the SQL data connection alias from Manage connections.
  - T_DIRECTORY / COL_* = your live table + columns. Brackets tolerate spaces
    in the name either way.
"""

import fabric.functions as fn

udf = fn.UserDataFunctions()

# --- reconcile to live schema ---
CONNECTION_ALIAS = "HubData"
T_DIRECTORY      = "Directory"
COL_SERVICE_ID   = "ServiceID"
COL_PLATFORM_ID  = "PlatformID"
COL_DIVISION_ID  = "DivisionID"
COL_COST_CENTRE  = "CostCentre"

ALLOWED_ENVIRONMENTS = {"dev", "test", "qa", "staging", "prod"}


def _norm(value: str) -> str:
    return (value or "").strip().upper()


@udf.connection(argName="dbconn", alias="HubData")
@udf.function()
def resolve_service_id(serviceId: str, dbconn: fn.FabricSqlConnection) -> dict:
    """Build-pipeline lookup. Returns whether the ServiceID resolves and its
    attributes. Creates nothing."""
    conn = dbconn.connect()
    try:
        sql = (
            f"SELECT {COL_SERVICE_ID} AS serviceId, {COL_PLATFORM_ID} AS platformId, "
            f"{COL_DIVISION_ID} AS divisionId, {COL_COST_CENTRE} AS costCentre "
            f"FROM {T_DIRECTORY} "
            f"WHERE UPPER(LTRIM(RTRIM({COL_SERVICE_ID}))) = ?"
        )
        cur = conn.cursor()
        cur.execute(sql, (_norm(serviceId),))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        if not rows:
            return {"exists": False, "serviceId": serviceId}
        rows[0]["exists"] = True
        return rows[0]
    finally:
        conn.close()


@udf.connection(argName="dbconn", alias="HubData")
@udf.function()
def render_bicep_tags(serviceId: str, environment: str,
                      dbconn: fn.FabricSqlConnection) -> str:
    """The control gate. Validate ServiceID resolves and environment is allowed,
    then return the Bicep tag block to inject into IaC. Hard-fail otherwise."""
    env = (environment or "").strip().lower()
    if env not in ALLOWED_ENVIRONMENTS:
        raise fn.UserThrownError(
            f"Environment '{environment}' is not allowed.",
            {"allowed": sorted(ALLOWED_ENVIRONMENTS)})

    conn = dbconn.connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT 1 FROM {T_DIRECTORY} "
            f"WHERE UPPER(LTRIM(RTRIM({COL_SERVICE_ID}))) = ?",
            (_norm(serviceId),))
        found = cur.fetchone() is not None
        cur.close()
        if not found:
            raise fn.UserThrownError(
                f"ServiceID '{serviceId}' does not resolve in the Hosting Directory. "
                f"Register the service in the directory before deploying.",
                {"serviceId": serviceId, "action": "create_in_directory_ux"})
    finally:
        conn.close()

    return ("tags: {\n"
            f"  ServiceID: '{_norm(serviceId)}'\n"
            f"  Environment: '{env}'\n"
            "}")
