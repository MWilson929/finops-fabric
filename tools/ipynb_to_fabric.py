"""Convert standard .ipynb files into Fabric .Notebook/ source-format folders.

Fabric's Git-integration source format for a notebook is a folder
``<Name>.Notebook/`` containing:

  - ``notebook-content.py`` — Python file with ``# METADATA ... # META { json }``
    and ``# CELL ********************`` / ``# PARAMETERS CELL ...`` markers.
    Markdown cells are flattened into ``# CELL`` blocks where each line is a
    ``#`` Python comment (matching the existing repo's convention — none of the
    in-repo Fabric notebooks use ``# MARKDOWN`` markers).
  - ``.platform`` — JSON metadata with ``displayName``, ``logicalId``, etc.

Notebooks the Fabric deployment pipeline picks up are only the ``.Notebook``
folders; loose ``.ipynb`` files are ignored. Convert anything you want
deployed, and delete the source ``.ipynb`` once verified.

Usage:
    python tools/ipynb_to_fabric.py notebooks/foo.ipynb [notebooks/bar.ipynb ...]
    python tools/ipynb_to_fabric.py --all      # convert every loose .ipynb under notebooks/

A converted notebook outputs into the same parent directory as the source
``.ipynb``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_LAKEHOUSE_META = """# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "PLACEHOLDER_WORKSPACE_ID",
# META       "default_lakehouse_name": "FinOpsHub",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
# META     }
# META   }
# META }"""

CELL_MARKER = "# CELL ********************"
PARAM_MARKER = "# PARAMETERS CELL ********************"
HEADER = "# Fabric notebook source"


def cell_to_fabric_chunk(cell: dict) -> str | None:
    """Return one ``# CELL`` / ``# PARAMETERS CELL`` chunk for the given ipynb cell."""
    source_lines = cell.get("source") or []
    if isinstance(source_lines, str):
        source_lines = source_lines.splitlines(keepends=True)
    text = "".join(source_lines).rstrip("\n")

    cell_type = cell.get("cell_type")
    if cell_type == "markdown":
        # Each line becomes a # comment; blank lines become a bare "#"
        body = "\n".join(f"# {ln}" if ln else "#" for ln in text.split("\n"))
        return f"{CELL_MARKER}\n\n{body}"

    if cell_type == "code":
        tags = (cell.get("metadata") or {}).get("tags") or []
        marker = PARAM_MARKER if "parameters" in tags else CELL_MARKER
        return f"{marker}\n\n{text}" if text else f"{marker}\n"

    return None  # raw or unknown — skip silently


def convert(ipynb_path: Path) -> Path:
    nb = json.loads(ipynb_path.read_text())
    display_name = ipynb_path.stem
    out_dir = ipynb_path.parent / f"{display_name}.Notebook"
    out_dir.mkdir(exist_ok=True)

    # notebook-content.py
    parts = [HEADER, "", "# METADATA ********************", "", DEFAULT_LAKEHOUSE_META]
    for cell in nb.get("cells", []):
        chunk = cell_to_fabric_chunk(cell)
        if chunk is not None:
            parts.extend(["", chunk])
    (out_dir / "notebook-content.py").write_text("\n".join(parts) + "\n")

    # .platform — keep minimal; users can enrich description/tags in Fabric or via PR
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {
            "type": "Notebook",
            "displayName": display_name,
        },
        "config": {
            "version": "2.0",
            "logicalId": f"PLACEHOLDER_GUID_{display_name.upper()}",
        },
    }
    (out_dir / ".platform").write_text(json.dumps(platform, indent=2) + "\n")
    return out_dir


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ipynb", nargs="*", type=Path, help=".ipynb file(s) to convert")
    p.add_argument("--all", action="store_true",
                   help="convert every loose .ipynb under notebooks/ that doesn't already have a sibling .Notebook/ folder")
    args = p.parse_args()

    targets: list[Path] = []
    if args.all:
        notebooks_dir = Path(__file__).resolve().parents[1] / "notebooks"
        if not notebooks_dir.is_dir():
            print(f"--all: {notebooks_dir} does not exist", file=sys.stderr)
            return 2
        for ipynb in sorted(notebooks_dir.glob("*.ipynb")):
            if (ipynb.parent / f"{ipynb.stem}.Notebook").is_dir():
                print(f"  skip: {ipynb.name} (sibling .Notebook/ already exists)")
                continue
            targets.append(ipynb)
    else:
        targets = args.ipynb

    if not targets:
        print("nothing to convert.")
        return 0

    for ipynb in targets:
        out = convert(ipynb)
        print(f"  converted: {ipynb.name} -> {out.name}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
