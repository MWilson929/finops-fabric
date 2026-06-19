# FinOps Hub Fabric Platform

Microsoft Fabric source and CI/CD for FinOps Hub. The repository contains Data
Engineering, reporting, operational, and reusable platform items.

## Repository Boundary

- `notebooks/` contains notebooks eligible for CI/CD deployment.
- `incubation/` contains source-controlled work in progress and is not deployed.

Promotion from incubation means moving the complete notebook source folder into
`notebooks/` through a reviewed pull request. Pipeline artifact selection,
Fabric folder exclusions, and repository validation all enforce this boundary.

## Release Model

Environment branches represent the complete desired state of each environment:

```text
feature/* -> dev -> test -> main
```

| Branch | Deployment |
|---|---|
| `feature/*` | Pull-request validation only |
| `dev` | Dev workspace |
| `test` | Test Data Engineering, then Test Reporting |
| `main` | Prod Data Engineering, then Prod Reporting |

Promotion happens through reviewed pull requests. Promote all related notebooks,
pipelines, models, and configuration together. Direct changes in Test and
Production workspaces are not part of the operating model.

See [ADR-0012](docs/adr/0012-environment-branches-five-workspaces.md) for the
decision and [CI/CD setup](docs/cicd_setup.md) for implementation details.

## Parameterization

Source-controlled Fabric definitions must not contain target-environment GUIDs.

- Use `PLACEHOLDER_WORKSPACE_ID` for the current engineering workspace.
- Use `PLACEHOLDER_LAKEHOUSE_ID` for the current `FinOpsHub` Lakehouse.
- Use named item placeholders for pipeline dependencies.
- Use the reporting placeholders for cross-workspace Engineering references.
- Use Fabric Variable Libraries for runtime application settings where supported.

`parameter.yml` resolves these values during deployment by using `fabric-cicd`
dynamic `$workspace` and `$items` references. Environment connection IDs are
held once in Azure DevOps variable groups.

`.platform` `logicalId` values are different: they are stable source-control
identities and must be valid, unique UUIDs. They do not change by environment.

See [parameter configuration](docs/deployment_parameters.md).

## Validation

```bash
python -m pip install --requirement requirements-cicd.txt
python scripts/validate_fabric_repository.py
```

Validation checks YAML, policy exceptions, standards-derived Fabric item names,
item metadata, logical IDs, placeholders, deployment scope, and every
environment contract with the pinned `fabric-cicd` version.
