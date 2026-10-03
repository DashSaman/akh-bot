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
