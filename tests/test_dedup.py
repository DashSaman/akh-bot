from app.clustering.dedup import classify_duplicate, fingerprints_for
from app.core.textnorm import canonical_url, normalize_title, title_hash
from app.core.simhash import simhash64, hamming_distance, likely_near_duplicate
from app.db.repo import RawItemsRepo, SourcesRepo


def _add(db, key, title, text, url=None, source_id=1):
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for(url or f"https://news.example/{key}", title, text)
    return RawItemsRepo(db).insert(
        source_id=source_id, platform="rss", external_key=key, url=url or f"https://news.example/{key}",
        canonical_url=fp["canonical_url"], title=title, text=text, activation_ok=True,
        lineage_key=f"dom:news{source_id}.example", fingerprints=fp,
    )


def _row(db, item_id):
    row = RawItemsRepo(db).get(item_id)
    fp = db.query_one("SELECT * FROM item_fingerprints WHERE raw_item_id=?", (item_id,))
    return {"canonical_url_hash": fp["canonical_url_hash"], "content_hash": fp["content_hash"],
            "title_norm_hash": fp["title_norm_hash"], "simhash": fp["simhash"]}


def test_canonical_url_stages(db):
    SourcesRepo(db).create(name="a", platform="rss", url="u", status="APPROVED")
    SourcesRepo(db).create(name="b", platform="rss", url="u", status="APPROVED")
    id1 = _add(db, "1", "عنوان", "متن خبر", url="https://news.example/story?utm_source=tg&id=1")
    # same canonical URL from another source → duplicate stage 1
    fp = fingerprints_for("https://news.example/story?id=1&fbclid=xyz", "عنوان", "متن خبر")
    dup = classify_duplicate(RawItemsRepo(db), fp, "")
    assert dup.is_duplicate and dup.stage == "url"


def test_exact_content_hash(db):
    SourcesRepo(db).create(name="a", platform="rss", url="u", status="APPROVED")
    SourcesRepo(db).create(name="b", platform="rss", url="u", status="APPROVED")
    _add(db, "1", "عنوان", "متن یکسان برای تست", url="https://x.example/1")
    fp = fingerprints_for("https://y.example/2", "عنوان", "متن یکسان برای تست")
    dup = classify_duplicate(RawItemsRepo(db), fp, "")
    assert dup.is_duplicate and dup.stage == "content_hash"


def test_normalized_title_collapse(db):
    SourcesRepo(db).create(name="a", platform="rss", url="u", status="APPROVED")
    SourcesRepo(db).create(name="b", platform="rss", url="u", status="APPROVED")
    # same headline, Arabic yeh/kaf spelling variant + punctuation
    _add(db, "1", "ترکیه حمله هوایی انجام داد", "متن متفاوت الف", url="https://a.example/1")
    fp = fingerprints_for("https://b.example/2", "تركیه حمله هوایی انجام داد!", "متن متفاوت ب")
    dup = classify_duplicate(RawItemsRepo(db), fp, "")
    assert dup.is_duplicate and dup.stage == "title"


def test_simhash_near_duplicate_new_story_not_dup(db):
    SourcesRepo(db).create(name="a", platform="rss", url="u", status="APPROVED")
    _add(db, "1", "بازار سهام رکورد زد", "شاخص بورس امروز با رشد بی‌سابقه به رقم تاریخی رسید و تحلیلگران هشدار دادند")
    fp = fingerprints_for("https://a.example/9", "حوادث ترافیکی شب گذشته", "یک تصادف در بزرگراه باعث اختلال ترافیک شد رانندگی با احتیاط")
    dup = classify_duplicate(RawItemsRepo(db), fp, "")
    assert not dup.is_duplicate


def test_simhash_helpers():
    a = simhash64("وزیر خارجه آمریکا درباره مذاکرات هسته‌ای اظهار نظر کرد و گفت")
    b = simhash64("وزیر خارجه آمریکا درباره مذاکرات هسته‌ای اظهار نظر کرد گفت")
    c = simhash64("تیم فوتبال استقلال در دیدار شب گذشته به پیروزی رسید و هواداران")
    assert hamming_distance(a, b) <= 12
    assert likely_near_duplicate(a, b, threshold=12)
    assert hamming_distance(a, c) > 12


def test_canonical_url_normalization():
    assert canonical_url("HTTPS://News.Example:443/a/?utm_source=x&b=2&a=1#frag") == \
        "https://news.example/a?a=1&b=2"
    assert normalize_title("عنوان! خبر؛ «مهم»") == normalize_title("عنوان خبر مهم")
    assert title_hash("الف") == title_hash("الف")
