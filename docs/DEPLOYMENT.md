# فارسی

# استقرار

سرور: Hetzner، Ubuntu 22.04، Docker 29.1.3 (بدون پلاگین compose → از `docker run` استفاده می‌شود).

## گام‌ها
1. `git clone https://github.com/DashSaman/akh-bot /opt/akhbot/app`
2. `cp /opt/akhbot/app/.env.example /opt/akhbot/.env` و پر کردن مقادیر (`chmod 600`)
   - `SESSION_SECRET`: `python -c "import secrets;print(secrets.token_urlsafe(48))"`
   - `ADMIN_PASSWORD_HASH`: `python -m app.core.security make-hash <password>`
3. `bash /opt/akhbot/app/scripts/deploy.sh` → بیلد image `akhbot-app:latest`، ساخت `akhbot_internal`، اجرای `akhbot-app` روی `127.0.0.1:8307`
4. بررسی: `curl http://127.0.0.1:8307/health`
5. بکاپ روزانه: `cron: 15 3 * * * bash /opt/akhbot/app/scripts/backup_db.sh`

## دسترسی پنل (تونل SSH)
```bash
ssh -N -L 18307:127.0.0.1:8307 root@91.107.240.235   # یا هر پورت محلی آزاد
# سپس: http://127.0.0.1:18307/admin
```
نکته مهم: `127.0.0.1` در مرورگرِ دستگاه شما یعنی دستگاه شما — بدون تونل فعال،
پنل در دسترس نیست (این عمدی است). پورت داکر روی `127.0.0.1:8307` سرور می‌ماند و
هرگز عمومی نمی‌شود. احراز هویت SSH با کلید (`~/.ssh/akh_key`) نصب شده است.

## اعتبارنامه مدیر
- `.env` فقط `ADMIN_PASSWORD_HASH` (scrypt) دارد — متن خام ندارد.
- گذرواژه واقعی فقط در `/opt/akhbot/admin-credential.txt` روی سرور (chmod 400، فقط root).
- چرخش: `python -m app.core.security make-hash <new>` → جایگزینی هش در `.env` → `deploy.sh`.
- هرگز در گزارش/گیت/لاگ نوشته نشود.

## به‌روزرسانی
```bash
cd /opt/akhbot/app && git pull && bash scripts/deploy.sh   # rm -f + run جدید؛ داده در والیوم akhbot_data می‌ماند
```

## نکات ایمنی
- هیچ پورت عمومی؛ بدون دامنه، هیچ تغییری در Apache داده نشده (قالب آماده: `scripts/apache-vhost.conf.template`).
- هیچ دستور سراسری نصب نشده؛ وابستگی‌ها داخل image.
- کانتینر non-root (uid 10001) با healthcheck و restart=unless-stopped.

---

# English

# Deployment

Server: Hetzner, Ubuntu 22.04, Docker 29.1.3 (no compose plugin → `docker run` based).

## Steps
1. Clone repo to `/opt/akhbot/app`.
2. Create `/opt/akhbot/.env` from `.env.example` (`chmod 600`); set `SESSION_SECRET`
   and preferably `ADMIN_PASSWORD_HASH` (`python -m app.core.security make-hash <pw>`).
3. `bash scripts/deploy.sh` — builds image, creates `akhbot_internal` network,
   runs `akhbot-app` bound to `127.0.0.1:8307` (health-checked, log-rotated).
4. Verify: `curl http://127.0.0.1:8307/health`.
5. Daily backup cron: `15 3 * * * bash /opt/akhbot/app/scripts/backup_db.sh`.

## Admin access (SSH tunnel — REQUIRED)
```bash
ssh -N -L 18307:127.0.0.1:8307 root@91.107.240.235
# then open: http://127.0.0.1:18307/admin
```
`127.0.0.1` in YOUR browser means your machine — without the tunnel the panel is
unreachable (intentional). Docker stays bound to server-local `127.0.0.1:8307`;
never expose it publicly. SSH key auth (`~/.ssh/akh_key`) is installed.

## Admin credential
- `.env` stores ONLY `ADMIN_PASSWORD_HASH` (scrypt) — no plaintext.
- The actual password lives only in `/opt/akhbot/admin-credential.txt` on the server
  (chmod 400, root-only).
- Rotation: `python -m app.core.security make-hash <new>` → replace hash in `.env`
  → `deploy.sh`. Never write it in reports/git/logs.

## Update
`git pull && bash scripts/deploy.sh` — data persists in the `akhbot_data` volume.

## Safety notes
- No public port, no Apache changes yet (template ready), no host packages installed,
  non-root container (uid 10001), restart=unless-stopped.
