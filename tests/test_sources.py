from app.db.repo import EventsRepo, RawItemsRepo, SourcesRepo


def _make_item(db, source_id, key, title, text, published_at, activation_ok=True, lineage="dom:a.com"):
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for(f"https://a.com/{key}", title, text)
    return RawItemsRepo(db).insert(
        source_id=source_id, platform="rss", external_key=key,
        url=f"https://a.com/{key}", canonical_url=fp["canonical_url"], title=title,
        text=text, published_at=published_at, activation_ok=activation_ok,
        lineage_key=lineage, fingerprints=fp,
    )


def test_source_crud_and_status_transitions(db):
    sources = SourcesRepo(db)
    sid = sources.create(name="تست", platform="rss", url="https://x.example/feed", status="DISCOVERED")
    assert sources.get(sid)["status"] == "DISCOVERED"
    assert sources.get(sid)["activated_at"] is None
    sources.set_status(sid, "APPROVED")
    row = sources.get(sid)
    assert row["status"] == "APPROVED"
    assert row["activated_at"] is not None  # backfill anchor set on approval
    sources.update(sid, polling_interval_min=7)
    assert sources.get(sid)["polling_interval_min"] == 7
    sources.set_status(sid, "BLOCKED")
    assert sources.get(sid)["status"] == "BLOCKED"


def test_backfill_protection_old_items_store_only(db):
    """Item published BEFORE source activation must never be publish-eligible."""
    from app.newsroom.pipeline import process_new_items

    sources = SourcesRepo(db)
    sources.create(name="s", platform="rss", url="u", status="DISCOVERED")
    sid = 1
    _make_item(db, sid, "old-1", "خبر قدیمی", "متن خبر قدیمی", "2020-01-01T00:00:00+00:00",
               activation_ok=False)  # RSS collector marks pre-activation entries STORE_ONLY
    sources.set_status(sid, "APPROVED")  # activation happens NOW
    _make_item(db, sid, "new-1", "خبر جدید", "متن خبر جدید", "2030-01-01T00:00:00+00:00", activation_ok=True)

    async def run():
        return await process_new_items(db, None, None, None)

    import asyncio

    summary = asyncio.run(run())
    assert summary["processed"] == 2
    items = RawItemsRepo(db).list()
    by_key = {i["external_key"]: i for i in items}
    assert by_key["old-1"]["processed_state"] == "PROCESSED"
    # old item never became an event/report candidate
    events = EventsRepo(db).list()
    attached = {r["id"] for e in events for r in EventsRepo(db).items(e["id"])}
    new_item = next(i for i in items if i["external_key"] == "new-1")
    old_item = next(i for i in items if i["external_key"] == "old-1")
    assert new_item["id"] in attached
    assert old_item["id"] not in attached
