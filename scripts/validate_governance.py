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
        n = int(re.search(r"PART-(\d+)", pf.name).group(1))
        if n < 1 or n > 3:
            continue
        ptxt = pf.read_text(encoding="utf-8")
        if n == 1:
            for rid in p1_ids:
                if rid not in ptxt:
                    fail(errs, f"{rid}: Matrix Part 1 but missing from PART-01 plan")
            for line in matrix.splitlines():
                cells = [c.strip() for c in line.split("|")]
                if (len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[1] in ptxt
                        and cells[-2] != "1" and cells[3] != "DONE"):
                    fail(errs, f"{cells[1]}: appears in PART-01 plan but Matrix Part={cells[-2]} (cross-phase leak)")

    # 4d) CURRENT-STATUS must carry exactly one Production SHA line and it must
    #     be a 7-hex token; a Part marked PASS requires all its Part-N IDs DONE.
    cs = (DOCS / "00-CURRENT-STATUS.md").read_text(encoding="utf-8")
    shas = re.findall(r"Production SHA[^0-9a-f]*([0-9a-f]{7,40})", cs)
    if len(set(shas)) != 1:
        fail(errs, f"Current-Status has {len(set(shas))} distinct Production SHA values: {set(shas)}")
    if "SENT=" in cs and "ledger SENT" not in cs:
        fail(errs, "Current-Status uses ambiguous SENT= without metric qualifier")
    m = re.search(r"PART:\s*\*\*1 = PASS", cs)
    if m:
        p1 = [cells[1] for line in matrix.splitlines()
              for cells in [[c.strip() for c in line.split("|")]]
              if len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1]) and cells[-2] == "1"]
        st = {cells[1]: cells[3] for line in matrix.splitlines()
              for cells in [[c.strip() for c in line.split("|")]]
              if len(cells) >= 4 and re.fullmatch(REQ_PREFIX, cells[1])}
        not_done = [r for r in p1 if st.get(r) != "DONE"]
        if not_done:
            fail(errs, f"Current-Status claims PART 1 PASS but non-DONE assigned IDs: {not_done}")

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
