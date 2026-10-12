#!/usr/bin/env python3
"""Safe shared-host disk housekeeping. Dry-run by default; --apply for timer.

Never prunes Docker globally, touches volumes/DB/snapshots/containerd stores,
truncates active logs, restarts services, or changes host networking.
"""
from __future__ import annotations
import argparse
import datetime as datetime
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys

RETENTION_DAYS = 5
CUTOFF = (datetime.datetime.now(datetime.timezone.utc) -
          datetime.timedelta(days=RETENTION_DAYS)).timestamp()
ROOTS_TEMP = (pathlib.Path("/tmp"), pathlib.Path("/var/tmp"))
TEMP_PREFIX = ("tmp", "pytest", "pip-", "ghchk", "relchk", "cleanchk", "node-compile-cache")
TEMP_EXCLUDE = ("systemd-private-", "android", "ssh-", "hsperfdata",
                ".X11", ".ICE", "xray", "pv-", "docker-", "containerd")
ARCHIVED_LOG = re.compile(r"(?:\.\d+(?:\.gz)?|\.gz|\.old|\.bak)$", re.I)
RELEASE_DIR = pathlib.Path("/opt/pv-growth/releases")
RELEASE_NAME = re.compile(r"[a-f0-9]{40}")
IMAGE_KEEP = {"pv-growth-app": 4, "akhbot-app": 3, "akhbot-qa-watch": 2}

def command(argv, timeout=30):
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=False)

_OPEN_FILES = None

def open_file(p):
    """Cache open /proc fd targets for fast read-only liveness checks."""
    global _OPEN_FILES
    if _OPEN_FILES is None:
        targets = set()
        try:
            for proc in pathlib.Path("/proc").iterdir():
                if not proc.name.isdigit():
                    continue
                fds = proc / "fd"
                try:
                    files = list(fds.iterdir())
                except (PermissionError, FileNotFoundError, NotADirectoryError):
                    continue
                for fd in files:
                    try:
                        target = os.readlink(fd)
                        if target.startswith("/"):
                            targets.add(target.removesuffix(" (deleted)"))
                    except (PermissionError, FileNotFoundError, OSError):
                        continue
        except OSError:
            return True  # fail closed
        _OPEN_FILES = targets
    path = str(p)
    if p.is_dir():
        return any(t == path or t.startswith(path + "/") for t in _OPEN_FILES)
    return path in _OPEN_FILES

def safe_tree(p):
    """No fresh children, symlinks, mounts, special files or open files."""
    try:
        if p.is_symlink() or os.path.ismount(p) or open_file(p):
            return False
        nodes = [p]
        if p.is_dir():
            nodes.extend(p.rglob("*"))
        if len(nodes) > 30000:
            return False
        for x in nodes:
            st = x.lstat()
            if x.is_symlink() or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                return False
            if max(st.st_mtime, st.st_ctime) > CUTOFF:
                return False
        return True
    except (OSError, PermissionError):
        return False

def candidate_temp():
    for base in ROOTS_TEMP:
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if p.name.startswith(TEMP_EXCLUDE):
                continue
            allowed = p.name.startswith(TEMP_PREFIX) or (
                p.is_file() and p.suffix.lower() in (".tmp", ".log", ".part"))
            if allowed and safe_tree(p):
                yield ("temp", p)

def candidate_logs():
    base = pathlib.Path("/var/log")
    for p in base.rglob("*"):
        if not p.is_file() or p.is_symlink() or "journal" in p.parts:
            continue
        if ARCHIVED_LOG.search(p.name) and p.stat().st_mtime < CUTOFF and not open_file(p):
            yield ("rotated-log", p)

def candidate_releases():
    if not RELEASE_DIR.exists():
        return
    folders = [p for p in RELEASE_DIR.iterdir()
               if p.is_dir() and not p.is_symlink() and RELEASE_NAME.fullmatch(p.name)]
    folders.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    protected = {p.name for p in folders[:4]}
    current = command(["docker", "inspect", "-f", "{{.Config.Image}}", "pv-growth-app"], 8)
    if current.returncode:
        return
    protected.add(current.stdout.strip().split(":")[-1])
    for folder in folders:
        if folder.name in protected or folder.stat().st_mtime >= CUTOFF:
            continue
        for p in folder.glob("pv-growth-app-*.tar"):
            if p.is_file() and not p.is_symlink() and p.stat().st_mtime < CUTOFF and not open_file(p):
                yield ("old-release-tar", p)

def created_time(value):
    """Docker nanosecond timestamps aren't accepted verbatim by datetime."""
    value = re.sub(r"\.(\d{6})\d+(?=[+-])", r".\1", value.replace("Z", "+00:00"))
    return datetime.datetime.fromisoformat(value).timestamp()

def candidate_images():
    images = command(["docker", "image", "ls", "--format", "{{.Repository}}|{{.Tag}}"], 15)
    containers = command(["docker", "ps", "-aq"], 15)
    if images.returncode or containers.returncode:
        return
    active_ids = set()
    for cid in containers.stdout.split():
        result = command(["docker", "inspect", "-f", "{{.Image}}", cid], 8)
        if result.returncode:
            return  # fail closed
        active_ids.add(result.stdout.strip())
    tags = {}
    for row in images.stdout.splitlines():
        if "|" not in row:
            continue
        repo, tag = row.split("|", 1)
        if repo not in IMAGE_KEEP or tag == "<none>":
            continue
        ref = repo + ":" + tag
        meta = command(["docker", "image", "inspect", "-f",
                        "{{.Id}}|{{.Created}}", ref], 8)
        if meta.returncode or "|" not in meta.stdout:
            return
        image_id, stamp = meta.stdout.strip().split("|", 1)
        try:
            moment = created_time(stamp)
        except ValueError:
            return
        tags.setdefault(repo, []).append((moment, ref, image_id))
    for repo, entries in tags.items():
        entries.sort(reverse=True)
        keep = {x[1] for x in entries[:IMAGE_KEEP[repo]]}
        for when, ref, image_id in entries:
            if when < CUTOFF and ref not in keep and image_id not in active_ids:
                yield ("old-image", pathlib.Path(ref))

def candidate_dr_volumes():
    """Old Rasteh DR-test volumes only; preserve newest VERIFIED restore point.

    All containers (including stopped) are protected. The live akhbot_data
    volume has a different name and is NEVER a candidate.
    """
    listing = command(["docker", "volume", "ls", "--format", "{{.Name}}"], 12)
    containers = command(["docker", "ps", "-aq"], 12)
    if listing.returncode or containers.returncode:
        return
    names = sorted((name for name in listing.stdout.splitlines()
                    if re.fullmatch(r"akhbot_dr_\d{8}T\d{6}Z", name)),
                   reverse=True)
    if len(names) < 2:
        return
    mounts = set()
    for cid in containers.stdout.splitlines():
        info = command(["docker", "inspect", "-f",
                        "{{range .Mounts}}{{.Name}} {{end}}", cid], 10)
        if info.returncode:
            return
        mounts.update(info.stdout.strip().split())
    for name in names[1:]:  # keep most recent even if older than 5 days
        if name in mounts:
            continue
        meta = command(["docker", "volume", "inspect", "-f",
                        "{{.CreatedAt}}", name], 10)
        if meta.returncode:
            return
        try:
            age = created_time(meta.stdout.strip())
        except ValueError:
            return
        if age < CUTOFF:
            yield ("old-dr-volume", pathlib.Path(name))

def apply(kind, p):
    global _OPEN_FILES
    _OPEN_FILES = None  # re-check active file descriptors before every deletion
    if kind == "old-dr-volume":
        name = str(p)
        if not re.fullmatch(r"akhbot_dr_\d{8}T\d{6}Z", name):
            return "SKIP_SCOPE"
        remaining = command(["docker", "volume", "ls", "--format", "{{.Name}}"], 10)
        if remaining.returncode:
            return "SKIP_UNKNOWN"
        snapshots = sorted(v for v in remaining.stdout.splitlines()
                           if re.fullmatch(r"akhbot_dr_\d{8}T\d{6}Z", v))
        if len(snapshots) < 2 or name == snapshots[-1]:
            return "SKIP_LATEST"
        refs = command(["docker", "ps", "-aq"], 10)
        if refs.returncode:
            return "SKIP_UNKNOWN"
        for cid in refs.stdout.splitlines():
            mounts = command(["docker", "inspect", "-f",
                              "{{range .Mounts}}{{.Name}} {{end}}", cid], 10)
            if mounts.returncode or name in mounts.stdout.split():
                return "SKIP_IN_USE"
        return "REMOVED" if command(["docker", "volume", "rm", name], 30).returncode == 0 else "SKIP_IN_USE"
    if kind == "old-image":
        ref = str(p)
        active = command(["docker", "ps", "-a", "--format", "{{.Image}}"], 10)
        if active.returncode or ref in active.stdout.splitlines():
            return "SKIP_ACTIVE"
        return ("REMOVED" if command(["docker", "image", "rm", ref], 90).returncode == 0
                else "SKIP_IN_USE")
    if p.is_symlink() or open_file(p):
        return "SKIP_OPEN"
    if kind == "temp":
        if not str(p).startswith(("/tmp/", "/var/tmp/")) or not safe_tree(p):
            return "SKIP_SAFETY"
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    elif kind == "rotated-log":
        if not str(p).startswith("/var/log/") or not ARCHIVED_LOG.search(p.name):
            return "SKIP_SCOPE"
        if p.stat().st_mtime >= CUTOFF:
            return "SKIP_AGE"
        p.unlink()
    elif kind == "old-release-tar":
        if not str(p).startswith(str(RELEASE_DIR) + "/") or not p.name.endswith(".tar"):
            return "SKIP_SCOPE"
        if p.stat().st_mtime >= CUTOFF:
            return "SKIP_AGE"
        p.unlink()   # manifests/scripts stay for audit
    else:
        return "SKIP_UNKNOWN"
    return "REMOVED"

def housekeeping():
    results = []
    npm_comm = command(["ps", "-eo", "comm="], 8).stdout.splitlines()
    cache = pathlib.Path("/root/.npm/_cacache")
    if not any(x in npm_comm for x in ("npm", "npx")) and cache.is_dir() and not cache.is_symlink() and not open_file(cache):
        shutil.rmtree(cache)
        results.append({"operation": "npm-download-cache", "result": "REMOVED"})
    apt = command(["systemctl", "is-active", "--quiet", "apt-daily.service"], 8)
    if apt.returncode:
        r = command(["apt-get", "clean"], 60)
        results.append({"operation": "apt-download-cache", "result": "CLEAN" if r.returncode == 0 else "SKIP"})
    r1 = command(["journalctl", "--rotate"], 30)
    r2 = command(["journalctl", "--vacuum-time=5days", "--vacuum-size=160M"], 60)
    results.append({"operation": "journal-5day-160MB",
                    "result": "VACUUMED" if r1.returncode == r2.returncode == 0 else "FAILED"})
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually reclaim; otherwise dry-run")
    parser.add_argument("--skip-images", action="store_true")
    args = parser.parse_args()
    before = shutil.disk_usage("/").free
    planned = list(candidate_temp()) + list(candidate_logs()) + list(candidate_releases())
    if not args.skip_images:
        planned += list(candidate_images())
        planned += list(candidate_dr_volumes())
    changes = []
    if args.apply:
        for kind, p in planned:
            try:
                status = apply(kind, p)
            except Exception as err:
                status = "FAILED:" + type(err).__name__
            changes.append({"kind": kind, "path": str(p), "status": status})
        try:
            changes.extend(housekeeping())
        except Exception as err:
            changes.append({"operation": "cache-journal", "result": "FAILED:" + type(err).__name__})
    payload = {"at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "mode": "APPLY" if args.apply else "DRY_RUN",
               "retention_days": RETENTION_DAYS, "planned": [
                   {"kind": kind, "path": str(p)} for kind, p in planned],
               "actions": changes, "free_before_bytes": before,
               "free_after_bytes": shutil.disk_usage("/").free}
    print(json.dumps(payload, ensure_ascii=False))
    return int(any("FAILED" in str(x) for x in changes))

if __name__ == "__main__":
    sys.exit(main())
