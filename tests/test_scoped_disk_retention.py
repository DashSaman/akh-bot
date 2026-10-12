"""Scope regression tests use real files; Docker is the only external fake."""
import importlib.util, os, sqlite3, json
from pathlib import Path
from types import SimpleNamespace
import pytest
SPEC=importlib.util.spec_from_file_location("retention",Path(__file__).resolve().parents[1]/"ops/host_disk_retention.py")
m=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)

def test_unknown_tmp_is_never_a_candidate(tmp_path,monkeypatch):
    for name in ("tmp123","twoid.log","pv-build.tmp","pytest-of-root","node-compile-cache"):
        (tmp_path/name).write_text("foreign")
    monkeypatch.setattr(m,"ROOTS_TEMP",(tmp_path,))
    monkeypatch.setattr(m,"CUTOFF",10**12)
    monkeypatch.setattr(m,"open_file",lambda p:False)
    assert list(m.candidate_temp())==[]

def test_foreign_images_never_candidates(monkeypatch):
    old="2026-01-01T00:00:00Z"
    def docker(args,timeout=30):
        if args[:3]==["docker","image","ls"]:
            out="pv-growth-app|old1\npv-growth-app|old2\npv-growth-app|old3\npv-growth-app|old4\npv-growth-app|old5"
        elif args[:3]==["docker","ps","-aq"]: out=""
        elif args[:3]==["docker","image","inspect"]: out="sha256:"+args[-1].split(":")[-1]+"|"+old
        else: raise AssertionError(args)
        return SimpleNamespace(returncode=0,stdout=out,stderr="")
    monkeypatch.setattr(m,"command",docker)
    assert list(m.candidate_images())==[]

def test_backups_keep_two_and_apply_rechecks(tmp_path,monkeypatch):
    monkeypatch.setattr(m,"BACKUP_ROOT",tmp_path)
    monkeypatch.setattr(m,"CUTOFF",10**12)
    monkeypatch.setattr(m,"open_file",lambda p:False)
    for i in range(4):
        p=tmp_path/f"akhbot-2026010{i+1}T010101Z.db"
        c=sqlite3.connect(p)
        for table in ("sources","raw_items","events","stories","jobs","publications"):
            c.execute(f"CREATE TABLE {table}(id INTEGER)")
        c.close()
        os.utime(p,(i+1,i+1))
    candidates=list(m.candidate_backups())
    assert [p.name for _,p in candidates]==["akhbot-20260101T010101Z.db","akhbot-20260102T010101Z.db"]
    for kind,p in candidates: assert m.apply(kind,p)=="REMOVED"
    assert len(list(tmp_path.glob("*.db")))==2
    assert m.apply("backup",tmp_path/"akhbot-20260103T010101Z.db")=="SKIP_PROTECTED"

def test_symlink_parent_and_hardlink_guard(tmp_path,monkeypatch):
    monkeypatch.setattr(m,"CUTOFF",10**12)
    monkeypatch.setattr(m,"open_file",lambda p:False)
    root=tmp_path/"real"; root.mkdir(); p=root/"old"; p.write_text("x")
    link=tmp_path/"link"; link.symlink_to(root,target_is_directory=True)
    assert not m.safe_tree(link/"old")
    os.link(p,root/"alias")
    assert not m.safe_tree(p)

def test_real_open_file_is_protected(tmp_path,monkeypatch):
    p=tmp_path/"open"; p.write_text("active")
    monkeypatch.setattr(m,"CUTOFF",10**12)
    with p.open() as f:
        assert not m.safe_tree(p)

def test_unknown_path_cannot_be_deleted_directly(tmp_path,monkeypatch):
    p=tmp_path/"twoid.log"; p.write_text("foreign")
    monkeypatch.setattr(m,"CUTOFF",10**12)
    assert m.apply("temp",p)=="SKIP_SCOPE"
    assert p.exists()

def test_dry_run_calls_no_mutations(tmp_path,monkeypatch,capsys):
    p=tmp_path/"candidate"; p.write_text("safe")
    monkeypatch.setattr(m,"candidate_temp",lambda:iter([("temp",p)]))
    for name in ("candidate_logs","candidate_backups","candidate_artifacts","candidate_images","candidate_dr_volumes"):
        monkeypatch.setattr(m,name,lambda:iter(()))
    monkeypatch.setattr(m,"LOCK_PATH",tmp_path/"lock")
    monkeypatch.setattr(m,"AUDIT_PATH",tmp_path/"audit.jsonl")
    monkeypatch.setattr(m,"BACKUP_ROOT",tmp_path/"missing-backups")
    monkeypatch.setattr(m,"apply",lambda *args:pytest.fail("dry-run deleted"))
    monkeypatch.setattr(m,"housekeeping",lambda:pytest.fail("dry-run housekeeping"))
    assert m.main([])==0
    assert p.exists()
    report=json.loads(capsys.readouterr().out)
    assert report["mode"]=="DRY_RUN"
    assert not (tmp_path/"audit.jsonl").exists()

def test_corrupt_latest_backup_blocks_cleanup(tmp_path,monkeypatch):
    monkeypatch.setattr(m,"BACKUP_ROOT",tmp_path)
    monkeypatch.setattr(m,"CUTOFF",10**12)
    for i in range(3): (tmp_path/f"akhbot-2026010{i+1}T010101Z.db").write_text("corrupt")
    assert list(m.candidate_backups())==[]

def test_empty_latest_databases_do_not_count_as_restore_points(tmp_path,monkeypatch):
    monkeypatch.setattr(m,"BACKUP_ROOT",tmp_path)
    monkeypatch.setattr(m,"CUTOFF",10**12)
    monkeypatch.setattr(m,"open_file",lambda p:False)
    for i in (1,2):
        p=tmp_path/f"akhbot-2026010{i}T010101Z.db"
        c=sqlite3.connect(p)
        for t in ("sources","raw_items","events","stories","jobs","publications"):
            c.execute(f"CREATE TABLE {t}(id INTEGER)")
        c.close(); os.utime(p,(i,i))
    for i in (3,4):
        p=tmp_path/f"akhbot-2026010{i}T010101Z.db"
        p.touch(); os.utime(p,(i,i))
    assert list(m.candidate_backups())==[]

def test_same_filesystem_bind_mount_is_never_traversed(tmp_path,monkeypatch):
    root=tmp_path/"owned";root.mkdir(); child=root/"foreign";child.mkdir()
    (child/"important").write_text("foreign")
    monkeypatch.setattr(m,"CUTOFF",10**12)
    monkeypatch.setattr(m,"open_file",lambda p:False)
    monkeypatch.setattr(m,"mount_points",lambda:{child})
    assert not m.safe_tree(root)

def test_lock_prevents_concurrent_cleanup(tmp_path,monkeypatch,capsys):
    import fcntl
    lock=tmp_path/"lock"; monkeypatch.setattr(m,"LOCK_PATH",lock)
    monkeypatch.setattr(m,"candidate_temp",lambda:pytest.fail("concurrent scan"))
    with lock.open("w") as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert m.main(["--apply"])==0
    assert json.loads(capsys.readouterr().out)["mode"]=="SKIP_LOCKED"

def test_audit_symlink_aborts_before_any_delete(tmp_path,monkeypatch):
    p=tmp_path/"cleanchk"; p.write_text("disposable")
    foreign=tmp_path/"foreign-audit"; foreign.write_text("preserve")
    audit=tmp_path/"audit";audit.symlink_to(foreign)
    monkeypatch.setattr(m,"AUDIT_PATH",audit)
    monkeypatch.setattr(m,"BACKUP_ROOT",tmp_path/"missing-backups")
    monkeypatch.setattr(m,"LOCK_PATH",tmp_path/"lock")
    monkeypatch.setattr(m,"candidate_temp",lambda:iter([("temp",p)]))
    for name in ("candidate_logs","candidate_backups","candidate_artifacts","candidate_images","candidate_dr_volumes"):
        monkeypatch.setattr(m,name,lambda:iter(()))
    with pytest.raises(OSError): m.main(["--apply"])
    assert p.exists()
    assert foreign.read_text()=="preserve"
