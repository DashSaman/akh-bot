"""Five-day cleanup cannot touch live files, symlinks or other projects."""
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

SPEC = importlib.util.spec_from_file_location(
    "host_disk_retention",
    Path(__file__).resolve().parents[1] / "ops" / "host_disk_retention.py",
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_docker_nanosecond_timestamp():
    s = "2026-10-06T13:39:56.843275145Z"
    got = m.created_time(s)
    assert datetime.fromtimestamp(got, timezone.utc).year == 2026


def test_old_temp_file_rejected_if_open(tmp_path, monkeypatch):
    p = tmp_path / "tmp-test.log"
    p.write_text("cache")
    monkeypatch.setattr(m, "CUTOFF", (datetime.now(timezone.utc) +
                        timedelta(days=1)).timestamp())
    monkeypatch.setattr(m, "open_file", lambda _: True)
    assert not m.safe_tree(p)


def test_symlinks_are_never_pruned(tmp_path, monkeypatch):
    p = tmp_path / "tmp-test.log"
    p.write_text("cache")
    link = tmp_path / "tmp-link"
    link.symlink_to(p)
    monkeypatch.setattr(m, "CUTOFF", (datetime.now(timezone.utc) +
                        timedelta(days=1)).timestamp())
    monkeypatch.setattr(m, "open_file", lambda _: False)
    assert not m.safe_tree(link)


def test_fresh_temp_file_is_preserved(tmp_path, monkeypatch):
    p = tmp_path / "tmp-new.log"
    p.write_text("still in use")
    monkeypatch.setattr(m, "open_file", lambda _: False)
    assert not m.safe_tree(p)


def test_no_global_docker_or_containerd_prune():
    src = Path(m.__file__).read_text()
    assert '"image", "prune"' not in src
    assert '"system", "prune"' not in src
    assert "containerd/snapshots" not in src
    assert "IMAGE_KEEP" in src
    assert m.IMAGE_KEEP["pv-growth-app"] >= 3


def test_dry_run_never_executes_deletes(monkeypatch):
    monkeypatch.setattr(m, "candidate_temp", lambda: iter(()))
    monkeypatch.setattr(m, "candidate_logs", lambda: iter(()))
    monkeypatch.setattr(m, "candidate_releases", lambda: iter(()))
    monkeypatch.setattr(m, "candidate_images", lambda: iter(()))
    assert m.RETENTION_DAYS == 5


def test_old_dr_volume_cleanup_keeps_newest(monkeypatch):
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta

    old = (datetime.now(timezone.utc)-timedelta(days=10)).isoformat()
    names = ("akhbot_dr_20261003T175910Z\n"
             "akhbot_dr_20261003T180007Z\n")
    def fake_command(args, timeout=30):
        if args[:3] == ["docker", "volume", "ls"]:
            return SimpleNamespace(returncode=0, stdout=names)
        if args[:3] == ["docker", "ps", "-aq"]:
            return SimpleNamespace(returncode=0, stdout="")
        if args[:3] == ["docker", "volume", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=old)
        raise AssertionError(f"unexpected operation {args!r}")
    monkeypatch.setattr(m, "command", fake_command)
    candidates = list(m.candidate_dr_volumes())
    assert candidates == [("old-dr-volume", Path("akhbot_dr_20261003T175910Z"))]


def test_dr_volume_names_are_strict():
    import re
    pattern = r"akhbot_dr_\d{8}T\d{6}Z"
    assert re.fullmatch(pattern, "akhbot_dr_20261003T175910Z")
    assert not re.fullmatch(pattern, "akhbot_data")
    assert not re.fullmatch(pattern, "twoid_postgres")
    assert not re.fullmatch(pattern, "../../containerd")
