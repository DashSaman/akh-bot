# فارسی

# سئو / GEO / AEO (درس‌های MyTel — الزامات پروژه)

1. **یک گراف اسکیمای واحد:** فقط `app/seo/seo.py` JSON-LD تولید می‌کند؛ هیچ خروجی اسکیمای دیگری در قالب‌ها نیست. تکرار JSON-LD ممنوع.
2. **ناشر درست:** `NewsMediaOrganization` با `@id` پایدار؛ نویسنده = همان سازمان تحریریه (هیچ Person جعلی/نشت هویت).
3. **یک رویداد = یک URL اصلی:** به‌روزرسانی‌ها خط زمانی/واقعیت‌ها را گسترش می‌دهند؛ ۱۵ صفحه تکراری برای ۱۵ به‌روزرسانی ممنوع.
4. **صفحه خبر با ساختار ثابت:** خلاصه / چه اتفاقی افتاده / تأییدشده / تأییدنشده / خط زمانی / منابع / بروزرسانی‌ها / اصلاحیه‌ها — هم برای مخاطب هم برای موتورهای Generative.
5. **دروازه کیفیت (تست رگرسیون خودکار):** HTTP 200، عنوان یکتا، متا، یک H1، canonical خودسازگار، robots درست، OG/X-card، اسکیمای معتبر.
6. **preview mode تا تعیین برند:** بدون `PUBLIC_BASE_URL`، robots کل را Disallow می‌کند و canonical نمی‌گذارد — این عمدی است تا محتوای بدون دامنه ایندکس نشود؛ بعد از اتصال دامنه خودکار برمی‌گردد.
7. **sitemap.xml + news-sitemap.xml (فقط ۴۸ ساعت اخیر) + RSS اولویت خودمان + robots آگاهانه.**
8. بدون آنتی‌کلمه‌کلیدی، بدون تولید انبوه صفحه بی‌ارزش (ترجمه/مترادف/ادغام RSS)؛ ارزش صفحه از ترکیب چندمنبعی + تفکیک تأیید/عدم‌تأیید + تبار منابع می‌آید.
9. بدون تعقیب امتیاز ۱۰۰/۱۰۰ ابزارهای سئو؛ اولویت: خزش‌پذیری، نیت، مفیدبودن، ساختار.

# English

# SEO / GEO / AEO (MyTel lessons as project requirements)

1. **One authoritative schema graph** — only `app/seo/seo.py` emits JSON-LD.
2. **Correct publisher entity** — NewsMediaOrganization with stable `@id`; author is the
   same organization (no fake Person, no identity leak).
3. **One event = one master URL** — updates extend timeline/facts, never duplicate pages.
4. **Fixed story structure** — summary / what happened / confirmed / unconfirmed /
   timeline / sources / updates / corrections (human- and AI-retrieval friendly).
5. **Automated quality gate** (SEO regression test): 200, unique title, meta, single H1,
   self-consistent canonical, correct robots, OG/X cards, valid schema.
6. **Preview mode until brand decided:** no `PUBLIC_BASE_URL` → robots Disallow-all and
   no canonical (intentional; auto-reverts when the domain is wired).
7. sitemap.xml + news-sitemap.xml (48h freshness) + first-party RSS + intentional robots.
8. No keyword stuffing, no scaled low-value pages; value comes from multi-source
   synthesis + verified/unverified separation + provenance.
9. No chasing tool scores; crawlability/intent/usefulness/structure first.
