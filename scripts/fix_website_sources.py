"""Repair ACTIVE/platform=website sources: bind each to a WORKING rss feed
(own feed → variants → Google News), or mark UNSUPPORTED truthfully."""
import datetime
import re
import sqlite3
import xml.etree.ElementTree as ET

import httpx

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row
UA = {"User-Agent": "Mozilla/5.0 (compatible; RastehNewsBot/1.0)"}


def feed_ok(url):
    try:
        with httpx.Client(timeout=15, headers=UA, follow_redirects=True) as c:
            r = c.get(url)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        root = ET.fromstring(r.text[:2_000_000])
        n = (len(root.findall(".//item"))
             + len(root.findall(".//{http://www.w3.org/2005/Atom}entry")))
        return (n > 0), f"feed:{n}"
    except Exception as ex:  # noqa: BLE001
        return False, type(ex).__name__


def domain_of(url):
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).replace("www.", "") if m else ""


rows = db.execute("SELECT id,name,identity,url,notes FROM sources "
                  "WHERE endpoint_state='ACTIVE' AND platform='website'").fetchall()
fixed = unsupported = 0
for s in rows:
    url = s["url"] or ""
    dom = domain_of(url)
    candidates = [url]
    if dom:
        candidates += [
            f"https://{dom}/feed", f"https://{dom}/rss",
            f"https://{dom}/feed/", f"https://{dom}/rss.xml",
            f"https://{dom}/?feed=rss2"]
    chosen, method = "", ""
    for cand in candidates:
        ok, _ = feed_ok(cand)
        if ok:
            chosen, method = cand, "rss"
            break
    if not chosen and dom:
        gn = (f"https://news.google.com/rss/search?q=site:{dom}"
              "&hl=en-US&gl=US&ceid=US:en")
        ok, _ = feed_ok(gn)
        if ok:
            chosen, method = gn, "google-news"
    if chosen:
        db.execute("UPDATE sources SET url=?, platform='rss', last_error='' "
                   "WHERE id=?", (chosen, s["id"]))
        fixed += 1
        print("FIXED", s["identity"], "->", method, chosen[:70])
    else:
        db.execute("UPDATE sources SET endpoint_state='UNSUPPORTED', enabled=0, "
                   "source_control_state='OWNER_DISABLED', "
                   "notes=COALESCE(notes,'')||' | NO_PUBLIC_FEED' WHERE id=?",
                   (s["id"],))
        unsupported += 1
        print("UNSUPPORTED", s["identity"], dom)
db.commit()
print("fixed:", fixed, "unsupported:", unsupported)
