# RoboT daily scoped disk maintenance

The operator authorized surplus-file cleanup across the mapped server projects, a 50% **available / total** disk target, and retirement of unused Android SDK packages. Unknown resources, live data, service configuration, ports, firewall, native authentication, and production processes are protected. This is a maintenance tool, not a service repair tool.

## Policy and guards

- `ops/server_disk_retention.py` defaults to read-only planning. Only `--apply` removes candidates. A nonblocking, no-follow, private lock covers manual and timer runs.
- Preflight and every action check all container identities, references, started times, restart counts and ports; required service states/PIDs; HTTP health/readiness; Rasteh SQLite quick integrity/jobs/last SEND; MySQL and TwoID PostgreSQL availability; configured listeners and normalized route/firewall fingerprints. Ignore only xray-owned outbound UDP client sockets outside its configured inbound ports; also fingerprint the unchanged xray configuration. Timestamp comments in iptables export are excluded, rules remain compared. If unhealthy or changed during a deployment, stop cleanup and record the reason. No restart, repair, message send, network mutation or global prune.
- Exact allowlist: named PV-NativePanel developer Go caches and node_modules in seven previously mapped workspaces. Keep source, Git, lockfiles, reports, dist evidence, and installed toolchains. Require package-lock for node_modules. Reject mounts/bind mounts, fresh descendants, special files, external symlinks/hardlinks, open descriptors/cwd/mappings and incomplete process visibility. Internal symlinks and hardlinks are allowed only when every target/link stays inside the same regenerable tree. Deletion uses parent directory descriptors and symlink-resistant rmtree.
- PV-Growth: unused tagged images older than five days only; preserve all running/stopped references, newest two distinct versions and newest unused rollback. Old release binaries/download chunks older than five days require a named SHA directory with delta metadata; current/rollback and newest two release directories remain protected. Keep release metadata/scripts/env and all fourteen existing SQL backups. Unknown tags disable release deletion.
- Apache and x-ui: only explicitly recognized rotated files older than five days; never active logs. The Rasteh policy additionally handles its named test/temp/media-cache artifacts, old unreferenced akhbot_dr volumes while keeping newest DR, and old DB backups while keeping at least two integrity-checked restore points.
- MySQL: local-only installation with no replica state, registered replicas, binlog consumers or remote replication account. Archive only the contiguous oldest closed binlog prefix older than five days. Require adequate headroom, successful transactional all-database dump, gzip verification, exact archive member SHA checks, unchanged files, stable health, and a second replication check. Use MySQL `PURGE BINARY LOGS TO`, never unlink its storage files. Do not alter server expiry settings or restart MySQL.
- New MySQL SQL backups: five-day retention and last two verified files; compact binlog recovery archives: thirty-day retention and last two verified archives. Failed/incomplete backups do not count as restore points. Initial October 12 cold recovery archive remains private under the audit directory.
- Daily private audit reports rotate after five days. CPU 25%, nice 19, idle I/O, memory 512MiB, maximum thirty minutes. Journal retention remains five days, system 200MiB/runtime 100MiB, vacuum target 160MiB. Below 50% produces a capacity warning; protected data is never removed to force a percentage.

## Installation on RoboT

Install the unchanged Rasteh guard and the new controller:
```sh
install -m 0750 ops/host_disk_retention.py /usr/local/sbin/rasteh-host-disk-retention.py
install -m 0750 ops/server_disk_retention.py /usr/local/sbin/server-disk-retention.py
install -m 0644 ops/server-disk-maintenance.service /etc/systemd/system/
install -m 0644 ops/server-disk-maintenance.timer /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/server-disk-maintenance.service /etc/systemd/system/server-disk-maintenance.timer
systemctl daemon-reload
# Only the superseded maintenance timer is disabled; no production service is stopped.
systemctl disable --now rasteh-host-disk-maintenance.timer
systemctl enable --now server-disk-maintenance.timer
```

Schedule: daily 03:40 UTC plus zero to ten minutes delay (07:10–07:20 Tehran), persistent after downtime. Root private reports: `/var/log/server-disk-maintenance/run-*.jsonl`. Native MySQL backups: `/var/backups/server-disk-maintenance`.

Manual dry-run: `python3 /usr/local/sbin/server-disk-retention.py`. Apply: `systemctl start server-disk-maintenance.service`. Inspect: `systemctl status server-disk-maintenance.service server-disk-maintenance.timer`.

Disable only maintenance if required: `systemctl disable --now server-disk-maintenance.timer`. This does not affect applications.

## October 12 cleanup and recovery

Audits on RoboT: `/opt/akhbot/audit/all-project-cleanup-20261012`, plus pre/post health snapshots. Inactive Android API27/API28 emulator/system-image/command-line packages were retired with owner confirmation. Active platform-tools/adb, licenses, all AVD data, and TwoID app/database remained.

One-off duplicate PV deployment exports younger than five days were removed only after exact current/rollback full-export SHA verification and source commit verification on GitHub. This exception does not change the daily five-day age guard. The two retained full exports (current 9f6c2a4 and rollback 32879be) were losslessly compressed, and decompressed bytes matched their original release hashes. Each release has a `.tar.compression.json` recovery marker:
- Current uncompressed SHA256: `7dde48287b3af804600717abaad31dcbb4be593a386f48391197d10417707ba4`.
- Rollback uncompressed SHA256: `9f39ddcb3e4fbd874da57d48781bc450da4c54aa6340efa54a498a2d52ad3d0d`.

For Docker restore, load the retained `.tar.gz` directly. For binary-delta tools or old deploy scripts requiring a raw `.tar`, first run `gzip -dk PATH.tar.gz`, verify its original SHA above, and leave the compressed recovery copy intact. Rehydration temporarily needs about 708MB per export. No running image was replaced.

MySQL binlogs 000210–000238 were archived byte-for-byte and then purged natively. Logs 000239 and later/current remain. Private SQL backup and `.tar.xz` archive, source/member hashes and verification manifest are in the audit directory. No application rows were removed. Archive checks are byte-integrity checks; they do not claim a full database restore drill.

## Repository mapping reviewed

| Server resource | Repository / source |
|---|---|
| Rasteh | DashSaman/akh-bot |
| TwoID | DashSaman/2-id |
| PV developer and SentinelX-named workers | DashSaman/PV-NativePanel (same project rules; no separate SentinelX runtime proven) |
| PV Growth | DashSaman/PV-GrowthOS |
| PV reseller dashboard | DashSaman/PVNetwork-Reseller-Dashboard |
| PV network documentation | DashSaman/OV-PvNetwork |
| Installed OV node/panel lineage | primeZdev/ov-node; primeZdev/ov-panel |
| Mirza bot lineage | mahdiMGF2/botmirzapanel; mahdiMGF2/mirzabot |
| nine-router image label | decolua/9router |

Live SQLite/PostgreSQL/MySQL data, customer/configuration secrets, fourteen Growth SQL backups, newest Rasteh backups/DR, current/rollback Docker versions, anonymous volumes, adb/AVD, active browser/Commander dependencies, swap and OS packages were preserved.

Primary MySQL maintenance reference: https://dev.mysql.com/doc/refman/8.0/en/purge-binary-logs.html
