"""Source registry audit + auto-activation (owner directive: no silent sources).

For every source: try official RSS/Atom → Telegram web preview → Google News
RSS (LAST fallback). Reachable → ACTIVATE (ingest 24/7). Unreachable → keep a
TRUTHFUL blocker. Never bypasses paywalls/logins/CAPTCHA/robots (we only read
public feeds/previews).

Output: per-IDENTITY coverage report (identity, active endpoint, last success,
items 24h, blocker) + summary counts.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
import xml.etree.ElementTree as ET

import httpx

DB = "/data/akhbot.db"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RastehNewsBot/1.0; +https://rasteh.softarg.ir)"}
TIMEOUT = 15
NOW = datetime.datetime.now(datetime.timezone.utc)

import sqlite3  # noqa: E402

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")


def parse_ts(s):
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def feed_ok(url: str) -> tuple[bool, str]:
    """A feed is usable if it parses as RSS/Atom AND has entries."""
    try:
        with httpx.Client(timeout=TIMEOUT, headers=UA, follow_redirects=True) as c:
            r = c.get(url)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        ct = (r.headers.get("content-type") or "").lower()
        if "html" in ct and "<rss" not in r.text[:2000] and "<feed" not in r.text[:2000]:
            return False, "html not feed"
        root = ET.fromstring(r.text[:2_000_000])
        for tag in ("channel", "feed"):
            pass
        n = len(root.findall(".//item")) + len(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
        if n == 0:
            return False, "feed empty"
        return True, f"feed:{n}"
    except Exception as ex:  # noqa: BLE001
        return False, type(ex).__name__ + ":" + str(ex)[:60]


def tg_preview_ok(handle: str) -> tuple[bool, str]:
    h = handle.lstrip("@")
    try:
        with httpx.Client(timeout=TIMEOUT, headers=UA, follow_redirects=True) as c:
            r = c.get(f"https://t.me/s/{h}")
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        if "tgme_widget_message" not in r.text:
            return False, "no preview"
        return True, "tg-preview"
    except Exception as ex:  # noqa: BLE001
        return False, type(ex).__name__


def google_news_feed(identity_name: str, domain: str) -> tuple[bool, str, str]:
    """Google News RSS for the org's domain (public search feed; last resort)."""
    if not domain:
        return False, "no domain", ""
    url = f"https://news.google.com/rss/search?q=site:{domain}&hl=en-US&gl=US&ceid=US:en"
    ok, why = feed_ok(url)
    return ok, why, url


def domain_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).replace("www.", "") if m else ""


rows = db.execute(
    "SELECT id,name,platform,url,identity,endpoint_state,enabled,"
    "source_control_state,notes,last_error FROM sources ORDER BY id").fetchall()

report = []
activated = kept_blocked = 0
for s in rows:
    sid, name, platform, url = s["id"], s["name"], s["platform"], s["url"] or ""
    state = s["endpoint_state"] or ""
    # ---- live stats for the report
    last24 = db.execute(
        "SELECT COUNT(*) c FROM raw_items WHERE source_id=? AND fetched_at >= ?",
        (sid, (NOW - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"))).fetchone()["c"]
    got_any = db.execute(
        "SELECT COUNT(*) c, MAX(fetched_at) m FROM raw_items WHERE source_id=?",
        (sid,)).fetchone()
    note = ""

    if state == "ACTIVE":
        report.append((s["identity"] or name, name, platform, "ACTIVE",
                       got_any["m"] or "", last24, ""))
        continue

    # ---- try to activate: RSS → TG preview → Google News (owner directive)
    chosen_url, method, why_not = "", "", ""
    if platform in ("rss", "website", "web"):
        for cand in filter(None, [url,
                                  url.rstrip("/") + "/rss" if url else "",
                                  url.rstrip("/") + "/feed" if url else "",
                                  url.rstrip("/") + "/rss.xml" if url else ""]):
            ok, why = feed_ok(cand)
            if ok:
                chosen_url, method = cand, "rss"
                break
            why_not = why
    if not chosen_url and platform == "telegram":
        ok, why = tg_preview_ok(name if name.startswith("@") else url)
        if ok:
            chosen_url, method = url, "tg-preview"
        else:
            why_not = why
    if not chosen_url and platform not in ("x", "twitter"):
        dom = domain_of(url)
        ok, why, gn_url = google_news_feed(name, dom)
        if ok and dom and "." in dom and not dom.startswith("t.me") \
                and not dom.startswith("x.com") and not dom.startswith("twitter.com"):
            chosen_url, method = gn_url, "google-news"
        else:
            why_not = why

    if chosen_url:
        if method == "google-news":
            db.execute(
                "UPDATE sources SET url=?, platform='rss', endpoint_state='ACTIVE', "
                "enabled=1, source_control_state='OWNER_ENABLED', last_error='', "
                "notes=COALESCE(notes,'')||? WHERE id=?",
                (chosen_url, f" | AUTO-{method}", sid))
        else:
            db.execute(
                "UPDATE sources SET endpoint_state='ACTIVE', enabled=1, "
                "source_control_state='OWNER_ENABLED', last_error='', "
                "notes=COALESCE(notes,'')||? WHERE id=?",
                (f" | AUTO-{method}", sid))
        activated += 1
        report.append((s["identity"] or name, name, method, "ACTIVATED",
                       "", 0, f"via {method}"))
    else:
        blocker = ("login/paywall" if "BLOCKED_AUTH" in (s["notes"] or "") or "auth" in why_not.lower()
                   else why_not or "dead")
        kept_blocked += 1
        report.append((s["identity"] or name, name, platform, "BLOCKED",
                       "", last24, blocker))

db.commit()

# ---- identity-collapsed view (website+TG+X of same org = ONE identity)
by_identity: dict[str, list] = {}
for r in report:
    by_identity.setdefault(r[0], []).append(r)

lines = []
for ident in sorted(by_identity):
    entries = by_identity[ident]
    active = [e for e in entries if e[3] in ("ACTIVE", "ACTIVATED")]
    items24 = sum(e[5] for e in entries)
    last = max((e[4] for e in entries if e[4]), default="")
    blocker = "; ".join({e[6] for e in entries if e[6] and e[3] == "BLOCKED"}) or ""
    lines.append({
        "identity": ident,
        "endpoints": len(entries),
        "active": len(active),
        "items_24h": items24,
        "last_fetch": str(last)[:19],
        "blocker": blocker[:80] if not active else "",
    })

out = {"identities": len(by_identity),
       "identities_active": sum(1 for v in by_identity.values()
                                if any(e[3] in ("ACTIVE", "ACTIVATED") for e in v)),
       "activated_now": activated,
       "still_blocked": kept_blocked,
       "rows": lines}
print(json.dumps(out, ensure_ascii=False, indent=1)[:12000])
