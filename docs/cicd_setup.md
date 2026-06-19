# Fabric CI/CD Setup

## Workspaces

Create the following workspaces:

| Workspace | Suggested display name |
|---|---|
| Dev | `FinOps Hub - Dev` |
| Test Data Engineering | `FinOps Hub - Test Data Engineering` |
| Test Reporting | `FinOps Hub - Test Reporting` |
| Prod Data Engineering | `FinOps Hub - Prod Data Engineering` |
| Prod Reporting | `FinOps Hub - Prod Reporting` |

The two Engineering names are referenced by `parameter.yml` for dynamic
cross-workspace reporting bindings. If the names change, update those two
parameter expressions; no workspace or item GUIDs need to be committed.

## Branches And Policies

Create `dev` and `test` from `main`. Protect all three environment branches:

- require pull requests;
- require the pipeline validation stage;
- prevent direct pushes;
- require reviewers appropriate to the target environment;
- keep feature branches short-lived;
- tag successful Production releases.

The Dev workspace can be connected to `dev` through Fabric Git integration.
Test and Production are deployed by Azure DevOps and should not be edited
directly.

## Deployable Notebook Boundary

`notebooks/` is the only deployable notebook root. Work in progress belongs in
`incubation/`, where it remains source controlled but is not copied into the
release artifact or scanned as a deployable Fabric item.

The Azure DevOps trigger and artifact lists intentionally name `notebooks/**`
and omit `incubation/**`. `fabric-config.yml` excludes incubation as defense in
depth. A notebook is promoted by moving its complete `.Notebook/` folder from
incubation into `notebooks/` through a pull request.

## Deployable Item Roots

Fabric items are stored in type-specific repository roots:

| Root | Fabric item type |
|---|---|
| `notebooks/` | Notebook |
| `lakehouses/` | Lakehouse |
| `datapipelines/` | Data pipeline |
| `dataflows/` | Dataflow |
| `environments/` | Environment |
| `eventhouses/` | Eventhouse |
| `sqldatabases/` | SQL database |
| `variablelibraries/` | Variable library |
| `udfs/` | User data function |
| `warehouses/` | Warehouse |
| `semanticmodels/` | Semantic model |
| `reports/` | Report |

Fabric Git source folders use `<displayName>.<ItemType>/` and include a
`.platform` file. The folder stem and `.platform` `displayName` must match.
Notebook source folders contain `notebook-content.py`; loose `.ipynb` files are
not deployment artifacts.

The release artifact uses an explicit allowlist. Supporting another Fabric item
type therefore requires coordinated changes to:

1. The trigger and artifact paths in `azure-pipelines.yml`.
2. `DEPLOYABLE_ROOTS`, `ITEM_SUFFIXES`, and the relevant scope in
   `scripts/validate_fabric_repository.py`.
3. The item scope used by `scripts/deploy_fabric_items.py`.

Refer to the official `fabric-cicd` item-type documentation for the source
format required by a newly supported type.

## Azure DevOps Service Connections

Create workload-identity-federated Azure Resource Manager service connections:

- `fabric-cicd-nonprod`
- `fabric-cicd-prod`

The corresponding identities require Fabric API access and sufficient access to
their target workspaces. The Production identity should not have access to Dev.
The reporting deployment identity also needs read access to its matching
Engineering workspace so cross-workspace `$workspace...$items...` references can
be resolved.

Change the service connection names in `azure-pipelines.yml` if your ADO naming
standard differs.

## Variable Groups

Create these variable groups and authorize the pipeline.

### `fabric-dev`

| Variable | Meaning |
|---|---|
| `workspace-id` | Dev workspace ID |
| `storage-account-name` | Dev/sample storage account |
| `container-name` | Dev/sample container |
| `connection-id` | Dev source connection ID |
| `lakehouse-connection-id` | Connection used by Dev semantic models |

### `fabric-test`

| Variable | Meaning |
|---|---|
| `engineering-workspace-id` | Test Data Engineering workspace ID |
| `reporting-workspace-id` | Test Reporting workspace ID |
| `storage-account-name` | Test storage account |
| `container-name` | Test container |
| `connection-id` | Test source connection ID |
| `lakehouse-connection-id` | Connection used by Test semantic models |

### `fabric-prod`

Use the same variable names as `fabric-test`, with Production values.

Workspace IDs are identifiers rather than credentials, but variable-group
permissions should still be restricted. Connection credentials belong in the
Fabric connection or Key Vault, not in source or ordinary ADO variables.

## Azure DevOps Environments

Create:

- `fabric-dev`
- `fabric-test-engineering`
- `fabric-test-reporting`
- `fabric-prod-engineering`
- `fabric-prod-reporting`

Configure approvals and checks on the Test and Production environments.
Engineering deploys before Reporting so cross-workspace references resolve
against an already deployed Engineering state.

## First Deployment

1. Run the pipeline against a pull request into `dev`.
2. Resolve every validation failure before merging.
3. Merge to `dev` and verify the Dev deployment.
4. Reconcile any existing manually created Test/Production items with Git.
5. Promote through `test`, then `main`.
6. After Git is confirmed as the complete source of truth, assess enabling
   orphan removal in `fabric-config.yml`. It is disabled during initial adoption
   to prevent accidental deletion.

CMK, inbound protection, and outbound protection are workspace controls and are
configured separately from item deployment.

## Policy Validation And Break Glass

The validation stage derives Fabric item naming rules from
`docs/naming_standards.md`. It checks every `.platform` display name and its
source folder before publishing an artifact.

Do not add a pipeline variable that disables policy validation. For a necessary
release that cannot immediately comply, add one exact, time-limited record to
`config/policy_exceptions.yml`. The pull request is the approval and audit
boundary. Exceptions are limited to 90 days. Expired, malformed, or stale
exceptions fail validation.
