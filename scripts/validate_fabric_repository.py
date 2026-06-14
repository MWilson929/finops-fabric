#!/usr/bin/env python3
"""Static validation for Fabric source and deployment configuration."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import yaml
from fabric_cicd import append_feature_flag
from fabric_cicd._common._config_validator import ConfigValidator
from fabric_cicd._parameter._utils import validate_parameter_file


ROOT = Path(__file__).resolve().parents[1]
NAMING_STANDARD_PATH = ROOT / "docs" / "naming_standards.md"
POLICY_EXCEPTIONS_PATH = ROOT / "config" / "policy_exceptions.yml"
NAMING_RULE = "fabric-item-naming"
DEPLOYABLE_ROOTS = {
    "datapipelines",
    "dataflows",
    "environments",
    "eventhouses",
    "lakehouses",
    "notebooks",
    "reports",
    "semanticmodels",
    "sqldatabases",
    "udfs",
    "variablelibraries",
    "warehouses",
}
NON_DEPLOYABLE_ROOTS = {"incubation", "scratch", "archive"}
ITEM_SUFFIXES = {
    ".DataPipeline",
    ".Environment",
    ".Eventhouse",
    ".Lakehouse",
    ".Notebook",
    ".Report",
    ".SemanticModel",
    ".SQLDatabase",
    ".UserDataFunction",
    ".VariableLibrary",
    ".Warehouse",
}
ALLOWED_PLACEHOLDERS = {
    "PLACEHOLDER_BRONZE_NOTEBOOK_ID",
    "PLACEHOLDER_CONNECTION_ID",
    "PLACEHOLDER_CONTAINER_NAME",
    "PLACEHOLDER_ENGINEERING_LAKEHOUSE_ID",
    "PLACEHOLDER_ENGINEERING_SQL_ENDPOINT_ID",
    "PLACEHOLDER_ENGINEERING_WORKSPACE_ID",
    "PLACEHOLDER_LAKEHOUSE_ID",
    "PLACEHOLDER_REPORTING_CONNECTION_ID",
    "PLACEHOLDER_SILVER_NOTEBOOK_ID",
    "PLACEHOLDER_STORAGE_ACCOUNT",
    "PLACEHOLDER_WORKSPACE_ID",
}
RUNTIME_SENTINELS = {"PLACEHOLDER_GUID"}
SCOPES = {
    "engineering": [
        "Notebook",
        "Lakehouse",
        "SQLDatabase",
        "DataPipeline",
        "Environment",
        "Eventhouse",
        "VariableLibrary",
        "UserDataFunction",
    ],
    "reporting": ["SemanticModel", "Report"],
}
SCOPES["all"] = SCOPES["engineering"] + SCOPES["reporting"]
ENVIRONMENT_SCOPES = {
    "DEV": "all",
    "PREPROD_ENGINEERING": "engineering",
    "PREPROD_REPORTING": "reporting",
    "PROD_ENGINEERING": "engineering",
    "PROD_REPORTING": "reporting",
}
DUMMY_ENVIRONMENT_VALUES = {
    "DEV_STORAGE_ACCOUNT_NAME": "devstorage",
    "DEV_CONTAINER_NAME": "data",
    "DEV_CONNECTION_ID": "00000000-0000-0000-0000-000000000001",
    "DEV_LAKEHOUSE_CONNECTION": "00000000-0000-0000-0000-000000000002",
    "PREPROD_STORAGE_ACCOUNT_NAME": "preprodstorage",
    "PREPROD_CONTAINER_NAME": "data",
    "PREPROD_CONNECTION_ID": "00000000-0000-0000-0000-000000000003",
    "PREPROD_LAKEHOUSE_CONNECTION": "00000000-0000-0000-0000-000000000004",
    "PROD_STORAGE_ACCOUNT_NAME": "prodstorage",
    "PROD_CONTAINER_NAME": "data",
    "PROD_CONNECTION_ID": "00000000-0000-0000-0000-000000000005",
    "PROD_LAKEHOUSE_CONNECTION": "00000000-0000-0000-0000-000000000006",
}
PLACEHOLDER_PATTERN = re.compile(r"PLACEHOLDER_[A-Z0-9_]+")
UNPARAMETERIZED_WORKSPACE_PATTERN = re.compile(r"<workspace-guid>", re.IGNORECASE)
MARKDOWN_TABLE_TOKEN_PATTERN = re.compile(r"^\|\s*([a-z][a-z0-9]*)\s*\|", re.MULTILINE)
EXCEPTION_FIELDS = {
    "id",
    "rule",
    "path",
    "reason",
    "owner",
    "approved_by",
    "ticket",
    "expires_on",
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_yaml(errors: list[str]) -> None:
    for relative in (
        "fabric-config.yml",
        "parameter.yml",
        "azure-pipelines.yml",
        "config/policy_exceptions.yml",
    ):
        path = ROOT / relative
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(errors, f"{relative}: invalid YAML: {exc}")


def iter_deployable_platform_files():
    for root_name in sorted(DEPLOYABLE_ROOTS):
        root = ROOT / root_name
        if root.is_dir():
            yield from root.glob("**/.platform")


def iter_deployable_files():
    for root_name in sorted(DEPLOYABLE_ROOTS):
        root = ROOT / root_name
        if root.is_dir():
            yield from (path for path in root.rglob("*") if path.is_file())


def validate_deployment_boundary(errors: list[str]) -> None:
    pipeline = yaml.safe_load((ROOT / "azure-pipelines.yml").read_text(encoding="utf-8"))
    serialized_pipeline = json.dumps(pipeline)
    config = yaml.safe_load((ROOT / "fabric-config.yml").read_text(encoding="utf-8"))
    folder_exclude = config.get("publish", {}).get("folder_exclude_regex", "")

    if "notebooks/**" not in serialized_pipeline:
        fail(errors, "azure-pipelines.yml: notebooks/** must be an explicit pipeline path")
    for root_name in NON_DEPLOYABLE_ROOTS:
        if f"{root_name}/**" in serialized_pipeline:
            fail(
                errors,
                f"azure-pipelines.yml: non-deployable {root_name}/** must not be "
                "included in triggers or release artifacts",
            )
        if root_name not in folder_exclude:
            fail(
                errors,
                f"fabric-config.yml: publish.folder_exclude_regex must exclude "
                f"{root_name}/",
            )


def tokens_between(document: str, start_heading: str, end_heading: str) -> list[str]:
    try:
        section = document.split(start_heading, 1)[1].split(end_heading, 1)[0]
    except IndexError as exc:
        raise ValueError(
            f"cannot find standards section between {start_heading!r} and {end_heading!r}"
        ) from exc
    tokens = MARKDOWN_TABLE_TOKEN_PATTERN.findall(section)
    if not tokens:
        raise ValueError(f"no tokens found under {start_heading!r}")
    return tokens


def load_naming_pattern() -> re.Pattern[str]:
    standard = NAMING_STANDARD_PATH.read_text(encoding="utf-8")
    domains = tokens_between(standard, "### Domain (token 1)", "### Layer (token 2)")
    layers = tokens_between(
        standard,
        "### Layer (token 2)",
        "### Source or subject (token 3)",
    )
    sources = tokens_between(
        standard,
        "#### Source (bronze and silver)",
        "#### Subject area (gold)",
    )
    subjects = tokens_between(
        standard,
        "#### Subject area (gold)",
        "### Entity (token 4)",
    )
    if set(layers) != {"bronze", "silver", "gold"}:
        raise ValueError(f"unexpected layer tokens in naming standard: {layers}")

    domain = "|".join(map(re.escape, domains))
    source = "|".join(map(re.escape, sources))
    subject = "|".join(map(re.escape, subjects))
    return re.compile(
        rf"^(?:{domain})_(?:bronze|silver)_(?:{source})_[a-z]+$"
        rf"|^(?:{domain})_gold_(?:{subject})_[a-z]+$"
    )


def load_policy_exceptions(
    errors: list[str],
) -> dict[tuple[str, str], dict[str, object]]:
    try:
        document = yaml.safe_load(POLICY_EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(document, dict) or not isinstance(document.get("exceptions"), list):
        fail(errors, "config/policy_exceptions.yml: root 'exceptions' must be a list")
        return {}

    exceptions: dict[tuple[str, str], dict[str, object]] = {}
    ids: set[str] = set()
    for index, record in enumerate(document["exceptions"], start=1):
        prefix = f"config/policy_exceptions.yml: exception {index}"
        if not isinstance(record, dict):
            fail(errors, f"{prefix} must be a mapping")
            continue

        missing = EXCEPTION_FIELDS - record.keys()
        unknown = record.keys() - EXCEPTION_FIELDS
        if missing:
            fail(errors, f"{prefix} missing fields: {', '.join(sorted(missing))}")
        if unknown:
            fail(errors, f"{prefix} has unknown fields: {', '.join(sorted(unknown))}")
        if missing or unknown:
            continue

        exception_id = record["id"]
        if not isinstance(exception_id, str) or not exception_id.strip():
            fail(errors, f"{prefix} id must be a non-empty string")
            continue
        if exception_id in ids:
            fail(errors, f"{prefix} duplicates id {exception_id!r}")
            continue
        ids.add(exception_id)

        rule = record["rule"]
        relative_path = record["path"]
        if rule != NAMING_RULE:
            fail(errors, f"{prefix} has unsupported rule {rule!r}")
            continue
        if (
            not isinstance(relative_path, str)
            or relative_path.startswith("/")
            or ".." in Path(relative_path).parts
            or not relative_path.endswith("/.platform")
        ):
            fail(errors, f"{prefix} path must be an exact relative .platform path")
            continue
        if not (ROOT / relative_path).is_file():
            fail(errors, f"{prefix} path does not exist: {relative_path}")
            continue

        for field in ("reason", "owner", "approved_by", "ticket"):
            if not isinstance(record[field], str) or not record[field].strip():
                fail(errors, f"{prefix} {field} must be a non-empty string")

        expires_on = record["expires_on"]
        if isinstance(expires_on, str):
            try:
                expires_on = date.fromisoformat(expires_on)
            except ValueError:
                fail(errors, f"{prefix} expires_on must use YYYY-MM-DD")
                continue
        if not isinstance(expires_on, date):
            fail(errors, f"{prefix} expires_on must use YYYY-MM-DD")
            continue
        if expires_on < date.today():
            fail(errors, f"{prefix} expired on {expires_on.isoformat()}")
            continue
        if expires_on > date.today() + timedelta(days=90):
            fail(errors, f"{prefix} expires_on cannot be more than 90 days ahead")
            continue

        key = (rule, relative_path)
        if key in exceptions:
            fail(errors, f"{prefix} duplicates rule/path {rule}:{relative_path}")
            continue
        exceptions[key] = record

    return exceptions


def validate_items(
    errors: list[str],
    warnings: list[str],
    policy_exceptions: dict[tuple[str, str], dict[str, object]],
) -> None:
    try:
        naming_pattern = load_naming_pattern()
    except Exception as exc:
        fail(errors, f"docs/naming_standards.md: cannot derive naming policy: {exc}")
        return

    logical_ids: dict[str, Path] = {}
    used_exceptions: set[tuple[str, str]] = set()
    for platform_path in iter_deployable_platform_files():
        item_dir = platform_path.parent
        if not any(item_dir.name.endswith(suffix) for suffix in ITEM_SUFFIXES):
            continue
        try:
            platform = json.loads(platform_path.read_text(encoding="utf-8"))
            logical_id = platform["config"]["logicalId"]
            uuid.UUID(logical_id)
        except Exception as exc:
            fail(errors, f"{platform_path.relative_to(ROOT)}: invalid logicalId: {exc}")
            continue
        if logical_id in logical_ids:
            first = logical_ids[logical_id].relative_to(ROOT)
            fail(errors, f"{platform_path.relative_to(ROOT)}: duplicate logicalId also used by {first}")
        logical_ids[logical_id] = platform_path

        display_name = platform.get("metadata", {}).get("displayName")
        item_type = platform.get("metadata", {}).get("type")
        expected_suffix = f".{item_type}"
        folder_name = item_dir.name
        source_name = (
            folder_name.removesuffix(expected_suffix)
            if isinstance(item_type, str) and folder_name.endswith(expected_suffix)
            else None
        )
        naming_violations = []
        if not isinstance(display_name, str) or not naming_pattern.fullmatch(display_name):
            naming_violations.append(f"displayName {display_name!r} is non-compliant")
        if source_name != display_name:
            naming_violations.append(
                f"folder name {folder_name!r} must be {display_name}.{item_type}"
            )
        if naming_violations:
            relative_path = platform_path.relative_to(ROOT).as_posix()
            exception = policy_exceptions.get((NAMING_RULE, relative_path))
            message = f"{relative_path}: " + "; ".join(naming_violations)
            if exception:
                used_exceptions.add((NAMING_RULE, relative_path))
                warnings.append(
                    f"{message} (excepted by {exception['id']} until "
                    f"{exception['expires_on']})"
                )
            else:
                fail(errors, f"{message}; add a compliant name or approved exception")

    for key, exception in policy_exceptions.items():
        if key not in used_exceptions:
            fail(
                errors,
                f"config/policy_exceptions.yml: {exception['id']} does not match "
                "an active policy violation; remove it",
            )


def validate_placeholders(errors: list[str]) -> None:
    parameter_text = (ROOT / "parameter.yml").read_text(encoding="utf-8")
    parameter_placeholders = set(PLACEHOLDER_PATTERN.findall(parameter_text))

    for path in iter_deployable_files():
        if path.name in {"parameter.yml", "validate_fabric_repository.py"}:
            continue
        if not any(part.endswith(tuple(ITEM_SUFFIXES)) for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for placeholder in PLACEHOLDER_PATTERN.findall(content):
            if placeholder in RUNTIME_SENTINELS:
                continue
            if placeholder not in ALLOWED_PLACEHOLDERS:
                fail(errors, f"{path.relative_to(ROOT)}: unknown placeholder {placeholder}")
            elif placeholder not in parameter_placeholders:
                fail(errors, f"{path.relative_to(ROOT)}: {placeholder} has no parameter.yml rule")
        if UNPARAMETERIZED_WORKSPACE_PATTERN.search(content):
            fail(errors, f"{path.relative_to(ROOT)}: unparameterized <workspace-guid> value")


def validate_fabric_cicd_contract(errors: list[str]) -> None:
    for name, value in DUMMY_ENVIRONMENT_VALUES.items():
        os.environ.setdefault(name, value)
    append_feature_flag("enable_environment_variable_replacement")

    for environment, scope_name in ENVIRONMENT_SCOPES.items():
        scope = SCOPES[scope_name]
        try:
            ConfigValidator().validate_config_file(
                str(ROOT / "fabric-config.yml"),
                environment,
                {
                    "core": {
                        "workspace_id": "00000000-0000-0000-0000-000000000007",
                        "item_types_in_scope": scope,
                    }
                },
            )
            if not validate_parameter_file(
                str(ROOT),
                item_type_in_scope=scope,
                environment=environment,
            ):
                fail(errors, f"parameter.yml: fabric-cicd validation failed for {environment}")
        except Exception as exc:
            fail(errors, f"fabric-cicd validation failed for {environment}: {exc}")


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []
    validate_yaml(errors)
    validate_deployment_boundary(errors)
    policy_exceptions = load_policy_exceptions(errors)
    validate_items(errors, warnings, policy_exceptions)
    validate_placeholders(errors)
    validate_fabric_cicd_contract(errors)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print("Fabric repository validation passed.")


if __name__ == "__main__":
    main()
