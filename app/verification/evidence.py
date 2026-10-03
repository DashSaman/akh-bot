"""PART-4 — canonical EvidenceLink (CORE-007) + independent-origin semantics.

A Claim may have many EvidenceLinks (SUPPORTS / CONTRADICTS / CONTEXT), each
preserving full source provenance (raw_item_id + source_id + lineage_key).
RawItem data is NEVER duplicated — links reference rows only.

Independence is computed from COLLAPSED ORIGINS, never from source count or
source priority (INV-006: priority = speed, never trust):
  - forward/repost copies carry the same lineage_key → one origin
  - endpoints of one identity (CENTCOM EN+AR, Trump X+Truth Social) collapse
    via source_registry.identity_key → one origin
  - Reuters + AP independent reporting → two origins → CORROBORATED
  - OFFICIAL_PRIMARY/PERSON sources are authoritative for «this institution
    SAID X» but are statement evidence, NOT automatic factual confirmation
"""
from __future__ import annotations

from app.db.database import Database
from app.db.repo import utcnow

SUPPORTS = "SUPPORTS"
CONTRADICTS = "CONTRADICTS"
CONTEXT = "CONTEXT"


def record_evidence_link(db: Database, *, claim_id: int, raw_item_id: int,
                         relation: str, observed_at: str | None = None) -> int | None:
    """Idempotent link insert (UNIQUE claim+item+relation). Provenance is read
    from the RawItem row — never copied."""
    if relation not in (SUPPORTS, CONTRADICTS, CONTEXT):
        raise ValueError(f"bad relation: {relation}")
    item = db.query_one(
        "SELECT source_id, lineage_key, published_at, fetched_at FROM raw_items"
        " WHERE id=?", (raw_item_id,))
    if not item:
        return None
    cur = db.execute(
        "INSERT OR IGNORE INTO evidence_links(claim_id, raw_item_id, source_id,"
        " lineage_key, relation, observed_at, created_at) VALUES(?,?,?,?,?,?,?)",
        (claim_id, raw_item_id, item["source_id"], item["lineage_key"] or "",
         relation, observed_at or item["published_at"] or item["fetched_at"],
         utcnow()))
    row = db.query_one(
        "SELECT id FROM evidence_links WHERE claim_id=? AND raw_item_id=?"
        " AND relation=?", (claim_id, raw_item_id, relation))
    return int(row["id"]) if row else None


def _collapsed_origin(lineage_key: str, source_name: str, source_id: int,
                      identity: str = "") -> str:
    """One origin per real-world originator. Priority: the canonical registry
    identity (Entity ID — authoritative, one per org/person), then
    forward/canonical lineage, then registry name identity, then source id."""
    if identity:
        return f"identity:{identity.strip().lower()}"
    if lineage_key:
        return f"lineage:{lineage_key}"
    from app.newsroom.source_registry import identity_key

    ident = identity_key(source_name or "")
    if ident:
        return f"identity:{ident}"
    return f"src:{source_id}"


def independent_origins(db: Database, claim_id: int) -> list[str]:
    """DISTINCT collapsed origins across a claim's SUPPORTS links."""
    rows = db.query(
        "SELECT el.lineage_key, el.source_id, s.name, s.identity FROM evidence_links el"
        " JOIN sources s ON s.id=el.source_id"
        " WHERE el.claim_id=? AND el.relation=?", (claim_id, SUPPORTS))
    return sorted({_collapsed_origin(r["lineage_key"] or "", r["name"],
                                     r["source_id"], r["identity"] or "")
                   for r in rows})


def independent_origin_count(db: Database, claim_id: int) -> int:
    return len(independent_origins(db, claim_id))


def link_counts(db: Database, claim_id: int) -> dict:
    rows = db.query(
        "SELECT relation, COUNT(*) AS c FROM evidence_links WHERE claim_id=?"
        " GROUP BY relation", (claim_id,))
    out = {SUPPORTS: 0, CONTRADICTS: 0, CONTEXT: 0}
    for r in rows:
        out[r["relation"]] = int(r["c"])
    return out


def is_official_origin(db: Database, claim_id: int) -> bool:
    """OFFICIAL_PRIMARY/PERSON_STATEMENT sources among the claim's evidence —
    authoritative for attribution («X said»), never auto-confirmation."""
    rows = db.query(
        "SELECT DISTINCT s.source_role AS role, s.role_detail AS detail"
        " FROM evidence_links el JOIN sources s ON s.id=el.source_id"
        " WHERE el.claim_id=?", (claim_id,))
    return any((r["role"] == "OFFICIAL_PRIMARY")
               or (r["detail"] in ("OFFICIAL_PRIMARY", "PERSON_STATEMENT"))
               for r in rows)
