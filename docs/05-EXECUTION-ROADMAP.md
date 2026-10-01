# 05-EXECUTION-ROADMAP
هر PART: الزامات/وابستگی‌ها/طرح/تست‌ها/پذیرش زنده/معیار خروج. قاعده: WORKING features که DONE اند بازنویسی نمی‌شوند.

| PART | Scope | Requirements (Matrix IDs) | Depends | Exit criteria (live/test) |
|---|---|---|---|---|
| **0** | Governance/baseline (این سند) | — | — | matrix+regression+gates frozen ✅ |
| **1** | Canonical Core | CORE-001, CORE-002, CORE-003, CORE-004, CORE-006(partial→media asset labels), GATE-11, REG-022, REG-026 | 0 | Story render فقط از فیلدهای ساخت‌یافته؛ source-line test؛ import-singleton test سبز |
| **2** | 24/7 Ingestion | INGEST-003 (Telethon), watermarks checkpoints fields | 0 | با session مالک: NewMessage → item در <5s؛ بدون آن: WEB_FALLBACK truthful (الان برقرار) |
| **3** | Event/Claim Engine | CLAIM-001..003, EVENT-001..003, PUB-003, GATE-03/05/06, REG-028..031/036..040 | 1 | **PART 3 EXIT (§P قانون اساسی):** یک مصاحبه در ۶ پیام→۱ Event؛ پارافریز→۱ Claim؛ ادعای جدید→همان Story؛ استوری عمومی→ویرایش همان پیام؛ نقل‌قول ناقص→عدم انتشار؛ سیل میکروپست=۰ |
| **4** | Verification Lifecycle | EvidenceLink/VerificationRun entities, SLA dashboards | 3 | بازبینی‌ها قابل ردیابی per-claim در پنل |
| **5** | Persian Editorial/Translation/AI | LANG-003, AI-002 live, ADMIN-002 (AI page) | 1 | با یک کلید رایگان: ar→fa زنده منتشر؛ بدون کلید: HOLD (الان برقرار) |
| **6** | Media | MEDIA-003 (original bytes via Telethon), REG-025 labels | 2 | عکس منبع واقعی (نه کارت) با rights مجاز منتشر شود |
| **7** | Admin Control Plane | SRC-003 کامل، ADMIN-002..004، MANUAL INTAKE | 0 | افزودن/ویرایش/تست/فچ/آرشیو بدون SSH؛ /admin/ai؛ /admin/health |
| **8** | Multi-platform | PLATFORM-002 (X/IG/Threads/FB) | 0+مالک | هر پلتفرم متصل: fan-out مستقل؛ شکست یکی مانع بقیه نیست |
| **9** | Security/Portability/DR | PORT-002 full drill, SEC hardening | 0 | restore کامل تولید-مانند یک‌بار اجرا شود |
| **10** | Website/SEO/Growth | WEB-001 فعال‌سازی دامن، GROWTH-001 | دامن مالک | خروج از preview؛ sitemap زنده؛ GSC hookup |

جزئیات اجرایی PART 1-3: `docs/plans/`؛ PARTهای بعدی placeholder تا رسیدن.
