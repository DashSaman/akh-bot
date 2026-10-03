"""URGENT production-fix regressions (§3/§4/§5/§6/§10/§8)."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.db.repo import PublicationsRepo, RawItemsRepo, SourcesRepo, utcnow
from app.jobs.runner import Throttled, make_send_handler, make_edit_handler
from app.newsroom.pipeline import _resolve_deadlines
from app.newsroom.v2_pipeline import process_new_items_v2
from app.publishing.telegram_bot import public_body_is_substantive

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
    max_posts_per_hour = 12
    max_posts_per_day = 120
    max_provisional_posts_per_hour = 6
    max_confirmed_posts_per_hour = 12


# ---------------- §5 final public body gate ----------------

def test_gate_screenshot_source_only_rejected():
    """Owner screenshot: only «منبع: یاشار» + footer → MUST reject."""
    body = "منبع: یاشار" + chr(10) + chr(10) + \
           "— راسته؟ | خبر و راستی‌آزمایی" + chr(10) + "🆔 @RastehNews"
    assert public_body_is_substantive(body) is False


def test_gate_generic_deadline_text_rejected():
    body = ("⚠️ بررسی این موضوع در منابع در دسترس، تا این لحظه به تأیید مستقل نرسیده است. "
            "پایش ادامه دارد و در صورت تأیید، همین پست به‌روزرسانی می‌شود.")
    assert public_body_is_substantive(body) is False


def test_gate_speaker_prefix_only_rejected():
    assert public_body_is_substantive("**ترامپ:**" + chr(10) + chr(10) +
                                      "— راسته؟ | خبر و راستی‌آزمایی") is False


def test_gate_real_news_and_caution_appended_accepted():
    real = ("🔴 🎖 **ارتش آمریکا در حال آماده‌سازی برای افزایش گسترده حضور نظامی در خاورمیانه است**"
            + chr(10) + chr(10) + "منبع: یاشار" + chr(10) + chr(10)
            + "— راسته؟ | خبر و راستی‌آزمایی" + chr(10) + "🆔 @RastehNews")
    assert public_body_is_substantive(real) is True
    with_caution = ("**نفتکش «اور وینست» هنگام ورود به تنگه هرمز ظاهراً اسکورت شده بود**"
                    + chr(10) + chr(10) + "⚠️ این ادعا تا این لحظه به تأیید مستقل نرسیده است."
                    + chr(10) + chr(10) + "— راسته؟ | خبر و راستی‌آزمایی")
    assert public_body_is_substantive(with_caution) is True


# ---------------- §4 deadline behavior ----------------

def _mk_story(db, slug, lifecycle="PROVISIONAL", published=False, minutes_old=90):
    db.execute(
        "INSERT INTO events(id,title,category,status,first_seen_at,last_seen_at)"
        " VALUES((SELECT COALESCE(MAX(id),0)+1 FROM events),'t','general','NEW',"
        " datetime('now'),datetime('now'))")
    eid = db.query_one("SELECT MAX(id) AS m FROM events")["m"]
    db.execute(
        "INSERT INTO stories(event_id,slug,headline,lead,draft_json,version,status,"
        " lifecycle,created_at,updated_at) VALUES(?,?,?,?,?,?, 'PUBLISHED',?,?,datetime('now'))",
        (eid, slug, f"تیتر واقعی خبر {slug}", "لید",
         json.dumps({"platform_variants": {"telegram": f"**تیتر واقعی خبر {slug}**"
          + chr(10) + chr(10) + "جزییات واقعی و کامل خبر در اینجا قرار دارد."
          + chr(10) + chr(10) + "منبع: یاشار" + chr(10) + chr(10)
          + "— راسته؟ | خبر و راستی‌آزمایی" + chr(10) + "🆔 @RastehNews"}},
          ensure_ascii=False), 1, lifecycle,
         (datetime.now(timezone.utc) - timedelta(minutes=minutes_old)).isoformat()))
    sid = db.query_one("SELECT MAX(id) AS m FROM stories")["m"]
    if published:
        pid = PublicationsRepo(db).upsert(sid, "telegram", "ph-" + slug, 1)
        PublicationsRepo(db).mark(pid, "SENT", remote_id="9" + str(sid))
        db.execute("UPDATE publications SET chat_id=? WHERE id=?", ("-1004459746525", pid))
    return sid


def test_deadline_sent_story_gets_caution_edit_not_generic(db, settings):
    sid = _mk_story(db, "a1", published=True)
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خبر"; telegram_handle = "RastehNews"
    n = _resolve_deadlines(db, S(), B())
    assert n == 1
    edits = db.query("SELECT * FROM jobs WHERE job_type='publish_edit'")
    assert len(edits) == 1, "deadline update must use publish_edit"
    payload = json.loads(edits[0]["payload_json"])
    text = payload["text"]
    # original headline preserved + caution appended + exact footer intact
    assert "تیتر واقعی خبر" in text
    assert "تأیید مستقل نرسیده" in text
    assert "🆔 @RastehNews" in text
    # NOT the generic replacement
    assert "بررسی این موضوع در منابع در دسترس" not in text
    # body gate accepts it
    assert public_body_is_substantive(text) is True
    # no second SEND ever
    assert db.query_one("SELECT COUNT(*) AS n FROM jobs WHERE job_type='publish_send'")["n"] == 0


def test_deadline_unpublished_story_no_public_post(db, settings):
    _mk_story(db, "a2", published=False)
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خبر"; telegram_handle = "RastehNews"
    _resolve_deadlines(db, S(), B())
    jobs = db.query("SELECT * FROM jobs WHERE job_type IN ('publish_send','publish_edit','publish_telegram')")
    assert jobs == [], "never-published story must resolve internally with 0 public jobs"
    st = db.query_one("SELECT lifecycle FROM stories WHERE slug='a2'")
    assert st["lifecycle"] == "ARCHIVED"


def test_deadline_three_stories_each_keep_own_content(db, settings):
    """§6: 3 provisional stories → 3 deadline edits, each with ITS own
    headline; generic-warning-only bodies = 0; no identical placeholders."""
    ids = [_mk_story(db, f"g{i}", published=True) for i in range(3)]
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خبر"; telegram_handle = "RastehNews"
    _resolve_deadlines(db, S(), B())
    edits = db.query("SELECT payload_json FROM jobs WHERE job_type='publish_edit'")
    assert len(edits) == 3
    bodies = [json.loads(e["payload_json"])["text"] for e in edits]
    heads = [b.split(chr(10))[0] for b in bodies]
    assert len(set(heads)) == 3, "each story keeps its OWN headline"
    for b in bodies:
        assert public_body_is_substantive(b) is True
        assert "بررسی این موضوع در منابع در دسترس" not in b


# ---------------- §3 rate-cap THROTTLED ----------------

def test_rate_cap_throttles_not_fails(db, settings):
    s = settings.model_copy(update={"event_engine_v2_enabled": True})
    a = SourcesRepo(db).create(name="src", platform="telegram", url="t.me/x",
                               status="APPROVED")
    SourcesRepo(db).update(a, source_control_state="OWNER_ENABLED")
    RawItemsRepo(db).insert(source_id=a, platform="telegram", external_key="k1",
                            title="", text="دلار امروز در بازار آزاد به کانال تازه رسید",
                            activation_ok=True,
                            published_at="2026-10-03T10:00:00+00:00")
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خ"; telegram_handle = "R"
    process_new_items_v2(db, B(), S())
    story = db.query_one("SELECT * FROM stories")
    # saturate the 1h cap with fake SENT rows (on real stories)
    now = datetime.now(timezone.utc)
    cap_story = db.query_one("SELECT MAX(id) AS m FROM stories")["m"]
    for i in range(12):
        pid = PublicationsRepo(db).upsert(cap_story, "telegram", f"cap{i}-{i}", 1)
        db.execute("UPDATE publications SET status='SENT', updated_at=? WHERE id=?",
                   (now.isoformat(timespec="seconds"), pid))

    job = db.query_one("SELECT * FROM jobs WHERE job_type='publish_send' ORDER BY id DESC")
    payload = json.loads(job["payload_json"])

    class NoPub:  # publisher must never be reached while throttled
        async def send_message(self, text):
            raise AssertionError("send must not run while rate-capped")

    handler = make_send_handler(db, s, lambda: NoPub())
    with pytest.raises(Throttled) as exc:
        asyncio.run(handler(payload))
    assert exc.value.retry_in_seconds >= 60
    # simulate runner behavior: reschedule, NOT finish/fail
    from app.db.repo import JobsRepo
    JobsRepo(db).reschedule(job["id"], now + timedelta(seconds=exc.value.retry_in_seconds))
    j2 = db.query_one("SELECT status, attempts FROM jobs WHERE id=?", (job["id"],))
    assert j2["status"] == "pending" and j2["attempts"] == 0, \
        "throttle must not consume failure retries"


# ---------------- §10 watchdog ----------------

def test_stall_watchdog_fires_only_with_fa_eligible(db, settings):
    from app.ingestion.scheduler import _publication_stall_check
    from app.db.repo import SettingsRepo
    a = SourcesRepo(db).create(name="y", platform="telegram", url="t.me/y",
                               status="APPROVED", language="fa")
    SourcesRepo(db).update(a, source_control_state="OWNER_ENABLED")
    RawItemsRepo(db).insert(source_id=a, platform="telegram", external_key="w1",
                            title="", text="قیمت دلار امروز در بازار آزاد جهش کرد",
                            activation_ok=True, language="fa")
    db.execute("INSERT INTO events(id,title,category,status,first_seen_at,last_seen_at)"
               " VALUES(1,'w','general','NEW',datetime('now'),datetime('now'))")
    db.execute("INSERT INTO stories(event_id,slug,headline,lead,draft_json,version,"
               " status,lifecycle,created_at,updated_at)"
               " VALUES(1,'w','h','l','{}',1,'DRAFT','CONFIRMED',datetime('now'),datetime('now'))")
    _publication_stall_check(db)
    marker = SettingsRepo(db).get("PUBLICATION_PIPELINE_STALLED")
    assert marker and "eligible_items" in marker

    # foreign-only traffic must NOT trigger (replace the fa item's language)
    RawItemsRepo(db).insert(source_id=a, platform="telegram", external_key="w2",
                            title="", text="خبر عربی للترجمة لاحقاً",
                            activation_ok=True, language="ar")
    db.execute("UPDATE raw_items SET language='ar', text='خبر عربی آخر'"
               " WHERE external_key='w1'")
    db.execute("UPDATE stories SET status='PUBLISHED'")
    _publication_stall_check(db)
    assert SettingsRepo(db).get("PUBLICATION_PIPELINE_STALLED") == ""


# ---------------- §8 Google News identity ----------------

def test_google_news_and_direct_feed_same_identity_one_origin(db, settings):
    """Reuters via Google-News RSS + Reuters direct feed = ONE origin."""
    from app.verification import evidence as ev
    from app.newsroom.v2_pipeline import process_new_items_v2 as proc

    gn = SourcesRepo(db).create(name="Reuters (Google News)", platform="rss",
                                url="https://news.google.com/rss/search?q=site:reuters.com",
                                status="APPROVED", verification_allowed=True)
    direct = SourcesRepo(db).create(name="Reuters", platform="rss",
                                    url="https://reuters.com/feed",
                                    status="APPROVED", verification_allowed=True)
    for s in (gn, direct):
        SourcesRepo(db).update(s, identity="Reuters", source_control_state="OWNER_ENABLED")
    text = "دلار امروز در بازار آزاد به کانال تازه رسید"
    for i, s in enumerate((gn, direct)):
        RawItemsRepo(db).insert(source_id=s, platform="rss", external_key=f"gn{i}",
                                title="", text=text, activation_ok=True, language="fa",
                                published_at=f"2026-10-03T10:0{i}:00+00:00")
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خ"; telegram_handle = "R"
    proc(db, B(), S())
    cid = db.query_one("SELECT id FROM claims ORDER BY id DESC LIMIT 1")["id"]
    assert ev.independent_origins(db, cid) == ["identity:reuters"], \
        "Google-News proxy must never become a separate factual origin"


# ---------------- §7 mixed-language event publishes Persian ----------------

def test_mixed_language_event_publishes_persian_claim(db, settings):
    """ROOT-CAUSE regression: ar+fa items on one event → Persian story SENDs
    (previously the whole event was HELD as foreign)."""
    s = settings.model_copy(update={"event_engine_v2_enabled": True})
    naya = SourcesRepo(db).create(name="tg naya_foriraq", platform="telegram",
                                  url="t.me/n", status="APPROVED", language="ar")
    yash = SourcesRepo(db).create(name="tg withyashar", platform="telegram",
                                  url="t.me/y2", status="APPROVED", language="fa")
    for src in (naya, yash):
        SourcesRepo(db).update(src, source_control_state="OWNER_ENABLED")
    # same happening: Arabic original + Persian wire copy
    RawItemsRepo(db).insert(source_id=naya, platform="telegram", external_key="mx1",
                            title="", text="القوات الجوية تستهدف قاعدة عسكرية في العراق اليوم",
                            activation_ok=True, language="ar",
                            published_at="2026-10-03T10:00:00+00:00")
    RawItemsRepo(db).insert(source_id=yash, platform="telegram", external_key="mx2",
                            title="", text="نیروی هوایی امروز پایگاه نظامی در عراق را هدف قرار داد",
                            activation_ok=True, language="fa",
                            published_at="2026-10-03T10:02:00+00:00")
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خبر و راستی‌آزمایی"; telegram_handle = "RastehNews"
    summary = process_new_items_v2(db, B(), S())
    events = db.query("SELECT * FROM events")
    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert len(sends) >= 1, "Persian claim in a mixed event MUST publish"
    payload = json.loads(sends[0]["payload_json"])
    assert public_body_is_substantive(payload["text"]) is True
    assert "منبع:" in payload["text"]
    # Arabic raw text must NOT be in the public body
    assert "القوات" not in payload["text"]
