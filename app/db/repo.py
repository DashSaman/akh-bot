"""Repository layer: all SQL lives here (storage abstraction for a later PostgreSQL move)."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import Database


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class SourcesRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, *, name: str, platform: str, url: str = "", external_id: str = "",
               language: str = "und", country: str = "", category: str = "general",
               source_type: str = "news_organization", status: str = "DISCOVERED",
               priority: int = 50, polling_interval_min: int = 15, notes: str = "",
               verification_allowed: bool = False, source_role: str = "MAJOR_NEWSROOM",
               can_increase_independent_count: bool = True,
               publication_policy: str = "AUTO", priority_rank: int = 99,
               polling_interval_seconds: int = 0) -> int:
        activated = utcnow() if status == "APPROVED" else None
        cur = self.db.execute(
            "INSERT INTO sources(name,platform,external_id,url,language,country,category,"
            "source_type,status,enabled,priority,polling_interval_min,notes,created_at,activated_at,"
            "verification_allowed,source_role,can_increase_independent_count,"
            "publication_policy,priority_rank,polling_interval_seconds)"
            " VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?)",
            (name, platform, external_id, url, language, country, category,
             source_type, status, priority, polling_interval_min, notes, utcnow(), activated,
             1 if verification_allowed else 0, source_role,
             1 if can_increase_independent_count else 0,
             publication_policy, priority_rank,
             polling_interval_seconds or max(20, polling_interval_min * 60)),
        )
        return int(cur.lastrowid)

    def get(self, source_id: int) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM sources WHERE id=?", (source_id,))

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            return self.db.query("SELECT * FROM sources WHERE status=? ORDER BY priority,id", (status,))
        return self.db.query("SELECT * FROM sources ORDER BY priority,id")

    def update(self, source_id: int, **fields: Any) -> None:
        allowed = {"name", "url", "external_id", "language", "country", "category",
                   "source_type", "priority", "polling_interval_min", "notes", "enabled",
                   "verification_allowed", "source_role", "can_increase_independent_count",
                   "publication_policy", "priority_rank", "polling_interval_seconds",
                   "source_control_state", "topic_mode", "selected_topics",
                   "identity", "endpoint_state", "speed_tier", "focus", "role_detail"}
        sets, params = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                params.append(v)
        if not sets:
            return
        params.append(source_id)
        self.db.execute(f"UPDATE sources SET {', '.join(sets)} WHERE id=?", params)

    def set_status(self, source_id: int, status: str) -> None:
        # Approving (re)anchors activation time for backfill protection.
        activated = utcnow() if status == "APPROVED" else None
        self.db.execute(
            "UPDATE sources SET status=?, activated_at=COALESCE(?, activated_at) WHERE id=?",
            (status, activated, source_id),
        )

    def due(self, now: datetime) -> list[dict[str, Any]]:
        """SOURCE_ALLOWLIST: only owner-ENABLED sources are ever polled."""
        rows = self.db.query(
            "SELECT * FROM sources WHERE status='APPROVED' AND enabled=1"
            " AND source_control_state IN ('OWNER_ENABLED','DISCOVERY_ONLY')"
            " ORDER BY priority_rank, priority, id"
        )
        out = []
        for s in rows:
            secs = int(s.get("polling_interval_seconds") or 0) or int(s["polling_interval_min"]) * 60
            last = parse_iso(s["last_fetch_at"])
            if last is None or (now - last) >= timedelta(seconds=max(20, secs)):
                out.append(s)
        return out

    def mark_fetch(self, source_id: int, ok: bool, error: str | None = None,
                   fetch_state: dict | None = None) -> None:
        s = self.get(source_id)
        health = float(s["health_score"]) if s else 1.0
        health = max(0.0, min(1.0, health * 0.9 if not ok else health + (1 - health) * 0.2))
        state = json.dumps(fetch_state) if fetch_state is not None else s["fetch_state"]
        self.db.execute(
            "UPDATE sources SET last_fetch_at=?, last_success_at=CASE WHEN ? THEN ? ELSE last_success_at END,"
            " last_error=?, health_score=?, fetch_state=? WHERE id=?",
            (utcnow(), 1 if ok else 0, utcnow(), error, health, state, source_id),
        )


class RawItemsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def exists(self, source_id: int, external_key: str) -> bool:
        return self.db.query_one(
            "SELECT id FROM raw_items WHERE source_id=? AND external_key=?",
            (source_id, external_key),
        ) is not None

    def insert(self, *, source_id: int, platform: str, external_key: str, url: str = "",
               canonical_url: str = "", title: str = "", text: str = "", language: str = "und",
               author: str = "", published_at: str | None = None, edited_at: str | None = None,
               forward_from: str | None = None,
               media: list | None = None, lineage_key: str = "", activation_ok: bool = False,
               fingerprints: dict[str, str] | None = None) -> int:
        media_json = json.dumps(media or [], ensure_ascii=False)
        with self.db.tx() as conn:
            cur = conn.execute(
                "INSERT INTO raw_items(source_id,platform,external_key,url,canonical_url,title,text,"
                "language,author,published_at,edited_at,fetched_at,forward_from,media_json,lineage_key,activation_ok)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source_id, platform, external_key, url, canonical_url, title, text, language,
                 author, published_at, edited_at, utcnow(), forward_from, media_json, lineage_key,
                 1 if activation_ok else 0),
            )
            item_id = int(cur.lastrowid)
            fp = fingerprints or {}
            conn.execute(
                "INSERT INTO item_fingerprints(raw_item_id,canonical_url_hash,content_hash,title_norm_hash,simhash)"
                " VALUES(?,?,?,?,?)",
                (item_id, fp.get("canonical_url_hash", ""), fp.get("content_hash", ""),
                 fp.get("title_norm_hash", ""), fp.get("simhash", "")),
            )
            conn.execute(
                "INSERT INTO item_revisions(raw_item_id,rev_no,title,text,content_hash,edited_at,created_at)"
                " VALUES(?,1,?,?,?,NULL,?)",
                (item_id, title, text, fp.get("content_hash", ""), utcnow()),
            )
        return item_id

    def add_revision(self, item_id: int, title: str, text: str, content_hash: str,
                     edited_at: str | None) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(MAX(rev_no),0)+1 AS nxt FROM item_revisions WHERE raw_item_id=?", (item_id,)
        )
        rev = int(row["nxt"]) if row else 1
        self.db.execute(
            "INSERT OR IGNORE INTO item_revisions(raw_item_id,rev_no,title,text,content_hash,edited_at,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (item_id, rev, title, text, content_hash, edited_at, utcnow()),
        )
        return rev

    def get(self, item_id: int) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM raw_items WHERE id=?", (item_id,))

    def find_by_fingerprint(self, canonical_url_hash: str = "", content_hash: str = "",
                            title_norm_hash: str = "",
                            exclude_item_id: int | None = None) -> list[dict[str, Any]]:
        conds, params = [], []
        if canonical_url_hash:
            conds.append("f.canonical_url_hash=?")
            params.append(canonical_url_hash)
        if content_hash:
            conds.append("f.content_hash=?")
            params.append(content_hash)
        if title_norm_hash:
            conds.append("f.title_norm_hash=?")
            params.append(title_norm_hash)
        if not conds:
            return []
        where = " OR ".join(conds)
        if exclude_item_id is not None:
            where = f"({where}) AND r.id != ?"
            params.append(exclude_item_id)
        sql = ("SELECT r.* FROM raw_items r JOIN item_fingerprints f ON f.raw_item_id=r.id"
               f" WHERE {where} ORDER BY r.id LIMIT 20")
        return self.db.query(sql, params)

    def recent_with_simhash(self, limit: int = 200,
                            exclude_item_id: int | None = None) -> list[dict[str, Any]]:
        extra = "AND r.id != ?" if exclude_item_id is not None else ""
        params: list = [limit]
        if exclude_item_id is not None:
            params.insert(0, exclude_item_id)
        return self.db.query(
            "SELECT r.*, f.simhash FROM raw_items r JOIN item_fingerprints f ON f.raw_item_id=r.id"
            f" WHERE f.simhash!='' {extra} ORDER BY r.id DESC LIMIT ?",
            params,
        )

    def list(self, limit: int = 100, only_new: bool = False,
             order: str = "DESC") -> list[dict[str, Any]]:
        cond = "WHERE processed_state='NEW'" if only_new else ""
        assert order in ("ASC", "DESC")
        return self.db.query(
            f"SELECT * FROM raw_items {cond} ORDER BY id {order} LIMIT ?", (limit,)
        )

    def set_state(self, item_id: int, state: str) -> None:
        self.db.execute("UPDATE raw_items SET processed_state=? WHERE id=?", (state, item_id))


class EventsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, title: str, category: str = "general", first_item: dict | None = None) -> int:
        now = utcnow()
        cur = self.db.execute(
            "INSERT INTO events(title,category,status,first_seen_at,last_seen_at) VALUES(?,?,?,?,?)",
            (title, category, "NEW", now, now),
        )
        event_id = int(cur.lastrowid)
        if first_item:
            self.attach(event_id, first_item["id"], is_duplicate=False)
        return event_id

    def attach(self, event_id: int, raw_item_id: int, is_duplicate: bool = False) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO event_items(event_id,raw_item_id,is_duplicate) VALUES(?,?,?)",
            (event_id, raw_item_id, 1 if is_duplicate else 0),
        )

    def get(self, event_id: int) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM events WHERE id=?", (event_id,))

    def items(self, event_id: int, include_dupes: bool = True) -> list[dict[str, Any]]:
        cond = "" if include_dupes else " AND ei.is_duplicate=0"
        return self.db.query(
            "SELECT r.*, ei.is_duplicate FROM event_items ei JOIN raw_items r ON r.id=ei.raw_item_id"
            f" WHERE ei.event_id=?{cond} ORDER BY r.id",
            (event_id,),
        )

    def recompute(self, event_id: int) -> dict[str, Any]:
        items = self.items(event_id)
        # report_count counts EVERY report; independence counts only sources whose
        # origin spread is real (aggregators flagged can_increase=0 never add).
        flags = {
            r["id"]: r
            for r in self.db.query(
                "SELECT id, can_increase_independent_count FROM sources"
            )
        }
        lineages = {
            i["lineage_key"] or f"src:{i['source_id']}"
            for i in items
            if flags.get(i["source_id"], {}).get("can_increase_independent_count", 1)
        }
        langs = sorted({i["language"] for i in items if i["language"] != "und"})
        independent = len(lineages)
        stamps = [(i["published_at"] or i["fetched_at"]) for i in items] or [utcnow()]
        first, last = min(stamps), max(stamps)
        now_d = datetime.now(timezone.utc)
        recent = sum(
            1 for s in stamps if (dt := parse_iso(s)) and (now_d - dt) < timedelta(hours=1)
        )
        self.db.execute(
            "UPDATE events SET report_count=?, independent_count=?, languages_json=?,"
            " first_seen_at=?, last_seen_at=?, velocity=? WHERE id=?",
            (len(items), independent, json.dumps(langs), first, last, recent, event_id),
        )
        return {"report_count": len(items), "independent_count": independent,
                "languages": langs, "velocity": recent}

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM events ORDER BY last_seen_at DESC LIMIT ?", (limit,))

    def set_status(self, event_id: int, status: str, verification: str | None = None) -> None:
        if verification:
            self.db.execute("UPDATE events SET status=?, verification=? WHERE id=?", (status, verification, event_id))
        else:
            self.db.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))


class ClaimsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert(self, event_id: int, text: str, state: str, risk_level: str,
               supporting: list, contradicting: list, independent_sources: int) -> int:
        now = utcnow()
        existing = self.db.query_one(
            "SELECT id FROM claims WHERE event_id=? AND text=?", (event_id, text)
        )
        if existing:
            self.db.execute(
                "UPDATE claims SET state=?, risk_level=?, supporting_json=?, contradicting_json=?,"
                " independent_sources=?, updated_at=? WHERE id=?",
                (state, risk_level, json.dumps(supporting, ensure_ascii=False),
                 json.dumps(contradicting, ensure_ascii=False), independent_sources, now, existing["id"]),
            )
            return int(existing["id"])
        cur = self.db.execute(
            "INSERT INTO claims(event_id,text,state,risk_level,supporting_json,contradicting_json,"
            " independent_sources,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (event_id, text, state, risk_level, json.dumps(supporting, ensure_ascii=False),
             json.dumps(contradicting, ensure_ascii=False), independent_sources, now, now),
        )
        return int(cur.lastrowid)

    def for_event(self, event_id: int) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM claims WHERE event_id=? ORDER BY id", (event_id,))


class StoriesRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _slugify(headline: str) -> str:
        import re

        s = re.sub(r"[^\w\u0600-\u06FF]+", "-", headline).strip("-")
        return (s[:60].strip("-") or "story") + "-" + secrets.token_hex(3)

    def create(self, event_id: int, headline: str, lead: str, draft: dict) -> int:
        now = utcnow()
        cur = self.db.execute(
            "INSERT INTO stories(event_id,slug,headline,lead,draft_json,version,status,created_at,updated_at)"
            " VALUES(?,?,?,?,?,1,'DRAFT',?,?)",
            (event_id, self._slugify(headline), headline, lead,
             json.dumps(draft, ensure_ascii=False), now, now),
        )
        story_id = int(cur.lastrowid)
        self.db.execute(
            "INSERT INTO story_versions(story_id,version,snapshot_json,change_note,created_at)"
            " VALUES(?,1,?,?,?)",
            (story_id, json.dumps(draft, ensure_ascii=False), "initial", now),
        )
        return story_id

    def get(self, story_id: int) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM stories WHERE id=?", (story_id,))

    def by_slug(self, slug: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM stories WHERE slug=?", (slug,))

    def by_event(self, event_id: int) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM stories WHERE event_id=? ORDER BY id DESC", (event_id,))

    def published(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT * FROM stories WHERE status IN ('PUBLISHED','CORRECTED') ORDER BY published_at DESC LIMIT ?",
            (limit,),
        )

    def recent(self, hours: int = 48, limit: int = 100) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        return self.db.query(
            "SELECT * FROM stories WHERE status IN ('PUBLISHED','CORRECTED') AND published_at>=? LIMIT ?",
            (cutoff, limit),
        )

    def mark_published(self, story_id: int, status: str = "PUBLISHED") -> None:
        self.db.execute(
            "UPDATE stories SET status=?, published_at=COALESCE(published_at,?), updated_at=? WHERE id=?",
            (status, utcnow(), utcnow(), story_id),
        )

    def set_lifecycle(self, story_id: int, lifecycle: str, note: str = "",
                      new_draft: dict | None = None) -> int:
        """Breaking-news lifecycle transition + audited version snapshot."""
        allowed = ("DETECTED", "VERIFYING", "PROVISIONAL", "CONFIRMED", "CONFLICTING",
                   "DISPUTED", "RETRACTED", "ARCHIVED")
        assert lifecycle in allowed
        story = self.get(story_id)
        if not story:
            raise ValueError("story not found")
        import json as _json

        version = int(story["version"]) + 1
        status_map = {"PROVISIONAL": "PUBLISHED", "CONFIRMED": "PUBLISHED",
                      "CONFIRMED_OFFICIAL": "PUBLISHED", "CONFLICTING": "PUBLISHED",
                      "RETRACTED": "CORRECTED", "DISPUTED": "HELD",
                      "VERIFYING": "HELD", "DETECTED": "DRAFT", "ARCHIVED": "HELD"}
        draft = new_draft if new_draft is not None else _json.loads(story["draft_json"])
        self.db.execute(
            "UPDATE stories SET lifecycle=?, status=?, version=?, draft_json=?, updated_at=? WHERE id=?",
            (lifecycle, status_map.get(lifecycle, "PUBLISHED"), version,
             _json.dumps(draft, ensure_ascii=False), utcnow(), story_id))
        self.db.execute(
            "INSERT OR IGNORE INTO story_versions(story_id,version,snapshot_json,change_note,created_at)"
            " VALUES(?,?,?,?,?)",
            (story_id, version, _json.dumps(draft, ensure_ascii=False),
             f"lifecycle->{lifecycle}" + (f": {note}" if note else ""), utcnow()))
        return version


class PublicationsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def already_sent(self, story_id: int, platform: str, payload_hash: str) -> bool:
        return self.db.query_one(
            "SELECT id FROM publications WHERE story_id=? AND platform=? AND payload_hash=? AND status='SENT'",
            (story_id, platform, payload_hash),
        ) is not None

    def upsert(self, story_id: int, platform: str, payload_hash: str, content_version: int) -> int:
        existing = self.db.query_one(
            "SELECT id FROM publications WHERE story_id=? AND platform=? AND payload_hash=?",
            (story_id, platform, payload_hash),
        )
        if existing:
            return int(existing["id"])
        cur = self.db.execute(
            "INSERT INTO publications(story_id,platform,status,payload_hash,content_version,created_at,updated_at)"
            " VALUES(?,?, 'PENDING',?,?,?,?)",
            (story_id, platform, payload_hash, content_version, utcnow(), utcnow()),
        )
        return int(cur.lastrowid)

    def mark(self, pub_id: int, status: str, remote_id: str | None = None,
             remote_url: str | None = None, error: str | None = None) -> None:
        self.db.execute(
            "UPDATE publications SET status=?, attempt=attempt+1, remote_id=COALESCE(?,remote_id),"
            " remote_url=COALESCE(?,remote_url), error=?, updated_at=? WHERE id=?",
            (status, remote_id, remote_url, error, utcnow(), pub_id),
        )

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM publications ORDER BY id DESC LIMIT ?", (limit,))

    def sent_since(self, since: datetime) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS c FROM publications WHERE status='SENT' AND updated_at>=?",
            (since.isoformat(timespec="seconds"),),
        )
        return int(row["c"]) if row else 0


class JobsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def enqueue(self, job_type: str, payload: dict | None = None, run_after: datetime | None = None,
                max_attempts: int = 5, dedupe_key: str | None = None,
                priority: int = 60) -> int | None:
        now = utcnow()
        if dedupe_key:
            row = self.db.query_one("SELECT id FROM jobs WHERE dedupe_key=?", (dedupe_key,))
            if row:
                return None
        try:
            cur = self.db.execute(
                "INSERT INTO jobs(job_type,payload_json,status,attempts,max_attempts,run_after,"
                "dedupe_key,created_at,updated_at,priority) VALUES(?,?, 'pending',0,?,?,?,?,?,?)",
                (job_type, json.dumps(payload or {}), max_attempts,
                 iso(run_after) or now, dedupe_key, now, now, priority),
            )
            return int(cur.lastrowid)
        except Exception:
            return None  # UNIQUE race on dedupe_key

    def claim_due(self, now: datetime, limit: int = 5) -> list[dict[str, Any]]:
        with self.db.tx() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status='pending' AND run_after<=? ORDER BY priority DESC, id LIMIT ?",
                (now.isoformat(timespec="seconds"), limit),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                conn.execute(
                    f"UPDATE jobs SET status='running', updated_at=? WHERE id IN ({','.join('?' * len(ids))})",
                    (utcnow(), *ids),
                )
        claimed = [dict(r) for r in rows]
        for r in claimed:
            r["status"] = "running"  # reflect the claim in returned rows
        return claimed

    def finish(self, job_id: int, ok: bool, error: str | None = None,
               base_backoff_seconds: int = 30) -> str:
        job = self.db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if job is None:
            return "missing"
        if ok:
            self.db.execute("UPDATE jobs SET status='done', updated_at=?, last_error=NULL WHERE id=?",
                            (utcnow(), job_id))
            return "done"
        attempts = int(job["attempts"]) + 1
        if attempts >= int(job["max_attempts"]):
            self.db.execute("UPDATE jobs SET status='failed', attempts=?, last_error=?, updated_at=? WHERE id=?",
                            (attempts, error, utcnow(), job_id))
            return "failed"
        delay = base_backoff_seconds * (2 ** (attempts - 1))
        run_after = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
        self.db.execute(
            "UPDATE jobs SET status='pending', attempts=?, run_after=?, last_error=?, updated_at=? WHERE id=?",
            (attempts, run_after, error, utcnow(), job_id),
        )
        return "retry"

    def reschedule(self, job_id: int, run_after: datetime) -> None:
        """URGENT-FIX: rate-cap throttle — reschedule WITHOUT consuming a
        failure retry (no attempts increment, stays pending)."""
        self.db.execute(
            "UPDATE jobs SET status='pending', run_after=?, updated_at=? WHERE id=?",
            (run_after.isoformat(timespec="seconds"), utcnow(), job_id))

    def requeue_running(self) -> int:
        """Crash recovery: jobs stuck in 'running' after restart go back to pending."""
        cur = self.db.execute(
            "UPDATE jobs SET status='pending', updated_at=? WHERE status='running'", (utcnow(),)
        )
        return cur.rowcount

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))


class SettingsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._db = db  # fanout platform-registry passthrough

    def get(self, key: str, default: str = "") -> str:
        row = self.db.query_one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def is_paused(self, platform: str | None = None) -> bool:
        if self.get("pause_all") == "1":
            return True
        if platform:
            return self.get(f"pause_platform:{platform}") == "1"
        return False


class LlmCacheRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, cache_key: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM llm_cache WHERE cache_key=?", (cache_key,))

    def put(self, cache_key: str, response_json: str, model: str, prompt_version: str,
            tokens_in: int, tokens_out: int, latency_ms: int) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO llm_cache(cache_key,response_json,model,prompt_version,"
            "tokens_in,tokens_out,latency_ms,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (cache_key, response_json, model, prompt_version, tokens_in, tokens_out, latency_ms, utcnow()),
        )
