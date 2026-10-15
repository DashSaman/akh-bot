#!/usr/bin/env python3
"""Allowlisted weekly cleanup. Dry-run default. No service/network repair."""
from __future__ import annotations
import argparse,datetime,fcntl,gzip,hashlib,importlib.util,ipaddress,json,os,pathlib,re,shutil,sqlite3,stat,subprocess,sys,tarfile,time,urllib.request
GUARD=pathlib.Path(__file__).with_name("guard.py")
if not GUARD.exists(): GUARD=pathlib.Path(__file__).with_name("host_disk_retention.py")
if not GUARD.exists(): GUARD=pathlib.Path("/usr/local/lib/scoped-server-cleanup/guard.py")
spec=importlib.util.spec_from_file_location("guard",GUARD)
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
CONFIG={}
CONFIG_PATH=pathlib.Path("/etc/scoped-server-cleanup.json")
LOCK=pathlib.Path("/run/lock/all-project-scoped-cleanup.lock")
REPORT=pathlib.Path("/var/log/scoped-server-cleanup")
RUN=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+str(os.getpid())
ROOT_LOG=re.compile(r"(?:syslog|auth\.log|kern\.log|daemon\.log|messages|btmp|wtmp|dpkg\.log|alternatives\.log|fail2ban\.log|mail(?:\.\w+)?|user\.log|cron\.log|dmesg|openvpn\.log)\.\d+(?:\.(?:gz|xz|bz2))?")
RSYSLOG_BASE={"syslog","auth.log","kern.log","daemon.log","messages","mail.log","mail.info","mail.warn","mail.err","user.log","cron.log","debug"}
RSYSLOG=pathlib.Path("/etc/logrotate.d/rsyslog")
GROWTH=pathlib.Path("/opt/pv-growth/releases")
EXPORT=re.compile(r"(?:pv-growth-app-[0-9a-f]{40}\.tar(?:\.gz)?|(?:ci-image|full-ci|verified-ci|artifact-direct|release-verified|verified-ci)\.zip|delta\.bin(?:\.gz)?)")

def checked(args,timeout=30):
 r=guard.command(args,timeout)
 if r.returncode: raise RuntimeError(args[0]+" failed")
 return r.stdout.strip()

def load_config():
 if not guard.clean_path(CONFIG_PATH): raise RuntimeError("unsafe config path")
 s=CONFIG_PATH.stat()
 if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid!=0 or s.st_mode&0o022: raise RuntimeError("unsafe config owner/mode")
 return json.loads(CONFIG_PATH.read_text())

def audit(row):
 if not guard.clean_path(REPORT): raise RuntimeError("unsafe report path")
 REPORT.mkdir(mode=0o700,exist_ok=True);REPORT.chmod(0o700)
 old=guard.AUDIT_PATH
 try:
  guard.AUDIT_PATH=REPORT/("run-"+RUN+".jsonl")
  guard.audit_append({"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),**row})
 finally: guard.AUDIT_PATH=old

def firewall_base(text):
 rows=[]
 for line in text.splitlines():
  if line.startswith("#"): continue
  # Runtime counters and exact fail2ban source-address reject/drop entries are telemetry.
  line=re.sub(r"\[\d+:\d+\]","[0:0]",line)
  f=line.split()
  if len(f)>=8 and f[0]=="-A" and f[1].startswith("f2b-") and f[2]=="-s" and f[4]=="-j" and f[5] in ("REJECT","DROP"):
   try:
    ipaddress.ip_network(f[3],strict=False)
    if f[6:]==["--reject-with","icmp-port-unreachable"] or f[6:]==["--reject-with","tcp-reset"]: continue
   except ValueError: pass
  if len(f)==6 and f[:1]==["-A"] and f[1].startswith("f2b-") and f[2]=="-s" and f[4]=="-j" and f[5]=="DROP":
   try: ipaddress.ip_network(f[3],strict=False);continue
   except ValueError: pass
  rows.append(line)
 return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def volatile_udp_client(fields):
 owners=tuple(re.findall(r'\("([^"]+)",pid=(\d+)'," ".join(fields[5:])))
 port=int(fields[3].rsplit(":",1)[1])
 return port not in CONFIG.get("protected_udp_ports",[]) and any(name in CONFIG.get("udp_client_names",[]) for name,_ in owners)

def listeners():
 xray_ports=set();configs={}
 for proc in pathlib.Path("/proc").iterdir():
  if not proc.name.isdigit(): continue
  try:
   comm=(proc/"comm").read_text().strip()
   if not comm.startswith("xray"): continue
   argv=(proc/"cmdline").read_bytes().decode().split("\0")
   for i,arg in enumerate(argv[:-1]):
    if arg in ("-c","-config","--config"):
     logical=pathlib.Path(argv[i+1])
     if ".." in logical.parts: raise RuntimeError("unknown xray config path")
     p=proc/"root"/str(logical).lstrip("/") if logical.is_absolute() else proc/"cwd"/logical
     raw=p.read_bytes();data=json.loads(raw);configs[str(proc)+":"+str(logical)]=hashlib.sha256(raw).hexdigest()
     for inbound in data.get("inbounds",[]):
      for group in str(inbound["port"]).split(","):
       if re.fullmatch(r"\d+",group): xray_ports.add(int(group))
       elif re.fullmatch(r"\d+-\d+",group):
        lo,hi=map(int,group.split("-"))
        if not 0<lo<=hi<65536: raise RuntimeError("invalid xray port")
        xray_ports.update(range(lo,hi+1))
       else: raise RuntimeError("unknown xray port")
  except (FileNotFoundError,ProcessLookupError): continue
 rows=[]
 for line in checked(["ss","-H","-lnt"]).splitlines():
  f=line.split();rows.append(("tcp",f[0],f[3],f[4]))
 for line in checked(["ss","-H","-lnup"]).splitlines():
  f=line.split();port=int(f[3].rsplit(":",1)[1]);owner=" ".join(f[5:])
  if volatile_udp_client(f): continue
  if "xray" in owner and configs and port not in xray_ports: continue
  owners=tuple(re.findall(r'\("([^"]+)",pid=(\d+)',owner))
  rows.append(("udp",f[0],f[3],f[4],owners))
 return sorted(rows),configs

def network_configuration():
 result={}
 patterns=[("/etc/netplan",("*.yaml","*.yml")),("/etc/systemd/network",("*.network","*.netdev","*.link"))]
 for name,globs in patterns:
  root=pathlib.Path(name)
  if not root.is_dir(): continue
  for pattern in globs:
   for p in root.glob(pattern):
    if not guard.clean_path(p) or not p.is_file(): raise RuntimeError("unsafe network configuration path")
    result[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 return result

def snapshot():
 errors=[];identity={};result={}
 try:
  units=CONFIG.get("critical_units",[])
  if units:
   identity["units"]=checked(["systemctl","show",*units,"--property=Id,ActiveState,SubState,MainPID,ExecMainPID"])
   if identity["units"].count("ActiveState=active")!=len(units): errors.append("required service inactive")
  containers=guard.container_inventory() if shutil.which("docker") else []
  running={c["Name"].lstrip("/") for c in containers if c["State"]["Running"]}
  if not set(CONFIG.get("running_containers",[]))<=running: errors.append("required container missing")
  identity["containers"]=[]
  for c in containers:
   if c["State"]["Running"] and c["State"].get("Health",{}).get("Status","healthy")!="healthy": errors.append("container health:"+c["Name"])
   identity["containers"].append((c["Name"],c["Id"],c["Image"],c["State"]["Status"],c["State"]["StartedAt"],c["RestartCount"],c["NetworkSettings"]["Ports"]))
  identity["containers"].sort()
  observed,identity["xray_configs"]=listeners()
  identity["listeners"]=[r for r in observed if r[0]=="tcp"]
  result["udp_observation"]=[r for r in observed if r[0]=="udp"]
  result["route_observation"]=checked(["ip","route","show","table","all"])
  identity["network_configuration"]=network_configuration()
  identity["firewall_base"]=firewall_base(checked(["iptables-save"]))
  for check in CONFIG.get("http_checks",[]):
   class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k): return None
   try:
    with urllib.request.build_opener(NoRedirect).open(check["url"],timeout=10) as r: status=r.status
   except urllib.error.HTTPError as e: status=e.code
   result.setdefault("http",[]).append({"url":check["url"],"status":status})
   if status not in check["codes"]: errors.append("HTTP:"+check["url"])
  for db in CONFIG.get("sqlite_checks",[]):
   p=pathlib.Path(db)
   if not guard.clean_path(p): raise RuntimeError("unsafe SQLite path")
   with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=10) as c:
    c.execute("PRAGMA query_only=ON")
    if c.execute("PRAGMA quick_check").fetchall()!=[("ok",)]: errors.append("SQLite integrity:"+str(p))
  for args in CONFIG.get("native_checks",[]): checked(args,30)
 except Exception as e: errors.append(type(e).__name__+":"+str(e)[:120])
 usage=shutil.disk_usage("/")
 result.update(ok=not errors,errors=errors,identity=identity,free=usage.free,total=usage.total)
 return result

def repository_busy(p):
 # A lazy importer may have no open module fd while its cwd remains in the project.
 ancestors=[]
 for root in p.parents:
  if (root/".git").exists() or (root/"package.json").is_file(): ancestors.append(root)
  if (root/".git").exists(): break
 if not ancestors: return False
 for proc in pathlib.Path("/proc").iterdir():
  if not proc.name.isdigit(): continue
  try:
   cwd=(proc/"cwd").stat()
   if any((a.stat().st_dev,a.stat().st_ino)==(cwd.st_dev,cwd.st_ino) for a in ancestors): return True
   name=os.readlink(proc/"cwd").removesuffix(" (deleted)")
   c=pathlib.Path(name)
   if any(c==a or a in c.parents for a in ancestors): return True
  except (FileNotFoundError,ProcessLookupError): continue
 return False

def container_mount_overlap(p):
 if not shutil.which("docker"): return False
 for c in guard.container_inventory():
  for mount in c.get("Mounts",[]):
   src=pathlib.Path(mount.get("Source",""))
   if src.is_absolute() and (src==p or src in p.parents or p in src.parents): return True
 return False

def safe_cache(p):
 try:
  if not guard.clean_path(p) or not p.is_dir(): return False
  if repository_busy(p) or container_mount_overlap(p): return False
  if any(x==p or p in x.parents for x in guard.mount_points()): return False
  root=p.lstat();nodes=[p]
  for base,dirs,files in os.walk(p,followlinks=False):
   nodes.extend(pathlib.Path(base)/n for n in dirs+files)
   if len(nodes)>30000: return False
  links={}
  for n in nodes:
   s=n.lstat()
   if stat.S_ISREG(s.st_mode): links[(s.st_dev,s.st_ino)]=links.get((s.st_dev,s.st_ino),0)+1
  for n in nodes:
   s=n.lstat()
   if s.st_dev!=root.st_dev or max(s.st_mtime,s.st_ctime)>=guard.CUTOFF: return False
   if stat.S_ISLNK(s.st_mode):
    if p not in n.resolve(strict=True).parents: return False
   elif not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)): return False
   elif stat.S_ISREG(s.st_mode) and s.st_nlink!=links[(s.st_dev,s.st_ino)]: return False
  return not guard.open_file(p)
 except (OSError,RuntimeError): return False

def remove_path(p):
 before=p.lstat();fd=guard.parent_fd(p)
 try:
  current=os.stat(p.name,dir_fd=fd,follow_symlinks=False)
  if fingerprint(before)!=fingerprint(current): return "SKIP_CHANGED"
  if stat.S_ISDIR(current.st_mode):
   if not shutil.rmtree.avoids_symlink_attacks: return "SKIP_PLATFORM"
   if sys.version_info>=(3,11): shutil.rmtree(p.name,dir_fd=fd)
   else:
    cwd=os.open(".",os.O_RDONLY|os.O_DIRECTORY)
    try: os.fchdir(fd);shutil.rmtree(p.name)
    finally: os.fchdir(cwd);os.close(cwd)
  else: os.unlink(p.name,dir_fd=fd)
  os.fsync(fd)
 finally: os.close(fd)
 return "REMOVED"

def fingerprint(s): return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns

def remove_cache(p):
 if str(p) not in CONFIG.get("cache_roots",[]): return "SKIP_SCOPE"
 if p.name=="node_modules" and not any((p.parent/n).is_file() and guard.clean_path(p.parent/n) for n in ("package-lock.json","pnpm-lock.yaml","yarn.lock")): return "SKIP_NO_LOCKFILE"
 if not safe_cache(p): return "SKIP_SAFETY"
 return remove_path(p)

def log_allowed(p):
 if p.parent==pathlib.Path("/var/log"): return bool(ROOT_LOG.fullmatch(p.name))
 if p.parent in (pathlib.Path("/var/log/nginx"),pathlib.Path("/var/log/apache2")): return bool(re.fullmatch(r"[\w.-]+\.log\.\d+(?:\.(?:gz|xz|bz2))?",p.name))
 if p.parent==pathlib.Path("/var/log/x-ui"): return bool(guard.XUI_LOG.fullmatch(p.name))
 if p.parent==pathlib.Path("/var/log/sysstat"): return bool(re.fullmatch(r"(?:sa|sar)(?:0[1-9]|[12]\d|3[01])(?:\.(?:gz|xz))?",p.name))
 if str(p.parent) in CONFIG.get("dated_log_roots",[]): return bool(re.fullmatch(r"(?:core|internal|access|error)\.\d{8}\.log(?:\.gz)?",p.name))
 if p.parent==REPORT: return bool(re.fullmatch(r"run-\d{8}T\d{6}Z-\d+\.jsonl",p.name))
 return False

def quiet_file(p):
 if not p.is_file() or not guard.clean_path(p): return False
 s=p.stat()
 if s.st_ctime>time.time()-3600: return False
 old=guard.CUTOFF
 try: guard.CUTOFF=float("inf");return guard.safe_tree(p)
 finally: guard.CUTOFF=old

def old_log(p):
 return log_allowed(p) and p.stat().st_mtime<guard.CUTOFF and quiet_file(p)

def compress_allowed(p):
 if p.parent!=pathlib.Path("/var/log") or p.name.rpartition(".")[0] not in RSYSLOG_BASE or not p.name.rpartition(".")[2].isdigit(): return False
 if not guard.clean_path(RSYSLOG) or not RSYSLOG.is_file(): return False
 return bool(re.search(r"^\s*nodelaycompress\s*$",RSYSLOG.read_text(),re.M))

def hash_stream(f):
 h=hashlib.sha256()
 for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()

def compress_log(p):
 if not compress_allowed(p) or not quiet_file(p): return "SKIP_SAFETY"
 dest=p.with_name(p.name+".gz")
 if dest.exists() or dest.is_symlink(): return "SKIP_EXISTING"
 before=p.stat();fd=guard.parent_fd(p);temp=".scoped-compress-"+str(os.getpid())+"-"+p.name+".part";made=False
 try:
  src=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
  if fingerprint(os.fstat(src))!=fingerprint(before): os.close(src);return "SKIP_CHANGED"
  out=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,before.st_mode&0o777,dir_fd=fd);made=True
  h=hashlib.sha256()
  with os.fdopen(src,"rb") as f,os.fdopen(out,"wb") as raw:
   os.fchmod(raw.fileno(),before.st_mode&0o777);os.fchown(raw.fileno(),before.st_uid,before.st_gid)
   with gzip.GzipFile(fileobj=raw,filename="",mode="wb",mtime=int(before.st_mtime),compresslevel=6) as z:
    for b in iter(lambda:f.read(1024*1024),b""): h.update(b);z.write(b)
   raw.flush();os.fsync(raw.fileno())
  with gzip.open(p.parent/temp,"rb") as f:
   if hash_stream(f)!=h.hexdigest(): raise RuntimeError("compression checksum mismatch")
  if os.stat(temp,dir_fd=fd).st_size>=before.st_size: return "SKIP_NO_SAVING"
  if fingerprint(os.stat(p.name,dir_fd=fd,follow_symlinks=False))!=fingerprint(before) or guard.open_file(p): return "SKIP_CHANGED_OR_OPEN"
  audit({"phase":"VERIFIED_COMPRESSION","path":str(p),"decompressed_sha256":h.hexdigest()})
  os.link(temp,dest.name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
  os.utime(dest.name,ns=(before.st_atime_ns,before.st_mtime_ns),dir_fd=fd,follow_symlinks=False);os.fsync(fd)
  if fingerprint(os.stat(p.name,dir_fd=fd,follow_symlinks=False))!=fingerprint(before) or guard.open_file(p): return "SKIP_SOURCE_CHANGED"
  os.unlink(p.name,dir_fd=fd);os.fsync(fd)
  return "COMPRESSED"
 finally:
  if made:
   try: os.unlink(temp,dir_fd=fd)
   except FileNotFoundError: pass
  os.close(fd)

PROVENANCE_CACHE={}
def growth_provenance(d):
 tag=d.name
 for p in d.iterdir():
  if p.name not in ("pv-growth-app-"+tag+".tar","pv-growth-app-"+tag+".tar.gz") or not guard.clean_path(p) or not p.is_file(): continue
  try:
   stamp=p.stat();key=(str(p),fingerprint(stamp))
   cacheable=stamp.st_ctime<time.time()-3600
   if cacheable and key in PROVENANCE_CACHE:
    if PROVENANCE_CACHE[key]:return True
    continue
   with tarfile.open(p,"r:*") as t:
    entry=t.getmember("manifest.json")
    if not entry.isfile() or entry.size>1024*1024: continue
    data=json.load(t.extractfile(entry))
    verified=len(data)==1 and ("pv-growth-app:"+tag) in data[0].get("RepoTags",[])
    if cacheable:PROVENANCE_CACHE[key]=verified
    if verified:return True
  except (OSError,tarfile.TarError,ValueError): continue
 marker=d/".scoped-verified-archive.json"
 try:
  if guard.clean_path(marker) and marker.is_file():
   data=json.loads(marker.read_text())
   return data.get("verified") is True and data.get("tag")==tag
 except (OSError,ValueError): pass
 return False

RESTORE_CACHE={}
def archive_complete(p,tag):
 try:
  before=p.stat()
  actual=json.loads(checked(["docker","image","inspect","pv-growth-app:"+tag],15))[0]
  key=(str(p),fingerprint(before),actual.get("Id"))
  if key in RESTORE_CACHE: return RESTORE_CACHE[key]
  with tarfile.open(p,"r:*") as t:
   member=t.getmember("manifest.json")
   if not member.isfile() or member.size>1024*1024: return False
   manifests=json.load(t.extractfile(member))
   if len(manifests)!=1 or "pv-growth-app:"+tag not in manifests[0].get("RepoTags",[]): return False
   info=manifests[0];cfg_member=t.getmember(info["Config"])
   if not cfg_member.isfile() or cfg_member.size>1024*1024: return False
   cfg=json.load(t.extractfile(cfg_member))
   expected=cfg["rootfs"]["diff_ids"]
   if expected!=actual["RootFS"]["Layers"] or len(expected)!=len(info["Layers"]): return False
   if any(value!=actual["Config"].get(k) for k,value in cfg.get("config",{}).items()): return False
   import io
   for name,wanted in zip(info["Layers"],expected):
    member=t.getmember(name)
    if not member.isfile(): return False
    with t.extractfile(member) as f:
     buffered=io.BufferedReader(f)
     if buffered.peek(2)[:2]==b"\x1f\x8b":
      with gzip.GzipFile(fileobj=buffered,mode="rb") as plain: digest=hash_stream(plain)
     else: digest=hash_stream(buffered)
    if "sha256:"+digest!=wanted: return False
  ok=fingerprint(p.stat())==fingerprint(before) and not guard.open_file(p)
  RESTORE_CACHE[key]=ok;return ok
 except (OSError,tarfile.TarError,ValueError,KeyError): return False

def mark_growth_directory(d):
 p=d/".scoped-verified-archive.json"
 if p.exists():
  if not growth_provenance(d): raise RuntimeError("unexpected archive marker")
  return
 fd=guard.parent_fd(p)
 try:
  out=os.open(p.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
  with os.fdopen(out,"w") as f:
   json.dump({"tag":d.name,"verified":True,"verification":"matching Docker archive RepoTags; surplus exports only"},f)
   f.flush();os.fsync(f.fileno())
  os.fsync(fd)
 finally: os.close(fd)

def growth_candidates():
 if not CONFIG.get("growth") or not guard.clean_path(GROWTH) or not GROWTH.is_dir(): return []
 containers=guard.container_inventory();used={c["Image"] for c in containers}
 entries=[]
 for row in checked(["docker","image","ls","--format","{{.Repository}}|{{.Tag}}"]).splitlines():
  repo,tag=row.split("|",1)
  if repo!="pv-growth-app": continue
  if not re.fullmatch(r"[0-9a-f]{40}",tag): return []
  identity=checked(["docker","image","inspect","-f","{{.Id}}|{{.Created}}",repo+":"+tag]);i,t=identity.split("|",1)
  entries.append((guard.created_time(t),tag,i))
 entries.sort(reverse=True)
 if not entries: return []
 keep={x[1] for x in entries[:2]};keep.update(x[1] for x in entries if x[2] in used)
 for c in containers:
  for mount in c.get("Mounts",[]):
   p=pathlib.Path(mount.get("Source",""))
   if GROWTH in p.parents:
    relative=p.relative_to(GROWTH)
    if relative.parts: keep.add(relative.parts[0])
 unused=[x for x in entries if x[2] not in used]
 if unused: keep.add(unused[0][1])
 dirs=[p for p in GROWTH.iterdir() if re.fullmatch(r"[0-9a-f]{40}",p.name) and guard.clean_path(p) and p.is_dir()]
 dirs.sort(key=lambda p:p.stat().st_mtime,reverse=True)
 valid_ids=set()
 by_tag={tag:image_id for _,tag,image_id in entries}
 for d in dirs:
  if d.name not in keep: continue
  for name in ("pv-growth-app-"+d.name+".tar","pv-growth-app-"+d.name+".tar.gz"):
   p=d/name
   if p.is_file() and guard.clean_path(p) and archive_complete(p,d.name): valid_ids.add(by_tag.get(d.name))
 if len(valid_ids-{None})<2: return []
 plan=[]
 for d in dirs:
  if d.name in keep: continue
  # Root-created verification marker or original verified delta manifest required.
  if not growth_provenance(d): continue
  for p in d.iterdir():
   # Verified surplus binary exports use count-based recovery retention, not log age.
   if EXPORT.fullmatch(p.name) and quiet_file(p): plan.append(("growth-export",p))
 return plan

def apt_idle():
 for proc in pathlib.Path("/proc").iterdir():
  if not proc.name.isdigit(): continue
  try:
   comm=(proc/"comm").read_text().strip()
   if comm in ("apt","apt-get","dpkg") or comm.startswith("dpkg-"): return False
   if comm.startswith("unattended"):
    argv=(proc/"cmdline").read_bytes().decode().split("\0")
    if "/usr/bin/unattended-upgrade" in argv: return False
  except (FileNotFoundError,ProcessLookupError): continue
 return True

def apt_allowed(p):
 return p.parent==pathlib.Path("/var/cache/apt/archives") and p.name.endswith(".deb") and bool(re.fullmatch(r"[A-Za-z0-9_.+:%~-]+\.deb",p.name))

def plans():
 plan=[]
 apt=pathlib.Path("/var/cache/apt/archives")
 if guard.clean_path(apt) and apt.is_dir() and apt_idle():
  plan.extend(("apt-download",p) for p in apt.iterdir() if apt_allowed(p) and guard.safe_tree(p))
 for name in CONFIG.get("cache_roots",[]):
  p=pathlib.Path(name)
  if p.exists() and safe_cache(p): plan.append(("cache",p))
 roots=[pathlib.Path(p) for p in ("/var/log","/var/log/nginx","/var/log/apache2","/var/log/x-ui","/var/log/sysstat",*CONFIG.get("dated_log_roots",[]),str(REPORT))]
 for root in roots:
  if not guard.clean_path(root) or not root.is_dir(): continue
  for p in root.iterdir():
   if not p.is_file(): continue
   if log_allowed(p) and old_log(p): plan.append(("old-log",p))
   elif compress_allowed(p) and quiet_file(p) and p.stat().st_size>64*1024 and not p.with_name(p.name+".gz").exists(): plan.append(("compress-log",p))
 guard.IMAGE_KEEP={repo:2 for repo in CONFIG.get("image_repos",[])}
 if guard.IMAGE_KEEP: plan+=list(guard.candidate_images())
 plan+=growth_candidates()
 if CONFIG.get("rasteh"):
  plan+=list(guard.candidate_backups())+list(guard.candidate_temp())+list(guard.candidate_artifacts())+list(guard.candidate_dr_volumes())
 plan.append(("journal",pathlib.Path("/var/log/journal")))
 return plan

def execute(kind,p):
 if kind=="cache": return remove_cache(p)
 if kind=="apt-download": return remove_path(p) if apt_allowed(p) and apt_idle() and guard.safe_tree(p) else "SKIP_SAFETY"
 if kind=="old-log": return remove_path(p) if old_log(p) else "SKIP_SAFETY"
 if kind=="compress-log": return compress_log(p)
 if kind=="growth-export":
  if (kind,p) not in growth_candidates() or not quiet_file(p): return "SKIP_PROTECTED"
  mark_growth_directory(p.parent)
  return remove_path(p)
 if kind=="journal":
  checked(["journalctl","--rotate"],60);checked(["journalctl","--vacuum-time=5days","--vacuum-size=200M"],90);return "OK"
 if kind in ("old-image","backup","temp","artifact","old-dr-volume"): return guard.apply(kind,p)
 return "SKIP_SCOPE"

def main(argv=None):
 global CONFIG
 args=argparse.ArgumentParser();args.add_argument("--apply",action="store_true");opt=args.parse_args(argv)
 CONFIG=load_config()
 parent=guard.parent_fd(LOCK)
 try: fd=os.open(LOCK.name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=parent)
 finally: os.close(parent)
 try:
  s=os.fstat(fd)
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise RuntimeError("unsafe lock")
  try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError: print('{"status":"SKIP_LOCKED"}');return 0
  before=snapshot();report={"mode":"APPLY" if opt.apply else "DRY_RUN","before":before,"actions":[]}
  if opt.apply: audit({"phase":"START",**report})
  if not before["ok"]:
   report["status"]="SKIP_UNHEALTHY"
   if opt.apply: audit({"phase":"FINISH",**report})
   print(json.dumps(report));return 2
  selected=plans();report["planned"]=[(k,str(p)) for k,p in selected];failed=False
  if opt.apply:
   for kind,p in selected:
    now=snapshot()
    if not now["ok"] or now["identity"]!=before["identity"]:
     changes={k:{"before":before["identity"].get(k),"observed":now["identity"].get(k)} for k in set(before["identity"])|set(now["identity"]) if before["identity"].get(k)!=now["identity"].get(k)}
     report["actions"].append({"status":"HALTED_HEALTH_OR_DEPLOYMENT_CHANGE","errors":now["errors"],"differences":changes});failed=True;break
    audit({"phase":"ACTION_START","kind":kind,"path":str(p)})
    try: status=execute(kind,p)
    except Exception as e: status="FAILED:"+type(e).__name__
    row={"kind":kind,"path":str(p),"status":status};report["actions"].append(row);audit({"phase":"ACTION",**row})
    if status.startswith("FAILED"): failed=True;break
  after=snapshot() if opt.apply else before
  report.update(after=after,available_percent=round(100*after["free"]/after["total"],2),net_freed_bytes=after["free"]-before["free"])
  failed=failed or not after["ok"] or after["identity"]!=before["identity"]
  report["status"]="ATTENTION" if failed else "OK"
  if report["available_percent"]<50: report["capacity_notice"]="Below target; protected resources retained."
  if opt.apply: audit({"phase":"FINISH",**report})
  print(json.dumps(report));return 2 if failed else 0
 finally: os.close(fd)

if __name__=="__main__": sys.exit(main())
