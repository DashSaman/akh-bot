"""Source registry import (PART-3-C §10-12): candidates only, never auto-enabled,
identity dedup across endpoints, tier≠trust."""
import json

from app.db.repo import SourcesRepo

from app.newsroom.source_registry import import_registry, identity_key

CSV = """name,platform,language,role,url
Trump X,x,en,PERSON_STATEMENT,https://x.com/realDonaldTrump
Trump Truth Social,x,en,PERSON_STATEMENT,https://truthsocial.com/@realDonaldTrump
CENTCOM EN,x,en,OFFICIAL_PRIMARY,
CENTCOM AR,x,ar,OFFICIAL_PRIMARY,
Netanyahu X,x,he,PERSON_STATEMENT,
NAYA,tg,ar,INDEPENDENT_NEWSROOM,https://t.me/naya_foriraq
Yashar,tg,fa,INDEPENDENT_NEWSROOM,https://t.me/withyashar
Unknown Lookalike,tg,fa,INDEPENDENT_NEWSROOM,
"""


def test_import_creates_candidates_not_enabled(db):
    out = import_registry(db, CSV)
    assert out["imported"] >= 8
    rows = SourcesRepo(db).list()
    assert all(r["enabled"] == 0 for r in rows), "no auto-enable"
    assert all(r["status"] == "DISCOVERED" for r in rows)
    assert all(r["verification_allowed"] == 0 for r in rows), "never auto-verify"


def test_identity_dedup_same_person_one_source(db):
    import_registry(db, CSV)
    rows = SourcesRepo(db).list()
    trump = [r for r in rows if "trump" in r["name"].lower()]
    assert len(trump) == 1, f"Trump endpoints must collapse: {[r['name'] for r in trump]}"
    assert "endpoint:x:" in trump[0]["notes"]  # second endpoint preserved as note
    centcom = [r for r in rows if "centcom" in r["name"].lower()]
    assert len(centcom) == 1
    # naya + yashar are DIFFERENT identities (different orgs)
    assert any("naya" in r["name"].lower() for r in rows)
    assert any("yashar" in r["name"].lower() for r in rows)


def test_tier_metadata_stored_never_trust(db):
    import_registry(db, CSV)
    rows = SourcesRepo(db).list()
    centcom = next(r for r in rows if "centcom" in r["name"].lower())
    assert "tier=A" in centcom["notes"]
    assert centcom["verification_allowed"] == 0  # OFFICIAL_PRIMARY ≠ auto-trust
    naya = next(r for r in rows if "naya" in r["name"].lower())
    assert "tier=B" in naya["notes"]


def test_lookalike_imported_as_candidate_not_enabled(db):
    import_registry(db, CSV)
    rows = SourcesRepo(db).list()
    lookalike = [r for r in rows if "lookalike" in r["name"].lower()]
    assert lookalike and lookalike[0]["enabled"] == 0  # present, owner decides


def test_rerun_does_not_duplicate(db):
    import_registry(db, CSV)
    n1 = len(SourcesRepo(db).list())
    import_registry(db, CSV)
    n2 = len(SourcesRepo(db).list())
    assert n2 == n1  # identity dedup makes import idempotent


def test_production_sources_untouched(db):
    SourcesRepo(db).create(name="tg naya_foriraq", platform="telegram",
                           external_id="naya_foriraq", status="APPROVED",
                           priority_rank=1, polling_interval_seconds=30)
    before = SourcesRepo(db).get(1)
    import_registry(db, CSV)
    after = SourcesRepo(db).get(1)
    assert after["enabled"] == 1 and after["priority_rank"] == 1  # untouched
