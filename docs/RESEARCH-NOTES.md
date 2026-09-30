# Research Notes — Open-Source Prior Art

Researched 2026-09-30 before implementation. **No code was copied from any project** —
all code in this repository is original; ideas/patterns only. License risks avoided
(GPL/AGPL projects studied conceptually, never vendored).

## Studied projects

### moguiyu/NewsPrism — MIT
- URL: https://github.com/moguiyu/NewsPrism
- Python + SQLite sole persistence + Docker Compose + LiteLLM-compatible LLM + static HTML + optional Telegram publishing.
- **Adopted ideas:** SQLite is enough for a single-host news pipeline; layered rule
  (types→config→repo→service→runtime) with repo boundary; event-identity clustering
  (group by real-world event, not topic); YAML-driven config; batch LLM summarization
  in one call to cut cost/latency.
- **Rejected:** LLM-first clustering as the primary mechanism (we keep cheap-first
  fingerprint stages; LLM/embedding only for ambiguity later); static report UI
  (we need a live site with trust pages).
- Resource impact: none (pattern only).

### frankzch/ai-news-brief — MIT
- URL: https://github.com/frankzch/ai-news-brief
- Python, PostgreSQL+pgvector, Playwright fallbacks, OpenAI-compatible LLM.
- **Adopted ideas:** SimHash screening BEFORE expensive semantic dedup (our stage 4);
  source catalog as DB data, not hardcoded config; recency-aware thresholds; deferred
  expensive processing.
- **Rejected:** pgvector/Postgres stack (too heavy for a 4 GB shared host); browser
  automation as a normal path.
- Resource impact: none (pattern only).

### philoking/cruxwire — MIT
- URL: https://github.com/philoking/cruxwire
- Pure-stdlib Python, single container, local Ollama, cosine clustering @0.74.
- **Adopted ideas:** configurable similarity thresholds; atomic state writes;
  lightweight self-hosted design philosophy.
- **Rejected:** local Ollama/embedding model (RAM-prohibited on this VPS);
  no-auth service exposure.

### sansan0/TrendRadar — GPL-3.0 ⚠
- URL: https://github.com/sansan0/TrendRadar
- **Adopted ideas (concept only, zero code):** keyword+AI hybrid filtering; scheduled
  ingestion windows; multi-channel delivery batching.
- **Rejected:** GPL license — no code reuse permitted; hot-list crawling irrelevant.

### DIYgod/RSSHub — MIT · dgtlmoon/changedetection.io — Apache-2.0
- Referenced as future ingestion helpers (RSS ecosystem breadth; change detection for
  pages without feeds). Not deployed yet; no code copied. Candidate for later
  containerized use if a source demands it.

### gitroomhq/postiz-app — AGPL-3.0 ⚠
- Studied as social-publishing reference ONLY. AGPL → **no code reuse**; we implement
  our own minimal per-platform publishers (Bot API + official APIs), which is lighter
  anyway.

## GitHub survey summary (searches: multilingual news aggregator, event clustering,
fact-checking pipelines, source dependency, Telegram newsroom bots, correction systems)

Common findings across the space: (1) cheap lexical dedup before embeddings is the
dominant cost-saving pattern; (2) event-level (not article-level) identity is what
readers and SEO both want; (3) most projects lack independence-of-source analysis —
this is our differentiator (lineage collapse via forward metadata + canonical origin);
(4) correction histories are almost never modeled — we store story versions + ledger.
