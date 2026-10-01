"""Wrapper so pytest runs the governance validator (docs consistency = regression
mechanism for REG-026)."""
import subprocess
import sys
from pathlib import Path


def test_governance_docs_consistent():
    script = Path(__file__).resolve().parent.parent / "scripts" / "validate_governance.py"
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
