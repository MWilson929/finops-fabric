# Lakehouse Table Standards — FinOps Fabric Platform

This document defines naming for tables, materialised lake views, and other queryable objects in the platform lakehouse. It is the counterpart to [naming_standards.md](naming_standards.md) (which governs Fabric item names) and [notebook_standards.md](notebook_standards.md) (which governs notebook content). Where this document references source tokens, the authoritative list lives in naming_standards.md and is not duplicated here.

This platform uses the **FOCUS one-big-table (OBT) model**. Tables are wide and denormalised by design. Kimball-style dimensional prefixes (`dim_`, `fct_`) are **not** used — they describe a different architectural pattern. Silver and gold transformations are implemented predominantly as **materialised lake views (MLVs)**; bronze is loaded by ingest notebooks.

## The Pattern

```
{schema}.{token1}_{token2}
```

- **schema** carries the medallion layer: `bronze`, `silver`, or `gold`
- **token1** is the source (at bronze/silver) or subject area (at gold)
- **token2** is the entity — a single word describing the table's content

Exactly two snake_case tokens after the schema. All lowercase. The two-token rule is inherited from the notebook convention: a table name is the last two tokens of the notebook (or the natural identifier of the MLV that produces it).

## Worked Examples

```
bronze.focusazure_billing
bronze.focusm365_billing
bronze.arg_resources
bronze.arg_advisors
bronze.pricesheet_rates
bronze.carbon_emissions
bronze.monitoring_logs

silver.focusazure_normalised
silver.focusazure_enriched
silver.arg_tagged
silver.carbon_normalised

gold.forecast_input
gold.forecast_arima
gold.forecast_mstl
gold.chargeback_monthly
gold.emissions_allocated
gold.monitoring_capacity
```

## Token 1: Source vs Subject

Token 1 changes meaning by layer, and this is deliberate:

- **Bronze and silver**: token 1 is the **source** — where the data came from (`focusazure`, `arg`, `carbon`, `pricesheet`). Sourced from the enumerated list in naming_standards.md.
- **Gold**: token 1 is the **subject area** — what the table is about (`forecast`, `chargeback`, `emissions`, `monitoring`). Gold tables are synthesised from multiple silver inputs and rarely have a single source, so naming them by source would be misleading.

The syntactic rule (two snake_case tokens) is unchanged across layers; only the semantics of token 1 differ. This is documented rather than hidden so contributors understand why `silver.arg_resources` and `gold.forecast_input` read differently.

### Gold subject-area enumeration

To keep gold as enforceable as bronze/silver, gold subject areas are a closed list. The authoritative enumeration lives in naming_standards.md ("Source or subject (token 3)" → "Subject area (gold)"), alongside the source list, and is not duplicated here. Adding a subject area requires a documented decision and an update to that table.

## Token 2: Entity

Single word, lowercase, no separators. Same rule as the notebook entity token. Describes what the table contains or what has been done to it.

Acceptable: `billing`, `resources`, `normalised`, `enriched`, `tagged`, `input`, `arima`, `mstl`, `monthly`, `allocated`, `capacity`.

Unacceptable: `forecast_output_arima` (three tokens), `monthly_summary` (compound), `v2`, `tmp`, `final`.

## Plural vs Singular

- **Plural** for tables holding many rows of the same entity (the common case): `arg_resources`, `pricesheet_rates`.
- **Singular** for genuine single-row state or config tables: `platform_state` (if such a thing exists).

Most tables are plural. Pick deliberately; consistency matters more than the choice.

## Tables, MLVs, and Views

All three appear in the lakehouse Tables view and share the same naming convention — a consumer querying `silver.focusazure_normalised` neither knows nor needs to know whether it is a Delta table or an MLV. The naming is unified; only the **governing artifact** differs:

| Object type           | Produced by                    | Source of truth for the name |
|-----------------------|--------------------------------|------------------------------|
| Delta table (bronze)  | Ingest notebook                | Notebook name (last 2 tokens)|
| Materialised lake view| SQL DDL in repo                | DDL filename / `CREATE` stmt |
| Plain view            | SQL DDL in repo                | DDL filename / `CREATE` stmt |

**Non-materialised views** (used for ad-hoc Power BI consumption or security boundaries, where materialisation isn't warranted) follow the same two-token pattern but carry a `vw_` prefix to signal they are not materialised: `gold.vw_chargeback_summary`. This is the one permitted prefix, because the materialisation status genuinely changes how a consumer reasons about freshness and cost.

MLV-specific standards (DDL structure, refresh cadence, dependency declaration) are covered in a separate document.

## FOCUS Column Casing

The FOCUS specification defines its columns in **PascalCase** (e.g. `BilledCost`, `EffectiveCost`, `ChargePeriodStart`, `ServiceName`, `ResourceId`). This clashes with the snake_case house style for table and schema names. The rule resolves the clash by layer:

- **Bronze and silver**: preserve FOCUS-defined columns in their **spec PascalCase**. These layers are FOCUS-compliant datasets and should remain interoperable with FOCUS tooling and validatable against the spec. Columns you add (audit columns, derived fields) use snake_case, which makes added columns visually distinguishable from spec columns.
- **Gold**: use house **snake_case** throughout. Gold tables are purpose-shaped and no longer claim FOCUS compliance, so house consistency wins over spec fidelity.

The alternative — snake_casing everything including FOCUS columns at bronze/silver — was considered and rejected: it breaks FOCUS tooling expectations and makes spec-compliance validation harder for no benefit beyond cosmetic uniformity.

## Standard Columns

Every bronze table carries audit columns appended to the source schema:

- `ingestion_timestamp` (timestamp, UTC) — when the row was loaded
- `source_file` (string) — the originating file or API call, where applicable
- `snapshot_date` (date) — for sources loaded as periodic snapshots (e.g. pricesheet, ARG resources)

Snapshot-based sources (pricesheet, ARG) append rather than overwrite, retaining history with `snapshot_date` as the discriminator. Silver selects the relevant snapshot. This preserves the ability to reconstruct historical state — essential for reconciling forecasts against the prices and resource inventory that were in effect at the time.

## Reference Data

Small, manually-maintained mapping and lookup tables that are not part of the medallion ingestion flow (cost-centre mappings, tag resolution rules, business-unit hierarchies) live in a dedicated `ref` schema rather than cluttering the medallion schemas:

```
ref.costcentre_mapping
ref.tag_rules
ref.businessunit_hierarchy
```

The medallion schemas describe the data flow; `ref` holds the static inputs that flow references. Ingested reference-like data that arrives on a schedule (e.g. pricesheet) stays in the medallion schemas — `ref` is only for data that is maintained by hand or by an out-of-band process.

## Reserved Characters and Length

- Lowercase ASCII letters, digits, and single underscore only.
- No hyphens (force backtick-quoting in SQL).
- No leading digits (parse failures in some contexts).
- Keep names under ~40 characters; most should be 15–25.

## What Not to Include

- **Environment** (`_dev`, `_prod`) — carried by workspace.
- **Version** (`_v2`) — carried by git and by Delta time travel.
- **Date** (`_20260601`) — a column inside the table, never in the name.
- **Owner or team** — carried by the schema and the repo.

## Validation

Structural regex applied to all tables and MLVs (excludes the `vw_` view prefix and the `ref` schema, which have their own checks):

```
^[a-z][a-z0-9]*_[a-z][a-z0-9]*$
```

Two lowercase snake_case words, no leading digit. In addition, token 1 is validated against the enumerated source list (bronze/silver) or subject list (gold) generated from naming_standards.md, mirroring the notebook validation. The check runs in the same CI stage as the notebook naming validation.

## Decision Log

- **Why two tokens, not four like notebooks?** Schema carries the layer; the lakehouse carries the platform scope; the domain is irrelevant at table level because the same table is consumed across domains. Only source/subject and entity remain.
- **Why no `dim_`/`fct_`?** The platform uses the FOCUS one-big-table model. Dimensional prefixes describe a star-schema pattern this platform deliberately does not use.
- **Why does token 1 mean different things at different layers?** Bronze/silver tables are *about* their source; gold tables are *about* a purpose synthesised from many sources. Forcing a single source token onto gold would misrepresent its lineage.
- **Why preserve FOCUS PascalCase at bronze/silver?** Spec compliance and tooling interoperability. Snake-casing spec columns gains only cosmetic uniformity and costs validatability.
- **Why a `ref` schema?** Keeps the medallion schemas as a clean representation of the data flow. Static, hand-maintained inputs are conceptually different from flowing data and benefit from separation.
- **Why allow `vw_` when no other prefix is permitted?** Materialisation status changes how a consumer reasons about freshness and query cost. That is consequential enough to surface in the name; nothing else is.

## Maintenance

Changes follow the same review process as code. Pull requests modifying the pattern, enumerations, or rules require platform-owner approval. The validation enumerations are generated from naming_standards.md; update that document to change the source and subject lists.
