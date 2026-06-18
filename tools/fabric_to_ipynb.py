"""Convert Fabric notebook source-format folders back into standard .ipynb files.

Inverse of ``ipynb_to_fabric.py``. Useful when you need to upload a notebook to
Fabric manually — the workspace's Import-from-file UI accepts ``.ipynb`` but
not the git source format the deployment pipeline reads.

Reads ``notebook-content.py`` from a ``<Name>.Notebook/`` folder and writes
``<Name>.ipynb`` to the parent directory (or wherever ``--output`` points).

Markdown cells are detected by the convention the forward converter uses:
every non-blank line in a ``# CELL`` block starts with ``#``. Each line has
its ``# `` prefix stripped to recover the original markdown source. A
``# PARAMETERS CELL`` block becomes a code cell tagged ``parameters``.

The Fabric ``# METADATA`` block is discarded — Jupyter has its own metadata
fields; the kernel, lakehouse defaults etc. come back when Fabric re-imports.

Usage:
    python tools/fabric_to_ipynb.py notebooks/foo.Notebook
    python tools/fabric_to_ipynb.py incubation/bar.Notebook -o /tmp/
    python tools/fabric_to_ipynb.py notebooks/*.Notebook
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

METADATA_MARKER = "# METADATA ********************"
CELL_MARKER = "# CELL ********************"
PARAM_MARKER = "# PARAMETERS CELL ********************"

MARKERS = {METADATA_MARKER, CELL_MARKER, PARAM_MARKER}


def _classify_and_unwrap(body: str) -> tuple[str, str]:
    """Return ('markdown'|'code', recovered_source) for a cell body."""
    non_blank = [ln for ln in body.split("\n") if ln.strip()]
    is_markdown = bool(non_blank) and all(ln.lstrip().startswith("#") for ln in non_blank)
    if not is_markdown:
        return "code", body

    recovered = []
    for ln in body.split("\n"):
        if ln.strip() in ("", "#"):
            recovered.append("")
        elif ln.startswith("# "):
            recovered.append(ln[2:])
        elif ln.startswith("#"):
            recovered.append(ln[1:])
        else:
            recovered.append(ln)
    return "markdown", "\n".join(recovered)


def parse_fabric_source(text: str) -> list[dict]:
    """Split notebook-content.py into a list of cell dicts."""
    cells: list[dict] = []
    current_lines: list[str] | None = None
    current_marker: str | None = None

    def flush() -> None:
        if current_lines is None or current_marker == METADATA_MARKER:
            return
        body = "\n".join(current_lines).strip("\n")
        cell_type, source = _classify_and_unwrap(body)
        tags = ["parameters"] if current_marker == PARAM_MARKER and cell_type == "code" else []
        cells.append({"cell_type": cell_type, "source": source, "tags": tags})

    for line in text.split("\n"):
        if line in MARKERS:
            flush()
            current_lines = []
            current_marker = line
            continue
        if current_lines is not None:
            current_lines.append(line)

    flush()
    return cells


def _source_as_list(text: str) -> list[str]:
    """Jupyter convention: each list entry ends with \\n except possibly the last."""
    if not text:
        return []
    lines = text.split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


def to_notebook(cells: list[dict]) -> dict:
    nb_cells = []
    for i, c in enumerate(cells):
        cell: dict = {
            "cell_type": c["cell_type"],
            "id": f"cell-{i}",
            "metadata": {"tags": c["tags"]} if c["tags"] else {},
            "source": _source_as_list(c["source"]),
        }
        if c["cell_type"] == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        nb_cells.append(cell)

    return {
        "cells": nb_cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def convert(notebook_dir: Path, output_dir: Path | None = None) -> Path:
    if not notebook_dir.is_dir() or not notebook_dir.name.endswith(".Notebook"):
        raise ValueError(f"{notebook_dir} is not a *.Notebook folder")
    src_file = notebook_dir / "notebook-content.py"
    if not src_file.exists():
        raise FileNotFoundError(f"{src_file} not found")

    cells = parse_fabric_source(src_file.read_text())
    nb = to_notebook(cells)

    out_dir = output_dir or notebook_dir.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = notebook_dir.name[: -len(".Notebook")] + ".ipynb"
    out_path = out_dir / out_name
    out_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
    return out_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("notebook", type=Path, nargs="+", help="<Name>.Notebook folder(s) to convert")
    p.add_argument("-o", "--output", type=Path, help="output directory (default: parent of .Notebook folder)")
    args = p.parse_args()

    for nb in args.notebook:
        try:
            out = convert(nb, args.output)
        except (ValueError, FileNotFoundError) as e:
            print(f"  skip: {e}", file=sys.stderr)
            continue
        print(f"  converted: {nb.name} -> {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
