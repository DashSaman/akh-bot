# Changelog

## 2026-09-30 — initial vertical slice
- Phases 0–1: open-source research notes; read-only Hetzner preflight + ports/networks map.
- Phase 2–3: FastAPI bootstrap, SQLite WAL + migrations, admin auth (scrypt/HMAC
  session/CSRF/throttle), health/ready, JSON logging, central brand config.
- Phase 4: source registry (APPROVED/DISCOVERED/BLOCKED, activation anchors).
- Phase 5: RSS collector (ETag/If-Modified-Since/304, failure isolation) + Telethon
  telegram adapter (lazy, revision-preserving, forward lineage).
- Phase 6: 4-stage dedup (canonical URL → content hash → normalized title → SimHash)
  + event clustering.
- Phase 7: LLMProvider abstraction, GLM adapter (cache/retry/measured tokens),
  Persian structured writer, evidence auditor.
- Phase 8: Telegram Bot API publisher + idempotent publication ledger + durable
  jobs/outbox + global/per-platform pause + rate caps.
- Phase 9: Persian RTL admin panel + public website + single-graph SEO layer
  (NewsArticle/NewsMediaOrganization, sitemaps, RSS, robots, preview mode).
- Tests: 52 passing. Deployed: /opt/akhbot, 127.0.0.1:8307.
