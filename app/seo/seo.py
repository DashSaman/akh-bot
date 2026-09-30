"""SEO layer: ONE authoritative schema graph, sitemaps, news sitemap, RSS/Atom feed, robots."""
from __future__ import annotations

import json
from typing import Any
from xml.sax.saxutils import escape

from app.brand import Brand


def org_node(brand: Brand, public_base_url: str) -> dict[str, Any]:
    org_id = f"{public_base_url.rstrip('/')}/#organization"
    node: dict[str, Any] = {
        "@type": brand.publisher_type or "NewsMediaOrganization",
        "@id": org_id,
        "name": brand.name_fa,
        "alternateName": [brand.name_en] if brand.name_en else [],
        "url": public_base_url.rstrip("/") or "/",
    }
    if brand.logo and brand.logo.startswith("http"):
        node["logo"] = {"@type": "ImageObject", "url": brand.logo}
    same_as = brand.same_as_list(public_base_url)
    if same_as:
        node["sameAs"] = same_as
    return node


def news_article_node(brand: Brand, public_base_url: str, story: dict[str, Any],
                      draft: dict[str, Any]) -> dict[str, Any]:
    base = public_base_url.rstrip("/")
    story_url = f"{base}/story/{story['slug']}"
    return {
        "@type": "NewsArticle",
        "@id": f"{story_url}#article",
        "headline": story["headline"],
        "description": draft.get("seo_description") or story["lead"],
        "inLanguage": "fa",
        "datePublished": story.get("published_at") or story["created_at"],
        "dateModified": story.get("updated_at") or story["created_at"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": story_url},
        "url": story_url,
        "publisher": {"@id": f"{base}/#organization"},
        "author": {
            "@type": "Organization",
            "@id": f"{base}/#organization",
            "name": brand.editorial_attribution_fa,
        },
        "isAccessibleForFree": True,
    }


def build_graph(brand: Brand, public_base_url: str, story: dict[str, Any] | None = None,
                draft: dict[str, Any] | None = None) -> dict[str, Any]:
    """The single source of JSON-LD for every page. No other schema emitters exist."""
    graph: list[dict[str, Any]] = [org_node(brand, public_base_url)]
    if story is not None:
        graph.append(news_article_node(brand, public_base_url, story, draft or {}))
    return {"@context": "https://schema.org", "@graph": graph}


def xml_url_entry(url: str, lastmod: str | None = None) -> str:
    lm = f"<lastmod>{escape(lastmod)}</lastmod>" if lastmod else ""
    return f"<url><loc>{escape(url)}</loc>{lm}</url>"


def build_sitemap(public_base_url: str, story_urls: list[tuple[str, str | None]],
                  static_pages: list[str]) -> str:
    base = public_base_url.rstrip("/")
    entries = [xml_url_entry(base)]
    entries += [xml_url_entry(f"{base}{p}") for p in static_pages]
    entries += [xml_url_entry(f"{base}/story/{slug}", lm) for slug, lm in story_urls]
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(entries) + "</urlset>")


def build_news_sitemap(public_base_url: str, stories: list[dict[str, Any]]) -> str:
    base = public_base_url.rstrip("/")
    entries = "".join(
        f"<url><loc>{escape(base)}/story/{escape(s['slug'])}</loc>"
        f"<news:news><news:publication><news:name>{escape(name)}</news:name>"
        f"<news:language>fa</news:language></news:publication>"
        f"<news:publication_date>{escape(s['published_at'] or s['created_at'])}</news:publication_date>"
        f"<news:title>{escape(s['headline'])}</news:title></news:news></url>"
        for s in stories
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
            ' xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
            + entries + "</urlset>")


def build_rss(brand: Brand, public_base_url: str, stories: list[dict[str, Any]],
              drafts: dict[int, dict[str, Any]]) -> str:
    base = public_base_url.rstrip("/")
    items = "".join(
        f"<item><title>{escape(s['headline'])}</title>"
        f"<link>{escape(base)}/story/{escape(s['slug'])}</link>"
        f"<guid>{escape(base)}/story/{escape(s['slug'])}</guid>"
        f"<pubDate>{escape(s['published_at'] or s['created_at'])}</pubDate>"
        f"<description>{escape(drafts.get(s['id'], {}).get('seo_description') or s['lead'])}</description>"
        "</item>"
        for s in stories
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<rss version="2.0"><channel><title>{escape(brand.name_fa)}</title>'
            f'<link>{escape(base)}</link><description>{escape(brand.tagline_fa)}</description>'
            f'<language>fa</language>{items}</channel></rss>')


def robots_txt(public_base_url: str) -> str:
    base = public_base_url.rstrip("/")
    if not base:
        # preview mode (brand/domain undecided): intentionally unindexed
        return "User-agent: *\nDisallow: /\n"
    return (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
        f"Sitemap: {base}/news-sitemap.xml\n"
    )
