# ADR-0012 — Environment branches promote into five security-aligned workspaces

**Status:** Accepted · **Date:** 2026-06-14

## Context

FinOps Hub contains independently developed Fabric items that do not all mature or release together. Multiple contributors may build notebooks concurrently; some are experimental, development-only, or ready for Test but not Production. A single trunk deployment of every item would therefore make release selection too coarse.

The environments also have different data and security requirements. Development uses sample, synthetic, or masked data. Test and Production use full data and require customer-managed key (CMK) encryption, restricted inbound access, and outbound data-exfiltration controls. Fabric currently applies these capabilities at workspace level and does not support every control for every item type. In particular, Power BI semantic models are incompatible with workspace-level Private Link, while CMK and outbound protection constrain which artifacts can coexist in a workspace.

## Decision

Use environment branching with controlled promotion:

- `feature/*` branches are short-lived and used with an isolated developer workspace or local tooling.
- `dev` is the complete desired state of the shared Development environment.
- `test` is the complete desired state approved for Test.
- `main` is the complete desired state approved for Production.
- Changes move `feature/*` → `dev` → `test` → `main` through reviewed pull requests. Related Fabric items and dependencies are promoted together; direct commits and workspace edits outside the development workflow are prohibited.

Deploy those branches into five workspaces:

| Branch | Workspace | Purpose |
|---|---|---|
| `dev` | Dev | Engineering and reporting against sample, synthetic, or masked data |
| `test` | Test Data Engineering | Full-scale validation of lakehouses, notebooks, pipelines, and related engineering items |
| `test` | Test Reporting | Validation of semantic models, reports, and apps against Test engineering data |
| `main` | Prod Data Engineering | Production lakehouses, notebooks, pipelines, and related engineering items |
| `main` | Prod Reporting | Production semantic models, reports, and apps |

Test and Production engineering workspaces will use CMK where supported, workspace-level inbound protection, and deny-by-default outbound protection with explicit approved connections. Reporting is separated because its item types, access model, and current Fabric networking support differ from Data Engineering.

Fabric User Data Functions remain an open architecture item. Their placement and exposure will be decided after confirming support or roadmap commitments for private inbound access. Alternatives include a separately secured API workspace or an Azure-hosted private endpoint service. This ADR does not add UDF workspaces to the five-workspace baseline.

## Consequences

- Git records the exact desired inventory of each environment and supports selective promotion of independently maturing capabilities.
- Test can validate full data volume, dependencies, security controls, and reporting behavior without granting developers Production data access.
- Engineering and reporting require separate deployments, identities, configuration, cross-workspace permissions, and connectivity tests.
- Environment branches intentionally diverge; promotion discipline must prevent omitted dependencies, out-of-order fixes, and workspace drift. Production deployments are tagged for audit and rollback.
- CI/CD must use the same pinned deployment tooling for every workspace, validate branch-to-workspace mappings, and apply environment-specific Variable Library and `parameter.yml` values.
- CMK and network-control support must be checked before introducing a new Fabric item type into a protected workspace.
