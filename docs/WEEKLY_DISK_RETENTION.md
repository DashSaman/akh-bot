# Weekly scoped server cleanup

The standalone controller in `ops/fleet_disk_retention.py` replaces the older daily general controller when the operator selects weekly maintenance. The Rasteh-specific guard remains available. Do not run both schedules independently: the controllers share one nonblocking lock.

The command defaults to dry-run. `--apply` is required for deletion. The private per-host policy is `/etc/scoped-server-cleanup.json`; it must be a regular root-owned file that is not writable by group or others. Policies, host inventories, credentials and customer data are not committed.

## Deployment

Install `ops/host_disk_retention.py` as `/usr/local/lib/scoped-server-cleanup/guard.py`, and this controller as `/usr/local/sbin/scoped-server-cleanup.py`. Install the supplied service, cron file and journald drop-in. Create an audited host policy with `critical_units`, `running_containers`, `http_checks` (URL plus accepted status codes), `native_checks` (argument lists), `sqlite_checks`, and only proven `cache_roots` / `image_repos`. Optional `rasteh`, `growth` and `dated_log_roots` enable explicit project scopes.

Run dry-run and inspect its plan before the first actual service execution. Confirm the actual service run succeeds before enabling cron. If replacing the old daily schedule, disable only `server-disk-maintenance.timer`. Keep cron itself and all production services running. The supplied cron invokes the bounded oneshot service every Sunday at 03:40 in the server timezone (03:40 UTC on UTC hosts).

## Retention and safety

Closed allowlisted rotated logs with modification time older than five days are deleted. A one-hour quiet period, mount/symlink/hardlink checks and fresh process fd/cwd/mmap checks protect active files. Current logs are never truncated or removed. Closed raw rsyslog rotations may be compressed only with native nodelaycompress configured; the replacement is decompressed and checksum-verified before removing its source. Preserve native logrotate postrotate hooks and validate in the global configuration context.

Journals are rotated and vacuumed through journalctl with five-day retention and a 200 MiB cap. The drop-in applies at the next normal journald restart; do not restart it for this task. Retain any stricter preexisting limits.

Developer dependency caches require an exact allowlist, an old tree, no external links, no repository process cwd, no container bind reference, and a package lock for node_modules. Source, Git history, runtime dependencies, unknown files, database files and installed toolchains are retained. Old apt download packages are skipped during package transactions.

Image deletion uses exact declared repositories, an age greater than five days, all running/stopped container references, newest versions and rollback protection. No global prune is used. Rasteh backups retain at least two validated DB recovery copies. DR volumes require exact ownership, age and no container references.

PV-Growth surplus binary export retention is count-based. Current/stopped references, newest versions and newest unused rollback are preserved. Two complete exports for distinct installed image IDs must pass config and every layer hash before redundant exports can be removed. Source, metadata, environment and SQL files remain untouched. Archive provenance and proof caches are bound to file fingerprints and installed image identity.

Before each action, required service PIDs/states, container identities/restarts/ports, TCP listeners, Xray/network configuration hashes and base firewall rules must match the baseline. HTTP and native database checks must pass. Naturally changing client UDP sockets and live kernel routes are recorded as observations. A deployment or unhealthy service halts cleanup. No action changes network/firewall/ports or restarts an application.

Private durable JSONL audits are written under `/var/log/scoped-server-cleanup`, including before/after capacity, action results and halt reasons. Old audit reports follow the same five-day closed-file retention. Low-priority CPU/I/O, memory and runtime limits protect production workload. A space target never overrides recovery or ownership guards.
