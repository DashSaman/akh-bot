# FCC / Rasteh: isolated zero-cost translation audit — 2026-10-12

## Decision
**Do not install FCC in the production newsroom.** Keep Rasteh -> FreeAiRouter -> 9Router and Telegram-only publishing. FCC is helpful for discovering candidate providers and for development-agent RTK/Headroom tool-output compression, not for making newsroom translation intrinsically more accurate or reducing LLM inference cost.

Reviewed upstream source checkout 2b55662, not run or installed. FCC requires Python == 3.14.7, carries AGPL-3.0-only, and lists 61 providers with *mixed* free, paid, subscription and local terms. No entitlement to its advertised free-token totals has been independently established for this newsroom. No FCC source copied into Rasteh.

## Read-only production baseline
- akhbot-app:liveblog-20261009 running/healthy, no observed restart; SQLite integrity_check=ok.
- Newest recorded Telegram remote_id=2187, 2026-10-11 13:05 UTC.
- 3793 ledger SENT, pending jobs 0, failures last 6h 0 and 24h 2 at inspection.
- 172 events in translation backoff; 1915 historical translation attempts. Do **not** bulk requeue them: many events are historical, held, stale or irrelevant.
- Host disk 95%; no FCC service/image was installed and no global Docker prune performed.
- Local repository: f5a2b36 plus uncommitted hotfixes was 15 commits ahead of origin/main d99a112. All differences were preserved in /opt/akhbot/backups/rasteh-sync-20261012T0048Z and isolated worktree. GitHub sync/CI is separate from runtime claims.

## Safe isolated gateway benchmarks
scripts/benchmark_zero_cost_translation.py is **OFFLINE** by default. Explicit --live uses only owner-validated free-only routes already configured via 9Router, short controlled fictional EN/AR/HE fixtures, no DB/publisher/outbox/Telegram, a hard model allowlist, and prints only result codes/latency.

| Model | Language | Result | Latency |
|---|---|---|---|
| groq/openai/gpt-oss-120b | EN | HTTP 503 (2 attempts) | 0.16–0.30s |
| zai/glm-4.5-flash | AR | PASS on one fixture | 19.2s |
| cf/@cf/mistralai/mistral-small-3.1-24b-instruct | HE | HTTP 503 (2 attempts) | 0.16–0.27s |
| groq/qwen/qwen3.8-27b | AR | FAIL: uncertainty dropped | 0.56s |

A single passed fixture is not production-grade language qualification. No new provider/model was added to production. Do not assume FCC catalog membership means production-free usage. Existing 9Router provider-level outages and quality regressions must be investigated independently of new integrations.

## Promotion criteria
- Official provider free production rights and zero-billing confirmed on the exact account. No cards, trials that auto-bill, paid APIs, unauthorized provider access, quota evasion or multiaccounts.
- Multiple blind fixtures per language and repeats over time, with correct proper nouns, quantities, uncertainty, negation, locations and source attribution. Record rate limits, 503s, malformed JSON and latency.
- Promoting *only* demonstrably qualified exact model IDs behind language-specific fallback lists and tests; retain existing working routing, content-hash caching, high-risk verification and fail-closed HOLD.
- FCC remains a separated reference/research tool; never chain it as a second live proxy.

## Isolation and release
Never modify unrelated GrowthOS, PV reseller, xray/VPN, Apache, Docker daemon, ports or global network. Do not reset Rasteh queues/DB/watermarks or post synthetic public news. CI and exact deployed source parity are needed before declaring the release complete.
