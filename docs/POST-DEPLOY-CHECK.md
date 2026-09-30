# Post-Deploy Check

## 2026-09-30 (session 2 — access, security rotation, browser E2E)

- **Root cause of browser error:** the in-app browser ran on the local machine;
  `127.0.0.1:8307` there refers to the LOCAL machine, not the VPS. The previous
  session's tunnel had been closed. Fix: standing SSH key-based tunnel
  (`ssh -N -L 18307:127.0.0.1:8307`) — verified working from the same machine the
  browser runs on. Docker remains localhost-bound; no public port opened.
- **Security:** the previously printed admin password was ROTATED. New credential
  generated on the server, stored as scrypt hash in `.env` (no plaintext) + root-only
  `/opt/akhbot/admin-credential.txt` (chmod 400). Never printed anywhere.
  A temporary E2E-only credential used during browser testing was invalidated by the
  same rotation. SSH key auth installed (`~/.ssh/akh_key`); password no longer needed.
- **New fix deployed:** CSRF enforcement on ALL admin mutations (was login-only);
  forged-token POST verified rejected with 403 in production. 54 unit tests passing.
- **Browser E2E (production, via tunnel):** RTL/fa ✅ · login ✅ · dashboard ✅ ·
  sources ✅ · raw items ✅ · events ✅ · publications ✅ · settings ✅ · navigation ✅ ·
  emergency pause ON→badge/OFF ✅ (left ACTIVE) · CSRF forged 403 ✅ · logout ✅ ·
  login required again ✅ · wrong password rejected ✅.
  Session-expiry wait (12h) not practical to wait out; cookie flags verified.
- **Git:** repository HEAD == deployed HEAD after final deploy (see 00-CURRENT-STATUS).
- **Existing services re-checked after all changes:** Apache :80 → 200, both other
  containers up, RAM available unchanged (see "Before/after" in session 1 + live
  checks during session 2).

## 2026-09-30 (session 1 — initial deployment)

## Deployed
- Commit: `3d2fe8b` (fix: render CSRF token on first login GET)
- Container: `akhbot-app` (image `akhbot-app:latest`, 288 MB), restart=unless-stopped, healthy
- Network `akhbot_internal`, volume `akhbot_data`, bind **127.0.0.1:8307 only**
- `/health` → `{"status":"ok"}` · `/ready` → workers ON, brand UNDECIDED, preview mode

## BEFORE vs AFTER comparison

| Check | Before deploy | After deploy |
|---|---|---|
| Containers | pv-reseller-dashboard, sentinelx-worker | + akhbot-app (both others unchanged, up) |
| RAM used / available | 1.2 Gi / 2.2 Gi | 1.2 Gi / 2.2 Gi (no measurable change) |
| Load (1m) | ~0.65 | ~0.6–1.3 (transient build) → settling |
| Listening ports | (see PORTS-NETWORKS) | + 127.0.0.1:8307 only; no public ports added |
| Apache :80/:443 | 200 OK | 200 OK (untouched) |
| MySQL/Postgres/x-ui/xray | running | running (untouched) |

**Existing services affected: NO.**

## Functional smoke tests (production, via localhost)
- Admin login (correct password) → 303 → dashboard 200 (RTL renders) ✅
- Wrong password → 401 ✅ · CSRF enforced on POSTs ✅
- Live ingestion E2E: added real source **BBC Persian** via admin API → container
  collected **29 real feed items** within one ingest pass ✅
- **Backfill protection verified live:** all 29 items have `activation_ok=0` (feed
  entries predate source activation) → STORE_ONLY, never auto-publish eligible ✅
- Backup script → `/data/backups/akhbot-20260930T142517Z.db` created via online backup ✅
- Full restore drill: pending (ROADMAP) — unit-level round-trip covered by tests.

## Resources at idle+worker (see RESOURCE-BASELINE.md)
RAM 45.9 MiB · CPU ≤0.31% · DB ~36 KB.
