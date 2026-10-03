"""P3-E — V2 pipeline: RawItem → completeness/context → Claim → claim dedup →
Event matcher → burst → ONE Story → SEND once / EDIT same message.

Wired behind EVENT_ENGINE_V2_ENABLED: when the flag is ON this module IS the
pipeline (process_new_items delegates here); when OFF the V1 path stays
authoritative and this code is inert.

Hard invariants (plan §20/§21, INV-012):
- Event with no public Telegram publication  → SEND once (publish_send)
- Event already published + new unique/MATERIAL claim → Story fields update +
  StoryVersion++ → publish_edit job → EDIT the SAME Telegram message
- an existing SENT publication makes SEND forbidden (runner-side guard too)
- fragments (CONTEXT_ONLY/INCOMPLETE) never publish alone (REG-031/GATE-03)
- non-material claims: evidence stored, public message untouched (P3-F)
- rapid material updates consolidate into ONE debounced EDIT; critical
  corrections bypass the debounce
- low-value content (SPORT/ENTERTAINMENT floor) is stored, never published
- no AI required: deterministic end-to-end; raw Arabic/English/Hebrew is
  HELD (NEEDS_LANGUAGE_PROCESSING), never published
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from app.core.textnorm import sha256_hex
from app.db.database import Database
from app.db.repo import (
    EventsRepo, JobsRepo, PublicationsRepo, RawItemsRepo, SettingsRepo,
    StoriesRepo, SourcesRepo, utcnow,
)
from app.newsroom.burst import assign_burst_group, make_signal
from app.newsroom.claim_compare import resolve_or_insert_claim
from app.newsroom.claim_completeness import CONTEXT_ONLY, evaluate as evaluate_completeness
from app.newsroom.claim_model import ClaimClass, extract_structured
from app.newsroom.event_fingerprint import (
    CONTINUATION_MINUTES, EventFingerprint, decide, extract_fingerprint,
)
from app.newsroom.materiality import is_material_update
from app.newsroom.source_context import resolve_context
from app.newsroom.story_evolution import build_v2_content, render_v2_public_text
from app.publishing.telegram_bot import is_persian_public_text
from app.verification.gates import (
    classify_priority, decide_claim_state, event_can_auto_publish, is_high_risk,
)

log = logging.getLogger("akh.pipeline.v2")

# matcher candidate scan is bounded (§39): never O(all-history)
_CANDIDATE_LIMIT = 20
_MAX_CONTINUATION_MIN = max(CONTINUATION_MINUTES.values())


def _occurred_at(item: dict) -> str:
    return item.get("published_at") or item.get("fetched_at") or utcnow()


def _iso_plus(ts: str, seconds: float) -> str:
    return (datetime.fromisoformat(ts) + timedelta(seconds=seconds)).isoformat()


def _claim_row_to_structured(row: dict):
    from app.newsroom.claim_model import StructuredClaim

    try:
        cls = ClaimClass(row["claim_class"]) if row["claim_class"] else ClaimClass.GENERAL
    except ValueError:
        cls = ClaimClass.GENERAL
    return StructuredClaim(
        claim_class=cls, text=row["text"], source_item_id=row["source_item_id"] or 0,
        actor=row["actor"], location=row["location"], quantity=row["quantity"],
        certainty=row["certainty"] or "ASSERTED", negation=bool(row["negation"]),
    )


def _link_evidence(db, *, claim_id: int, raw_item_id: int, decision: str,
                   occurred: str) -> None:
    """PART-4 EvidenceLink for one claim resolution (idempotent, never blocks)."""
    from app.verification import evidence as ev

    try:
        ev.record_evidence_link(db, claim_id=claim_id, raw_item_id=raw_item_id,
                                relation=ev.CONTRADICTS
                                if decision == "POTENTIAL_CONTRADICTION"
                                else ev.SUPPORTS,
                                observed_at=occurred)
    except Exception:  # noqa: BLE001
        log.exception("evidence link failed claim=%s item=%s", claim_id, raw_item_id)


def _record_run_for(db, *, event_id: int, claim_id: int,
                    raw_item_id: int, decision: str) -> None:
    """PART-4 VerificationRun for one claim resolution (idempotent)."""
    from app.verification import evidence as ev
    from app.verification import runs as vr

    try:
        counts = ev.link_counts(db, claim_id)
        indep = ev.independent_origin_count(db, claim_id)
        row = db.query_one("SELECT state, risk_level FROM claims WHERE id=?", (claim_id,))
        high_risk = bool(row and row["risk_level"] == "high")
        if decision == "POTENTIAL_CONTRADICTION":
            # the contradicting claim keeps its own SUPPORTS trace; this run
            # records the conflict without choosing a side (no fabricated resolution)
            vr.record_run(
                db, event_id=event_id, claim_id=claim_id, trigger=vr.CONTRADICTION,
                result=row["state"] if row else "CONFLICTING",
                independent_origin_count=indep, support_count=counts[ev.SUPPORTS],
                contradiction_count=max(1, counts[ev.CONTRADICTS]),
                high_risk=high_risk,
                reason_codes=[decision] + (["HIGH_RISK"] if high_risk else []),
                next_verify_seconds=vr.REVERIFY_INTERVAL_SECONDS,
                dedupe_key="contra:%s:%s:%s" % (event_id, claim_id, raw_item_id))
        else:
            vr.record_run(
                db, event_id=event_id, claim_id=claim_id, trigger=vr.NEW_EVIDENCE,
                result=row["state"] if row else "UNVERIFIED",
                independent_origin_count=indep, support_count=counts[ev.SUPPORTS],
                contradiction_count=counts[ev.CONTRADICTS], high_risk=high_risk,
                reason_codes=[decision] + (["HIGH_RISK"] if high_risk else []),
                next_verify_seconds=vr.REVERIFY_INTERVAL_SECONDS
                if (row and row["state"] in ("UNVERIFIED", "SINGLE_SOURCE", "CONFLICTING"))
                else None,
                dedupe_key="ev:%s:%s:%s" % (event_id, claim_id, raw_item_id))
    except Exception:  # noqa: BLE001 — traceability must never block the pipeline
        log.exception("verification trace failed claim=%s item=%s", claim_id, raw_item_id)


def _independent_origins(db, claim_id: int) -> int:
    """Canonical independent-origin count: EvidenceLink origins with identity
    collapse (PART-4). Falls back to claim_source_items lineages for legacy
    claims that predate evidence links."""
    from app.verification import evidence as _ev

    n_links = db.query_one(
        "SELECT COUNT(*) AS n FROM evidence_links WHERE claim_id=?", (claim_id,))["n"]
    if n_links:
        return _ev.independent_origin_count(db, claim_id)
    rows = db.query(
        "SELECT DISTINCT COALESCE(NULLIF(r.lineage_key,''), 'src:' || r.source_id) AS lineage"
        " FROM claim_source_items csi JOIN raw_items r ON r.id=csi.source_item_id"
        " WHERE csi.claim_id=?", (claim_id,))
    return len(rows)


def _store_claim_verification(db, claim_id: int, has_contradiction: bool) -> dict:
    """Verification fields for a structured claim (V1 gate parity)."""
    row = db.query_one("SELECT * FROM claims WHERE id=?", (claim_id,))
    indep = _independent_origins(db, claim_id)
    risk = "high" if is_high_risk(row["text"]) else "normal"
    state = decide_claim_state(row["text"], independent_sources=indep,
                               has_contradiction=has_contradiction, risk=risk)
    db.execute("UPDATE claims SET state=?, risk_level=?, independent_sources=? WHERE id=?",
               (state, risk, indep, claim_id))
    return {"id": claim_id, "text": row["text"], "state": state,
            "risk_level": risk, "independent_sources": indep}


def _candidate_events(db, item_time: str) -> list[dict]:
    cutoff = _iso_plus(item_time, -_MAX_CONTINUATION_MIN * 60)
    return db.query(
        "SELECT * FROM events WHERE (state='OPEN' OR state IS NULL)"
        " AND status IN ('NEW','CLUSTERED','READY','HELD','PUBLISHED')"
        " AND last_seen_at >= ? ORDER BY last_seen_at DESC LIMIT ?",
        (cutoff, _CANDIDATE_LIMIT))


def _find_same_claim_event(db, claim, occurred: str) -> int | None:
    """REG-038 cross-event guard: a new item whose claim is the SAME_CLAIM —
    or a near-identical paraphrase — of an existing one joins that claim's
    event and never creates a duplicate one. Exact structural fingerprints
    match regardless of age (cheap equality); lexical near-dups are bounded."""
    from app.newsroom.claim_compare import _STOP, _jaccard, _tokens, compare

    def _content_toks(t: str) -> set:
        return _tokens(t) - _STOP

    if claim.fingerprint:
        row = db.query_one(
            "SELECT c.*, c.event_id AS eid FROM claims c WHERE c.fingerprint=?"
            " ORDER BY c.id DESC LIMIT 1", (claim.fingerprint,))
        if row:
            return int(row["eid"])
    item_toks = _content_toks(claim.text)
    if not item_toks:
        return None
    rows = db.query(
        "SELECT c.*, c.event_id AS eid FROM claims c JOIN events e ON e.id=c.event_id"
        " ORDER BY c.id DESC LIMIT 40")
    for row in rows:
        ex = _claim_row_to_structured(row)
        decision = compare(claim, ex).decision
        if decision in ("SAME_CLAIM", "POTENTIAL_CONTRADICTION"):
            # SAME: paraphrase joins its event; CONTRADICTION: a differing
            # figure/negation about the same happening joins the event it
            # contradicts — the conflict is preserved and traced, never merged
            return int(row["eid"])
        if decision == "AMBIGUOUS_CLAIM" \
                and _jaccard(item_toks, _content_toks(row["text"])) >= 0.6:
            return int(row["eid"])
    return None


def _event_fingerprint_of(db, event_row: dict) -> EventFingerprint:
    """Candidate fingerprint = the event's CURRENT claim union (the event is
    the union of its claims, so matching tracks evolution), enriched with the
    stored V2 columns. Falls back to title-based extraction for legacy events."""
    claims = db.query(
        "SELECT text, actor, location, negation FROM claims WHERE event_id=? ORDER BY id"
        " LIMIT 30", (event_row["id"],))
    if not claims:
        return extract_fingerprint(event_row["title"],
                                   occurred_at=event_row.get("last_seen_at"))
    from app.newsroom.event_fingerprint import detect_second_occurrence, tokens as _tok

    toks: set[str] = set()
    actors: set[str] = set()
    location = None
    second = False
    for c in claims:
        toks |= _tok(c["text"] or "")
        if c["actor"]:
            actors.add(c["actor"].strip().lower())
        if c["location"] and not location:
            location = c["location"]
        second = second or detect_second_occurrence(c["text"] or "")
    etype = event_row.get("event_type") or "GENERAL_NEWS"
    return EventFingerprint(
        primary_actors=sorted(actors), predicate_tokens=toks, object_tokens=set(),
        location=location, event_type=etype,
        topic=",".join(sorted(toks))[:120],
        conversation_context_ref=event_row.get("context_ref") or None,
        occurred_at=event_row.get("last_seen_at"), second_occurrence=second)


def process_item_v2(db: Database, item: dict) -> dict | None:
    """Completeness → context → claim → dedup → event → burst for one item.
    Returns the touched event_id (or None for fragment/store-only items).
    Fragments never create claims/events/stories (REG-031)."""
    items_repo = RawItemsRepo(db)
    text = item["text"] or ""
    occurred = _occurred_at(item)
    ctx = resolve_context(db, source_id=item["source_id"], raw_item_id=item["id"],
                          text=text, now=occurred,
                          ttl_seconds=_ttl(db))
    speaker_hint = (ctx.inherited or {}).get("speaker")
    comp = evaluate_completeness(text, source_language=item.get("language") or "fa",
                                 speaker_hint=speaker_hint)
    if comp.state in (CONTEXT_ONLY, "INCOMPLETE"):
        items_repo.set_state(item["id"], "PROCESSED")
        return None  # context stored above; 0 claim/event/story/publication
    if not item["activation_ok"]:
        items_repo.set_state(item["id"], "PROCESSED")  # STORE_ONLY backfill guard
        return None

    # structured claim with inherited speaker (REG-039) recorded on the claim
    claim = extract_structured(text, source_item_id=item["id"],
                               speaker_hint=speaker_hint)
    if ctx.inherited:
        claim.extra["inherited_context_ref"] = ctx.inherited["context_ref"]

    # event matching (bounded candidates, hard conflicts force CREATE_NEW);
    # REG-038 cross-event guard runs FIRST: a paraphrase of an existing recent
    # claim must join that claim's event, never create a duplicate one
    fp = extract_fingerprint(
        text, actor=claim.actor, occurred_at=occurred,
        conversation_context_ref=(ctx.inherited or {}).get("context_ref"))
    events_repo = EventsRepo(db)
    event_id = _find_same_claim_event(db, claim, occurred)
    if event_id is not None:
        events_repo.attach(event_id, item["id"], is_duplicate=False)
    else:
        decision = decide(fp, [(e["id"], _event_fingerprint_of(db, e))
                               for e in _candidate_events(db, occurred)], occurred)
        if decision.decision == "ATTACH_EXISTING" and decision.candidate_event_id:
            event_id = int(decision.candidate_event_id)
            events_repo.attach(event_id, item["id"], is_duplicate=False)
            db.execute("UPDATE events SET state='OPEN' WHERE id=? AND state IS NULL", (event_id,))
        else:  # CREATE_NEW / AMBIGUOUS_EVENT → provisional separate event, never contaminate
            title = (claim.actor + ": " if claim.actor else "") + text.strip().split("\n")[0][:120]
            event_id = events_repo.create(title, first_item={"id": item["id"]})
            db.execute(
                "UPDATE events SET fingerprint_json=?, event_type=?, context_ref=?,"
                " state='OPEN', epoch=? WHERE id=?",
                (fp.to_json(), fp.event_type, (ctx.inherited or {}).get("context_ref") or "",
                 occurred, event_id))
    events_repo.recompute(event_id)

    # claim dedup within the event (SAME/NEW/CONTRADICTION/AMBIGUOUS)
    claim_id, cdec = resolve_or_insert_claim(db, event_id, claim, item["id"])
    # PART-4: EvidenceLink first — origin counts and runs read from it
    _link_evidence(db, claim_id=claim_id, raw_item_id=item["id"],
                   decision=cdec.decision, occurred=occurred)
    info = _store_claim_verification(db, claim_id, cdec.decision == "POTENTIAL_CONTRADICTION")
    if cdec.decision == "NEW_CLAIM":
        priors = [_claim_row_to_structured(r) for r in db.query(
            "SELECT * FROM claims WHERE event_id=? AND id!=? ORDER BY id", (event_id, claim_id))]
        material, reasons = is_material_update(claim, priors)
        db.execute("UPDATE claims SET material=?, material_reasons=? WHERE id=?",
                   (1 if material else 0, ",".join(reasons), claim_id))
    elif cdec.decision == "SAME_CLAIM":
        # a NEW independent origin corroborating an existing claim is itself a
        # material status change (e.g. single-source → corroborated)
        before = info["independent_sources"]
        indep_now = _independent_origins(db, claim_id)
        if indep_now > before >= 1:
            db.execute("UPDATE claims SET material=1, material_reasons=? WHERE id=?",
                       ("CORROBORATION", claim_id))
            _store_claim_verification(db, claim_id, has_contradiction=False)

    # PART-4: VerificationRun after state updates (result = final state)
    _record_run_for(db, event_id=event_id, claim_id=claim_id,
                    raw_item_id=item["id"], decision=cdec.decision)

    # burst grouping — informational only, never delays anything (REG-037)
    try:
        assign_burst_group(db, make_signal(item["source_id"], text, occurred,
                                           context_ref=(ctx.inherited or {}).get("context_ref", "")),
                           raw_item_id=item["id"],
                           window_seconds=_burst_window(db))
    except Exception:  # noqa: BLE001 — grouping must never block the news flow
        log.exception("burst grouping failed for item %s", item["id"])
    items_repo.set_state(item["id"], "PROCESSED")
    return event_id


def _ttl(db) -> int:
    row = db.query_one("SELECT value AS v FROM settings WHERE key='source_context_ttl_seconds'")
    return int(row["v"]) if row else 1800


def _burst_window(db) -> int:
    row = db.query_one("SELECT value AS v FROM settings WHERE key='event_burst_window_seconds'")
    return int(row["v"]) if row else 180


# ---------------------------------------------------------------- publication

def _last_sent(db, story_id: int, platform: str = "telegram") -> dict | None:
    return db.query_one(
        "SELECT * FROM publications WHERE story_id=? AND platform=? AND status='SENT'"
        " ORDER BY id DESC LIMIT 1", (story_id, platform))


def _enqueue_send(db, settings, story_id: int, text: str, ph: str, pub_id: int,
                  lifecycle: str) -> None:
    priority = 100 if lifecycle in ("PROVISIONAL", "CONFIRMED") else 60
    JobsRepo(db).enqueue(
        "publish_send",
        {"story_id": story_id, "platform": "telegram", "payload_hash": ph,
         "text": text, "publication_id": pub_id},
        dedupe_key="send:%s:telegram:%s" % (story_id, ph[:16]), priority=priority)


def _enqueue_edit(db, settings, story_id: int, text: str, ph: str, pub_id: int,
                  critical: bool) -> None:
    """Debounced EDIT: rapid material updates consolidate into one job;
    critical corrections bypass the debounce (P3-F §24/§33)."""
    now = datetime.now(timezone.utc)
    pending = [j for j in db.query(
        "SELECT * FROM jobs WHERE job_type='publish_edit' AND status='pending'"
        " ORDER BY id DESC LIMIT 10")
        if json.loads(j["payload_json"] or "{}").get("story_id") == story_id]
    if pending:
        job = pending[0]
        payload = json.loads(job["payload_json"])
        old_pub = int(payload.get("publication_id") or 0)
        payload.update({"text": text, "payload_hash": ph, "publication_id": pub_id})
        db.execute("UPDATE jobs SET payload_json=?, updated_at=? WHERE id=?",
                   (json.dumps(payload, ensure_ascii=False), utcnow(), job["id"]))
        if old_pub and old_pub != pub_id:
            PublicationsRepo(db).mark(old_pub, "SKIPPED", error="SUPERSEDED_BY_DEBOUNCE")
        return
    run_after = now
    if not critical:
        debounce = int(getattr(settings, "edit_debounce_seconds", 120))
        run_after = now + timedelta(seconds=debounce)
        for done in db.query(
                "SELECT payload_json, updated_at AS u FROM jobs WHERE"
                " job_type='publish_edit' AND status='done' ORDER BY id DESC LIMIT 10"):
            try:
                if json.loads(done["payload_json"]).get("story_id") != story_id:
                    continue
                last = datetime.fromisoformat(done["u"].replace("Z", "+00:00"))
                if (now - last).total_seconds() < debounce:
                    run_after = last + timedelta(seconds=debounce)
                break
            except (ValueError, TypeError):
                continue
    JobsRepo(db).enqueue(
        "publish_edit",
        {"story_id": story_id, "platform": "telegram", "payload_hash": ph,
         "text": text, "publication_id": pub_id},
        run_after=run_after,
        dedupe_key="edit:%s:telegram:%s" % (story_id, ph[:16]), priority=90)


def _publish_event(db, settings, brand, event: dict, summary: dict) -> None:
    """Publication/evolution decision for one event: SEND once, or material
    EDIT of the same message, or HOLD. Deterministic; no AI."""
    stories = StoriesRepo(db)
    story = stories.by_event(event["id"])
    claims = db.query("SELECT * FROM claims WHERE event_id=? ORDER BY id", (event["id"],))
    items = [i for i in EventsRepo(db).items(event["id"]) if i["activation_ok"]]
    if not claims or not items:
        return
    pub_policies = {s["id"]: s.get("publication_policy", "AUTO")
                    for s in SourcesRepo(db).list()}
    if story is None and all(pub_policies.get(i["source_id"], "AUTO") != "AUTO" for i in items):
        EventsRepo(db).set_status(event["id"], "HELD")
        return

    from app.newsroom.pipeline import _event_has_eligible, source_display_names

    src_names = source_display_names(db, event["id"])
    if not src_names and _event_has_eligible(db, event["id"]):
        EventsRepo(db).set_status(event["id"], "HELD")  # GATE-11 fail-closed
        return

    ok, reason = event_can_auto_publish([dict(c) for c in claims])
    content = build_v2_content(event, [dict(c) for c in claims],
                               max_details=int(getattr(settings, "max_public_story_details", 5)))
    if content is None:
        EventsRepo(db).set_status(event["id"], "HELD")  # CONTENT_QUALITY_HOLD
        log.info("V2 CONTENT_QUALITY_HOLD event %s", event["id"], extra={"event_id": event["id"]})
        return
    text = render_v2_public_text(content, brand, src_names)
    ph = sha256_hex(text)

    if story is None:
        if not ok:
            EventsRepo(db).set_status(event["id"], "HELD",
                                      "CONFLICTING" if reason == "CONFLICTING_CLAIMS" else "SINGLE_SOURCE")
            return
        topic, weight = classify_priority(content["headline"] + " " + " ".join(
            c["text"] for c in claims))
        if weight <= 20:  # importance floor: stored, not published (PUB-003)
            EventsRepo(db).set_status(event["id"], "HELD")
            log.info("V2 LOW_PUBLICATION_VALUE event %s (topic=%s)", event["id"], topic)
            return
        if not is_persian_public_text(text):
            EventsRepo(db).set_status(event["id"], "HELD")  # NEEDS_LANGUAGE_PROCESSING
            log.info("V2 NEEDS_LANGUAGE_PROCESSING event %s", event["id"])
            return
        draft = {"headline": content["headline"], "lead": content["lead"],
                 "details": content["details"], "source_names": src_names,
                 "platform_variants": {"telegram": text}, "generation_mode": "DETERMINISTIC",
                 "claim_refs": [str(c["id"]) for c in claims],
                 "language": "fa", "topic": "V2"}
        story_id = stories.create(event["id"], content["headline"], content["lead"], draft)
        db.execute("UPDATE stories SET lifecycle=? WHERE id=?", (content["lifecycle"], story_id))
        pub_id = PublicationsRepo(db).upsert(story_id, "telegram", ph, 1)
        _enqueue_send(db, settings, story_id, text, ph, pub_id, content["lifecycle"])
        EventsRepo(db).set_status(event["id"], "PUBLISHED")
        summary["stories"] += 1
        summary["sends"] += 1
        return

    # story exists ---------------------------------------------------------
    sent = _last_sent(db, story["id"])
    if sent is None:
        # never published: first SEND (publish_send guard forbids a second)
        if not ok or not is_persian_public_text(text):
            return
        current = stories.get(story["id"])
        if current["headline"] != content["headline"] or current["lead"] != content["lead"]:
            stories.set_lifecycle(story["id"], content["lifecycle"],
                                  "V2 content refresh before first send",
                                  {"headline": content["headline"], "lead": content["lead"],
                                   "details": content["details"],
                                   "platform_variants": {"telegram": text}})
        pub_id = PublicationsRepo(db).upsert(story["id"], "telegram", ph,
                                             int(stories.get(story["id"])["version"]))
        _enqueue_send(db, settings, story["id"], text, ph, pub_id, content["lifecycle"])
        EventsRepo(db).set_status(event["id"], "PUBLISHED")
        summary["sends"] += 1
        return

    # SENT exists → EDIT-only invariant
    material_rows = db.query(
        "SELECT * FROM claims WHERE event_id=? AND material=1", (event["id"],))
    if not material_rows:
        return  # non-material: evidence stored, message untouched
    if not ok:
        return  # contradiction/single-source: a verification matter, not an edit
    if ph == sent["payload_hash"]:
        db.execute("UPDATE claims SET material=0 WHERE event_id=? AND material=1", (event["id"],))
        return
    critical = any("CORRECTION" in (r["material_reasons"] or "")
                   for r in material_rows)  # a corrected fact goes out NOW
    stories.set_lifecycle(story["id"], content["lifecycle"],
                          "material update: " + ",".join(sorted({
                              x for r in material_rows for x in (r["material_reasons"] or "").split(",") if x})),
                          {"headline": content["headline"], "lead": content["lead"],
                           "details": content["details"],
                           "platform_variants": {"telegram": text}})
    version = int(stories.get(story["id"])["version"])
    pub_id = PublicationsRepo(db).upsert(story["id"], "telegram", ph, version)
    _enqueue_edit(db, settings, story["id"], text, ph, pub_id, critical)
    db.execute("UPDATE claims SET material=0 WHERE event_id=? AND material=1", (event["id"],))
    summary["edits"] += 1


def process_new_items_v2(db: Database, brand, settings) -> dict:
    """One V2 pass. Idempotent; deterministic; 0 AI. Safe to re-run."""
    summary: dict = {"processed": 0, "touched": set(), "stories": 0,
                     "sends": 0, "edits": 0}
    SettingsRepo(db).set("pipeline_last_run", utcnow())
    from app.newsroom.pipeline import _resolve_deadlines

    _resolve_deadlines(db, settings, brand)

    # phase 1 — per-item: completeness/context/claim/dedup/event/burst
    for item in RawItemsRepo(db).list(limit=100, only_new=True, order="ASC"):
        event_id = process_item_v2(db, item)
        summary["processed"] += 1
        if event_id is not None:
            summary["touched"].add(event_id)

    # phase 2 — publication/evolution for touched events + active scan
    events_repo = EventsRepo(db)
    seen: set[int] = set()
    for event_id in sorted(summary["touched"]):
        ev = events_repo.get(event_id)
        if ev and event_id not in seen:
            _publish_event(db, settings, brand, ev, summary)
            seen.add(event_id)
    for ev in events_repo.list(limit=80):
        if ev["status"] in ("NEW", "CLUSTERED", "READY", "HELD") and ev["id"] not in seen:
            _publish_event(db, settings, brand, ev, summary)
            seen.add(ev["id"])

    # phase 3 — PART-4 standing reverify: one SCHEDULED_REVERIFY run per
    # unresolved event per 5-minute slot (deduped); prompt re-checks happen
    # naturally via NEW_EVIDENCE runs in phase 1
    _scheduled_reverify(db)

    summary["touched"] = len(summary["touched"])
    return summary


def _scheduled_reverify(db) -> int:
    """Record scheduled reverify runs for unresolved events (dedupe per slot).
    Also refreshes event-level last_verified_at so nothing stays stale."""
    from app.verification import evidence as ev
    from app.verification import runs as vr

    recorded = 0
    try:
        for evrow in db.query(
                "SELECT DISTINCT e.id, e.status FROM events e"
                " LEFT JOIN claims c ON c.event_id=e.id"
                " WHERE e.status IN ('NEW','CLUSTERED','READY','HELD')"
                "    OR c.state IN ('UNVERIFIED','SINGLE_SOURCE','CONFLICTING')"
                " ORDER BY e.last_seen_at DESC LIMIT 40"):
            event_id = int(evrow["id"])
            if not vr.scheduled_reverify_due(db, event_id=event_id):
                continue
            claims = db.query(
                "SELECT id, state, risk_level FROM claims WHERE event_id=? ORDER BY id LIMIT 30",
                (event_id,))
            unresolved = [c for c in claims
                          if c["state"] in ("UNVERIFIED", "SINGLE_SOURCE", "CONFLICTING")]
            if not unresolved and evrow["status"] != "HELD":
                continue  # nothing to reverify on a clean unpublished event
            contra = sum(1 for c in claims if c["state"] == "CONFLICTING")
            high = any(c["risk_level"] == "high" for c in claims)
            max_indep = 0
            for c in unresolved or claims[:5]:
                max_indep = max(max_indep, ev.independent_origin_count(db, int(c["id"])))
            vr.record_run(
                db, event_id=event_id, claim_id=None, trigger=vr.SCHEDULED_REVERIFY,
                result="STILL_UNRESOLVED" if unresolved else "NO_CHANGE",
                independent_origin_count=max_indep,
                contradiction_count=contra, high_risk=high,
                reason_codes=[c["state"] for c in unresolved[:5]] or ["EVENT_HELD"],
                next_verify_seconds=vr.REVERIFY_INTERVAL_SECONDS,
                dedupe_key="reverify:%s:0:%s" % (event_id, vr.due_reverify_slot()))
            db.execute("UPDATE events SET last_verified_at=? WHERE id=?",
                       (utcnow(), event_id))
            recorded += 1
    except Exception:  # noqa: BLE001 — reverify bookkeeping must never block
        log.exception("scheduled reverify recording failed")
    return recorded
