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

## 2026-10-05 — translation fidelity hotfix
- EN: Added fail-closed canonical-name validation for evidence-backed Iranian
  proper names. `Araghchi`/`Araqchi` must render as «عراقچی»; a drift such as
  «عارقی» is rejected before publication. Existing lost-country/number checks
  are now enforced in the translation consistency gate.
- FA: کنترل قطعی نام‌های خاص به مسیر ترجمه اضافه شد؛ برای نمونه
  `Araghchi`/`Araqchi` باید «عراقچی» منتشر شود و خروجی‌هایی مانند «عارقی»
  پیش از انتشار رد می‌شوند. کنترل حذف کشور/عدد نیز اکنون در گیت ترجمه فعال است.
- Translation prompt/cache contract bumped to `fa-rewrite-v3`; full regression
  suite: 427 passed.

## 2026-10-06 — language-aware translation routing
- EN: English sources now prefer `groq/openai/gpt-oss-120b`; Arabic sources
  prefer `groq/qwen/qwen3.8-27b`, based on live same-text translation probes.
  A preferred-model failure automatically retries the existing
  `rasteh-translation` 9Router combo before normal provider failover.
- FA: ترجمه منابع انگلیسی ابتدا با GPT-OSS-120B و منابع عربی ابتدا با Qwen
  انجام می‌شود. اگر مدل ترجیحی خطا بدهد، مسیر fallback قبلی `rasteh-translation`
  به‌طور خودکار حفظ می‌شود و انتشار همچنان fail-closed است.
- Other source languages keep the existing routing. Translation cache contract
  bumped to `fa-rewrite-v4`.
- Numeric fidelity now normalizes press-style thousands separators, so `3,200`
  and `۳۲۰۰` compare as the same fact while genuinely invented numbers still fail.
- Full regression suite: 432 passed.

## 2026-10-06 — free Z.AI emergency translation fallback
- EN: Live no-publish probes found `zai/glm-4.5-flash` fact-faithful for both
  the English and Arabic test sentences (Araghchi, Tuesday, 3,200 centrifuges,
  negation, two weeks), but slower and stylistically weaker than the preferred
  models. It is therefore configured only after the existing
  `rasteh-translation` combo as a last-resort OpenAI-compatible fallback.
  `zai/glm-4.7-flash` was excluded after overload/429 instability.
- FA: در تست زنده و بدون انتشار، `GLM-4.5-Flash` اطلاعات اصلی متن انگلیسی
  و عربی را درست حفظ کرد، اما کندتر و از نظر نثر ضعیف‌تر از مدل‌های اصلی بود؛
  بنابراین فقط به‌عنوان fallback اضطراری بعد از combo فعلی
  `rasteh-translation` فعال شد. `GLM-4.7-Flash` به‌دلیل ناپایداری و خطای
  overload/429 وارد مسیر production نشد.
- The fallback list is environment-configurable through
  `OPENAI_COMPAT_FALLBACK_MODELS`; provider failures remain fail-closed.
- EN runtime note: after deploy, a forced no-publish Z.AI smoke encountered
  an upstream 429/overload and automatically returned through the existing
  combo; keep Z.AI emergency-only until its availability is consistently stable.
- FA: در smoke پس از deploy، فراخوانی اجباری Z.AI با 429/overload موقت روبه‌رو
  شد و مسیر قبلی به‌درستی جایگزین شد؛ بنابراین Z.AI فعلاً فقط fallback اضطراری
  باقی می‌ماند تا پایداری سرویس بهتر شود.
- Full regression suite: 433 passed.

## 2026-10-06 — free-provider qualification and safer language failover
- EN: Re-qualified every currently connected/free candidate on the same EN+AR
  fact-preservation fixture. Cloudflare Mistral Small 3.1 was 6/6 HTTP 200 in
  qualification calls, preserved Araghchi/Tuesday/3,200 centrifuges/negation/
  two weeks, and repeated in roughly 2–5 seconds. Z.AI GLM-4.5-Flash also
  preserved those facts in 6/6 calls in this round, but remained much slower
  (roughly 18–29 seconds) and has prior intermittent upstream 429s.
- FA: همه مسیرهای رایگان/موجود با یک ورودی ثابت انگلیسی و عربی دوباره
  ارزیابی شدند. Mistral Small 3.1 کلادفلر در ۶/۶ فراخوانی موفق بود، واقعیت‌های
  حساس را حفظ کرد و سریع‌تر بود. GLM-4.5-Flash زد‌ای‌آی نیز در ۶/۶ فراخوانی
  این دور درست بود، اما کندتر است و سابقه 429 موقت دارد.
- EN: Language failover is now ordered as EN GPT-OSS-120B / AR Qwen3.8-27B,
  then Cloudflare Mistral, then Z.AI GLM-4.5-Flash, then the legacy generic
  combo. This prevents a generic cross-language model from winning before
  the validated language-safe fallbacks.
- FA: ترتیب fallback اکنون برای انگلیسی و عربی ابتدا مدل تخصصی همان زبان،
  سپس Cloudflare/Mistral، بعد Z.AI GLM-4.5-Flash و در پایان combo عمومی است.
- Rejected/not promoted: Cohere trial (429 quota), SambaNova (no active
  credential in 9Router despite the saved connection), LLM7 GLM-5.3-Flash
  (JSON mode unsupported and 40-second timeouts without JSON mode),
  LLM7 Mistral-Nemo (fact errors), OpenRouter Nemotron (malformed/length
  output), OpenRouter free Google Gemma 4 models (upstream 429), Z.AI 4.7
  (empty length-limited output), and Cloudflare Llama 8B (technical-term
  errors). Direct Gemini remains unconfigured because no Gemini API key is
  present on the server.
- EN runtime verification: production SHA `edd819a` is healthy; forced-primary-failure no-publish smoke tests for both EN and AR reached Cloudflare Mistral next and preserved the protected facts.
- FA: در تست زنده بدون انتشار، با fail اجباری مدل اصلی برای هر دو زبان انگلیسی و عربی، مسیر بعدی Cloudflare/Mistral انتخاب شد و واقعیت‌های حساس حفظ شدند.
- Full regression suite: 435 passed.
