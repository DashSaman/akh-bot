# فارسی

# معماری

**الگوی انتخابی: مونولیت ماژولار سبک** (FastAPI + SQLite WAL + asyncio، تک‌کانتینر).

```
app/
  api/        نقاط سلامت (/health, /ready)
  admin/      پنل مدیریت RTL (نشست امضاشده + CSRF + throttle)
  web/        سایت عمومی server-rendered + صفحات اعتماد
  ingestion/  زمان‌بند جمع‌آوری + RSS (ETag/304) + تلگرام (Telethon، import تنبل)
  clustering/ دداپ ۴ مرحله‌ای + خوشه‌بندی رویداد
  verification/ گیت‌های سخت + تشخیص پرخطر + ارقام فارسی/عربی
  newsroom/   خط تولید: ادعاها → بسته واقعیت → نویسنده GLM → ممیز
  publishing/ ناشر تلگرام + متن پلتفرمی
  jobs/       اجراگر کارهای پایدار (outbox در SQLite، backoff نمایی)
  seo/        گراف واحد JSON-LD + sitemap/news-sitemap/RSS/robots
  integrations/llm/ انتزاع LLMProvider + آداپتور GLM (کش + retry)
  db/         SQLite WAL + مایگریشن + مخزن‌ها (مرز انتزاع برای PostgreSQL آینده)
```

## حلقه‌های پس‌زمینه (تک‌پروسه، متوالی برای صرفه‌جویی RAM)
- `ingest_loop`: منابع سررسید → RSS/تلگرام (هر منبع ایزوله؛ خطا فقط سلامت منبع را خراب می‌کند)
- `pipeline_loop`: مواد NEW → دداپ/خوشه/ادعا/نویسنده/ممیز → داستان + صف انتشار
- `jobs_loop`: کارهای pending → اجرا با idempotency دفتر انتشار

## تصمیم‌های کلیدی
- SQLite تک‌اتصاله + RLock: برای بار این سرور صحیح و سبک‌ترین گزینه؛ لایه repo مرز مهاجرت به PostgreSQL است.
- بدون Redis/Celery: جدول jobs همان outbox پایدار است (بعد از restart دوباره صف می‌شوند).
- LLM فقط برای ابهام چندزبانه/ادعا/نگارش؛ هرگز برای هش/مسیریابی/فرمت.
- همه متن‌های بیرونی داخل مرزهای UNTRUSTED به مدل می‌روند.

---

# English

# Architecture

**Chosen pattern: lightweight modular monolith** (FastAPI + SQLite WAL + asyncio, single container). See `app/` tree in the Persian section (identical).

## Background loops (single process, sequential — RAM-frugal on a 2-core host)
- `ingest_loop`: due sources → RSS/Telegram (per-source isolation; failures only decay source health)
- `pipeline_loop`: NEW items → dedup/cluster/claims/writer/auditor → story + publish queue
- `jobs_loop`: pending durable jobs → ledger-idempotent execution

## Key decisions
- Single-connection SQLite + RLock: correct at this scale and lightest; the repository
  layer (`app/db/repo.py`) is the migration boundary to PostgreSQL later.
- No Redis/Celery: the SQLite `jobs` table IS the durable outbox (requeued after restart).
- LLM only for multilingual ambiguity / claims / writing — never hashing/routing/formatting.
- All external text reaches the model inside UNTRUSTED delimiters (injection defense).
