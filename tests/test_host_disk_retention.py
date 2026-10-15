"""Basic retention safety behavior."""
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import json

SPEC=importlib.util.spec_from_file_location("host_disk_retention",Path(__file__).resolve().parents[1]/"ops/host_disk_retention.py")
m=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)

def test_docker_nanosecond_timestamp():
    assert datetime.fromtimestamp(m.created_time("2026-10-06T13:39:56.843275145Z"),timezone.utc).year==2026

def test_old_temp_file_rejected_if_open(tmp_path,monkeypatch):
    p=tmp_path/"old";p.write_text("x")
    monkeypatch.setattr(m,"CUTOFF",10**12)
    monkeypatch.setattr(m,"open_file",lambda _:True)
    assert not m.safe_tree(p)

def test_symlinks_are_never_pruned(tmp_path,monkeypatch):
    p=tmp_path/"old";p.write_text("x"); link=tmp_path/"link";link.symlink_to(p)
    monkeypatch.setattr(m,"CUTOFF",10**12)
    assert not m.safe_tree(link)

def test_fresh_temp_file_is_preserved(tmp_path):
    p=tmp_path/"new";p.write_text("x")
    assert not m.safe_tree(p)

def test_dr_volume_cleanup_keeps_newest_and_container_refs(monkeypatch):
    names=["akhbot_dr_20260101T010101Z","akhbot_dr_20260102T010101Z","akhbot_dr_20260103T010101Z","foreign"]
    def fake(args,timeout=30):
        if args[:3]==["docker","volume","ls"]: out="\n".join(names)
        elif args[:3]==["docker","ps","-aq"]: out="stopped"
        elif args[:2]==["docker","inspect"]: out=json.dumps([{"Image":"sha256:a","Mounts":[{"Name":names[1]}]}])
        elif args[:3]==["docker","volume","inspect"]:
            n=args[-1]
            out=json.dumps([{"CreatedAt":"2026-01-01T01:01:01Z","Driver":"local","Options":None,"Mountpoint":"/var/lib/docker/volumes/"+n+"/_data"}])
        else: raise AssertionError(args)
        return SimpleNamespace(returncode=0,stdout=out,stderr="")
    monkeypatch.setattr(m,"command",fake)
    monkeypatch.setattr(m,"safe_tree",lambda p:True)
    assert list(m.candidate_dr_volumes())==[("old-dr-volume",Path(names[0]))]

def test_images_keep_running_stopped_and_newest_distinct_rollback(monkeypatch):
    entries={"running":("a",1),"running-alias":("a",1),"rollback":("b",4),"stopped":("c",3),"old":("d",2)}
    def fake(args,timeout=30):
        if args[:3]==["docker","image","ls"]: out="\n".join("akhbot-app|"+n for n in entries)
        elif args[:3]==["docker","ps","-aq"]: out="running stopped"
        elif args[:2]==["docker","inspect"]: out=json.dumps([{"Image":"sha256:a"},{"Image":"sha256:c"}])
        elif args[:3]==["docker","image","inspect"]:
            n=args[-1].split(":")[-1];id,day=entries[n]
            out=f"sha256:{id}|2026-01-0{day}T00:00:00Z"
        else: raise AssertionError(args)
        return SimpleNamespace(returncode=0,stdout=out,stderr="")
    monkeypatch.setattr(m,"command",fake)
    assert list(m.candidate_images())==[("old-image",Path("akhbot-app:old"))]

def test_inventory_error_aborts_instead_of_deleting(monkeypatch):
    import pytest
    monkeypatch.setattr(m,"command",lambda *a,**k:SimpleNamespace(returncode=1,stdout="",stderr="failed"))
    with pytest.raises(RuntimeError): list(m.candidate_images())

def test_rotated_log_allowlist_rejects_active_and_foreign():
    assert m.log_allowed(Path("/var/log/x-ui/3xui-2026-01-01T01-01-01.123.log.gz"))
    assert m.log_allowed(Path("/var/log/apache2/rasteh_access.log.2.gz"))
    for p in ("/var/log/x-ui/3xui.log","/var/log/apache2/mirza_access.log.2.gz","/var/log/mysql/error.log.6.gz"):
        assert not m.log_allowed(Path(p))
