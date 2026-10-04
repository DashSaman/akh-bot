"""Governance validation regression tests (PART 2.1) — in-process fixtures."""
from __future__ import annotations

import contextlib
import io as _io
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "scripts"))

import validate_governance as vg  # noqa: E402


def validate(docs_root: Path):
    old = vg.DOCS
    vg.DOCS = docs_root
    buf = _io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = vg.main()
    finally:
        vg.DOCS = old
    return rc, buf.getvalue()


def mutated_docs(status_repl=None, matrix_fn=None):
    tmp = Path(tempfile.mkdtemp()) / "docs"
    shutil.copytree(DOCS, tmp)
    st_p = tmp / "00-CURRENT-STATUS.md"
    if status_repl:
        st = st_p.read_text(encoding="utf-8")
        find, repl = status_repl
        assert find in st, "anchor missing: %r" % find
        st_p.write_text(st.replace(find, repl), encoding="utf-8")
    if matrix_fn:
        (tmp / "01-REQUIREMENTS-MATRIX.md").write_text(
            matrix_fn((tmp / "01-REQUIREMENTS-MATRIX.md").read_text(encoding="utf-8")),
            encoding="utf-8")
    return tmp


def test_part_pass_fails_when_assigned_id_not_done():
    d = mutated_docs(matrix_fn=lambda mx: mx.replace(
        "| CORE-002 | No RawItem\u2192publisher direct path | DONE |",
        "| CORE-002 | No RawItem\u2192publisher direct path | PARTIAL |", 1))
    rc, out = validate(d)
    assert rc != 0 and "CORE-002" in out


def test_blocked_external_part_rejects_partial_assigned():
    def fix(mx):
        out = []
        for ln in mx.split(chr(10)):
            if ln.startswith('| CORE-009 |') and '| DONE |' in ln:
                cells = ln.split('|')
                cells[-2] = ' 2 '
                ln = '|'.join(cells)
            out.append(ln)
        return chr(10).join(out)

    d = mutated_docs(matrix_fn=fix)
    rc, out = validate(d)
    assert rc != 0 and ('PART 2' in out or 'Part 2' in out)


def test_missing_production_runtime_sha_field_fails():
    d = mutated_docs(status_repl=("Production runtime SHA:", "Prod SHA:"))
    rc, out = validate(d)
    assert rc != 0 and "Production runtime SHA" in out


def test_asserted_sha_equality_without_verification_fails():
    d = mutated_docs(status_repl=(
        "Production runtime SHA",
        "- **Production SHA (=repo HEAD):** 1fd0200"))
    rc, out = validate(d)
    assert rc != 0 and ("=repo HEAD" in out or "equals repo HEAD" in out)


def test_ambiguous_sent_wording_fails():
    import re as _re

    st = (DOCS / "00-CURRENT-STATUS.md").read_text(encoding="utf-8")
    m = _re.search(r"Publication ledger SENT: \*\*\d+\*\*", st)
    assert m, "SENT metric line missing from status doc"
    for bad in ("Publication ledger SENT: 92 and 86 SENT mapped",
                "total: SENT 89 today"):
        d = mutated_docs(status_repl=(m.group(0), bad))
        rc, out = validate(d)
        assert rc != 0, "must reject: %r" % bad
        assert "ambiguous metric" in out


def test_done_row_with_stale_blocker_text_fails():
    def fix(mx):
        lines = mx.split("\n")
        for i, ln in enumerate(lines):
            if ln.startswith("| CORE-002 |") and "| DONE |" in ln:
                cells = ln.split("|")
                cells[-3] = " direct-story admin path exists (scripts) "
                lines[i] = "|".join(cells)
        return "\n".join(lines)

    d = mutated_docs(matrix_fn=fix)
    rc, out = validate(d)
    assert rc != 0 and "stale blocker" in out


def test_current_docs_pass():
    rc, out = validate(DOCS)
    assert rc == 0, out
