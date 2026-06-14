"""Bulk-rename Fabric notebooks to the naming_standards.md convention.

Renames are safe for orchestration (pipelines/schedules bind to item GUIDs,
not names) but BREAK run-by-name references inside other notebooks
(notebookutils.notebook.run("Name"), %run Name). The `check` step finds those
before you rename.

Workflow:
    1. python rename_notebooks.py inventory --workspace "Finops Hub" -o rename_plan.csv
       Lists every notebook, marks conformance, emits a CSV. Fill in the
       proposed_name column by hand for non-conformant items.
    2. python rename_notebooks.py check --workspace "Finops Hub" -i rename_plan.csv
       Scans all notebook definitions for run-by-name references to any
       notebook you plan to rename. Fix those (or accept the breakage) first.
    3. python rename_notebooks.py apply --workspace "Finops Hub" -i rename_plan.csv
       Dry-run by default; add --execute to PATCH the display names.
       Keep the CSV — it is your rollback mapping.

Auth: Azure CLI credential if `az login` is active, otherwise interactive
browser. Requires: pip install azure-identity requests
"""

import argparse
import base64
import csv
import re
import sys
import time

import requests
from azure.identity import AzureCliCredential, InteractiveBrowserCredential

API = "https://api.fabric.microsoft.com/v1"
SCOPE = "https://api.fabric.microsoft.com/.default"

DOMAINS = "finops|fcst|cback|esg|ops|gov"
SOURCES = "focusazure|focusm365|arg|pricesheet|reservations|carbon|benefits|defender|gh|instana|monitoring"
SUBJECTS = "forecast|chargeback|emissions|monitoring|budget"

# Layer-aware, per naming_standards.md: source token at bronze/silver, subject token at gold.
VALID_RE = re.compile(
    rf"^({DOMAINS})_(bronze|silver)_({SOURCES})_[a-z]+$"
    rf"|^({DOMAINS})_gold_({SUBJECTS})_[a-z]+$"
)

# run-by-name patterns that a rename breaks
REF_PATTERNS = [
    re.compile(r"""notebookutils\.notebook\.run\(\s*["']([^"']+)["']"""),
    re.compile(r"""mssparkutils\.notebook\.run\(\s*["']([^"']+)["']"""),
    re.compile(r"^%run\s+(\S+)", re.MULTILINE),
]


def get_session() -> requests.Session:
    try:
        token = AzureCliCredential().get_token(SCOPE)
    except Exception:
        token = InteractiveBrowserCredential().get_token(SCOPE)
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token.token}"
    return s


def get_paged(s: requests.Session, url: str, params: dict | None = None) -> list[dict]:
    items, params = [], dict(params or {})
    while True:
        r = s.get(url, params=params)
        r.raise_for_status()
        body = r.json()
        items.extend(body.get("value", []))
        token = body.get("continuationToken")
        if not token:
            return items
        params["continuationToken"] = token


def resolve_workspace(s: requests.Session, name: str) -> str:
    matches = [w for w in get_paged(s, f"{API}/workspaces") if w["displayName"] == name]
    if not matches:
        sys.exit(f"Workspace not found: {name!r}")
    return matches[0]["id"]


def list_notebooks(s: requests.Session, wid: str) -> list[dict]:
    return get_paged(s, f"{API}/workspaces/{wid}/items", {"type": "Notebook"})


def get_definition_text(s: requests.Session, wid: str, item_id: str) -> str:
    r = s.post(f"{API}/workspaces/{wid}/items/{item_id}/getDefinition")
    while r.status_code == 202:  # long-running operation
        time.sleep(int(r.headers.get("Retry-After", 2)))
        r = s.get(r.headers["Location"])
    r.raise_for_status()
    body = r.json()
    if "definition" not in body:  # operation result indirection
        r = s.get(r.url.rstrip("/") + "/result")
        r.raise_for_status()
        body = r.json()
    parts = body["definition"]["parts"]
    return "\n".join(
        base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
        for p in parts
        if p.get("payloadType") == "InlineBase64" and not p["path"].endswith(".platform")
    )


def read_plan(path: str) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def cmd_inventory(s, wid, args):
    notebooks = list_notebooks(s, wid)
    rows = []
    for nb in sorted(notebooks, key=lambda n: n["displayName"]):
        name = nb["displayName"]
        conformant = bool(VALID_RE.match(name))
        rows.append({
            "item_id": nb["id"],
            "current_name": name,
            "conformant": conformant,
            "proposed_name": name if conformant else "",
        })
    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "current_name", "conformant", "proposed_name"])
        w.writeheader()
        w.writerows(rows)
    bad = sum(1 for r in rows if not r["conformant"])
    print(f"{len(rows)} notebooks, {bad} non-conformant -> {args.output}")
    print("Fill in proposed_name for non-conformant rows, then run `check`.")


def cmd_check(s, wid, args):
    plan = read_plan(args.input)
    renames = {r["current_name"] for r in plan if r["proposed_name"] and r["proposed_name"] != r["current_name"]}
    if not renames:
        sys.exit("No renames planned in the CSV (proposed_name empty or unchanged everywhere).")

    invalid = [r["proposed_name"] for r in plan if r["proposed_name"] and not VALID_RE.match(r["proposed_name"])]
    for name in invalid:
        print(f"NON-CONFORMANT PROPOSAL: {name}")

    broken = 0
    for nb in list_notebooks(s, wid):
        text = get_definition_text(s, wid, nb["id"])
        refs = {m for pat in REF_PATTERNS for m in pat.findall(text)}
        hits = refs & renames
        for hit in sorted(hits):
            print(f"REFERENCE: {nb['displayName']!r} runs {hit!r} by name — fix before renaming")
            broken += 1
    print(f"\n{len(renames)} renames planned, {broken} breaking references, {len(invalid)} bad proposals.")
    sys.exit(1 if (broken or invalid) else 0)


def cmd_apply(s, wid, args):
    plan = read_plan(args.input)
    todo = [r for r in plan if r["proposed_name"] and r["proposed_name"] != r["current_name"]]
    for r in todo:
        if not VALID_RE.match(r["proposed_name"]):
            sys.exit(f"Refusing: {r['proposed_name']!r} does not match the naming convention.")
    names = [r["proposed_name"] for r in todo]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        sys.exit(f"Refusing: duplicate proposed names {sorted(dupes)}")

    for r in todo:
        print(f"{r['current_name']!r} -> {r['proposed_name']!r}")
        if args.execute:
            resp = s.patch(
                f"{API}/workspaces/{wid}/items/{r['item_id']}",
                json={"displayName": r["proposed_name"]},
            )
            resp.raise_for_status()
    verb = "Renamed" if args.execute else "Would rename (dry run — add --execute)"
    print(f"\n{verb} {len(todo)} notebooks.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["inventory", "check", "apply"])
    p.add_argument("--workspace", required=True, help="Workspace display name")
    p.add_argument("-o", "--output", default="rename_plan.csv", help="inventory: output CSV")
    p.add_argument("-i", "--input", default="rename_plan.csv", help="check/apply: plan CSV")
    p.add_argument("--execute", action="store_true", help="apply: actually rename (default is dry run)")
    args = p.parse_args()

    s = get_session()
    wid = resolve_workspace(s, args.workspace)
    {"inventory": cmd_inventory, "check": cmd_check, "apply": cmd_apply}[args.command](s, wid, args)


if __name__ == "__main__":
    main()
