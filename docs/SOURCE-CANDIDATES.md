# SOURCE CANDIDATES / نامزدهای منبع (بilingual)

# فارسی

**این‌ها فقط پیشنهاد هستند. تأیید نهایی با مالک است — هیچ‌کدام به‌صورت خودکار APPROVED نمی‌شوند.**

**اصل اعتماد مبتنی بر شواهد است نه گرایش سیاسی:** مدرک اصلی در برابر ثانویه، دسترسی مستقیم به رویداد/سند، استقلال خاستگاه، سابقه دقت و اصلاحیه، کیفیت انتساب، هم‌تأییدی و زمان/تبارِ داده. وابستگی سیاسی/دولتی/مخالف فقط به‌عنوان «متادیتای خنثی تبار» ثبت می‌شود و به‌تنهایی اعتماد را کم/زیاد نمی‌کند.

## OFFICIAL_PRIMARY — خاستگاه رسمی (منطبق با «مدرک اصلی» در راستی‌آزمایی)
| نام | پلتفرم | زبان | چرا مفید | نقش | مدرک اصلی؟ | احتیاط |
|---|---|---|---|---|---|---|
| سخنگوی وزارت خارجه | وب/X | fa | اظهارنظر رسمی قابل استناد | خاستگاه اعلام رسمی | بله | منبع رسمی دولتی (متادیتای خنثی)؛ همیشه با انتساب |
| ISPR (ارتش پاکستان) | وب/X | en | اعلامیه‌های نظامی مستقیم | تأیید/رد رویداد نظامی | بله | روایت رسمی یک‌سویه؛ نیاز به منبع مستقل برای تأیید |
| IAEA Press | RSS/X | en | داده فنی هسته‌ای | مدرک فنی | بله | — |
| United Nations Press | RSS | en/ar | بیانیه‌های بین‌المللی | مدرک رسمی | بله | — |

## MAJOR_NEWSROOM — رسانه‌های بزرگ (تأیید متقابل، نه لزوماً مستقل از هم)
| نام | پلتفرم | زبان | چرا مفید | نقش | مدرک اصلی؟ | احتیاط |
|---|---|---|---|---|---|---|
| Reuters | RSS | en | سرعت/دقت، منبع بازنشر بسیاری | لنگر تأیید متقابل | خیر (ثانویه) | منشأ بازنشر گسترده → lineage_key مشترک خاستگاه‌ها را یکی می‌کند |
| AP News | RSS | en | استاندارد ویرایشی بالا | تأیید متقابل | خیر | — |
| AFP | RSS | fr/en | پوشش جهانی | تأیید متقابل | خیر | — |
| BBC Persian | RSS ✅(تست فنی) | fa | گردش بالا فارسی | تأیید متقابل | خیر | وضعیت فعلی: فقط ورودی فنی تست (verification_allowed=0)؛ تأیید تحریریه با مالک |
| Al Jazeera Arabic | RSS | ar | پوشش خاورمیانه | تأیید متقابل عربی | خیر | — |
| Iran International | RSS | fa | پوشش ایران | منبع مخالف‌سوی حکومت | خیر | خبرگزاری مستقل (روایت منتقد/بیرونی — متادیتای خنثی)؛ ادعاهای حساس نیازمند تأیید متقابل |
| BBC Arabic | RSS | ar | پوشش عربی | تأیید متقابل | خیر | — |

## JOURNALIST — خبرنگاران شناخته‌شده (حساس به تأیید هویت)
| نام | پلتفرم | زبان | چرا مفید | نقش | مدرک اصلی؟ | احتیاط |
|---|---|---|---|---|---|---|
| خبرنگاران محلی میدانی (به انتخاب مالک) | X/تلگرام | fa | رصد زودهنگام | سیگنال اولیه | خیر | دسترسی میدانی مستقیم اما تکی؛ هرگز مبنای تنهایی ادعای پرخطر |
| گزارشگران بین‌المللی مستقر (به انتخاب مالک) | X | en | تأیید سریع از محل | تأیید متقابل | خیر | حساب تقلبی؟ هویت باید بازبینی شود |

## LOCAL_SOURCE — منابع محلی
| نام | پلتفرم | زبان | چرا مفید | نقش | مدرک اصلی؟ | احتیاط |
|---|---|---|---|---|---|---|
| خبرگزاری‌های داخلی (IRNA/ISNA/Tasnim) | RSS | fa | روایت رسمی داخلی | سند موضع رسمی | خیر (روایت رسمی) | رسانه وابسته به دولت (متادیتای خنثی)؛ با انتساب شفاف |
| استانی‌ها (به انتخاب مالک) | RSS | fa | جزئیات محلی | سیگنال محلی | خیر | دقت متغیر؛ سابقه اصلاحیه‌ها ملاک ارزیابی است |

## AGGREGATOR — تجمیع‌کننده‌ها (هیچ‌وقت شمارش استقلال افزایش نمی‌دهند)
| نام | پلتفرم | زبان | چرا مفید | نقش | مدرک اصلی؟ | احتیاط |
|---|---|---|---|---|---|---|
| کانال‌های تجمیع تلگرامی (به انتخاب مالک) | تلگرام | fa | کشف سریع | فقط کشف؛ lineage_key فرومی‌ریزد به مبدأ | خیر | هرگز «تأیید» حساب نمی‌شود |

**قاعده کلیدی:** `report_count ≠ independent_count` — تجمیع‌کننده‌ها با forward/لینک مبدأ به همان خاستگاه فرومی‌ریزند.

---

# English

**Suggestions ONLY. The owner approves; nothing here is auto-APPROVED.**

**Trust is EVIDENCE-based, never ideology-based:** primary vs secondary evidence, direct access, source independence, historical correction/accuracy record, attribution quality, corroboration, timestamps/provenance. Political/state/opposition affiliation is stored only as neutral provenance metadata and never by itself raises or lowers factual trust.

- **OFFICIAL_PRIMARY** (primary evidence): ministry spokespersons, ISPR, IAEA Press,
  UN Press — official statements; suitable as primary evidence, always attributed.
- **MAJOR_NEWSROOM** (corroboration): Reuters, AP, AFP, BBC Persian (technical test
  only so far), Al Jazeera Arabic, BBC Arabic, Iran International — corroboration
  anchors, NOT primary evidence; beware shared lineage (many Telegram channels copy
  Reuters — lineage_key collapses them to one origin).
- **JOURNALIST**: field reporters (owner-selected) — early signals; identity must be
  verified; never the basis for high-risk claims alone.
- **LOCAL_SOURCE**: domestic agencies (IRNA/ISNA/Tasnim) — documented official
  position with clear attribution bias; provincial outlets for local detail.
- **AGGREGATOR**: Telegram aggregators — discovery only; they NEVER increase the
  independent-origin count (forward/link lineage collapses to origin).

Rule: `report_count ≠ independent_count`.
