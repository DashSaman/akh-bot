# ADMIN-PANEL / پنل مدیریت (بilingual)

## ورود — `/admin/login`
| | فارسی | English |
|---|---|---|
| هدف | ورود امن مدیر | secure admin login |
| ریسک | قفل ۱۵ دقیقه بعد از ۵ خطا | 15-min lockout after 5 failures |
| دسترسی | نشست امضاشده HMAC، ۱۲ ساعت | signed HMAC session, 12h TTL |

## داشبورد — `/admin`
آمار (منابع/مواد/رویدادها/خبرها/انتشارها/کارهای شکست‌خورده)، وضعیت کلید توقف، وضعیت اتصال سرویس‌ها (LLM/تلگرام)، آخرین رویدادها و کارها.
Stats, kill-switch state, integration wiring state, recent events/jobs.

## منابع — `/admin/sources`
- افزودن منبع (نام/پلتفرم/نشانی/زبان/دسته/نوع/وضعیت/فاصله نظرسنجی)
- تغییر وضعیت: **APPROVED** (زمان فعال‌سازی ثبت می‌شود ← حفاظت بازگشتی) / DISCOVERED / BLOCKED
- فعال/غیرفعال، سلامت، آخرین خطا
- **اثر:** تأیید منبع شروع جمع‌آوری را روشن می‌کند؛ محتوای قبل از فعال‌سازی فقط ذخیره می‌شود.
- **ریسک:** تأیید منبع غیرمعتبر کیفیت کل تحریریه را تهدید می‌کند — با احتیاط.
Add sources; status transitions (approval stamps activation time → backfill
protection); enable/disable; health & last error. Risk: approving an untrusted
source degrades the whole newsroom.

## مواد خام — `/admin/items`
شواهد اصلی تغییرناپذیر؛ ستون «واجد شرایط انتشار» نشان می‌دهد آیتم پس از فعال‌سازی آمده یا نه (backfill).
Immutable raw evidence; publish-eligibility column shows backfill state.

## رویدادها — `/admin/events`, `/admin/events/{id}`
گزارش‌ها در برابر خاستگاه مستقل؛ ادعاها با حالت/ریسک؛ خبر تولیدشده. `HELD` یعنی گیت پرخطر عمداً نگه داشته.
Reports vs independent origins; claims with states/risk; generated story. HELD =
intentional high-risk gate.

## انتشارها — `/admin/publications`
دفتر کامل: وضعیت/تلاش/شناسه پیام distant/خطا — مبنا برای اطمینان از عدم پست تکراری.
Full ledger: status/attempts/remote id/error — the no-duplicates guarantee.

## تنظیمات — `/admin/settings`
- توقف کل انتشار (جمع‌آوری ادامه دارد) / توقف تک‌پلتفرمی
- وضعیت برند (UNDECIDED تا تأیید مالک)
Global + per-platform pause (collection continues); brand status display.

**Permissions:** all admin routes require a valid session; POSTs require the CSRF
cookie+field. Admin URL is reachable only through the SSH tunnel (no public bind).
