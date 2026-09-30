# فارسی

# راستی‌آزمایی

## تفکیک ادعاها
هر رویداد به ادعاهای اتمی شکسته می‌شود (چه اتفاقی/کجا/کی/چند نفر/چه کسی). GLM ادعاها را استخراج می‌کند؛ در نبود GLM یک خط مبنا بر پایه قواعد ساخته می‌شود (محافظه‌کارانه UNVERIFIED) تا خط هرگز متوقف نشود.

## حالت‌های ادعا
`CONFIRMED / CORROBORATED / SINGLE_SOURCE / CONFLICTING / UNVERIFIED / RETRACTED`

## گیت‌های سخت (قواعد + شواهد، نه فقط عدد اعتماد)
- تناقض (ارقام متفاوت برای یک واقعیت) → `CONFLICTING` → انتشار فقط با انتساب عدم‌قطعیت یا توقف (HELD).
- ادعای پرخطر (تلفات/حمله/بازداشت/مسئولیت/جنگ/...) با یک خاستگاه → `SINGLE_SOURCE` → هرگز تیتر قطعی نمی‌شود.
- ≥۲ خاستگاه مستقل → `CORROBORATED`. `CONFIRMED` برای مدرک رسمی/اصلی رزرو است.

## استقلال منابع (خط لوله تبار)
بازنشرها با `lineage_key` (فوروارد تلگرام، دامنه مبدأ لینک) فرومی‌ریزند:
`report_count=۵` و `independent_count=۱` برای ۵ کپی یک خبر — تعداد گزارش ≠ تعداد تأیید.

## امتیازهای جدا
راستی‌آزمایی، اهمیت و سرعت جدا نگه داشته می‌شوند؛ وایرالی‌شدن هیچ‌وقت دلیل درستی نیست.

# English

# Verification

## Atomic claims
Events decompose into atomic claims (what/where/when/how many/who). GLM extracts them;
a conservative rules-based baseline (UNVERIFIED) exists so the pipeline never stalls
when the LLM is unavailable.

## Claim states
`CONFIRMED / CORROBORATED / SINGLE_SOURCE / CONFLICTING / UNVERIFIED / RETRACTED`

## Hard gates (rules + evidence, never a bare confidence number)
- Contradiction (diverging figures) → `CONFLICTING` → publish only attributed
  uncertainty, or HOLD.
- High-risk claim (casualties/attacks/arrests/responsibility/war/...) with a single
  origin → `SINGLE_SOURCE` → never a definitive headline.
- ≥2 independent origins → `CORROBORATED`; `CONFIRMED` reserved for primary/official evidence.

## Independence (lineage)
Reposts collapse via `lineage_key` (Telegram forward origin, canonical link domain):
five copies of one story = `report_count 5`, `independent_count 1`.
Report count is never confirmation count.

## Separate scores
Verification, importance and velocity stay separate; virality is never proof.
