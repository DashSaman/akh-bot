# Hetzner VPS Preflight — READ-ONLY Inventory

**Date:** 2026-09-30 · **Method:** read-only SSH inspection only · **No services were modified.**

## Verified system state

| Item | Value |
|---|---|
| Hostname | RoboT |
| OS | Ubuntu 22.04.5 LTS (Jammy) |
| Kernel | 5.15.0-191-generic (x86_64) |
| Virtualization | KVM (Hetzner) |
| CPU | 2 × Intel Xeon (Skylake, IBRS) |
| RAM total | 3.7 GiB |
| RAM used / available | 1.2 GiB / 2.2 GiB |
| Swap | **0 B (none)** |
| Disk `/` | 38 G total, 15 G used (42%) |
| Inodes | 15% used |
| Timezone | UTC |
| Uptime | 13 days |
| Load (1m/5m/15m) | 0.65 / 0.73 / 0.58 |
| Docker | 29.1.3 (server) |
| Docker Compose plugin | **NOT installed** (deploy via `docker run`) |
| Reverse proxy | **Apache2** (mod_proxy, mod_ssl, mod_rewrite) on :80/:443 — NOT nginx |
| Apache vhosts | robot.ahsg.top (+SSL), npanel.softarg.ir (+SSL) |
| Certbot cron | present |

## Existing production services (DO NOT TOUCH)

| Service | Port(s) | Notes |
|---|---|---|
| sshd | 22/tcp public | — |
| Apache2 | 80, 443 public | reverse proxy + vhosts above |
| MySQL | 127.0.0.1:3306, 33060 | local only; ~567 MB RSS |
| PostgreSQL | 127.0.0.1:5432 (+::1) | local only |
| x-ui panel | 2087, 4020 (local) | proxy panel |
| xray | 1194–1197, 8443, many UDP, 11111/62789 local | VPN core, ~68 MB, high CPU share |
| hedioum-tunnel | 465, 993, 2083, 2096, 3000, 5000, 9090 | tunnel service |
| pvnetwork_web.py | 8080 public | python service |
| Docker: pv-reseller-dashboard | 127.0.0.1:31080→3000 | compose-less container, 93 MB |
| Docker: sentinelx-worker | none (internal) | 47 MB, 128 MB limit |
| next-server (v…) | — | Node app, ~163 MB RSS |

## RAM/disk budget conclusion

With ~2.2 GiB available and other production loads, the resource target for akhbot
(idle ≤200 MB, processing ≤300 MB) fits comfortably. Disk has 21 G free — SQLite +
logs are negligible; media mirroring stays off by design.

## Safety rules honored

- No `apt upgrade`, no kernel/OS upgrades (out of scope by owner policy).
- No docker prune/down/restart of any existing container/network/volume.
- No reverse-proxy changes yet (no domain; app binds localhost only).
- No swap created (recommendation only — see below).

## Swap recommendation (NOT applied — needs owner approval)

Given 0 swap and other production services: a 1–2 GB swapfile (swappiness=10) would
reduce OOM risk during memory spikes at ~1–2 GB disk cost. **Not created**; awaiting
owner decision (spec §15).
