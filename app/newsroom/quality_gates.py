"""Hard publication quality gates (owner directive 2026-10-04 §Q).

A public Telegram post must be SELF-CONTAINED (understandable without the
source): a named person/institution or a clear country/place scope, a
concrete action, and — where needed — why it matters. Vague subjects
(«وزیر گفت…»), unresolved pronouns, trivia, and routine diplomatic ceremony
are BLOCKED with explicit reasons. 500/day is a ceiling, never a filler
target: low-value content never consumes capacity.

Gate reasons (event verification column on HELD):
  CONTEXT_INCOMPLETE      — dangling subject, no anchor anywhere in the text
  LOW_VALUE_CONTENT       — trivia / viral oddities / lifestyle filler
  LOW_MATERIALITY         — routine diplomatic ceremony without substance
  MATERIALITY_FLOOR       — non-Iran P2/P3 below the higher materiality bar
  DROP_DUPLICATE          — same real event already SENT (near-dup hardening)

Order matters: material/Iran substance exempts from ceremony/trivia; the
anchor scan spans the FULL public text (headline + lead + details), so a
vague headline resolved by body context passes (§1 "unless the preceding
source context reliably resolves the identity").
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- anchors
COUNTRIES_FA = (
    "ایران", "تهران", "آمریکا", "واشنگتن", "اسرائیل", "تل‌آویو", "روس", "روسیه",
    "مسکو", "چین", "پکن", "ترکیه", "آنکارا", "آلمان", "برلین", "فرانسه",
    "پاریس", "بریتانیا", "لندن", "عربستان", "ریاض", "امارات", "ابوظبی",
    "دبی", "قطر", "بحرین", "کویت", "عمان", "مسقط", "یمن", "صنعا", "عراق",
    "بغداد", "سوریه", "دمشق", "لبنان", "بیروت", "فلسطین", "غزه", "اسلام‌آباد",
    "پاکستان", "افغانستان", "کابل", "هند", "دهلی", "ژاپن", "توکیو", "کره",
    "اوکراین", "کی‌یف", "لهستان", "آزربایجان", "باکو", "ارمنستان", "قزاقستان",
    "مصر", "قاهره", "اردن", "امان", "لیبی", "تونس", "الجزیره", "مراکش",
    "مغرب", "سودان", "اتیوپی", "کنیا", "نیجریه", "سومالی", "اریتره",
    "جیبوتی", "کانادا", "مکزیک", "برزیل", "آرژانتین", "استرالیا",
    "سعودی", "یمنی", "عراقی", "سوری", "لبنانی", "فلسطینی", "اماراتی",
    "عمانی", "ایرانی", "آمریکایی", "اسرائیلی", "روسی", "چینی", "ترکیه‌ای",
    "اروپا", "اتحادیه اروپا", "ناتو",
)
ORGS_FA = (
    "سازمان ملل", "شورای امنیت", "آژانس", "اتحادیه اروپا", "ناتو", "اوپک",
    "بریکس", "شانگهای", "سازمان بهداشت جهانی", "صندوق بین‌المللی پول",
    "بانک مرکزی", "دادگاه", "نیروهای مسلح", "ارتش", "سپاه", "انرژی اتمی",
)
MATERIAL_KEYWORDS = (
    "تحریم", "جنگ", "آتش‌بس", "حمله", "موشک", "پهپاد", "ایران", "اسرائیل",
    "آمریکا", "هسته‌ای", "غنی‌سازی", "توافق", "قرارداد سرنوشتساز",
    "نظامی", "امنیتی", "ترور", "تروریست", "کشته", "زخمی", "تلفات",
    "اخراج", "استعفا", "انتخابات", "سرکوب", "اعتراض", "تحول",
    "دلار", "تومان", "نفت", "گاز", "صادرات", "واردات", "تحریم‌ها",
    "دیپلماسی", "مذاکره", "گفت‌وگو", "بن‌بست", "قطع رابطه", "حمله نظامی",
    "بازداشت", "دستگیر", "محاکمه", "اعدام", "جواز", "لغو", "توقف",
    "جزایر", "خلیج فارس", "هرمز", "تحریم جدید",
)
REGIONAL_MARKERS = (
    "اسرائیل", "فلسطین", "غزه", "لبنان", "سوریه", "عراق", "یمن", "حوثی",
    "خلیج فارس", "هرمز", "عربستان", "امارات", "قطر", "بحرین", "کویت",
    "عمان", "اردن", "مصر", "ناتو", "بغداد", "بیروت", "دمشق", "صنعا",
    "تل‌آویو", "الریاض", "جنگ منطقه", "شورای همکاری",
)
VAGUE_ROLES = (
    "وزیر", "رئیس", "سفیر", "نماینده", "مقامات", "فرمانده", "دبیرکل",
    "جانشین", "والی", "استاندار", "قائم‌مقام", "معاون", "خلبان",
)
_PRONOUN_SUBJ = re.compile(
    r"^(?:او|وی|آنها|آن‌ها|این کشور|آن کشور)\b")
_ROLE_VERB = re.compile(
    r"(?:^|\s)(?:وزیر|رئیس|رئیس جمهور|رئیس‌جمهور|رئیس وزیران|نخست وزیر|"
    r"سفیر|نماینده|مقامات|فرمانده|دبیرکل|جانشین)\s*"
    r"(?:از|با|در|برای|گفت|اعلام|امروز|دیروز|ساعتی پیش)?")
_LATIN = re.compile(r"[A-Za-z]{3,}")
_QUOTED = re.compile(r"[«“\"'].{2,60}[»”\"']")

TRIVIA_PATTERNS = (
    re.compile(r"پرنده|پرندگان|حیوانات|فیل‌ها|فیل\b|خرگوش|گربه|سگ‌ها|سگ\b|"
               r"موجود عجیب|دایناسور|نهنگ|دلفین"),
    re.compile(r"شگفت|عجیب‌ترین|باورنکردنی|جالب‌ترین|دانستنی‌ها|آیا می‌دانستید"),
    re.compile(r"سلبریتی|بازیگر出名|ستاره اینستاگرام|وایرال|ویدیوی واکنش"),
    re.compile(r"داماد|عروس|سفرهای .*سفری|دیلیتی|گوشتی‌ترین"),
    re.compile(r"آخرین فیلم|بوکس ?آفیس|پوستر فیلم|تیزر فیلم|فصل جدید سریال"),
)
TRIVIA_ESCAPE = re.compile("|".join(MATERIAL_KEYWORDS[:24]))

# §ABUSE (owner 2026-10-04): unambiguous Persian profanity / mockery /
# gutter-talk words that a serious newsroom NEVER publishes, even quoted in
# a headline. When they ARE the story (verbatim quote in body), the material
# escape below still applies.
ABUSIVE_PATTERNS = (
    re.compile(r"\b(کص|کیر|جنده|قحبه|حروم‌زاده|حرومزاده|بی‌شرف|بیشرف|عوضی|"
               r"فاحشه|شلوار|مرد\s?کون|کون\s?ده|هرمی|الکسی|لات\b|لاقول|"
               r"مغز\s?کم|عقب‌مانده|کره|معلول|حیوان صفت)"),
    re.compile(r"زن\s?(موشلی|کثیف|بدکاره)|مرد\s?(کثیف|پست)|اخوند\s?(کذب|دزد)"),
    re.compile(r"تنکه|حروم|ننه\s?تو|دختت|خواهرت"),
)
ABUSIVE_ESCAPE = re.compile("|".join(MATERIAL_KEYWORDS))


CEREMONY_PATTERNS = (
    re.compile(r"استقبال کرد|استقبال نمود|استقبال به عمل آورد"),
    re.compile(r"اعتبارنامه خود را تقدیم|تقدیم اعتبارنامه"),
    re.compile(r"پیام تبریک|تبریک به مناسبت|پیام تسلیت رسمی متن"),
    re.compile(r"مراسم یادبود|جلسه تشریفاتی|دیدار تودیع"),
    re.compile(r"سفیر جدید"),  # credential-presenting context
    re.compile(r"جشن روز ملی|روز ملی|مناسبت روز ملی"),
)
CEREMONY_ESCAPE = re.compile("|".join(MATERIAL_KEYWORDS))

_NUM = re.compile(r"\d+")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# country en/ar -> fa for the translation sanity check
_COUNTRY_MAP = {
    "iran": "ایران", "tehran": "تهران", "israel": "اسرائیل", "gaza": "غزه",
    "america": "آمریکا", "american": "آمریکایی", "u.s.": "آمریکا", "us": "آمریکا",
    "united states": "آمریکا", "russia": "روس", "china": "چین",
    "turkey": "ترکیه", "turkiye": "ترکیه", "britain": "بریتانیا",
    "uk": "بریتانیا", "france": "فرانسه", "germany": "آلمان",
    "saudi": "عربستان", "emirates": "امارات", "uae": "امارات",
    "qatar": "قطر", "iraq": "عراق", "syria": "سوریه", "lebanon": "لبنان",
    "yemen": "یمن", "oman": "عمان", "egypt": "مصر", "pakistan": "پاکستان",
    "ایران": "ایران", "اسرائیل": "اسرائیل", "امریکا": "آمریکا",
}


def _norm(t: str) -> str:
    return (t or "").replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip()


def _has_anchor(t: str) -> bool:
    """A concrete identity/scope: country, institution, Latin name, or quote."""
    if any(c in t for c in COUNTRIES_FA):
        return True
    if any(o in t for o in ORGS_FA):
        return True
    if _LATIN.search(t) or _QUOTED.search(t):
        return True
    return False


def _has_material(t: str) -> bool:
    return any(k in t for k in MATERIAL_KEYWORDS)


def _is_regional(t: str) -> bool:
    return any(k in t for k in REGIONAL_MARKERS)


def _is_iran(t: str) -> bool:
    return any(k in t for k in ("ایران", "تهران", "ایرانی", "Iran", "Tehran"))


# ------------------------------------------------------------------ gates
def context_incomplete(headline: str, body: str = "") -> bool:
    """§1/§2: a dangling subject that the full public text never resolves."""
    h = _norm(headline)
    full = _norm(headline + " " + body)
    if not h:
        return True
    if _PRONOUN_SUBJ.match(h) and not _has_anchor(full):
        return True
    if _ROLE_VERB.search(h):
        # bare role subject with NO anchor anywhere in the public text
        if not _has_anchor(full):
            return True
    return False


def low_value(headline: str, body: str = "") -> bool:
    """§4: trivia/viral/lifestyle filler — unless material substance present."""
    t = _norm(headline + " " + body)
    if TRIVIA_ESCAPE.search(t):
        return False
    return any(p.search(t) for p in TRIVIA_PATTERNS)


def abusive_content(headline: str, body: str = "") -> bool:
    """§ABUSE: profanity/mockery as content — HOLD regardless of weight."""
    t = _norm(headline + " " + body)
    if ABUSIVE_ESCAPE.search(t):
        return False
    return any(p.search(t) for p in ABUSIVE_PATTERNS)


def routine_ceremony(headline: str, body: str = "") -> bool:
    """§5: protocol-only diplomacy — unless material substance present."""
    t = _norm(headline + " " + body)
    if CEREMONY_ESCAPE.search(t):
        return False
    return any(p.search(t) for p in CEREMONY_PATTERNS)


def materiality_floor(headline: str, body: str = "") -> int:
    """§6/§9: Iran-first — non-Iran/non-regional stories face a higher bar."""
    t = _norm(headline + " " + body)
    if _is_iran(t):
        return 25
    if _is_regional(t):
        return 45
    return 65


def translation_lost_entities(source_text: str, translated: str) -> list[str]:
    """§8: critical identity dropped in translation — numbers and countries."""
    src = _norm(source_text).translate(_FA_DIGITS).lower()
    out = _norm(translated).translate(_FA_DIGITS)
    lost: list[str] = []
    for n in set(_NUM.findall(src)):
        if n not in out:
            lost.append(f"num:{n}")
    for en, fa in _COUNTRY_MAP.items():
        if en in src and fa not in out:
            lost.append(f"country:{fa}")
    return lost


def duplicate_of_recent(db, event_id: int, headline: str,
                        *, hours: int = 48, jaccard_min: float = 0.55
                        ) -> int | None:
    """§10: same real event already SENT under a DIFFERENT event row.

    Requires BOTH high headline token overlap AND a shared canonical source
    identity, so distinct events from the same outlet never merge."""
    import itertools
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)) \
        .isoformat(timespec="seconds")
    rows = db.query(
        "SELECT DISTINCT st.id sid, st.event_id eid, st.headline h FROM stories st"
        " JOIN publications p ON p.story_id = st.id"
        " WHERE p.status='SENT' AND p.created_at>=?", (since,))
    mine = set(re.findall(r"[\u0600-\u06FF]{3,}", _norm(headline)))
    if not mine:
        return None
    my_srcs = _event_sources(db, event_id)
    for r in rows:
        if r["eid"] == event_id:
            continue
        other = set(re.findall(r"[\u0600-\u06FF]{3,}", _norm(r["h"] or "")))
        if not other:
            continue
        j = len(mine & other) / len(mine | other)
        if j >= jaccard_min and my_srcs & _event_sources(db, r["eid"]):
            return r["sid"]
    return None


def _event_sources(db, event_id: int) -> set[str]:
    return {str(r["i"]) for r in db.query(
        "SELECT DISTINCT COALESCE(NULLIF(s.identity,''), s.name) i"
        " FROM event_items ei JOIN raw_items ri ON ri.id = ei.raw_item_id"
        " JOIN sources s ON s.id = ri.source_id WHERE ei.event_id=?",
        (event_id,))}


def publication_quality_gate(db, headline: str, body: str, weight: int,
                             event_id: int = 0) -> str | None:
    """Returns None (publish) or a HOLD reason. §1-§6, §9, §10."""
    if abusive_content(headline, body):
        return "HOLD_ABUSIVE"
    if low_value(headline, body):
        return "LOW_VALUE_CONTENT"
    if routine_ceremony(headline, body):
        return "LOW_MATERIALITY"
    if context_incomplete(headline, body):
        return "CONTEXT_INCOMPLETE"
    if weight < materiality_floor(headline, body):
        return "MATERIALITY_FLOOR"
    if event_id and duplicate_of_recent(db, event_id, headline):
        return "DROP_DUPLICATE"
    return None
