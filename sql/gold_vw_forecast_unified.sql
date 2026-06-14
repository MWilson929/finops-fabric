-- gold.vw_forecast_unified
-- Unions hierarchical actuals (gold.forecast_input) and reconciled forecasts
-- (gold.forecast_reconciled) for Power BI consumption.
-- Consumers MUST filter on `level` (and `model_id` for forecasts) before
-- aggregating — the tables contain every hierarchy level.

CREATE OR REPLACE VIEW gold.vw_forecast_unified AS

SELECT
    ds AS date,
    unique_id,
    level,
    division,
    platform,
    workload,
    component,
    y AS cost,
    'actual' AS record_type,
    CAST(NULL AS STRING) AS model_id,
    CAST(NULL AS TIMESTAMP) AS forecast_generated_at
FROM gold.forecast_input

UNION ALL

SELECT
    ds AS date,
    unique_id,
    level,
    division,
    platform,
    workload,
    component,
    yhat AS cost,
    'forecast' AS record_type,
    model_id,
    forecast_generated_at
FROM gold.forecast_reconciled;
