# Roadmap (parked ideas — do NOT auto-implement)

1. Wire credentials when owner provides: GLM key, Telegram bot token + staging
   channel, (optional) Telethon ingest session → first live ingest → first live
   staging publication test.
2. Real UI screenshots → `docs/images/*.webp` (via SSH tunnel).
3. Brand decision → domain + Apache vhost (template ready) + SSL + exit preview mode.
4. X / Instagram / Threads adapters (official APIs; status machine already in place).
5. Stage-5 dedup for ambiguous cases only: multilingual embeddings or batched LLM
   event comparison (deferred by design until volume justifies it).
6. Evidence graph UI (claim ↔ item ↔ source visualization) in admin.
7. Google Search Console + first-party analytics + growth dashboard.
8. Story corrections propagation to Telegram via editMessageText (mechanism present;
   needs editorial workflow trigger).
9. Full production restore drill.
10. Consider 1–2 GB swap (owner approval required).
