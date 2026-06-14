# CI/CD Scripts

## `validate_fabric_repository.py`

Runs static and `fabric-cicd` validation for all five deployment targets:

```bash
python scripts/validate_fabric_repository.py
```

It validates YAML, `.platform` logical IDs, placeholder coverage, deployment
configuration, parameter structure, scoped item types, notebook naming, and
folder/display-name consistency for Fabric items.
The naming regex is derived from `docs/naming_standards.md`, rather than being
duplicated in the script.

An unavoidable temporary violation requires an exact, approved, time-limited
record in `config/policy_exceptions.yml`. Invalid or expired records fail the
same validation command.

## `deploy_fabric_items.py`

Deploys an immutable pipeline artifact:

```bash
python scripts/deploy_fabric_items.py \
  --environment PREPROD_ENGINEERING \
  --workspace-id <workspace-id> \
  --scope engineering
```

Scopes:

- `engineering`: Data Engineering and platform item types
- `reporting`: semantic models and reports
- `all`: both scopes, used for Dev

Authentication uses `AzureCliCredential`. In Azure DevOps the script must run
inside an `AzureCLI@2` task bound to the appropriate workload-federated service
connection.

`fabric_debug_tool.py` and `fabric_testing_suite.py` are retained as operational
diagnostics but are not part of the deployment path.
