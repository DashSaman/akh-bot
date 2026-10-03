"""Convert the owner's XLSX source registry to canonical endpoint JSON.

Sheets: External Registry / Fast Social / People & Reporters (+ Dedup Rules
kept for documentation). Output: data/source_registry_endpoints.json — a
committed, reproducible artifact consumed by import_full_registry().

Run:  python scripts/import_source_xlsx.py <path-to-xlsx> [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _clean(v) -> str:
    return str(v).strip() if v is not None else ""


def convert(path: str) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    endpoints: list[dict] = []

    def sheet_rows(name: str) -> list[dict]:
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        header = [_clean(h) for h in rows[0]]
        return [{header[i]: _clean(c) for i, c in enumerate(r)}
                for r in rows[1:] if any(_clean(c) for c in r)]

    # External Registry: full metadata per endpoint
    for r in sheet_rows("External Registry"):
        endpoints.append({
            "entity": r.get("Entity ID", ""),
            "name": r.get("Name", ""),
            "kind": r.get("Kind", ""),
            "language": r.get("Language", ""),
            "platform": r.get("Platform", ""),
            "url": r.get("URL", ""),
            "trust_use": r.get("Trust use", ""),
            "independent": r.get("Counts as independent confirmation?", ""),
            "speed": r.get("Speed", ""),
            "focus": r.get("Focus", ""),
            "evidence": r.get("Evidence / verification", ""),
        })
    # Fast Social + People: role-flavored sheets, same canonical shape
    for r in sheet_rows("Fast Social"):
        endpoints.append({
            "entity": r.get("Entity ID", ""),
            "name": r.get("Name", ""),
            "kind": r.get("Role", ""),
            "language": r.get("Language", ""),
            "platform": r.get("Platform", ""),
            "url": r.get("URL", ""),
            "trust_use": r.get("Role", ""),
            "independent": r.get("Independent?", ""),
            "speed": "realtime",
            "focus": r.get("Focus", ""),
            "evidence": r.get("Evidence", ""),
        })
    for r in sheet_rows("People & Reporters"):
        endpoints.append({
            "entity": r.get("Entity ID", ""),
            "name": r.get("Name", ""),
            "kind": "Person",
            "language": r.get("Language", ""),
            "platform": r.get("Platform", ""),
            "url": r.get("URL", ""),
            "trust_use": "Direct person",
            "independent": r.get("Independent?", ""),
            "speed": "realtime",
            "focus": r.get("Focus", ""),
            "evidence": r.get("Evidence", ""),
        })
    # dedup identical endpoints across sheets (same entity+platform+url)
    seen: set[tuple] = set()
    out = []
    for ep in endpoints:
        key = (ep["entity"].lower(), ep["platform"].lower(), ep["url"].lower())
        if key in seen or not ep["entity"] or not ep["url"]:
            continue
        seen.add(key)
        out.append(ep)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--out", default=str(ROOT / "data" / "source_registry_endpoints.json"))
    args = ap.parse_args()
    endpoints = convert(args.xlsx)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(endpoints, ensure_ascii=False, indent=1), encoding="utf-8")
    ids = {e["entity"].lower() for e in endpoints}
    print(f"converted {len(endpoints)} endpoints / {len(ids)} identities -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
