#!/usr/bin/env python3
"""Convert Fabric notebook source (`notebook-content.py`) into `.ipynb`.

The repo stores notebooks in Fabric's Git-integration source format — a `.py` with
`# CELL ********************` markers — which is generated, not hand-authored. This
script reverses that serialization so you can open the notebook in Jupyter/VS Code or
import it manually into Fabric ("Import notebook") without wiring up Git integration.

Usage:
    python scripts/fabric_py_to_ipynb.py                 # all notebooks/ -> build/ipynb/
    python scripts/fabric_py_to_ipynb.py NB1 NB2 ...     # specific .Notebook dirs or .py files
    python scripts/fabric_py_to_ipynb.py --out DIR       # choose output directory
    python scripts/fabric_py_to_ipynb.py --faithful      # keep doc cells as code (no markdown)

By default, cells whose every non-blank line is a `#` comment (the doc/"## Section"
cells) become rendered markdown cells; everything else stays a code cell. The
parameters cell keeps its `parameters` tag. The lakehouse `dependencies` metadata
(which holds unresolved PLACEHOLDER ids) is dropped so manual import doesn't choke —
attach the lakehouse in the Fabric UI after importing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = re.compile(r"^# (METADATA|CELL|PARAMETERS CELL|MARKDOWN) \*{4,}\s*$")


def parse_blocks(text: str) -> list[tuple[str, list[str]]]:
    """Split Fabric notebook source into (kind, body-lines) blocks by its markers."""
    blocks: list[tuple[str, list[str]]] = []
    kind: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        m = MARKER.match(line)
        if m:
            if kind is not None:
                blocks.append((kind, body))
            kind, body = m.group(1), []
        elif kind is not None:
            body.append(line)
        # lines before the first marker (e.g. "# Fabric notebook source") are dropped
    if kind is not None:
        blocks.append((kind, body))
    return blocks


def _trim_blank_edges(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _strip_comment(line: str) -> str:
    if line.startswith("# "):
        return line[2:]
    if line.startswith("#"):
        return line[1:]
    return line


def _is_all_comment(lines: list[str]) -> bool:
    nonblank = [line for line in lines if line.strip()]
    return bool(nonblank) and all(line.lstrip().startswith("#") for line in nonblank)


def _parse_metadata(body: list[str]) -> dict:
    json_lines = [line[len("# META ") :] if line.startswith("# META ") else "" for line in body]
    blob = "\n".join(json_lines).strip()
    return json.loads(blob) if blob else {}


def to_notebook(text: str, *, markdown: bool = True) -> dict:
    """Build an nbformat 4.5 notebook dict from Fabric notebook source text."""
    cells: list[dict] = []
    meta: dict = {}
    idx = 0
    for kind, body in parse_blocks(text):
        if kind == "METADATA":
            meta = _parse_metadata(body)
            continue
        source = _trim_blank_edges(body)
        cell_id = f"c{idx}"
        idx += 1
        if kind == "MARKDOWN" or (markdown and kind != "PARAMETERS CELL" and _is_all_comment(source)):
            text_src = "\n".join(_strip_comment(line) for line in source)
            cells.append(
                {"cell_type": "markdown", "id": cell_id, "metadata": {}, "source": text_src}
            )
        else:
            cell_meta = {"tags": ["parameters"]} if kind == "PARAMETERS CELL" else {}
            cells.append(
                {
                    "cell_type": "code",
                    "id": cell_id,
                    "metadata": cell_meta,
                    "execution_count": None,
                    "outputs": [],
                    "source": "\n".join(source),
                }
            )

    kernel_name = (meta.get("kernel_info") or {}).get("name", "synapse_pyspark")
    nb_meta: dict = {
        "kernelspec": {"name": kernel_name, "display_name": kernel_name, "language": "python"},
        "language_info": {"name": "python"},
    }
    if "kernel_info" in meta:
        nb_meta["kernel_info"] = meta["kernel_info"]
    return {"cells": cells, "metadata": nb_meta, "nbformat": 4, "nbformat_minor": 5}


def _resolve_sources(paths: list[str]) -> list[Path]:
    if not paths:
        return sorted((ROOT / "notebooks").glob("*.Notebook/notebook-content.py"))
    resolved: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            p = p / "notebook-content.py"
        if not p.exists():
            sys.exit(f"Not found: {raw}")
        resolved.append(p)
    return resolved


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert Fabric notebook source to .ipynb")
    ap.add_argument("paths", nargs="*", help=".Notebook dirs or notebook-content.py files")
    ap.add_argument("--out", default=str(ROOT / "build" / "ipynb"), help="output directory")
    ap.add_argument(
        "--faithful",
        action="store_true",
        help="keep comment-only doc cells as code cells (no markdown promotion)",
    )
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for src in _resolve_sources(args.paths):
        name = src.parent.name.removesuffix(".Notebook")
        nb = to_notebook(src.read_text(), markdown=not args.faithful)
        dest = out_dir / f"{name}.ipynb"
        dest.write_text(json.dumps(nb, indent=1) + "\n")
        n_md = sum(c["cell_type"] == "markdown" for c in nb["cells"])
        n_code = len(nb["cells"]) - n_md
        print(f"{name}.ipynb  ({n_code} code, {n_md} markdown)  -> {dest}")


if __name__ == "__main__":
    main()
