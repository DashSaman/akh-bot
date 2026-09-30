# Ports & Networks Map (Hetzner host)

Snapshot 2026-09-30. **Selection: akhbot binds `127.0.0.1:8307` only.**

## Conflict table

| RESOURCE | CURRENT OWNER | PURPOSE | DO NOT TOUCH | DECISION FOR AKHBOT |
|---|---|---|---|---|
| :22 | sshd | ssh | yes | use for deploy |
| :80/:443 | apache2 | reverse proxy, 2 vhosts | yes | not used yet (no domain) |
| :3000 | hedioum-tunnel | tunnel | yes | avoid |
| :465/:993 | hedioum-tunnel | mail proxies | yes | avoid |
| :1194–1197, :8443 | xray | VPN | yes | avoid |
| :2083/:2096 | hedioum-tunnel | tunnel | yes | avoid |
| :2087 | x-ui | panel | yes | avoid |
| :5000 | hedioum-tunnel | tunnel | yes | avoid |
| :8080 | pvnetwork_web.py | python web | yes | avoid |
| :9090 | hedioum-tunnel | tunnel | yes | avoid |
| 127.0.0.1:3306/33060 | mysqld | existing DBs | yes | not used (SQLite) |
| 127.0.0.1:5432 | postgres | existing DB | yes | not used |
| 127.0.0.1:31080 | docker-proxy | pv-reseller-dashboard | yes | avoid |
| 127.0.0.1:4020 | x-ui | panel internal | yes | avoid |
| **127.0.0.1:8307** | — free — | — | — | **akhbot app** ✅ |
| :8308, :8309, :8777 | — free (verified) — | — | — | spare |

## Docker objects

- Networks: `bridge`, `host`, `none`, `pv_reseller_net` (foreign — untouched).
- New network created for this project: `akhbot_internal` (bridge).
- New volume: `akhbot_data` (SQLite DB + backups live here).
- Container: `akhbot-app` (restart=unless-stopped, log rotation 10m×3).

## Exposure strategy

1. **Now (brand UNDECIDED):** app reachable only via SSH tunnel
   `ssh -L 8307:127.0.0.1:8307 root@91.107.240.235` → http://127.0.0.1:8307
2. **Later (after domain + brand approval):** isolated Apache vhost (existing proxy)
   with `ProxyPass / http://127.0.0.1:8307/` + SSL via certbot — template prepared at
   `scripts/apache-vhost.conf.template`. Reload (not restart), `apache2ctl configtest`
   before reload.

No public bind. No firewall changes. No other project touched.
