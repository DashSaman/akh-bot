"""PART-5 — Persian translation + free AI router (LANG-003, AI-001/002/003,
ADMIN-002). Fail-closed Persian-only publishing preserved end-to-end.

Fixtures per Part-5 spec §12.
"""
import asyncio
import json

import httpx
import pytest

from app.db.repo import RawItemsRepo, SourcesRepo
from app.integrations.llm.base import LlmError
from app.integrations.llm.router import FreeAiRouter, redact
from app.newsroom.translator import (
    consistency_issues, needs_translation_for, translate_event,
    translate_event_sync,
)
from app.newsroom.v2_pipeline import process_new_items_v2

T0 = "2026-10-03T10:00:00+00:00"


class Brand:
    short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خبر و راستی‌آزمایی"
    telegram_handle = "RastehNews"


class S:
    event_engine_v2_enabled = True
    max_public_story_details = 5
    edit_debounce_seconds = 120
    verifying_deadline_minutes = 60
    standard_max_age_minutes = 180


def _ts(m):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(T0) + timedelta(minutes=m)).isoformat()


def _source(db, name="naya_like", language="ar"):
    sid = SourcesRepo(db).create(name=name, platform="telegram", url=f"t.me/{name}",
                                 status="APPROVED", language=language)
    SourcesRepo(db).update(sid, source_control_state="OWNER_ENABLED")
    return sid


def _item(db, source_id, key, text, minutes=0, language="ar"):
    return RawItemsRepo(db).insert(
        source_id=source_id, platform="telegram", external_key=key, title="",
        text=text, published_at=_ts(minutes), activation_ok=True,
        language=language)


def _router(env, transport):
    return FreeAiRouter(env=env, transport=transport)


def _ok_handler(payload_builder):
    def handler(request: httpx.Request) -> httpx.Response:
        body = payload_builder(request)
        return httpx.Response(200, json=body)
    return handler


def _shape_aware(payload):
    """openai-compat providers get {choices}, gemini gets {candidates}."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "generativelanguage" in str(request.url):
            body = {"candidates": [{"content": {"parts": [{"text": json.dumps(
                payload, ensure_ascii=False)}]}}]}
        else:
            body = {"choices": [{"message": {"content": json.dumps(
                payload, ensure_ascii=False)}}]}
        return httpx.Response(200, json=body)
    return handler


# ---- provider adapters return real-shaped payloads ----

def _openai_body(request):
    return {"choices": [{"message": {"content": json.dumps(
        {"headline": "حمله موشکی به پایگاه در عراق روی داد", "lead": "منابع نظامی گفتند حمله امروز صورت گرفت"},
        ensure_ascii=False)}}]}


# ---- §12: Arabic → valid Persian ----

def test_arabic_to_persian_via_router(db):
    env = {"GROQ_API_KEY": "sk-groq-test-1234567890"}
    transport = httpx.MockTransport(_ok_handler(_openai_body))
    r = _router(env, transport)
    tr = asyncio.run(translate_event(
        r, "هجوم صاروخي", "شن الطيران الحربي استهدف قاعدة عسكرية في العراق اليوم"))
    assert tr and tr["headline"]
    from app.publishing.telegram_bot import is_persian_public_text
    assert is_persian_public_text(tr["headline"] + " " + tr["lead"])


# ---- §12: English → valid Persian / Hebrew → valid Persian ----

def test_english_and_hebrew_translate(db):
    payload = {"headline": "بازار نفت امروز رشد کرد", "lead": "به گزارش رویترز قیمت نفت بالا رفت"}
    transport = httpx.MockTransport(_shape_aware(payload))
    tr = asyncio.run(translate_event(_router({"GEMINI_API_KEY": "gem-key-12345678901234"}, transport),
                                     "Oil market rises", "Reuters: oil prices rose today"))
    assert tr and tr["cache"] in ("MISS", "HIT")
    tr2 = asyncio.run(translate_event(
        _router({"OPENROUTER_API_KEY": "or-key-123456789012345",
                 "AI_PROVIDER_PRIORITY": "openrouter"}, transport),
        "שוק הנפט עלה", "לפי הדיווח מחירי הנפט עלו"))
    assert tr2 and tr2["headline"]


@pytest.mark.parametrize(("source_language", "title", "evidence", "expected_model"), [
    ("en", "Talks continue", "Sources said talks are continuing",
     "groq/openai/gpt-oss-120b"),
    ("ar", "استمرار المحادثات", "قالت مصادر إن المحادثات مستمرة",
     "zai/glm-4.5-flash"),
    ("he", "השיחות נמשכות", "לפי מקורות השיחות נמשכות",
     "rasteh-translation"),
])
def test_translation_routes_model_by_source_language(
        source_language, title, evidence, expected_model):
    """EN/AR get their proven model first; other languages keep the combo."""
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_models.append(json.loads(request.content.decode())["model"])
        payload = {"headline": "گفت‌وگوها ادامه یافت",
                   "lead": "منابع گفتند گفت‌وگوها همچنان ادامه دارد"}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, title, evidence, source_language=source_language))
    assert tr and tr["headline"]
    assert seen_models == [expected_model]


@pytest.mark.parametrize(("source_language", "title", "evidence", "preferred_model"), [
    ("en", "Talks continue", "Sources said talks are continuing",
     "groq/openai/gpt-oss-120b"),
    ("ar", "استمرار المحادثات", "قالت مصادر إن المحادثات مستمرة",
     "zai/glm-4.5-flash"),
])
def test_language_preferred_failure_uses_validated_fallbacks_before_combo(
        source_language, title, evidence, preferred_model):
    """Validated language-specific fallbacks must precede the generic combo."""
    seen_models = []
    success_model = (
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct"
        if source_language == "ar" else "zai/glm-4.5-flash"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model != success_model:
            return httpx.Response(503, text="candidate unavailable")
        payload = {"headline": "گفت‌وگوها ادامه یافت",
                   "lead": "منابع گفتند گفت‌وگوها همچنان ادامه دارد"}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, title, evidence, source_language=source_language))
    assert tr and tr["headline"]
    expected = [
        preferred_model,
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
    ] if source_language == "ar" else [
        preferred_model,
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
        "zai/glm-4.5-flash",
    ]
    assert seen_models == expected


def test_english_validated_fallbacks_failure_still_reaches_existing_combo():
    """Language-aware fallbacks must not remove the existing 9Router combo."""
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model != "rasteh-translation":
            return httpx.Response(503, text="validated candidate unavailable")
        payload = {"headline": "گفت‌وگوها ادامه یافت",
                   "lead": "منابع گفتند گفت‌وگوها همچنان ادامه دارد"}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, "Talks continue", "Sources said talks are continuing",
        source_language="en"))
    assert tr and tr["headline"]
    assert seen_models == [
        "groq/openai/gpt-oss-120b",
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
        "zai/glm-4.5-flash",
        "rasteh-translation",
    ]


def test_existing_combo_failure_falls_back_to_configured_zai_model():
    """If the 9Router combo fails, configured free Z.AI is the last gateway fallback."""
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model != "zai/glm-4.5-flash":
            return httpx.Response(503, text="gateway candidate unavailable")
        payload = {"headline": "گفت‌وگوها ادامه یافت",
                   "lead": "منابع گفتند گفت‌وگوها همچنان ادامه دارد"}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "OPENAI_COMPAT_FALLBACK_MODELS": "zai/glm-4.5-flash",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    result = asyncio.run(r.chat_json(
        system="Translate to Persian JSON", user="Talks continue", max_tokens=100))
    assert result and result["headline"]
    assert seen_models == [
        "rasteh-translation",
        "zai/glm-4.5-flash",
    ]


# ---- §12: no provider → HOLD (V2 integration) ----

def test_no_provider_holds_arabic_event(db, settings):
    s = settings.model_copy(update={"event_engine_v2_enabled": True, "_ai_router": None})
    sid = _source(db)
    _item(db, sid, "a1", "القوات الجوية استهدفت قاعدة عسكرية في العراق اليوم", 0)
    process_new_items_v2(db, Brand(), s)
    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert sends == [], "raw Arabic must never publish without translation"
    assert db.query_one("SELECT status FROM events")["status"] == "HELD"


# ---- §12: provider A fails → B succeeds (failover) ----

def test_failover_a_to_b(db):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "groq" in url:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(
                {"headline": "حمله به پایگاه روی داد", "lead": "منابع گفتند حمله امروز بود"},
                ensure_ascii=False)}]}}]})

    env = {"GROQ_API_KEY": "sk-a-1234567890", "GEMINI_API_KEY": "g-b-12345678901234",
           "AI_PROVIDER_PRIORITY": "groq,gemini"}
    r = _router(env, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(r, "هجوم", "استهدف الطيران قاعدة اليوم"))
    assert tr and tr["headline"], "failover A→B must succeed"
    assert "api.groq.com" in calls[0] and "generativelanguage" in calls[1]
    states = {s["name"]: s for s in r.provider_states()}
    assert states["groq"]["health"] == "DEGRADED"
    assert states["gemini"]["health"] == "HEALTHY"


# ---- §12: all providers fail → HOLD ----

def test_all_fail_returns_none():
    def handler(request):
        return httpx.Response(429, text="rate limited")
    env = {"GROQ_API_KEY": "sk-x-1234567890", "GEMINI_API_KEY": "g-y-12345678901234"}
    r = _router(env, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(r, "x", "استهداف قاعدة"))
    assert tr is None
    states = {s["name"]: s for s in r.provider_states()}
    assert states["groq"]["health"] == "RATE_LIMITED"


# ---- §12: consistency rejects ----

def test_invented_number_rejected():
    assert "NUMBERS_INVENTED" in consistency_issues(
        " في الهجوم قتل 10 جنود", "در این حمله ۱۲ نظامی کشته شدند")


def test_thousands_separator_change_is_same_number():
    """News-style 3,200 and Persian ۳۲۰۰ are the same factual number."""
    assert consistency_issues(
        "The report mentions 3,200 centrifuges",
        "گزارش به ۳۲۰۰ سانتریفیوژ اشاره می‌کند") == []


def test_negation_reversal_rejected():
    assert "NEGATION_REVERSED" in consistency_issues(
        "الجيش لم يؤكد الحادثة", "ارتش حمله را تأیید کرد")


def test_negation_participle_not_false_positive():
    # qwen-style rewrite: negation via participle/past stem — «قرار نداد»،
    # «نشانه نرفته»، prefix «غیر»
    assert consistency_issues(
        "قال مصدر إن الغارة لم تستهدف مدنيين",
        "منبع نظامی: حمله هوایی به حومه بیروت مدنیان را هدف قرار نداد") == []
    assert consistency_issues(
        "قال مصدر إن الغارة لم تستهدف مدنيين",
        "حمله مستقیماً به غیرنظامیان نشانه نرفته است") == []


def test_certainty_escalation_rejected():
    # may/ممکن است → قطعاً
    assert "CERTAINTY_ESCALATED" in consistency_issues(
        "قد يكون الهجوم وقع صباحا", "حمله قطعاً صبح رخ داد")
    assert "CERTAINTY_ESCALATED" in consistency_issues(
        "the attack may have happened", "حمله قطعاً اتفاق افتاد")


def test_consistent_translation_passes():
    assert consistency_issues(
        " قد يكون الهجوم وقع صباحا وقتل 10 جنود",
        "به گزارش منابع، حمله ممکن است صبح رخ داده و ۱۰ نظامی کشته شدند") == []


def test_protected_iranian_name_mistranslation_rejected():
    """Regression: Araghchi must never silently become «عارقی»."""
    issues = consistency_issues(
        "Iranian Foreign Minister Abbas Araghchi spoke in New York",
        "عباس عارقی، وزیر امور خارجه ایران، در نیویورک سخنرانی کرد")
    assert "ENTITY_CHANGED:عراقچی" in issues


def test_protected_iranian_name_arabic_jeem_alias_rejected():
    """Regression: Arabic عراقجي must still require canonical Persian عراقچی."""
    issues = consistency_issues(
        "قال وزير الخارجية الإيراني عباس عراقجي إن المحادثات ستستمر",
        "عباس عراقی‌جی، وزیر امور خارجه ایران، گفت مذاکرات ادامه خواهد یافت")
    assert "ENTITY_CHANGED:عراقچی" in issues


def test_arabic_source_token_leak_rejected():
    """Regression: Arabic definite-article tokens must not leak into Persian copy."""
    issues = consistency_issues(
        "نقص البنزين يضع الحكومة أمام مأزق حقيقي",
        "نقص البنزین دولت را در موقعیتی دشوار قرار داد")
    assert "ARABIC_SOURCE_TOKEN_LEAK:البنزین" in issues


@pytest.mark.parametrize("token", [
    "\u0642\u0648\u0627\u062a",
    "\u0627\u0642\u062a\u062d\u0627\u0645",
    "\u0645\u062f\u0627\u0647\u0645\u0627\u062a",
    "\u0627\u0639\u062a\u0642\u0627\u0644\u0627\u062a",
    "\u062c\u0628\u0647\u0627\u062a",
    "\u0645\u062a\u0637\u0648\u0639\u06cc\u0646",
    "\u0641\u06cc",
])
def test_observed_arabic_newsroom_terms_are_rejected(token):
    source = f"{token} source context"
    generated = f"{token} Persian-looking output"
    assert f"ARABIC_SOURCE_TOKEN_LEAK:{token}" in consistency_issues(source, generated)


def test_newsroom_term_leak_fails_over_to_next_arabic_model():
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model == "zai/glm-4.5-flash":
            payload = {
                "headline": "\u0642\u0648\u0627\u062a Israeli bad output",
                "lead": "\u0645\u062f\u0627\u0647\u0645\u0627\u062a and \u0627\u0639\u062a\u0642\u0627\u0644\u0627\u062a bad output",
            }
        else:
            payload = {
                "headline": "نیروهای اسرائیلی خانه یک زندانی فلسطینی را منفجر کردند",
                "lead": "نیروهای اسرائیلی پس از یورش به منطقه، چند نفر را بازداشت کردند.",
            }
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r,
        "\u0642\u0648\u0627\u062a source",
        "\u0642\u0648\u0627\u062a \u0648 \u0645\u062f\u0627\u0647\u0645\u0627\u062a \u0648 \u0627\u0639\u062a\u0642\u0627\u0644\u0627\u062a",
        source_language="ar"))
    assert tr and tr["headline"].startswith("نیروهای اسرائیلی")
    assert seen_models[:2] == [
        "zai/glm-4.5-flash",
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
    ]


def test_malformed_persian_typo_rejected():
    """Regression: a Persian-looking AI typo must not pass the language gate."""
    issues = consistency_issues(
        "الجمهور السعودي يقتحم مقصورات الجماهير الاماراتي",
        "هوادع سعودی به تماشاگران اماراتی حمله کردند")
    assert "PERSIAN_ORTHOGRAPHY:هوادع" in issues


def test_arabic_plural_leak_is_rejected():
    """Regression: Arabic newsroom morphology must not masquerade as Persian."""
    issues = consistency_issues(
        "إصابات مباشرة لمطار عدن في جنوب اليمن",
        "اصابات مستقیم به فرودگاه عدن در جنوب یمن")
    assert "PERSIAN_ORTHOGRAPHY:اصابات" in issues


def test_known_malformed_farsi_and_literal_arabic_calque_rejected():
    issues = consistency_issues(
        "على إيران أن تنهي هذا الملف ونقص البنزين يفاقم الأزمة",
        "ترامپ: باید با ایران خاتیه دهیم؛ نقص بنزین بحران را تشدید کرد")
    assert "PERSIAN_ORTHOGRAPHY:خاتیه" in issues
    assert "PERSIAN_CALQUE:نقص_بنزین" in issues


def test_observed_arabic_hybrid_word_is_rejected():
    issues = consistency_issues(
        "\u062d\u0644\u0641\u0627\u0624\u0647\u0645",
        "\u062d\u0644\u0641\u0627\u06cc\u0634\u0627\u0646 \u062f\u0631 \u06cc\u0645\u0646 \u062d\u0636\u0648\u0631 \u062f\u0627\u0631\u0646\u062f")
    assert any(x.startswith("PERSIAN_ORTHOGRAPHY:") for x in issues)


def test_tadnis_alaqsa_must_not_become_production():
    issues = consistency_issues(
        "\u0625\u0646 \u062a\u062f\u0646\u064a\u0633 \u0627\u0644\u0623\u0642\u0635\u0649 \u064a\u0633\u062a\u0635\u0631\u062e \u0627\u0644\u062c\u0645\u064a\u0639",
        "\u062a\u0648\u0644\u06cc\u062f \u0645\u0633\u062c\u062f \u0627\u0644\u0627\u0642\u0635\u06cc \u0647\u0645\u0647 \u0631\u0627 \u0628\u0647 \u0641\u0631\u06cc\u0627\u062f \u0645\u06cc\u200c\u06a9\u0634\u0627\u0646\u062f")
    assert "SEMANTIC_MISTRANSLATION:TADNIS_ALAQSA" in issues


def test_arabic_plural_leak_fails_over_to_clean_translation():
    """The exact production regression must fail over to a clean provider output."""
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model == "zai/glm-4.5-flash":
            payload = {"headline": "اصابات مستقیم به فرودگاه عدن در جنوب یمن",
                       "lead": "اصابات مستقیم در فرودگاه عدن گزارش شد."}
        else:
            payload = {"headline": "اصابت مستقیم به فرودگاه عدن در جنوب یمن",
                       "lead": "فرودگاه عدن در جنوب یمن هدف اصابت مستقیم قرار گرفت."}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, "إصابات مباشرة لمطار عدن",
        "إصابات مباشرة لمطار عدن في جنوب اليمن",
        source_language="ar"))
    assert tr and tr["headline"] == "اصابت مستقیم به فرودگاه عدن در جنوب یمن"
    assert seen_models[:2] == [
        "zai/glm-4.5-flash",
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
    ]


def test_arabic_typo_rejection_tries_next_validated_model():
    """The exact production «هوادع» regression must fail over to a clean model."""
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model == "zai/glm-4.5-flash":
            payload = {"headline": "هوادع سعودی به تماشاگران اماراتی حمله کردند",
                       "lead": "هوادع سعودی به جایگاه تماشاگران یورش بردند."}
        else:
            payload = {"headline": "هواداران سعودی به تماشاگران اماراتی حمله کردند",
                       "lead": "هواداران سعودی به جایگاه تماشاگران یورش بردند."}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, "الجمهور السعودي",
        "الجمهور السعودي يقتحم مقصورات الجماهير الاماراتي",
        source_language="ar"))
    assert tr and tr["headline"] == "هواداران سعودی به تماشاگران اماراتی حمله کردند"
    assert seen_models[:2] == [
        "zai/glm-4.5-flash",
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
    ]


def test_translated_long_headline_is_not_cut_mid_word():
    """A provider ignoring the 110-char prompt must still return a complete headline."""
    long_headline = (
        "جمال خدارحمی و هیرش ناوگران، دو فعال مدنی اهل سنندج، در دو پرونده جداگانه "
        "توسط دستگاه قضایی جمهوری اسلامی ایران به حبس تعلیقی و جزای نقدی محکوم شدند."
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = {"headline": long_headline,
                   "lead": "این دو فعال مدنی به حبس تعلیقی و جزای نقدی محکوم شدند."}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, "حكم قضائي", "صدر حكم بالسجن المعلق والغرامة المالية",
        source_language="ar"))
    assert tr and tr["headline"] == long_headline


def test_cjk_script_leak_rejected():
    """Regression: Han/CJK glyphs must never survive inside Persian news copy."""
    issues = consistency_issues(
        "نجحوا في طرد المحتلين ليكون البلد مستقلاً عزيزاً",
        "شیخ نعیم قاسم: عراق با驱逐 اشغالگران مستقل شد")
    assert "FOREIGN_SCRIPT_LEAK:CJK" in issues


def test_cjk_quality_rejection_tries_next_validated_model():
    """The exact production class of CJK leak must fail over to a clean model."""
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model == "zai/glm-4.5-flash":
            payload = {"headline": "شیخ نعیم قاسم: عراق با驱逐 اشغالگران مستقل شد",
                       "lead": "عراق با موفقیت اشغالگران را از کشور بیرون راند."}
        else:
            payload = {"headline": "شیخ نعیم قاسم: عراق با اخراج اشغالگران مستقل شد",
                       "lead": "عراق با موفقیت اشغالگران را از کشور بیرون راند."}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, "امين عام حزب الله الشيخ نعيم قاسم",
        "نجحوا في طرد المحتلين ليكون البلد مستقلاً عزيزاً",
        source_language="ar"))
    assert tr and tr["headline"] == "شیخ نعیم قاسم: عراق با اخراج اشغالگران مستقل شد"
    assert seen_models[:2] == [
        "zai/glm-4.5-flash",
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
    ]


def test_translation_quality_rejection_tries_next_validated_model():
    """A fluent-but-bad model answer must fail over, not be published or merely held."""
    seen_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content.decode())["model"]
        seen_models.append(model)
        if model == "zai/glm-4.5-flash":
            payload = {"headline": "نقص البنزین دولت را تحت فشار گذاشت",
                       "lead": "نقص البنزین دولت را با مشکل روبه‌رو کرده است"}
        else:
            payload = {"headline": "کمبود بنزین دولت را تحت فشار گذاشت",
                       "lead": "کمبود بنزین دولت را با مشکل روبه‌رو کرده است"}
        return httpx.Response(200, json={"choices": [{"message": {"content":
            json.dumps(payload, ensure_ascii=False)}}]})

    r = _router({
        "OPENAI_COMPAT_API_KEY": "sk-test-1234567890",
        "OPENAI_COMPAT_BASE_URL": "http://nine-router.test/v1",
        "OPENAI_COMPAT_MODEL": "rasteh-translation",
        "AI_PROVIDER_PRIORITY": "openai_compat",
    }, httpx.MockTransport(handler))
    tr = asyncio.run(translate_event(
        r, "أزمة البنزين", "نقص البنزين يضع الحكومة أمام مأزق حقيقي",
        source_language="ar"))
    assert tr and tr["headline"] == "کمبود بنزین دولت را تحت فشار گذاشت"
    assert seen_models[:2] == [
        "zai/glm-4.5-flash",
        "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
    ]


def test_translation_consistency_rejects_lost_country_entity():
    issues = consistency_issues(
        "Iran announced a new sanctions response",
        "پاسخ تازه‌ای به تحریم‌ها اعلام شد")
    assert "ENTITY_LOST:country:ایران" in issues


# ---- §12: source language ar forces translation (heuristic-proof) ----

def test_source_language_arabic_forces_translation():
    # Persian-looking text WITH Persian footer additions — configured ar wins
    text = "متن به ظاهر فارسی — راسته؟ | خبر و راستی‌آزمایی 🆔 @RastehNews"
    assert needs_translation_for("ar", text) is True
    # Persian source stays direct
    assert needs_translation_for("fa", "قیمت دلار امروز در بازار آزاد بالا رفت") is False


def test_foreign_text_with_persian_footer_cannot_bypass_gate():
    """Content-level check: an Arabic body with a Persian footer is NOT Persian."""
    from app.publishing.telegram_bot import is_persian_public_text
    arabic_with_footer = ("القوات الجوية استهدفت قاعدة عسكرية\n\n— راسته؟ | خبر و راستی‌آزمایی\n🆔 @RastehNews")
    assert is_persian_public_text(arabic_with_footer) is False


# ---- §12: cache hit avoids second provider call ----

def test_cache_hit_avoids_provider_call(db):
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=_openai_body(request))
    r = _router({"GROQ_API_KEY": "sk-c-1234567890"}, httpx.MockTransport(handler))
    t1 = asyncio.run(translate_event(r, "هجوم", "استهداف قاعدة امروز", db=db, source_language="ar"))
    t2 = asyncio.run(translate_event(r, "هجوم", "استهداف قاعدة امروز", db=db, source_language="ar"))
    assert t1["cache"] == "MISS" and t2["cache"] == "HIT"
    assert len(calls) == 1, "cached translation must not re-call the provider"
    # failures never cached: different content still calls
    t3 = asyncio.run(translate_event(r, "هجوم آخر", "استهداف مطار امروز", db=db, source_language="ar"))
    assert len(calls) == 2


# ---- §12: secrets never appear in admin/log output ----

def test_secrets_never_leak_in_state_or_errors():
    env = {"GROQ_API_KEY": "sk-supersecret-987654321"}
    def handler(request):
        return httpx.Response(500, text="leak attempt sk-supersecret-987654321")
    r = _router(env, httpx.MockTransport(handler))
    asyncio.run(r.chat_json(system="x", user="y", max_tokens=5))
    states = r.provider_states()
    blob = json.dumps(states, ensure_ascii=False)
    assert "supersecret" not in blob, "secret value must never appear"
    assert "987654321" not in blob
    assert redact("key=abc12345678 secret") == "key=[REDACTED] secret"


def test_router_config_consistency_no_env_reads():
    """Provider calls must not read os.environ at call time (config snapshot)."""
    import inspect
    from app.integrations.llm import router as router_mod
    src = inspect.getsource(router_mod.FreeAiRouter._call)
    assert "os.environ" not in src, "_call must use resolved state only"


# ---- §12: V2 translated story invariants (one Event/Story, SEND-EDIT) ----

def test_v2_translated_story_full_invariants(db, settings):
    router = _router({"GROQ_API_KEY": "sk-v2-1234567890"},
                     httpx.MockTransport(_ok_handler(_openai_body)))
    s = settings.model_copy(update={"event_engine_v2_enabled": True, "_ai_router": router})
    sid = _source(db)
    _item(db, sid, "v1", "القوات الجوية استهدفت قاعدة عسكرية في العراق اليوم", 0)
    _item(db, sid, "v2", "القوات الجوية استهدفت قاعدة عسكرية في العراق اليوم", 2)
    process_new_items_v2(db, Brand(), s)

    events = db.query("SELECT * FROM events")
    stories = db.query("SELECT * FROM stories")
    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert len(events) == 1, "translated wire copies share ONE event"
    assert len(stories) == 1 and len(sends) == 1, "ONE story, ONE send"
    payload = json.loads(sends[0]["payload_json"])
    from app.publishing.telegram_bot import is_persian_public_text
    assert is_persian_public_text(payload["text"]), "public text Persian only"
    assert "منبع:" in payload["text"], "source attribution preserved"
    # a later material Arabic update must EDIT, never re-SEND
    from app.db.repo import PublicationsRepo
    story = stories[0]
    pub = db.query_one("SELECT * FROM publications WHERE story_id=? ORDER BY id DESC LIMIT 1", (story["id"],))
    PublicationsRepo(db).mark(pub["id"], "SENT", remote_id="777")
    db.execute("UPDATE publications SET chat_id=? WHERE id=?", ("-1004459746525", pub["id"]))
    db.execute("UPDATE claims SET material=0")
    _item(db, sid, "v3", "القوات الجوية استهدفت قاعدة عسكرية في العراق اليوم وقتل 10 جنود", 10)
    process_new_items_v2(db, Brand(), s)
    sends2 = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert len(sends2) == 1, "SEND/EDIT invariant holds for translated stories"


# ---- ADMIN-002: /admin/ai page (auth-gated, no secrets) ----

def test_admin_ai_page_requires_login(client):
    resp = client.get("/admin/ai", follow_redirects=False)
    assert resp.status_code in (303, 401)


def test_admin_ai_page_renders_state(admin_client):
    resp = admin_client.get("/admin/ai")
    assert resp.status_code == 200
    assert "ZERO_COST_MODE" in resp.text
    assert "groq" in resp.text  # provider order visible
    assert "NOT_CONFIGURED" in resp.text  # unconfigured providers exposed
    # no key material anywhere on the page
    assert "sk-" not in resp.text
    assert "API_KEY" not in resp.text


def test_admin_ai_toggle_persists(admin_client, db):
    csrf = admin_client.cookies.get("akh_csrf", "")
    resp = admin_client.post("/admin/ai/provider",
                             data={"csrf": csrf, "action": "disable", "name": "groq"},
                             follow_redirects=False)
    assert resp.status_code == 303
    from app.db.repo import SettingsRepo
    assert "groq" in SettingsRepo(admin_client.app.state.db).get("ai_disabled")
