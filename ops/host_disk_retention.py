#!/usr/bin/env python3
"""Rasteh-only retention. Dry-run by default; no global prune or service restart."""
from __future__ import annotations
import argparse, datetime, fcntl, json, os, pathlib, re, shutil, sqlite3, stat, subprocess, sys

RETENTION_DAYS = 5
CUTOFF = (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=5)).timestamp()
DATA_ROOT = pathlib.Path("/var/lib/docker/volumes/akhbot_data/_data")
BACKUP_ROOT = DATA_ROOT/"backups"
ROOTS_TEMP = (pathlib.Path("/tmp"), pathlib.Path("/var/tmp"))
TEMP_NAMES = {"cleanchk", "cleanchk2", "ghchk", "relchk"}
TEMP_LOG = re.compile(r"(?:rasteh|akhbot)[-_][A-Za-z0-9_.-]+\.(?:log|tmp|part|exit)")
ARTIFACTS = tuple(pathlib.Path("/opt/akhbot")/x for x in ("drill-013","drill-014","shadow-p3","dr-20261003T175910Z","dr-20261003T175923Z","dr-src.db")) + (DATA_ROOT/"media-cache",)
LOG_ROOTS = (pathlib.Path("/var/log/apache2"),pathlib.Path("/var/log/x-ui"))
APACHE_LOG = re.compile(r"(?:rasteh|akhbot)[_-](?:access|error)\.log\.\d+(?:\.gz)?")
XUI_LOG = re.compile(r"3xui-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d+\.log\.gz")
DB_BACKUP = re.compile(r"(?:akhbot-\d{8}T\d{6}Z|pre-[A-Za-z0-9_-]+-\d{8}T\d{6}Z)\.db")
OTHER_BACKUP = re.compile(r"rasteh_(?:footer|duplicate)_\d{8}_originals\.json")
DR_NAME = re.compile(r"akhbot_dr_\d{8}T\d{6}Z")
IMAGE_KEEP = {"akhbot-app": 2, "akhbot-qa-watch": 2}
LOCK_PATH = pathlib.Path("/run/lock/rasteh-host-disk-maintenance.lock")
AUDIT_PATH = DATA_ROOT/"reports/disk-maintenance.jsonl"

def command(argv, timeout=30):
    return subprocess.run(argv,text=True,capture_output=True,timeout=timeout,check=False)

def clean_path(p):
    p = pathlib.Path(p)
    return p.is_absolute() and ".." not in p.parts and not any(x.is_symlink() for x in (p,*p.parents))

def open_file(p):
    """Fresh fd/cwd/root/mmap scan, including container paths via /proc."""
    try:
        nodes=[p]
        if p.is_dir():
            for base,dirs,files in os.walk(p,followlinks=False):
                nodes.extend(pathlib.Path(base)/n for n in dirs+files)
                if len(nodes)>30000: return True
        targets={(s.st_dev,s.st_ino) for s in (n.stat() for n in nodes)}
        for proc in pathlib.Path("/proc").iterdir():
            if not proc.name.isdigit(): continue
            try:
                refs=list((proc/"fd").iterdir())+[proc/"cwd",proc/"root"]
                for ref in refs:
                    try:
                        st=ref.stat()
                        if (st.st_dev,st.st_ino) in targets: return True
                        name=os.readlink(ref).removesuffix(" (deleted)")
                        if p.is_dir() and (name==str(p) or name.startswith(str(p)+"/")): return True
                    except FileNotFoundError: continue
                # Mapping inodes also protect already-closed memory-mapped files.
                for line in (proc/"maps").read_text().splitlines():
                    fields=line.split(None,5)
                    major,minor=fields[3].split(":")
                    if (os.makedev(int(major,16),int(minor,16)),int(fields[4])) in targets:
                        return True
            except (FileNotFoundError,ProcessLookupError): continue
        return False
    except (OSError,ValueError): return True  # fail closed on incomplete visibility

def mount_points():
    """Mountinfo also detects bind mounts on the same filesystem."""
    rows=pathlib.Path("/proc/self/mountinfo").read_text().splitlines()
    return {pathlib.Path(re.sub(r"\\([0-7]{3})",lambda m:chr(int(m[1],8)),row.split()[4])) for row in rows}

def safe_tree(p):
    try:
        if not clean_path(p) or os.path.ismount(p): return False
        if any(m==p or p in m.parents for m in mount_points()): return False
        root_stat=p.lstat()
        nodes=[p]
        if p.is_dir():
            for base,dirs,files in os.walk(p,followlinks=False):
                nodes.extend(pathlib.Path(base)/x for x in dirs+files)
                if len(nodes)>30000: return False
        for node in nodes:
            s=node.lstat()
            if node.is_symlink() or os.path.ismount(node) or s.st_dev!=root_stat.st_dev: return False
            if not (stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)): return False
            if stat.S_ISREG(s.st_mode) and s.st_nlink!=1: return False
            if max(s.st_mtime,s.st_ctime)>=CUTOFF: return False
        return not open_file(p)
    except OSError: return False

def temp_allowed(p):
    return p.parent in ROOTS_TEMP and (p.name in TEMP_NAMES or TEMP_LOG.fullmatch(p.name))

def log_allowed(p):
    return (p.parent==LOG_ROOTS[0] and APACHE_LOG.fullmatch(p.name)) or (
        p.parent==LOG_ROOTS[1] and XUI_LOG.fullmatch(p.name))

def candidate_temp():
    for root in ROOTS_TEMP:
        if clean_path(root) and root.is_dir():
            for p in root.iterdir():
                if temp_allowed(p) and safe_tree(p): yield ("temp",p)

def candidate_logs():
    for root in LOG_ROOTS:
        if clean_path(root) and root.is_dir():
            for p in root.iterdir():
                if log_allowed(p) and p.is_file() and safe_tree(p): yield ("rotated-log",p)

def candidate_artifacts():
    for p in ARTIFACTS:
        if p.exists() and safe_tree(p): yield ("artifact",p)

def protected_backups():
    if not clean_path(BACKUP_ROOT) or not BACKUP_ROOT.is_dir(): return None
    files=[p for p in BACKUP_ROOT.iterdir() if DB_BACKUP.fullmatch(p.name)]
    if any(not clean_path(p) or not p.is_file() for p in files): return None
    files.sort(key=lambda p:(p.stat().st_mtime,p.name),reverse=True)
    if len(files)<2: return None
    keep=set(files[:2])
    # Two real, readable SQLite restore points required, not merely two filenames.
    try:
        for p in keep:
            c=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=5)
            try:
                c.execute("PRAGMA query_only=ON")
                tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if p.stat().st_size==0 or not {"sources","raw_items","events","stories","jobs","publications"}<=tables: return None
                if c.execute("PRAGMA quick_check").fetchall()!=[("ok",)]: return None
            finally: c.close()
    except (sqlite3.Error,OSError): return None
    return keep

def candidate_backups():
    keep=protected_backups()
    if keep is None: return
    for p in sorted(BACKUP_ROOT.iterdir()):
        if p not in keep and (DB_BACKUP.fullmatch(p.name) or OTHER_BACKUP.fullmatch(p.name)) and safe_tree(p):
            yield ("backup",p)

def created_time(value):
    value=re.sub(r"(\.\d{6})\d+(?=[+-])",r"\1",value.replace("Z","+00:00"))
    return datetime.datetime.fromisoformat(value).timestamp()

def container_inventory():
    r=command(["docker","ps","-aq"],15)
    if r.returncode: raise RuntimeError("container inventory failed")
    if not r.stdout.split(): return []
    r=command(["docker","inspect",*r.stdout.split()],20)
    if r.returncode: raise RuntimeError("container inspect failed")
    return json.loads(r.stdout)

def candidate_images():
    listing=command(["docker","image","ls","--format","{{.Repository}}|{{.Tag}}"],15)
    if listing.returncode: raise RuntimeError("image inventory failed")
    containers=container_inventory()
    active={x["Image"] for x in containers}
    repos={}
    for row in listing.stdout.splitlines():
        repo,tag=row.split("|",1)
        if repo not in IMAGE_KEEP or tag=="<none>": continue
        ref=repo+":"+tag
        meta=command(["docker","image","inspect","-f","{{.Id}}|{{.Created}}",ref],10)
        if meta.returncode: raise RuntimeError("image inspect failed")
        image_id,stamp=meta.stdout.strip().split("|",1)
        repos.setdefault(repo,[]).append((created_time(stamp),ref,image_id))
    for repo,entries in repos.items():
        entries.sort(reverse=True)
        distinct=list(dict.fromkeys(x[2] for x in entries))
        keep=set(distinct[:IMAGE_KEEP[repo]])|active
        unused=[x for x in entries if x[2] not in active]
        if unused: keep.add(unused[0][2])  # newest distinct unused rollback
        for age,ref,image_id in entries:
            if age<CUTOFF and image_id not in keep: yield ("old-image",pathlib.Path(ref))

def candidate_dr_volumes():
    listing=command(["docker","volume","ls","--format","{{.Name}}"],15)
    if listing.returncode: raise RuntimeError("volume inventory failed")
    names=sorted((n for n in listing.stdout.splitlines() if DR_NAME.fullmatch(n)),reverse=True)
    containers=container_inventory()
    refs={v.get("Name") for c in containers for v in c["Mounts"]}
    for name in names[1:]:  # preserve previous policy's newest DR restore point
        if name in refs: continue
        r=command(["docker","volume","inspect",name],10)
        if r.returncode: raise RuntimeError("volume inspect failed")
        meta=json.loads(r.stdout)[0]
        mount=pathlib.Path("/var/lib/docker/volumes")/name/"_data"
        if meta["Driver"]!="local" or meta.get("Options") or meta["Mountpoint"]!=str(mount): continue
        if created_time(meta["CreatedAt"])<CUTOFF and safe_tree(mount):
            yield ("old-dr-volume",pathlib.Path(name))

def parent_fd(p):
    """Open each absolute parent component with O_NOFOLLOW, anchoring deletion."""
    fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parent.parts[1:]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd); fd=new
        return fd
    except BaseException:
        os.close(fd); raise

def apply(kind,p):
    p=pathlib.Path(p)
    if kind in ("old-image","old-dr-volume"):
        candidates=candidate_images if kind=="old-image" else candidate_dr_volumes
        if (kind,p) not in list(candidates()): return "SKIP_PROTECTED"
        argv=["docker","image" if kind=="old-image" else "volume","rm",str(p)]
        r=command(argv,90)
        return "REMOVED" if r.returncode==0 else "SKIP_IN_USE"
    scoped=(kind=="temp" and temp_allowed(p)) or (kind=="rotated-log" and log_allowed(p)) or (
        kind=="artifact" and p in ARTIFACTS) or (kind=="backup" and p.parent==BACKUP_ROOT and (
            DB_BACKUP.fullmatch(p.name) or OTHER_BACKUP.fullmatch(p.name)))
    if not scoped: return "SKIP_SCOPE"
    if kind=="backup":
        keep=protected_backups()
        if keep is None or p in keep: return "SKIP_PROTECTED"
    if not safe_tree(p): return "SKIP_SAFETY"
    before=p.lstat()
    fd=parent_fd(p)
    try:
        current=os.stat(p.name,dir_fd=fd,follow_symlinks=False)
        if (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_ctime_ns)!=(current.st_dev,current.st_ino,current.st_mtime_ns,current.st_ctime_ns):
            return "SKIP_CHANGED"
        if stat.S_ISDIR(current.st_mode):
            if not shutil.rmtree.avoids_symlink_attacks: return "SKIP_PLATFORM"
            if sys.version_info >= (3,11):
                shutil.rmtree(p.name,dir_fd=fd)
            else:  # Python 3.10 host: anchor cwd to the verified parent fd.
                cwd=os.open(".",os.O_RDONLY|os.O_DIRECTORY)
                try:
                    os.fchdir(fd); shutil.rmtree(p.name)
                finally:
                    os.fchdir(cwd); os.close(cwd)
        else: os.unlink(p.name,dir_fd=fd)
    finally: os.close(fd)
    return "REMOVED"

def housekeeping():
    """Only the explicitly requested shared journal exception."""
    changes=[]
    for argv in (["journalctl","--rotate"],["journalctl","--vacuum-time=5days","--vacuum-size=160M"]):
        r=command(argv,60)
        changes.append({"operation":argv,"status":"OK" if r.returncode==0 else "FAILED","detail":r.stderr.strip()})
        if r.returncode: break
    return changes

def audit_append(payload):
    if not clean_path(AUDIT_PATH.parent): raise RuntimeError("unsafe audit parent")
    fd=parent_fd(AUDIT_PATH)
    try:
        out=os.open(AUDIT_PATH.name,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            s=os.fstat(out)
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise RuntimeError("unsafe audit file")
            with os.fdopen(out,"a") as f:
                out=-1; f.write(json.dumps(payload)+"\n"); f.flush(); os.fsync(f.fileno())
        finally:
            if out!=-1: os.close(out)
    finally: os.close(fd)

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--skip-images",action="store_true")
    args=parser.parse_args(argv)
    # The same lock covers direct/manual and timer invocations.
    lock_parent=parent_fd(LOCK_PATH)
    try: lock=os.open(LOCK_PATH.name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600,dir_fd=lock_parent)
    finally: os.close(lock_parent)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink!=1: raise RuntimeError("unsafe lock")
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"mode":"SKIP_LOCKED"})); return 0
        before=shutil.disk_usage("/").free
        planned=list(candidate_temp())+list(candidate_logs())+list(candidate_artifacts())+list(candidate_backups())
        if not args.skip_images: planned+=list(candidate_images())
        planned+=list(candidate_dr_volumes())
        payload={"at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"mode":"APPLY" if args.apply else "DRY_RUN","retention_days":5,
                 "planned":[{"kind":k,"path":str(p)} for k,p in planned],"actions":[],"free_before_bytes":before,
                 "protected_db_backups":sorted(str(p) for p in (protected_backups() or set())),
                 "journal_plan":["rotate","vacuum-time=5days","vacuum-size=160M"],
                 "exclusions":["unknown temp/cache","foreign images/volumes/releases","active logs","newest DR restore point","container image/mount references","newest unused image rollback"]}
        if args.apply:
            audit_append({**payload,"phase":"START"})  # abort before deleting if durable audit unavailable
            for kind,p in planned:
                try: result=apply(kind,p)
                except Exception as err: result="FAILED:"+type(err).__name__
                entry={"kind":kind,"path":str(p),"status":result}
                payload["actions"].append(entry)
                audit_append({"at_utc":payload["at_utc"],"phase":"ACTION",**entry})
            payload["actions"].extend(housekeeping())
        payload["free_after_bytes"]=shutil.disk_usage("/").free
        payload["net_free_delta_bytes"]=payload["free_after_bytes"]-before
        if args.apply: audit_append({**payload,"phase":"FINISH"})
        print(json.dumps(payload))
        return int(any("FAILED" in x["status"] for x in payload["actions"]))
    finally: os.close(lock)

if __name__=="__main__": sys.exit(main())
