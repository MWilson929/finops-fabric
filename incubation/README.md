# incubation/

Work-in-progress Fabric notebooks that will graduate to `notebooks/` once mature, but are **not deployed by CICD today**.

Each notebook here carries the same canonical name (per [`docs/naming_standards.md`](../docs/naming_standards.md)) that it will graduate to. Graduation is a single `git mv` operation, after deleting the predecessor in `notebooks/`.

See [`docs/notebook_standards.md`](../docs/notebook_standards.md) → "Where notebooks live" for the governing rule. Nothing else lives here.

## Today's incubation residents

| Notebook | Graduates by replacing | Gating maturity step |
|---|---|---|
| `esg_bronze_carbon_emissions` | `notebooks/esg_bronze_carbon_emissions` | Refactor onto the `finops-core` package, tested |
| `fcst_gold_forecast_hierarchical` | (new slot in `notebooks/`) | Hierarchical forecasting proven against real data via the accuracy backtest |
