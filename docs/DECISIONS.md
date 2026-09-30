# Decisions (ADR-style log — do not re-litigate without new evidence)

| # | Decision | Rationale | Date |
|---|---|---|---|
| D1 | Lightweight modular monolith (FastAPI + SQLite WAL + asyncio), single container | 2-core/3.7 GB shared host; resource budget idle ≤200 MB | 2026-09-30 |
| D2 | No Redis/Celery/pgvector/K8s/Chromium/Ollama initially | measured need absent; SQLite jobs table is a sufficient durable outbox | 2026-09-30 |
| D3 | Bind 127.0.0.1:8307 only; no Apache changes until domain/brand approved | brand UNDECIDED; zero impact on existing vhosts; admin via SSH tunnel | 2026-09-30 |
| D4 | Deploy via `docker run` scripts (host lacks compose plugin); keep compose.yml for portability | avoids installing host packages (owner policy) | 2026-09-30 |
| D5 | Content-hash/SimHash over BODY only; title equality is separate stage 3 | headlines legitimately vary across outlets for the same story | 2026-09-30 |
| D6 | report_count counts all reports; independent_count collapses lineages | spec §120: 5 copies → 5 reports, 1 origin | 2026-09-30 |
| D7 | Pipeline processes NEW items oldest-first | first occurrence must own the event before copies attach | 2026-09-30 |
| D8 | Preview mode (robots Disallow-all, no canonical) while PUBLIC_BASE_URL empty | prevent indexing brand-less placeholder content; auto-reverts | 2026-09-30 |
| D9 | Rules-only baseline claims when LLM offline (conservative UNVERIFIED) | pipeline never stalls; never fakes verification | 2026-09-30 |
| D10 | Writer outage → event returns to READY (retry), never HELD-fake-success | transient LLM downtime ≠ editorial hold | 2026-09-30 |
| D11 | Persian/Arabic digit normalization in number checks | casualty contradictions are written in Persian digits | 2026-09-30 |
| D12 | No code reuse from GPL/AGPL projects (TrendRadar, postiz) | license safety; MIT ideas only | 2026-09-30 |
