"""Pipeline orchestrator: NEW items → dedup → cluster → claims → gates → writer →
auditor → story → enqueue publications. Each stage is small and independently testable.

If the LLM is not configured, events simply wait (never crash, never fake success).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.brand import Brand
from app.clustering.dedup import classify_duplicate, find_or_create_event
from app.core.textnorm import sha256_hex
from app.db.database import Database
from app.db.repo import (
    ClaimsRepo, EventsRepo, JobsRepo, PublicationsRepo, RawItemsRepo, SettingsRepo,
    StoriesRepo, SourcesRepo,
)
from app.integrations.llm.base import LLMProvider, wrap_untrusted
from app.newsroom.auditor import audit_draft
from app.newsroom.models import (
    CLAIMS_SYSTEM, StoryDraft, build_writer_user_prompt,
)
from app.verification.gates import decide_claim_state, event_can_auto_publish, is_high_risk
from app.publishing.fanout import distribution_plan

log = logging.getLogger("akh.pipeline")


def ingest_classify_and_cluster(db: Database, item: dict[str, Any]) -> dict[str, Any]:
    """Dedup + event assignment for one NEW raw item (pure DB logic, no LLM)."""
    items = RawItemsRepo(db)
    fp_row = db.query_one(
        "SELECT * FROM item_fingerprints WHERE raw_item_id=?", (item["id"],)
    )
    fp = {
        "canonical_url_hash": fp_row["canonical_url_hash"],
        "content_hash": fp_row["content_hash"],
        "title_norm_hash": fp_row["title_norm_hash"],
        "simhash": fp_row["simhash"],
    }
    dup = classify_duplicate(items, fp, item["text"], exclude_item_id=item["id"])
    events = EventsRepo(db)
    event_id = find_or_create_event(events, items, item, dup)
    stats = events.recompute(event_id)
    items.set_state(item["id"], "PROCESSED")
    return {"event_id": event_id, "duplicate": dup.is_duplicate,
            "duplicate_stage": dup.stage, **stats}


def build_claim_evidence(event: dict[str, Any], items: list[dict[str, Any]],
                         verification_flags: dict[int, int] | None = None) -> list[dict[str, Any]]:
    """Group reports into (claim-text → origins) from item text without an LLM.

    TRUST RULE: only sources the OWNER approved for verification
    (verification_allowed=1) contribute independent VERIFICATION origins.
    Independence is governed by LINEAGE (forward/canonical-origin collapse),
    not by the duplicate flag — two outlets legitimately share one event.
    """
    reports = [i for i in items if i["activation_ok"]]
    by_key: dict[str, dict[str, Any]] = {}
    for i in reports:
        key_lines = [ln.strip() for ln in (i["title"] + "\n" + i["text"]).splitlines() if 25 < len(ln.strip()) < 300]
        for ln in key_lines[:5]:
            k = sha256_hex(ln)[:16]
            slot = by_key.setdefault(k, {"text": ln, "trusted": set(), "items": []})
            if (verification_flags or {}).get(i["source_id"], 0):
                slot["trusted"].add(i["lineage_key"] or f"src:{i['source_id']}")
            slot["items"].append({"item_id": i["id"], "source_id": i["source_id"], "quote": ln[:200]})
    return [
        {"text": v["text"], "supporting": v["items"], "independent": len(v["trusted"])}
        for v in by_key.values()
    ]


async def llm_extract_claims(provider: LLMProvider, event: dict[str, Any],
                             items: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    reports = [i for i in items if not i["is_duplicate"]]
    if not reports:
        return None
    evidence = wrap_untrusted("\n\n".join(
        f"[item {i['id']} | source {i['source_id']} | {i['title']}]\n{i['text'][:1200]}"
        for i in reports[:12]
    ))
    result = await provider.chat_json(
        system=CLAIMS_SYSTEM,
        user=("Extract atomic claims from these reports. Report metadata:\n"
              f"event: {event['title']}\n{evidence}"),
        max_tokens=3000, temperature=0.0,
    )
    raw_claims = result.get("claims") or []
    if not isinstance(raw_claims, list):
        return None
    return [c for c in raw_claims if isinstance(c, str) and c.strip()][:25]


def merge_and_verify_claims(db: Database, event_id: int,
                            baseline: list[dict[str, Any]],
                            llm_claims: list[str] | None) -> list[dict[str, Any]]:
    """Combine LLM atomic claims with lineage evidence, then apply hard gates."""
    claims_repo = ClaimsRepo(db)
    claims: list[dict[str, Any]] = []
    if llm_claims:
        # attach each atomic claim to the most overlapping baseline evidence group
        for text in llm_claims:
            best, best_overlap = None, 0
            for b in baseline:
                words_a = set(text.split())
                words_b = set(b["text"].split())
                overlap = len(words_a & words_b)
                if overlap > best_overlap:
                    best, best_overlap = b, overlap
            risk = "high" if is_high_risk(text) else "normal"
            indep = best["independent"] if best else 1
            # contradiction detection: same risk class, different numbers, >=2 origins
            has_conflict = False
            from app.verification.gates import numbers_in

            nums = numbers_in(text)
            if nums and best:
                for other in baseline:
                    if other is best:
                        continue
                    o_words = set(other["text"].split()) & set(text.split())
                    o_nums = numbers_in(other["text"])
                    if len(o_words) >= 4 and o_nums and not (o_nums & nums):
                        has_conflict = True
                        break
            state = decide_claim_state(text, independent_sources=indep,
                                       has_contradiction=has_conflict, risk=risk)
            claims.append({
                "text": text, "state": state, "risk_level": risk,
                "supporting": best["supporting"] if best else [],
                "contradicting": [], "independent_sources": indep,
            })
    else:
        for b in baseline:
            risk = "high" if is_high_risk(b["text"]) else "normal"
            state = decide_claim_state(b["text"], independent_sources=b["independent"],
                                       has_contradiction=False, risk=risk)
            claims.append({
                "text": b["text"], "state": state, "risk_level": risk,
                "supporting": b["supporting"], "contradicting": [],
                "independent_sources": b["independent"],
            })
    for c in claims:
        claims_repo.upsert(event_id, c["text"], c["state"], c["risk_level"],
                           c["supporting"], c["contradicting"], c["independent_sources"])
    return claims_repo.for_event(event_id)


def _public_text_for(det, brand, mode="hidden"):
    from app.publishing.telegram_bot import build_public_text
    return build_public_text(det["lifecycle"], det["body"], brand, mode, True)


def _create_and_enqueue(db, settings, brand, event_id, det):
    from app.publishing.telegram_bot import build_public_text
    text = build_public_text(det["lifecycle"], det["body"], brand, "hidden", True)
    draft = {"headline": det["body"].split("chr(10)")[0][:120], "lead": det["body"],
             "platform_variants": {"telegram": text},
             "generation_mode": "DETERMINISTIC", "claim_refs": det.get("claim_refs", [])}
    story_id = StoriesRepo(db).create(event_id, draft["headline"], draft["lead"], draft)
    db.execute("UPDATE stories SET lifecycle=? WHERE id=?",
               ("PROVISIONAL" if det["lifecycle"] == "PROVISIONAL" else "CONFIRMED", story_id))
    _enqueue_platforms(db, settings, story_id, text, det["lifecycle"])
    return story_id


def _publish_deterministic(db, settings, brand, story, det, lifecycle):
    from app.publishing.telegram_bot import build_public_text
    text = build_public_text(det["lifecycle"], det["body"], brand, "hidden", True)
    draft = {"headline": det["body"].split("chr(10)")[0][:120], "lead": det["body"],
             "platform_variants": {"telegram": text},
             "generation_mode": "DETERMINISTIC", "claim_refs": det.get("claim_refs", [])}
    StoriesRepo(db).set_lifecycle(story["id"], lifecycle, "evidence changed (reverify)", draft)
    _enqueue_platforms(db, settings, story["id"], text, lifecycle)


def _enqueue_platforms(db, settings, story_id, text, lifecycle):
    from app.db.repo import SettingsRepo
    ph = sha256_hex(text)
    repo = SettingsRepo(db)
    for platform in distribution_plan(lifecycle, settings, repo):
        if platform == "website_preview":
            continue
        pid = PublicationsRepo(db).upsert(story_id, platform, ph, 1)
        JobsRepo(db).enqueue(
            "publish_%s" % platform,
            {"story_id": story_id, "platform": platform, "payload_hash": ph,
             "text": text, "publication_id": pid},
            dedupe_key="pub:%s:%s:%s" % (platform, story_id, ph[:16]),
            priority=100 if lifecycle in ("PROVISIONAL", "CONFIRMED") else 60)

def llm_budget_ok(db: Database, settings: Any) -> bool:
    """Cost guard: real LLM calls are recorded in llm_cache; cap them per minute/hour."""
    if settings is None:
        return True
    now = datetime.now(timezone.utc)
    for seconds, limit in ((60, getattr(settings, "max_llm_calls_per_minute", 30)),
                           (3600, getattr(settings, "max_llm_calls_per_hour", 500))):
        if limit <= 0:
            continue
        cutoff = (now - timedelta(seconds=seconds)).isoformat(timespec="seconds")
        n = db.query_one("SELECT COUNT(*) c FROM llm_cache WHERE created_at>=?", (cutoff,))["c"]
        if n >= limit:
            log.warning("llm budget exceeded: %s calls in %ss (limit %s)", n, seconds, limit)
            return False
    return True


ACTIVE_EVENT_STATUSES = ("NEW", "CLUSTERED", "READY", "HELD")


def deterministic_story_text(lifecycle: str, event: dict[str, Any],
                             claims: list[dict[str, Any]], items: list[dict[str, Any]],
                             source_roles: dict[int, str]) -> dict[str, Any]:
    """NO-AI safe templates: ONLY structured known fields, no invented prose.
    Returns draft dict with a telegram variant; caller applies brand footer."""
    official = any(source_roles.get(i["source_id"]) == "OFFICIAL_PRIMARY" for i in items)
    if lifecycle == "CONFIRMED" and claims:
        main = next((c for c in claims if c["state"] in ("CONFIRMED", "CORROBORATED")), claims[0])
        if official:
            body = ("[سازمان رسمی] در اطلاعیه‌ای اعلام کرد:\n" + main["text"])
            status = "CONFIRMED_OFFICIAL"
        else:
            body = ("بر پایه گزارش‌های رسیده:\n" + main["text"] +
                    "\nاین موارد از منابع تحت پایش راسته تأیید شده است.")
            status = "CONFIRMED"
    else:
        body = ("گزارش‌هایی درباره «" + event["title"][:120] + "» منتشر شده است.\n"
                "این اطلاعات تاکنون به‌طور مستقل تأیید نشده است.")
        status = "PROVISIONAL"
    return {"lifecycle": status, "body": body,
            "claim_refs": [str(c["id"]) for c in claims[:3]]}


async def process_new_items(db: Database, provider: LLMProvider | None,
                            brand: Brand, settings: Any) -> dict[str, Any]:
    """One pipeline pass over NEW items. Idempotent; safe to re-run."""
    items_repo = RawItemsRepo(db)
    events_repo = EventsRepo(db)
    stories = StoriesRepo(db)
    jobs = JobsRepo(db)
    summary: dict[str, Any] = {"processed": 0, "new_events": set(), "stories": 0}

    # oldest first: the first occurrence must own the event before copies attach
    for item in items_repo.list(limit=100, only_new=True, order="ASC"):
        if not item["activation_ok"]:
            items_repo.set_state(item["id"], "PROCESSED")  # STORE_ONLY: backfill protection
            summary["processed"] += 1
            continue
        result = ingest_classify_and_cluster(db, item)
        summary["processed"] += 1
        summary["new_events"].add(result["event_id"])
    summary["new_events"] = len(summary["new_events"])

    # active events: NEW/CLUSTERED/READY plus HELD (NEVER terminal) — re-verified
    # every pass; existing stories are UPDATED, not skipped (no starvation).
    verification_flags = {
        s["id"]: s["verification_allowed"] for s in SourcesRepo(db).list()
    }
    source_roles = {s["id"]: s["source_role"] for s in SourcesRepo(db).list()}
    llm_allowed = provider is not None and llm_budget_ok(db, settings)
    for event in events_repo.list(limit=80):
        if event["status"] not in ACTIVE_EVENT_STATUSES:
            continue
        existing_story = stories.by_event(event["id"])
        event_items = events_repo.items(event["id"])
        eligible = [i for i in event_items if i["activation_ok"]]
        if not eligible:
            continue
        baseline = build_claim_evidence(event, event_items, verification_flags)
        llm_claims: list[str] | None = None
        if provider is not None and llm_allowed and not existing_story:
            try:
                llm_claims = await llm_extract_claims(provider, event, event_items)
            except Exception as e:  # noqa: BLE001 — LLM outage must not stop collection
                log.warning("claim extraction unavailable: %s", e, extra={"event_id": event["id"]})
                llm_claims = None
        claims = merge_and_verify_claims(db, event["id"], baseline, llm_claims)
        ok, reason = event_can_auto_publish([dict(c) for c in claims])
        summary_claims = [dict(c) for c in claims]

        if existing_story:
            # evidence changed? promote/update instead of skipping
            current = existing_story.get("lifecycle") or "CONFIRMED"
            if ok and current in ("PROVISIONAL", "VERIFYING", "DETECTED"):
                det = deterministic_story_text("CONFIRMED", event, summary_claims, eligible, source_roles)
                _publish_deterministic(db, settings, brand, existing_story, det, "CONFIRMED")
                events_repo.set_status(event["id"], "PUBLISHED")
                summary["stories"] += 1
            elif not ok and current == "CONFIRMED":
                pass  # confirmed story, gates still fine, nothing to change
            db.execute("UPDATE events SET processed_at=? WHERE id=?", (utcnow(), event["id"]))
            continue

        if not ok:
            events_repo.set_status(event["id"], "HELD",
                                    "CONFLICTING" if reason == "CONFLICTING_CLAIMS" else "SINGLE_SOURCE")
            log.info("event %s held: %s", event["id"], reason, extra={"event_id": event["id"]})
            continue
        if provider is None or not llm_allowed:
            # DETERMINISTIC MODE: safe structured publication without any AI
            det = deterministic_story_text("CONFIRMED", event, summary_claims, eligible, source_roles)
            story_id = _create_and_enqueue(db, settings, brand, event["id"], det)
            events_repo.set_status(event["id"], "PUBLISHED")
            summary["stories"] += 1
            continue

        from app.newsroom.models import WRITER_SYSTEM

        sources_map = {
            (i["lineage_key"] or f"src:{i['source_id']}"): {
                "source_id": i["source_id"], "name": "", "platform": i["platform"],
                "language": i["language"],
                "verification_allowed": bool(verification_flags.get(i["source_id"], 0)),
            }
            for i in eligible
        }
        names = {s["id"]: s["name"] for s in SourcesRepo(db).list()}
        bundle = {
            "event_title": event["title"],
            "independent_count": event["independent_count"],
            "claims": [dict(c) for c in claims],
            "items": eligible[:12],
            "sources": [
                {**v, "name": names.get(v["source_id"], f"source {v['source_id']}"), "lineage": k}
                for k, v in sources_map.items()
            ],
        }
        try:
            raw = await provider.chat_json(
                system=WRITER_SYSTEM,
                user=build_writer_user_prompt(bundle, wrap_untrusted),
                max_tokens=4000, temperature=0.3,
            )
            draft = StoryDraft.model_validate(raw)
        except Exception as e:  # noqa: BLE001 — writer outage: event waits, collection continues
            log.warning("writer unavailable for event %s: %s", event["id"], e,
                        extra={"event_id": event["id"]})
            events_repo.set_status(event["id"], "READY")  # retried on next pass
            continue
        draft, issues = audit_draft(draft, claims)
        if issues and any(i.startswith("REJECTED") for i in issues):
            log.warning("story rejected by auditor: %s", issues, extra={"event_id": event["id"]})
            events_repo.set_status(event["id"], "HELD")
            continue
        story_id = stories.create(event["id"], draft.headline, draft.lead, draft.model_dump())
        events_repo.set_status(event["id"], "WRITTEN")
        summary["stories"] += 1
        draft_json = draft.model_dump()

        if settings.telegram_publish_ready:
            from app.publishing.telegram_bot import telegram_text_for_story

            text = telegram_text_for_story(draft_json, f"— {brand.short_name}")
            payload_hash = sha256_hex(text)
            pubs = PublicationsRepo(db)
            pub_id = pubs.upsert(story_id, "telegram", payload_hash, 1)
            jobs.enqueue(
                "publish_telegram",
                {"story_id": story_id, "platform": "telegram", "payload_hash": payload_hash,
                 "text": text, "publication_id": pub_id},
                dedupe_key=f"pub:tg:{story_id}:{payload_hash[:16]}",
            )
        else:
            # website-only publication (staging channel not configured yet)
            stories.mark_published(story_id)
    return summary
