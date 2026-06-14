# Fabric CI/CD Setup

## Workspaces

Create the following workspaces:

| Workspace | Suggested display name |
|---|---|
| Dev | `FinOps Hub - Dev` |
| Preprod Data Engineering | `FinOps Hub - Preprod Data Engineering` |
| Preprod Reporting | `FinOps Hub - Preprod Reporting` |
| Prod Data Engineering | `FinOps Hub - Prod Data Engineering` |
| Prod Reporting | `FinOps Hub - Prod Reporting` |

The two Engineering names are referenced by `parameter.yml` for dynamic
cross-workspace reporting bindings. If the names change, update those two
parameter expressions; no workspace or item GUIDs need to be committed.

## Branches And Policies

Create `dev` and `preprod` from `main`. Protect all three environment branches:

- require pull requests;
- require the pipeline validation stage;
- prevent direct pushes;
- require reviewers appropriate to the target environment;
- keep feature branches short-lived;
- tag successful Production releases.

The Dev workspace can be connected to `dev` through Fabric Git integration.
Preprod and Production are deployed by Azure DevOps and should not be edited
directly.

## Deployable Notebook Boundary

`notebooks/` is the only deployable notebook root. Work in progress belongs in
`incubation/`, where it remains source controlled but is not copied into the
release artifact or scanned as a deployable Fabric item.

The Azure DevOps trigger and artifact lists intentionally name `notebooks/**`
and omit `incubation/**`. `fabric-config.yml` excludes incubation as defense in
depth. A notebook is promoted by moving its complete `.Notebook/` folder from
incubation into `notebooks/` through a pull request.

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

### `fabric-preprod`

| Variable | Meaning |
|---|---|
| `engineering-workspace-id` | Preprod Data Engineering workspace ID |
| `reporting-workspace-id` | Preprod Reporting workspace ID |
| `storage-account-name` | Preprod storage account |
| `container-name` | Preprod container |
| `connection-id` | Preprod source connection ID |
| `lakehouse-connection-id` | Connection used by Preprod semantic models |

### `fabric-prod`

Use the same variable names as `fabric-preprod`, with Production values.

Workspace IDs are identifiers rather than credentials, but variable-group
permissions should still be restricted. Connection credentials belong in the
Fabric connection or Key Vault, not in source or ordinary ADO variables.

## Azure DevOps Environments

Create:

- `fabric-dev`
- `fabric-preprod-engineering`
- `fabric-preprod-reporting`
- `fabric-prod-engineering`
- `fabric-prod-reporting`

Configure approvals and checks on the Preprod and Production environments.
Engineering deploys before Reporting so cross-workspace references resolve
against an already deployed Engineering state.

## First Deployment

1. Run the pipeline against a pull request into `dev`.
2. Resolve every validation failure before merging.
3. Merge to `dev` and verify the Dev deployment.
4. Reconcile any existing manually created Preprod/Production items with Git.
5. Promote through `preprod`, then `main`.
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
