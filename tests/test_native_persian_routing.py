import asyncio
import json

import pytest

from app.core.textnorm import detect_language
from app.db.repo import EventsRepo, PublicationsRepo, RawItemsRepo, SourcesRepo, StoriesRepo
from app.newsroom.qa_watch import _foreign_evidence, _native_original, qa_pass
from app.newsroom.translator import needs_translation_for
from app.newsroom.v2_pipeline import process_new_items_v2
from app.publishing.telegram_bot import is_persian_public_text

FA_NAMES = "شرکت OpenAI مدل ChatGPT را با API تازه در ایران معرفی کرد."
FA_LETTERS = "علي امروز در تهران اعلام کرد نرخ دلار افزایش یافت."
AR_MADDA = "الآن قالت وزارة الصحة إن الحادث وقع في القاهرة."


class Brand:
    name_fa="آزمون"; short_name="test"; tagline_fa="خبر و بررسی"; telegram_handle="test_news"


@pytest.mark.parametrize(("text","expected"), [
    (FA_NAMES,"fa"),
    ("دلار امروز در بازار تهران افزایش یافت", "fa"),
    (AR_MADDA,"ar"),
    ("قال وزير الخارجية إن عراقچی سيصل إلى القاهرة اليوم.", "ar"),
    ("Oil prices rose today", "en"),
])
def test_language_comes_from_content_not_one_shared_letter(text,expected):
    assert detect_language(text)==expected


@pytest.mark.parametrize("lang",["fa","fa-IR","fa_IR","ar","en",""])
def test_clear_persian_with_latin_names_never_requests_translation(lang):
    assert not needs_translation_for(lang,FA_NAMES)


def test_persian_named_entities_pass_language_check_without_rewriting():
    assert is_persian_public_text(FA_NAMES)


@pytest.mark.parametrize("lang",["fa","ar",""])
def test_arabic_with_madda_and_persian_footer_still_requires_translation(lang):
    assert needs_translation_for(lang,AR_MADDA+"\n\n— آزمون | خبر و بررسی\n🆔 @test_news")


@pytest.mark.parametrize("foreign", [AR_MADDA, "Oil prices rose today after the US announcement."])
def test_native_persian_sentence_cannot_mask_foreign_body(foreign):
    assert needs_translation_for("fa", FA_NAMES + "\n" + foreign)
    assert not is_persian_public_text(FA_NAMES + "\n" + foreign)


def _source_item(db,text,language):
    sid=SourcesRepo(db).create(name='native_'+language,platform='telegram',status='APPROVED',language=language)
    SourcesRepo(db).update(sid,source_control_state='OWNER_ENABLED')
    rid=RawItemsRepo(db).insert(source_id=sid,platform='telegram',external_key='native_'+language,
        title=text,text=text,language=language,activation_ok=True)
    return rid


@pytest.mark.parametrize("text",[FA_NAMES,FA_LETTERS])
def test_native_persian_pipeline_preserves_copy_without_translation(db,settings,monkeypatch,text):
    _source_item(db,text,'fa')
    calls=[]
    monkeypatch.setattr('app.newsroom.v2_pipeline._translate_event_content',
        lambda *args:calls.append(args[3]) or None)
    process_new_items_v2(db,Brand(),settings.model_copy(update={'event_engine_v2_enabled':True}))
    assert calls==[]
    event=db.query_one('SELECT * FROM events')
    assert event['translate_attempts']==0
    story=db.query_one('SELECT * FROM stories')
    assert story is not None
    draft=json.loads(story['draft_json'])
    assert draft['translated'] is False
    assert 'OpenAI' in draft['headline'] if text==FA_NAMES else 'علی' in draft['headline']


def test_mislabeled_arabic_routes_to_arabic_model_not_persian_rewrite(db,settings,monkeypatch):
    _source_item(db,AR_MADDA,'fa')
    calls=[]
    monkeypatch.setattr('app.newsroom.v2_pipeline._translate_event_content',
        lambda *args:calls.append(args[3]) or None)
    process_new_items_v2(db,Brand(),settings.model_copy(update={'event_engine_v2_enabled':True}))
    assert calls==['ar']
    assert db.query('SELECT * FROM jobs')==[]


def test_qa_recovers_arabic_evidence_mislabeled_as_persian(db):
    rid = _source_item(db, AR_MADDA, "fa")
    eid = EventsRepo(db).create(AR_MADDA, first_item=RawItemsRepo(db).get(rid))
    evidence = _foreign_evidence(db, eid)
    assert evidence["language"] == "ar"
    assert AR_MADDA in evidence["evidence"]


def test_unrelated_native_report_does_not_exempt_translated_story(db):
    rid = _source_item(db, FA_NAMES, "fa")
    eid = EventsRepo(db).create(FA_NAMES, first_item=RawItemsRepo(db).get(rid))
    head = "قیمت دلار در ایران به ۱۰ تومان رسید"
    sid = StoriesRepo(db).create(eid, head, "", {"headline": head, "topic": "V2"})
    assert not _native_original(db, StoriesRepo(db).get(sid))


def test_qa_does_not_retranslate_native_persian_because_event_has_foreign_report(db,settings,monkeypatch):
    rid=_source_item(db,'Dollar price in Iran reached 20 tomans.','en')
    eid=EventsRepo(db).create('Dollar price',first_item=RawItemsRepo(db).get(rid))
    head='قیمت دلار در ایران به ۱۰ تومان رسید'
    lead='گزارش بازار تهران از افزایش قیمت خبر داد.'
    native=_source_item(db,head+'\n'+lead,'fa')
    EventsRepo(db).attach(eid,native)
    st=StoriesRepo(db).create(eid,head,lead,{'headline':head,'lead':lead,'topic':'V2'})
    StoriesRepo(db).mark_published(st)
    pub=PublicationsRepo(db).upsert(st,'telegram','native-original',1)
    PublicationsRepo(db).mark(pub,'SENT',remote_id='42')
    calls=[]
    async def translate(*args,**kwargs):
        calls.append(True)
        return None
    monkeypatch.setattr('app.newsroom.qa_watch.translate_event',translate)
    asyncio.run(qa_pass(db,settings,Brand(),None))
    assert calls==[]
    assert StoriesRepo(db).get(st)['headline']==head
    assert db.query('SELECT * FROM jobs')==[]
    assert EventsRepo(db).get(eid)['quality_hold']==''
