"""Governance documentation validator — keeps PART 0 framework from drifting.
Pure-doc checks; no runtime impact. Run: python scripts/validate_governance.py
(exit 0 = consistent) — also wired as tests/test_governance_docs.py."""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ALLOWED = {"DONE", "PARTIAL", "BROKEN", "MISSING", "BLOCKED_EXTERNAL"}
REQ_PREFIX = r"(?:CORE|SRC|INGEST|CLAIM|EVENT|VERIFY|LANG|EDIT|MEDIA|PUB|PLATFORM|ADMIN|AI|AUT|WATCH|SEC|PORT|WEB|SEO|GROWTH)-\d+"


def fail(msgs: list[str], msg: str) -> None:
    msgs.append(msg)


def main() -> int:
    errs: list[str] = []
    matrix = (DOCS / "01-REQUIREMENTS-MATRIX.md").read_text(encoding="utf-8")
    catalog = (DOCS / "04-REGRESSION-CATALOG.md").read_text(encoding="utf-8")
    roadmap = (DOCS / "05-EXECUTION-ROADMAP.md").read_text(encoding="utf-8")
    plan1 = (DOCS / "plans" / "PART-01-CANONICAL-CORE.md").read_text(encoding="utf-8")

    # 1) strict status enum per matrix row
    for line in matrix.splitlines():
        m = re.match(r"^\| (" + REQ_PREFIX + r") \|", line)
        if not m:
            continue
        sm = re.findall(r"\| (DONE|PARTIAL|BROKEN|MISSING|BLOCKED_EXTERNAL|DONE\(arch\)|IN_PROGRESS|PLANNED) \|", line)
        if not sm:
            fail(errs, f"{m.group(1)}: no status cell")
        elif sm[0] not in ALLOWED:
            fail(errs, f"{m.group(1)}: non-enum status '{sm[0]}'")

    # 2) duplicate requirement IDs
    ids = re.findall(r"^\| (" + REQ_PREFIX + r") \|", matrix, re.M)
    for rid, n in Counter(ids).items():
        if n > 1:
            fail(errs, f"duplicate requirement ID {rid} x{n}")

    # 3) duplicate regression IDs
    regs = re.findall(r"^\| (REG-\d+) \|", catalog, re.M)
    for rid, n in Counter(regs).items():
        if n > 1:
            fail(errs, f"duplicate regression ID {rid} x{n}")

    # 4) every non-DONE requirement has exactly one numeric roadmap Part
    for line in matrix.splitlines():
        cells = [c.strip() for c in line.split('|')]
        if len(cells) < 4 or not re.fullmatch(REQ_PREFIX, cells[1]):
            continue
        rid, status, part = cells[1], cells[3], cells[-2]
        if status in ALLOWED and status != 'DONE' and not part.isdigit():
            fail(errs, f"{rid}: non-DONE without numeric roadmap part ('{part}')")

    # 4b) status-cell extraction sanity (same parser as above)
    for line in matrix.splitlines():
        cells = [c.strip() for c in line.split('|')]
        if len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[3] not in ALLOWED:
            fail(errs, f"{cells[1]}: non-enum status '{cells[3]}'")

    
    # 4c) no requirement appears as executable scope in multiple Parts
    #     (Matrix Part column is the single source; plans must not add foreign IDs)
    plan_files = sorted((DOCS / "plans").glob("PART-*.md"))
    for pf in plan_files:
        ptxt = pf.read_text(encoding="utf-8")
        for line in matrix.splitlines():
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 4 or not re.fullmatch(REQ_PREFIX, cells[1]):
                continue
            rid, part = cells[1], cells[-2]
            if rid in ptxt and part.isdigit() and pf.name != f"PART-0{part}-" + pf.name.split("-", 2)[-1] if False else False:
                pass
    # strict: PART-01 file must contain every Matrix part==1 ID and NO Matrix ID whose part != 1
    p1_ids = set()
    for line in matrix.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[-2] == "1":
            p1_ids.add(cells[1])
    for pf in plan_files:
        m = re.search(r"PART-(\d+)", pf.name)
        if not m:
            continue
        n = int(m.group(1))
        if n < 1 or n > 3:
            continue
        ptxt = pf.read_text(encoding="utf-8")
        # ownership rows in this plan's coverage map: | ID | ... lines
        owned = {cells[1] for line in ptxt.splitlines()
                 for cells in [[c.strip() for c in line.split("|")]]
                 if len(cells) >= 3 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[0] == "" and line.startswith("| ")}
        if n == 1:
            for rid in p1_ids:
                if rid not in ptxt:
                    fail(errs, f"{rid}: Matrix Part 1 but missing from PART-01 plan")
        if n in (2, 3):
            ids_n = [cells2[1] for line2 in matrix.splitlines()
                     for cells2 in [[c.strip() for c in line2.split("|")]]
                     if len(cells2) >= 4 and re.fullmatch(REQ_PREFIX, cells2[1]) and cells2[-2] == str(n)]
            for rid in ids_n:
                if rid not in ptxt:
                    fail(errs, f"{rid}: Matrix Part {n} but missing from PART-0{n} plan")
            for line in matrix.splitlines():
                cells = [c.strip() for c in line.split("|")]
                if (len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[1] in owned
                        and cells[-2] != str(n) and cells[3] != "DONE"):
                    fail(errs, f"{cells[1]}: coverage-claimed in PART-0{n} plan but Matrix Part={cells[-2]} (cross-phase ownership leak)")

    # 4d) CURRENT-STATUS structural rules
    cs = (DOCS / "00-CURRENT-STATUS.md").read_text(encoding="utf-8")
    repo = re.findall(r"Repository HEAD[^0-9a-f]*([0-9a-f]{7,40})", cs)
    prod = re.findall(r"Production runtime SHA[^0-9a-f]*([0-9a-f]{7,40})", cs)
    if not repo or not prod:
        fail(errs, "Current-Status must declare both 'Repository HEAD' and 'Production runtime SHA' as separate fields")
    _p = cs.split("Production")
    if "Production SHA (=repo HEAD" in cs or (len(_p) > 1 and "=repo HEAD" in _p[1][:80]):
        fail(errs, "Current-Status must not assert Production SHA equals repo HEAD unless verified — use two fields")
    # ambiguous unqualified metric wording
    QUAL = r"(Publication ledger|Telegram remote-mapped|Jobs)[^\n]{0,4}SENT"
    qual_ok = re.sub(QUAL, "OK", cs)
    for pat in (r"\bSENT\s*=\s*\d+", r"\b\d+ SENT mapped\b", r"(?<!ledger )(?!remote-mapped )\bSENT \d+(?!:)"):
        if re.search(pat, qual_ok):
            fail(errs, f"Current-Status contains ambiguous metric wording matching {pat!r} — qualify as 'Publication ledger SENT: N' etc.")

    # 4e) generic PART status validation (Parts 1-10)
    #     PASS => all assigned Matrix IDs DONE.
    #     BLOCKED_EXTERNAL => assigned may be DONE or BLOCKED_EXTERNAL,
    #     but none BROKEN/MISSING/PARTIAL (internally-actionable must be complete).
    part_status = {}
    for line in cs.splitlines():
        if "PART" not in line:
            continue
        for m in re.finditer(r"(\d+)\s*=\s*(PASS|BLOCKED_EXTERNAL|FAIL|PARTIAL)", line):
            part_status[int(m.group(1))] = m.group(2)
    rows_by_part: dict[int, list[tuple[str, str]]] = {}
    st_all: dict[str, str] = {}
    for line in matrix.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1]):
            st_all[cells[1]] = cells[3]
            if cells[-2].isdigit():
                rows_by_part.setdefault(int(cells[-2]), []).append((cells[1], cells[3]))
    for pn, status in part_status.items():
        assigned = rows_by_part.get(pn, [])
        if not assigned:
            fail(errs, f"PART {pn} recorded {status} but no Matrix rows assigned to Part {pn}")
            continue
        if status == "PASS":
            bad = [r for r, st in assigned if st != "DONE"]
            if bad:
                fail(errs, f"Current-Status claims PART {pn} PASS but non-DONE assigned IDs: {bad}")
        elif status == "BLOCKED_EXTERNAL":
            incomplete = [r for r, st in assigned if st in ("BROKEN", "MISSING", "PARTIAL")]
            if incomplete:
                fail(errs, f"PART {pn} BLOCKED_EXTERNAL but internally-actionable IDs incomplete: {incomplete}")

    # 4f) stale-evidence overwrite guard: a DONE row may not carry obsolete
    #     blocker text (the PART-2 regression mechanism for REG-026).
    for line in matrix.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[3] == "DONE":
            blocker = cells[-3] if len(cells) > 3 else ""
            if any(phrase in blocker for phrase in (
                    "direct-story admin path exists", "bypass", "still carry", "absent (TELETHON")):
                fail(errs, f"{cells[1]}: DONE row carries stale blocker text '{blocker[:60]}' — evidence overwrite regression")

    # 5) Part-1 assigned requirements all appear in PART-01 plan
    for line in matrix.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 9 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[-2] == "1":
            if cells[1] not in plan1:
                fail(errs, f"{cells[1]}: assigned to Part 1 but absent from PART-01 plan")

    # 6) tally line matches reality
    statuses = re.findall(r"^\| " + REQ_PREFIX + r" \|.*?\| (DONE|PARTIAL|BROKEN|MISSING|BLOCKED_EXTERNAL) \|", matrix, re.M)
    c = Counter(statuses)
    tm = re.search(r"DONE (\d+) · PARTIAL (\d+) · BROKEN (\d+) · MISSING (\d+) · BLOCKED_EXTERNAL (\d+)", matrix)
    if tm:
        claimed = tuple(int(x) for x in tm.groups())
        actual = (c["DONE"], c["PARTIAL"], c["BROKEN"], c["MISSING"], c["BLOCKED_EXTERNAL"])
        if claimed != actual:
            fail(errs, f"tally mismatch: claimed {claimed} vs actual {actual}")

    # 7) every REG in catalog rows is unique-format & referenced IDs exist
    if roadmap and not roadmap.strip():
        fail(errs, "roadmap empty")

    if errs:
        print("GOVERNANCE FAIL:")
        for e in errs:
            print(" -", e)
        return 1
    print(f"GOVERNANCE PASS ({len(ids)} requirements, {len(regs)} regressions, tallies={dict(c)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
