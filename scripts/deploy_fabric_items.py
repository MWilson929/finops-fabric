#!/usr/bin/env python3
"""Deploy one FinOps Hub workspace from an immutable pipeline artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

from azure.identity import AzureCliCredential
from fabric_cicd import deploy_with_config


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--scope", choices=SCOPES, required=True)
    parser.add_argument("--config-file", default="fabric-config.yml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config_file).resolve()

    deploy_with_config(
        config_file_path=str(config_path),
        token_credential=AzureCliCredential(),
        environment=args.environment,
        config_override={
            "core": {
                "workspace_id": args.workspace_id,
                "item_types_in_scope": SCOPES[args.scope],
            }
        },
    )


if __name__ == "__main__":
    main()
