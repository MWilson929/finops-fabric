# Fabric Deployment Parameterization

## Rules

Fabric definitions in Git are environment neutral. Do not commit Dev, Test,
or Production workspace/item GUIDs into notebooks, pipelines, semantic models,
or reports.

Use:

| Placeholder | Deployment value |
|---|---|
| `PLACEHOLDER_WORKSPACE_ID` | Current target workspace ID |
| `PLACEHOLDER_LAKEHOUSE_ID` | `FinOpsHub` Lakehouse ID in the target workspace |
| `PLACEHOLDER_BRONZE_NOTEBOOK_ID` | `finops_bronze_arg_containers` Notebook ID |
| `PLACEHOLDER_SILVER_NOTEBOOK_ID` | `finops_silver_arg_containers` Notebook ID |
| `PLACEHOLDER_ENGINEERING_WORKSPACE_ID` | Engineering workspace used by a reporting item |
| `PLACEHOLDER_ENGINEERING_LAKEHOUSE_ID` | `FinOpsHub` Lakehouse in that Engineering workspace |
| `PLACEHOLDER_ENGINEERING_SQL_ENDPOINT_ID` | SQL endpoint ID of that Lakehouse |
| `PLACEHOLDER_REPORTING_CONNECTION_ID` | Environment-specific Fabric connection |

Storage account, container, and connection placeholders are resolved from the
ADO variable group for the target environment.

## Same-Workspace References

Notebooks use:

```python
# META       "default_lakehouse": "PLACEHOLDER_LAKEHOUSE_ID",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
```

`fabric-cicd` resolves these by item name:

```yaml
replace_value:
  DEV: "$items.Lakehouse.FinOpsHub.$id"
```

Pipelines follow the same pattern for Notebook activities. This avoids changing
pipeline JSON after promotion.

## Reporting-To-Engineering References

Test and Production Reporting are separate workspaces. Use the Engineering
placeholders in semantic-model or report definitions. They resolve through the
controlled workspace display name:

```yaml
TEST_REPORTING: "$workspace.FinOps Hub - Test Data Engineering.$items.Lakehouse.FinOpsHub.$id"
```

The deployment identity must be able to read the Engineering workspace.

When a semantic model requires an environment-specific connection, put
`PLACEHOLDER_REPORTING_CONNECTION_ID` in the source definition and maintain its
single environment value in the ADO variable group.

## Stable Logical IDs

The `logicalId` in each `.platform` file is deliberately not parameterized.
Fabric uses it to identify the same source-controlled item across deployments.
It must be:

- a valid UUID;
- unique within the repository;
- retained when the item changes;
- regenerated only when intentionally creating a distinct item.

## Variable Libraries

Use Variable Libraries for runtime configuration consumed by supported Fabric
items. Use `parameter.yml` for deployment-time references, item IDs, workspace
IDs, source connections, and settings that cannot be read from a Variable
Library.

Never store secrets in a Variable Library source definition. Store a secret in
Key Vault or a managed Fabric connection and reference its name or connection.

## Adding A Parameter

1. Add a descriptive placeholder to the Fabric item.
2. Add a narrowly scoped `find_replace` or `key_value_replace` rule.
3. Prefer `$workspace` or `$items` dynamic references over GUID variables.
4. Add a variable-group value only when the target cannot be resolved by name.
5. Run `python scripts/validate_fabric_repository.py`.

Do not add wildcard `file_path` rules until at least one matching file exists;
`fabric-cicd` treats an unmatched wildcard as a validation error.
