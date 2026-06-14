# Notebook Standards — FinOps Fabric Platform

This document defines how notebooks are written in this platform. Naming is covered separately in [naming_standards.md](naming_standards.md); this document covers content, structure, output discipline, and the engineering practices that apply inside the notebook.

These standards are enforced by code review. Items marked **must** are non-negotiable; items marked **should** are strong defaults that can be deviated from with a documented reason in PR.

## Where notebooks live

Notebooks live in exactly one of three places. Anything outside these three is deleted — git history is the archive.

| Folder | Purpose | CICD scope |
|---|---|---|
| `notebooks/` | Production: deployed by CICD to Fabric. The canonical name (per naming_standards.md) is reserved here. | Deployed |
| `incubation/` | Work-in-progress destined for `notebooks/`. Uses the *same* canonical name it will graduate to, so promotion is a single `git mv`. | Not deployed |
| `tools/` | Utilities and developer scripts (data synth, format converters, bulk renamers). Not deployable Fabric items; can be `.py` or `.ipynb`. | Not deployed |

**The incubation rule:** the only way out of `incubation/` is graduation to `notebooks/` (delete the predecessor + `git mv` the incubation copy up) or deletion. No sideways drift, no parallel maintenance forever, no using `incubation/` as a holding pen for "maybe useful one day" — that's what git history is for.

## Header

Every notebook begins with a markdown cell containing structured intent. Git owns history; the header owns intent.

**Required fields:**

```markdown
# {notebook_name}

**Purpose**: One sentence describing what this notebook produces.

**Domain**: {domain token from naming_standards.md}
**Schema**: {bronze | silver | gold}

**Inputs**:
- `schema.table_name` (Delta table)
- External API or file source if applicable

**Output**: `schema.table_name`

**Parameters** (from calling pipeline, via Variable Library):
- `parameter_name` (type, default value)

**Trigger**: Pipeline name and schedule, or "ad-hoc" if applicable
```

**Do not include** created date, last modified date, author name, version number, or change history. Git already has all of these. Long boilerplate descriptions ("This notebook is part of the FinOps platform...") waste reader attention.

## Body Structure

**Cells should be focused.** One logical operation per cell. This aids debugging because cells can be rerun individually and execution output is scoped to the operation.

**Markdown cells provide structural narrative.** Major sections begin with a markdown cell explaining what the next block of code accomplishes and, where non-obvious, *why* a particular approach was chosen. Markdown cells are not executed; they are documentation embedded in the artifact, optimised for the next reader.

**Code comments handle line-level concerns.** Use comments to flag non-obvious gotchas, document parameter expectations, or capture decisions the code itself can't convey (e.g. an explicit cast preventing a schema drift downstream). Do not use comments to narrate what the code already says.

**The deletion test:** if removing a comment or markdown cell loses no information, delete it.

## Compute Choice

**Polars on single-node Python is the default.** Use `polars` for all dataframe operations unless Spark is justified.

**Spark is justified when:**

- Data size exceeds approximately 50GB in memory (significantly larger than the FOCUS fact table)
- Joins require shuffles across truly large datasets
- Streaming workloads with windowed aggregations
- Existing Spark-only library is required (rare in this platform)

Below these thresholds, single-node Polars is faster, cheaper, easier to debug, and avoids cluster startup time. The FOCUS fact table at current size is comfortably single-node territory.

**Document the choice in the PR description** if you select Spark for a new notebook. The default is Polars; deviation requires reasoning.

## Secrets

**All secrets must be retrieved from Azure Key Vault at runtime.** No exceptions.

**Do:**

```python
from notebookutils import mssparkutils
secret = mssparkutils.credentials.getSecret("https://kv-finops-prod.vault.azure.net/", "secret-name")
```

**Do not:**

- Hardcode secrets in notebook cells
- Store secrets in environment variables, Variable Library, or workspace settings
- Commit `.env` files or secret-containing config files to the repo
- Pass secrets as parameters from calling pipelines

**Key Vault access** is granted to the workspace identity. Adding a new secret means adding it to the appropriate Key Vault (`kv-finops-{env}`) and granting workspace identity read access. Do not create per-notebook Key Vaults.

## Parameterisation

**Environment-specific configuration belongs in the Fabric Variable Library**, not in the notebook code.

**Use Variable Library for:**

- Workspace IDs, lakehouse names, schema names that differ across dev/PPE/prod
- Schedule parameters (lookback windows, forecast horizons) that vary by environment
- Feature flags that toggle behaviour between environments
- External system endpoints (API URLs, storage account names)

**Keep in notebook code:**

- Business logic constants (FOCUS column names, fixed enumerations)
- Schema definitions
- Anything that does not legitimately vary across environments

**Pattern:**

```python
from notebookutils import variableLibrary
lookback_months = variableLibrary.get("finops/lookback_months")
```

## Imports

**Imports go in the first code cell**, grouped and ordered as standard Python:

1. Standard library
2. Third-party packages
3. Internal wheel packages (`finops_utils`, etc.)
4. Relative imports (rare in notebooks)

Blank line between groups. No inline imports inside later cells unless absolutely necessary.

```python
import datetime as dt
from pathlib import Path

import polars as pl
from statsforecast import StatsForecast

from finops_utils.focus import normalise_billing
from finops_utils.delta import safe_overwrite
```

## Reusable Code

**Reusable functions must be packaged as Python wheels in the ADO Artifact feed**, not duplicated across notebooks.

**The rule:** a function used in three or more notebooks belongs in a wheel. A function used in one or two notebooks stays in the notebook. Premature wheel-packaging adds release coordination overhead; over-duplication adds maintenance burden. Three is the threshold where the wheel earns its place.

**Wheel contents:**

- Stable, tested, reusable functions
- Schema definitions used across multiple notebooks
- Domain-specific helpers (FOCUS normalisation, Delta write helpers, forecasting utilities)

**Notebook contents:**

- Orchestration: which functions get called in what order
- Configuration: parameter resolution, environment-specific glue
- One-off transformations specific to this notebook's purpose

**Wheels are installed via Fabric environments**, not via inline `%pip install`. The environment definition (managed in source control) declares the wheel version; the notebook inherits it. This makes notebook behaviour reproducible and prevents per-notebook drift in library versions.

## Environments

**Use Fabric environments for shared library management.** Each platform workspace has a dedicated environment defining the Python runtime, library versions, and custom wheel installations. Notebooks inherit the environment; do not install libraries inline at runtime.

**Avoid `%pip install` and `%conda install`** in production notebooks. These are exploratory tools, not production patterns. If a library is needed in production, add it to the environment definition.

**Exception:** development notebooks in a sandbox workspace may use `%pip install` for experimentation. These do not deploy to the platform and are not bound by these standards.

## Output and Logging

**Production notebooks should be quiet by default.** Orchestration must never depend on parsing print output.

**Use Python's `logging` module** for things worth capturing:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Loaded %d rows from FOCUS billing", row_count)
```

Fabric's notebook runtime surfaces these in execution logs at the appropriate level (INFO, WARNING, ERROR).

**Use `mssparkutils.notebook.exit(value)`** to return structured values to calling pipelines. This is the supported mechanism for inter-notebook communication.

**Use `display()` sparingly** for diagnostic snapshots that genuinely help future debugging — row counts and schemas after critical transforms. Not for confirming success.

**Delete exploratory print statements before commit.** Scratch-work output does not belong in production code.

## Idempotency

**Notebooks must be safe to rerun.** Rerunning a notebook against the same inputs must produce the same output without error, regardless of how many times it has been run before.

**Do:**

- Use `MERGE` for upserts
- Use full overwrite (`mode="overwrite"`) for deterministic regenerations
- Use partition-level overwrite (`mode="overwrite", partition_overwrite_mode="dynamic"`) for incremental scenarios

**Do not:**

- Use unconditional `INSERT` that would duplicate rows on rerun
- Branch on "first run vs subsequent run" logic — this is a code smell indicating non-idempotent design
- Rely on external state (filesystem flags, control tables) to determine behaviour, unless that state is itself managed idempotently

A notebook that fails halfway through should be safe to rerun without manual cleanup. This is the test of idempotency.

## Error Handling

**Fail fast and noisily.** Production notebooks must surface errors to the calling pipeline, not absorb them silently.

**Do:**

- Let exceptions propagate unless you have a specific recovery action
- Use `logger.exception()` to record context before re-raising
- Validate inputs at the top of the notebook and exit early with a clear error if invalid

**Do not:**

- Wrap entire notebooks in `try/except` blocks that swallow exceptions and continue
- Catch `Exception` (the base class) without re-raising; catch specific exception types
- Return partial results on failure — this corrupts downstream data

**Pattern for recoverable errors:**

```python
try:
    df = fetch_with_retry(url)
except TransientAPIError as e:
    logger.warning("Transient API failure, will retry on next run: %s", e)
    raise  # let the pipeline handle the retry
```

Notebooks that fail are notebooks that get fixed. Notebooks that silently produce wrong outputs are notebooks that erode trust in the platform.

## Testing

**Unit tests live with the wheel package, not in notebooks.** Notebooks are integration glue and are difficult to unit-test in isolation; the functions they call are testable.

**Wheel package** (`finops_utils` or equivalent): full pytest suite, run in CI before publishing the wheel to the ADO Artifact feed. New wheel versions fail the pipeline if tests fail.

**Notebook validation** is integration-level: deploy to PPE workspace, run the notebook, verify it produces the expected Delta table with expected row counts and schemas. This is pipeline-level testing, not notebook-internal testing.

**Do not embed pytest or unittest inside notebook cells.** This pattern looks helpful but creates artifacts that are hard to maintain and that conflate test code with production code.

## Linting

Notebooks are linted by `ruff` as part of CI. The same ruleset applies to notebook cells as to Python files in the wheel. The Ruff configuration in `pyproject.toml` includes `*.ipynb` in `extend-include`.

Violations fail the pipeline. Auto-fix locally with `ruff check --fix --extend-include "*.ipynb" .` before committing.

## Decision Log

This section records why specific choices were made.

- **Why Polars not pandas?** Polars is significantly faster on the FOCUS dataset size, has a more consistent API, and is the established pattern in this platform's existing notebooks. Pandas remains acceptable for very small dataframes (configuration, lookup tables) where performance is irrelevant, but Polars is the default.
- **Why single-node not Spark?** For Finops data volumes, single-node Polars outperforms Spark on cost, latency, and developer experience. Spark adds cluster startup time and shuffle overhead that single-node avoids. The 50GB threshold is the rough point at which Spark begins to pay back its overhead.
- **Why Variable Library not workspace settings?** Variable Library integrates with deployment pipelines and source control; workspace settings do not. Variable Library is the Fabric-native mechanism for environment-specific config and is the supported path forward.
- **Why wheels at the three-notebook threshold?** Lower thresholds create release coordination overhead for functions that don't yet need to be shared. Higher thresholds allow drift. Three is the point at which the cost of maintaining duplicates exceeds the cost of packaging.
- **Why no inline `%pip install`?** Inline installs make notebook behaviour irreproducible — the same notebook produces different results depending on when it last ran. Environments make library versions explicit and source-controlled.
- **Why no embedded tests in notebooks?** Tests in notebooks run only when the notebook runs, which is too late. Tests in wheel packages run in CI before deployment and catch issues earlier. Notebooks are tested at the integration level (does the pipeline succeed) not the unit level.

## Maintenance

Changes to this document follow the same review process as code changes. Pull requests modifying standards require approval from the platform owner. Standards that are repeatedly deviated from in PRs should be reviewed for whether the standard or the practice is wrong.
