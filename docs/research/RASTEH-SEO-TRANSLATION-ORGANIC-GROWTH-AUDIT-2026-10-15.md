# Rasteh — Independent SEO, organic Telegram growth and zero-cost AI audit
Date: 2026-10-15 / baseline production and GitHub main 5cd683c4
MODE: RESEARCH ONLY. No live modifications, API billing, Telegram sends, DNS changes or server restarts.

## Executive summary (فارسی)

بزرگ‌ترین مانع رشد راسته مدل ترجمه نیست؛ وب عمومیِ قابل‌ایندکس و مسیر
جذب عضو واقعی وجود ندارد. موتور جمع‌آوری خبر قوی‌تر از موتور جذب مخاطب
است. ابتدا کیفیت و نمایش کامل خبر، عمومی‌سازی امن فقط مسیرهای وب،
آمار واقعی و مسیر پیوستن اختیاری به کانال را کامل کنیم. بعد مدل‌های
رایگان را به‌صورت زبان‌محور و آزمایشی ارزیابی کنیم.

فقط @RastehNews مقصد انتشار است؛ X/Threads/Facebook مقصد نیستند.
خرید اعضای جعلی، پیام خصوصی ناخواسته، کپی محتوای دارای حق نشر و
ساختن اخبار پرکننده ممنوع‌اند. هیچ عددی برای رشد تضمین نیست.

## What was ACTUALLY measured

- Repository GitHub HEAD 5cd683c4; last matching GitHub CI green.
  Running akhbot-app revision 5cd683c4, healthy, DB quick_check ok.
  Pending jobs=0; jobs failed during last 24h=0.
- Telegram Bot API getChatMemberCount (read-only): 26 real channel members
  counted by Telegram, no interpretation of active engagement.
- New Telegram remote IDs last 24h: 199 (unique messages).
  SENT ledger rows in same window: 398 (including edits). Keep these separate.
- 123 endpoints, 116 owner-enabled, 88 fetched in last hour.
  The other 28 are 27 BLOCKED_AUTH X/TruthSocial records plus one internal
  Manual Editorial Submission endpoint; do not mislabel as collector failures.
- RawItems fetched 24h: 4,857; new Events 2,593; 2,185 new Events HELD.
  16 genuinely future translation-backoff Events using ISO-consistent
  comparison; 316 Events from last 24h had a translation attempt.
- RAM total 3.7GiB and available ~1.7GiB at inspection; swap 2GiB,
  ~907MiB used. Do not deploy heavyweight local models to this shared VPS.
- Public website source exists with home, latest, story, RSS, sitemap,
  News sitemap, NewsArticle JSON-LD, but PUBLIC_BASE_URL is EMPTY,
  PREVIEW_MODE is TRUE, robots.txt returns Disallow: /,
  external https://rasteh.softarg.ir/robots.txt and / return HTTP 401.
  Existing Apache SSL vhost has blanket HTTP Basic auth for <Location />.
- 2,807 PUBLISHED/CORRECTED stories: only 1,785 have a lead >=50
  characters, and ZERO have draft.body or draft.source_references
  structures consumed by templates/public/story.html. Publishing 2,807
  thin pages before fixing this would be poor SEO and source transparency.
- Google News sitemap limit=200, yet 371 eligible published stories in
  recent 48 hours. StoriesRepo.recent does not include an ORDER BY clause.
- Of 33,656 aggregate web views recorded, 33,507 are health endpoint
  requests, 120 are /ready and very few are actual public pages.
  Count this as infrastructure traffic, NOT website visitors.
- app/seo/analytics.py seo_health reproduces a TypeError from list
  indexing on db.query(...)[n]. Admin /growth calls this function.
- RSS pubDate uses ISO8601 rather than a standard RSS date.
- Telegram media captions currently slice public copy at 1,020
  characters; text mode slices converted HTML at 4,096 characters.
  Risk: sentence/source/footer loss or invalid HTML. Correct BEFORE
  adding more syndicated content or opening the site.

## Recommended P0 — crawlability, quality, real visitors

1. Maintain current admin protection. Build a public read-only hostname
   and Apache vhost, narrow allowlist only:
   /, /latest, /story/*, /page/*, /robots.txt, /sitemap.xml,
   /news-sitemap.xml, /feed.xml, /static/*.
   Deny /admin, /api, private metrics, SQLite files and internal backend
   routes. Never remove existing Basic auth globally. DNS/SSL and Apache
   should be changed only in a separately reviewed outage-safe rollout.
2. Set actual canonical PUBLIC_BASE_URL, exit preview on the public
   frontend, validate 200/404/robots/canonical, JSON-LD and News sitemap
   (only truly recent 48h stories). Search Console only once public.
3. Populate public body and source references from canonical Event,
   Claims and Evidence with accurate provenance, uncertainty, timeline
   and corrections. One Event => one URL. No invented facts.
   Use noindex for low-value/thin/unverified-only summaries until they
   qualify for useful public editorial coverage.
4. Fix health check /ready filtering in the analytics middleware,
   fix seo_health's db.query list indexing and filter out private and
   crawler traffic. Measure real page views, source referrers and
   aggregate voluntary Telegram join clicks instead of health checks.
5. Fix unsafe Telegram photo/video caption slicing: use short COMPLETE
   evidence-safe summaries within Bot API limits or text-only fallback;
   never slice an unclosed HTML tag / sentence.
6. Correct RSS date format, sitemap ordering and 48h news listing
   (Google News sitemap supports <=1000 News URLs).

## Organic Telegram growth (P1)

- Channel title suggestion subject to owner approval: «راسته؟ | اخبار
  ایران و راستی‌آزمایی» (searchable topic and honest value), and clear
  About text mentioning primary sources, uncertainty and corrections.
  SEO keywords do NOT guarantee Telegram channel recommendations.
- Pin one short onboarding message with what makes the newsroom
  distinctive and direct link https://t.me/RastehNews.
- Public story pages: clear mobile "پیگیری خبر در تلگرام" button;
  separate aggregate click and consent-based join measurement.
- Publish a morning and an evening digest, plus important P0
  breaking updates. A/B test materially lower routine message
  volume vs 199 new messages/day, while preserving P0 exceptions
  and the existing 500/day safety ceiling. Optimize for net
  subscribers, share/view ratio, retention and genuine trust.
- Publish 2–4 ORIGINAL factual explainers each week: "آنچه می‌دانیم /
  آنچه نمی‌دانیم", primary evidence, source disagreements and
  post-publication correction notices. Avoid recycled filler.
- Optional subscriber-initiated Telegram bot: /start, /search,
  /factcheck and inline share verified news on request; topic-based
  opt-in alerts only. Bots cannot DM strangers.
- Honest cross-channel partnerships with owner-approved editors and
  attributed reposts. No forced joining, mass invites, spam, fake
  forwarding, paid/fake followers or engagement manipulation.
- Telegram Similar Channels is a recommendation feature based on
  overlapping public channel subscribers; do not promise ranking.
- Opt-in campaign invite links via official Bot API if channel rights
  permit; store aggregate joins and campaign conversions, not
  behavioral profiles or sensitive audience inference.

## Zero-cost translation: selection logic and options (P2)

Current FreeAiRouter + 9Router:
EN primary Groq GPT-OSS-120B; AR primary Z.AI GLM-4.5-Flash.
Validated per-language fallbacks include Cloudflare Mistral and Groq
Qwen (with known previous AR lexical/uncertainty regressions).
Hebrew does not have an explicit validated dedicated chain.
9Router should remain the ONLY live gateway; FCC remains research.

Candidate ranking and conditions:
1. Gemini 3.1 Flash-Lite via Gemini API: official free-tier text
   input/output, promising for EN/AR/HE to Persian. Check exact
   account, location, data-retention terms and sustained availability;
   the free tier may be used to improve Google's products.
2. Cloudflare Workers AI: 10,000 free neurons/day. Evaluate allowed
   free candidates such as GLM-4.7-Flash or Gemma-4-26B; some
   powerful newer models require paid plans and are EXCLUDED.
3. Existing Groq GPT-OSS-120B: documented Free-plan 1000
   requests/day and 200K tokens/day (subject to account limits).
   Rebenchmark model-language quality and rate-limit handling.
4. Argos Translate (MIT/CC0) and Meta M2M100-418M (MIT, supports
   EN/AR/HE/FA) are research-only offline fallback ideas. M2M100
   full model is about 1.94GB weights plus runtime and unsuitable
   for default placement on this shared 3.7GiB host.
5. OpenRouter :free tier around 50 requests/day without prior paid
   credits is emergency/experimental only, not main production.
6. Cerebras Sep/Oct 2026 PayGo developer tier requires payment
   method for promotional free credit and is evaluation-only:
   EXCLUDE as no-card production service.
7. NLLB-200-distilled-600M model is CC-BY-NC and explicitly says
   NOT for production deployment: EXCLUDE.

Promotion requires explicit permission for free production usage,
account-level zero-billing guarantee, 100+ per-language news
fixtures and repeat trials (EN/AR/HE), preservation of numbers,
names, places, chronology, negation, uncertainty, source attribution,
natural Persian and safety gates, p95 latency, 429/503, bad JSON,
cache hit rate and easy rollback. Never auto-select a model merely
because it claims to be "free".

## Open-source projects reviewed — reuse IDEAS by license

- NewsNow (newsnext/newsnow; MIT): elegant live trends, category
  navigation, story discovery and lightweight feed-source interface.
- Miniflux (miniflux/v2; Apache-2.0): conditional ETag/Last-Modified,
  robust feed scraper selectors and custom filters.
- Huginn (huginn/huginn; MIT): event-driven monitored agents and
  observable workflow triggers; implement small patterns in current
  Python workers, not a heavy extra Rails service.
- RSSHub (DIYgod/RSSHub; AGPL-3.0): discover feed adapters for
  sites where access is legal. License constraints apply; do NOT
  paste AGPL code into a proprietary/incompatible core.
- Argos Translate (argosopentech/argos-translate; MIT/CC0):
  local packages and optional pivot translations, evaluate quality.
- Free Claude Code (Alishahryar1/free-claude-code; AGPL-3.0):
  catalog and coding tool optimization, not a second production
  router. Many listed providers are NOT truly free production APIs.
Follow each exact project/model license and retain attribution;
never copy competitors' full articles/media without permission.

## Proposed releases and acceptance

R1 — QUALITY + MEASUREMENT:
repair seo_health 500, middleware health-page pollution,
complete editorial web schema + links, safe Telegram caption
fitting, historical thin-page noindex. Clean CI and private canary.

R2 — SAFE PUBLIC LAUNCH:
separate read-only public frontend hostname/vhost, controlled
DNS/TLS, no admin exposure, robots/sitemaps/RSS/schema valid,
Search Console submission and index coverage observability.

R3 — ORGANIC CONVERSION:
honest channel title/bio/onboarding, pinned CTA, public-site
Telegram buttons, daily digest, optional verified search/share
bot and consent-based partner distribution with join-click funnel.

R4 — ZERO-COST AI:
add only quality-qualified and commercially permitted/free
Gemini and Cloudflare candidates to existing 9Router;
collect p95 and provider budget logs, never silently charge.

Primary KPI is genuine net retained channel members and
accurate public-interest news, NOT Telegram sends or 33k
health-check pageviews. From 26 members, automatic growth
to thousands is not guaranteed; legitimate distribution is required.

## Primary public sources

https://telegram.org/blog/similar-channels
https://telegram.org/blog/my-profile-and-15-more
https://core.telegram.org/bots/features
https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap
https://developers.google.com/search/docs/essentials/spam-policies
https://developers.google.com/search/docs/appearance/google-discover
https://ai.google.dev/gemini-api/docs/pricing
https://console.groq.com/docs/rate-limits
https://developers.cloudflare.com/workers-ai/platform/pricing/
https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/
https://www.cerebras.ai/pricing
https://openrouter.ai/pricing
https://github.com/newsnext/newsnow
https://github.com/miniflux/v2
https://github.com/huginn/huginn
https://github.com/DIYgod/RSSHub
https://github.com/argosopentech/argos-translate
https://github.com/Alishahryar1/free-claude-code
https://huggingface.co/facebook/m2m100_418M
https://huggingface.co/facebook/nllb-200-distilled-600M
