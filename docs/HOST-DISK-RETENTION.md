# Safe shared-host disk maintenance — Rasteh / RoboT (2026-10-12)

## Purpose and scope

This host runs **multiple unrelated production projects**. Disk retention is
limited to provably disposable files and never treats age alone as evidence
that a project database, active container, AVD image, config, backup, or
runtime volume may be destroyed.

Scheduled maintenance is installed from the versioned source
`ops/host_disk_retention.py` to
`/usr/local/sbin/rasteh-host-disk-retention.py` with:
`rasteh-host-disk-maintenance.service` and
`rasteh-host-disk-maintenance.timer`.

Run read-only preflight:

```bash
python3 ops/host_disk_retention.py
systemctl list-timers rasteh-host-disk-maintenance.timer
```

Apply safely as root:

```bash
/usr/bin/flock -n /run/lock/rasteh-host-disk-maintenance.lock \
  /usr/bin/python3 /usr/local/sbin/rasteh-host-disk-retention.py --apply
```

Timer: **daily at 03:40 UTC** with up to 10 minutes randomized delay and
persistent missed-run catch-up. It does **not** restart Docker, containers,
Apache, VPN, network ports or databases. Results are JSON in systemd journal:
`journalctl -u rasteh-host-disk-maintenance.service -n 20`.
Historical journald settings already target **5 days**; the job rotates active
journal segments and vacuums archives to 5 days / 160 MB. It does not
truncate live journal or application log files.

## Precisely eligible for deletion

- Old `/tmp` and `/var/tmp` test/build artifacts: only known `tmp*`,
  `pytest*`, `pip-*`, `cleanchk*`, `ghchk*`, `relchk*`, etc and stale
  `.log/.tmp/.part` files, **after five days**, no symlinks, no open file
  descriptors, no recent child file, no device paths.
- Rotated/archived `/var/log` files with recognized numeric, gzip, old/bak
  suffix and modified >5 days ago. Active logs never truncated; existing
  `logrotate.timer` and host's `maxage 5` rules continue to rotate them.
- Regenerable package download caches: APT, root NPM download cache
  (`/root/.npm/_cacache` only, **NOT** Remote Desktop's active
  `/root/.npm/_npx` installation).
- Old `pv-growth/releases/<40-character-SHA>/pv-growth-app-*.tar` artifacts
  only when >5 days old and **not** among the newest **four** release
  directories. Backup scripts, checksums, manifests, SQL backups and env
  snapshots remain untouched.
- Tagged **unused**, older-than-five-days Docker images **only** for
  `pv-growth-app`, `akhbot-app`, `akhbot-qa-watch` and only outside
  latest 4/3/2 versions respectively. All Docker container image IDs
  (including stopped containers) are protected, and `docker image rm`
  refuses images in use. No global `image prune`, `system prune` or
  `volume prune`.

## Explicit exclusions

**Never automatically delete:**

- `/var/lib/containerd` (6.8 GiB managed content/snapshotter), Docker
  overlay files or any Docker volumes (including news data, PostgreSQL/MySQL).
- Android system images and AVD files under `/opt/2-id`. In particular
  the `userdata-qemu.img` displays 6 GiB logical size but takes only
  ~224 MiB on disk with sparse allocation; removal would destroy state.
- `/opt/pv-growth/backups`, any `.sql/.sql.gz`, `.env`, APK/toolchains,
  existing PVNetwork, GrowthOS, SentinelX, TwoID and xray runtime data.
- Active logs, sockets, `systemd-private-*`, SSH, Android and program
  temp directories, recently used files or mounted paths.
- Firewall, DNS, network routes, TLS/vhosts and unrelated ports/services.

If a candidate fails any safety check, **skip it** and report it. A nightly
run does not silently assume all old images are redundant.

## Initial audited cleanup and outcomes

Baseline at 2026-10-12T01:18Z: root FS 38 GiB, **95% used** (~2.0 GiB
free), 9 production containers running; details and port snapshot in
`/opt/akhbot/audit/host-disk-20261012` (host-local, permissions 0700).

Performed with no Docker daemon restart or service interruption:

- APT download cache: ~111 MiB reclaimed.
- UV re-download cache: ~121 MiB reclaimed (one-time).
- NPM `_cacache`: ~286 MiB reclaimed; `_npx` intact.
- Journald rotated/vacuumed: archived ~48 MiB freed, 5-day rule.
- Removed only the redundant >5-day GrowthOS image tar for
  `c8666fb252dc211131610b74cf58bd7d6fe33c5e`: ~638 MiB used.
  Release metadata/checksum/backup script preserved.
- Docker image rm on exactly two unused Oct-6 GrowthOS tags
  `6388743673beec4bec97fead1d44367b34ea502c` and
  `7d5e9eb0b722f2bd0c2aecf49560eba4e6311e30`; newer
  production/rollback tags protected. Freed about 1 GiB actually allocated.

Disk after these steps: **~4.4 GiB free, 88% used**. Totals are approximate
because active applications may write during measurement.

## Verification and rollback of the maintenance *rule*

After every initial/manual apply, confirm active containers/ports and unit
states against the baseline audit snapshot. The service is oneshot, with
`flock`, idle I/O priority, nice 19, CPU quota, and a 15-minute timeout.

To disable future maintenance without affecting running services:

```bash
systemctl disable --now rasteh-host-disk-maintenance.timer
```

The cleanup job has no direct rollback for deleted caches/logs and old
archives; therefore retention limits deliberately preserve recent rollback
copies, avoid databases and fail closed under uncertainty. Do not lower the
retention further without a project-by-project recovery audit.

## 2026-10-12 execution evidence
- Two exact unused GrowthOS Docker image tags safely removed; the root filesystem improved from 95% used (~2.0 GiB free) to 88% used (~4.4 GiB free).
- First guard apply removed 129 stale temporary entries and 13 rotated log archives, zero deletion errors; APT/journal maintenance also passed.
- systemd units were verified, timer enabled and active. Manual service execution completed Result=success / ExecMainStatus=0. Next automatic run is daily at 03:40 UTC plus 0–10 minutes randomized delay.
- Source and installed Python script SHA256 matched at installation. Host baseline: /opt/akhbot/audit/host-disk-20261012, directory protected root-only.
- The 5-day rule is only for safe rotated logs, expired disposable temp and explicitly allowlisted unused rollback artifacts; never globally prune Docker or delete Android/containerd/DB data.
