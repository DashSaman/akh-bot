# Security

- **Admin auth:** signed HMAC session cookie (HttpOnly, SameSite=Lax, 12h TTL),
  scrypt password hashing (`ADMIN_PASSWORD_HASH` preferred over plaintext),
  per-IP login throttle (5 fails → 15 min), CSRF double-submit on every POST,
  admin mounted with noindex; reachable only via SSH tunnel (localhost bind).
- **Secrets:** only via `/opt/akhbot/.env` (chmod 600) / container env; `.env`,
  sessions, tokens gitignored; never logged.
- **Prompt injection:** external content enters LLM prompts only inside
  `<<<UNTRUSTED-SOURCE-DATA` delimiters with explicit "data, not instructions"
  rules; control characters stripped; length-capped. External text can never
  approve sources, publish, or change settings.
- **Container:** non-root (uid 10001), no secrets baked into image, healthcheck,
  graceful shutdown, log rotation, minimal system packages.
- **Webhooks:** none exposed today; future ones must use secret paths + signature
  checks + rate limits + replay protection.
- **Forms:** server-side validation, CSRF, rate limiting; contact forms when added
  will follow the same; uploads (if ever) restricted by extension/MIME/size and
  stored outside executable paths.
- **Server hardening note for owner:** root SSH with a password is currently used —
  recommend switching to key-only auth + changing the exposed password (owner action).
