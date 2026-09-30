"""SEO regression: one H1, canonical, single schema graph, Organization publisher,
sitemaps, robots, and preview-mode noindex behavior."""
import json

from app.db.repo import SourcesRepo, StoriesRepo

DRAFT = {
    "headline": "خبر آزمون سئو",
    "lead": "لید خبر آزمون",
    "body": [{"text": "پاراگراف اول.", "claim_refs": ["1"]}],
    "confirmed_facts": ["فکت ۱"], "uncertain_facts": ["نامشخص ۱"],
    "timeline": [{"time": "10:00", "event": "اتفاق"}],
    "source_references": [{"source_id": 1, "name": "منبع", "platform": "rss", "language": "fa", "url": "https://x"}],
    "category": "general", "tags": ["تست"],
    "seo_title": "عنوان سئو", "seo_description": "توضیح متا آزمون",
    "platform_variants": {"telegram": "t", "x": "x", "threads": "", "instagram_caption": "", "web_extra": ""},
}


def _publish_story(db):
    SourcesRepo(db).create(name="s", platform="rss", url="u", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES('e','NEW',?,?)",
               ("2030-01-01T00:00:00+00:00",) * 2)
    story_id = StoriesRepo(db).create(1, DRAFT["headline"], DRAFT["lead"], DRAFT)
    StoriesRepo(db).mark_published(story_id)
    return StoriesRepo(db).get(story_id)


def test_story_page_seo_quality_gate(client):
    story = _publish_story(client.app.state.db)
    resp = client.get(f"/story/{story['slug']}")
    assert resp.status_code == 200
    html = resp.text
    assert html.count("<h1>") == 1                          # exactly one primary H1
    assert DRAFT["headline"] in html
    assert 'name="description"' in html and "توضیح متا آزمون" in html
    assert '<link rel="canonical" href="https://news.example.test/story/' in html
    assert 'property="og:title"' in html and 'name="twitter:card"' in html
    # ONE authoritative schema graph, publisher is an Organization (no Person leak)
    assert html.count("application/ld+json") == 1
    block = html.split('type="application/ld+json">', 1)[1].split("</script>")[0]
    graph = json.loads(block)
    types = [n["@type"] for n in graph["@graph"]]
    assert "NewsArticle" in types and "NewsMediaOrganization" in types
    article = next(n for n in graph["@graph"] if n["@type"] == "NewsArticle")
    assert article["publisher"]["@id"].endswith("#organization")  # reference, not inline Person
    assert article["author"]["@type"] == "Organization"
    assert article["datePublished"] and article["dateModified"]
    # structured story sections (GEO/AEO friendly)
    for section in ("خلاصه", "چه اتفاقی افتاده؟", "منابع", "خط زمانی"):
        assert section in html


def test_story_page_sections_confirmed_unconfirmed(client):
    story = _publish_story(client.app.state.db)
    html = client.get(f"/story/{story['slug']}").text
    assert "چه چیزهایی تأیید شده؟" in html
    assert "چه چیزهایی هنوز تأیید نشده؟" in html


def test_sitemap_contains_story(client):
    story = _publish_story(client.app.state.db)
    xml = client.get("/sitemap.xml").text
    assert story["slug"] in xml and "/page/about" in xml and "<urlset" in xml


def test_news_sitemap_fresh_only(client):
    story = _publish_story(client.app.state.db)
    xml = client.get("/news-sitemap.xml").text
    assert story["slug"] in xml and "<news:news>" in xml


def test_robots_blocks_admin_and_lists_sitemaps(client):
    robots = client.get("/robots.txt").text
    assert "Disallow: /admin" in robots and "sitemap.xml" in robots


def test_preview_mode_noindex(client):
    """While brand/domain undecided, preview stays unindexed (deliberate, documented)."""
    client.app.state.settings.public_base_url = ""  # preview_mode derives from this
    robots = client.get("/robots.txt").text
    assert "Disallow: /" in robots
    story = _publish_story(client.app.state.db)
    html = client.get(f"/story/{story['slug']}").text
    assert "noindex" in html
    assert "rel=\"canonical\"" not in html


def test_rss_feed_output(client):
    story = _publish_story(client.app.state.db)
    xml = client.get("/feed.xml").text
    assert story["headline"] in xml and "<rss" in xml


def test_trust_pages_render(client):
    for slug in ("about", "editorial-policy", "verification", "corrections", "ai-use"):
        resp = client.get(f"/page/{slug}")
        assert resp.status_code == 200
        assert resp.text.count("<h1>") == 1


def test_no_accidental_noindex_when_live(client):
    story = _publish_story(client.app.state.db)
    html = client.get(f"/story/{story['slug']}").text
    assert "noindex" not in html  # live mode indexes content
