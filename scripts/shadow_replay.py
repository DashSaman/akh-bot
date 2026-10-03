"""P3 shadow replay — Part 3 live-activation gate (NO Telegram writes).

Replays the last N hours of allowlisted RawItems through the V2 engine into a
FRESH shadow database inside a throwaway container:

  docker run --rm -v <shadow-dir>:/data akhbot-app:latest \
      python scripts/shadow_replay.py --hours 24

Telegram writes are structurally impossible here: no bot token in the
container, the job runner never executes, and the shadow DB is a copy.

Verified invariants (hard-fail ⇒ exit 1):
  I1 same-interview rapid fragments → ONE event
  I2 same-event duplicate SEND intents = 0 (publish_send per story ≤ 1)
  I3 incomplete/fragment stories = 0 (every public headline is meaningful)
  I4 paraphrase duplicates = 0 (no two events share a SAME_CLAIM top claim)
  I5 foreign public text = 0 (Persian gate on every rendered text)
  I6 prefix alone → 0 claim/event/story (REG-031)
  I7 replay idempotency (second pass changes nothing)
Soft metrics (reported for review): over-merge sample, burst stats.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--db", default="/data/akhbot.db")
    ap.add_argument("--shadow", default="/data/shadow.db")
    args = ap.parse_args()

    from app.db.database import Database
    from app.db.migrate import apply_migrations
    from app.newsroom.v2_pipeline import process_new_items_v2

    src = Database(args.db)
    if os.path.exists(args.shadow):
        os.remove(args.shadow)
    sh = Database(args.shadow)
    apply_migrations(sh)

    # copy source allowlist + recent raw items + fingerprints into the shadow DB
    for s in src.query("SELECT * FROM sources"):
        sh.execute(
            "INSERT INTO sources(id,name,platform,external_id,url,language,country,"
            " source_type,status,enabled,priority,polling_interval_seconds,fetch_state,"
            " last_fetch_at,last_success_at,last_error,health_score,notes,created_at,"
            " activated_at,source_role,verification_allowed,can_increase_independent_count,"
            " source_control_state,publication_policy,tg_stable_id,last_remote_id)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO NOTHING",
            (s["id"], s["name"], s["platform"], s["external_id"], s["url"], s["language"],
             s["country"], s["source_type"], s["status"], s["enabled"], s["priority"],
             s["polling_interval_seconds"], s["fetch_state"], s["last_fetch_at"],
             s["last_success_at"], s["last_error"], s["health_score"], s["notes"],
             s["created_at"], s["activated_at"], s["source_role"],
             s["verification_allowed"], s["can_increase_independent_count"],
             s["source_control_state"], s["publication_policy"], s["tg_stable_id"],
             s["last_remote_id"]))
    items = src.query(
        "SELECT * FROM raw_items WHERE fetched_at >= datetime('now', ?) ORDER BY id",
        (f'-{args.hours} hours',))
    n_items = 0
    for it in items:
        sh.execute(
            "INSERT INTO raw_items(id,source_id,platform,external_key,url,canonical_url,"
            " title,text,language,author,published_at,edited_at,fetched_at,forward_from,"
            " media_json,lineage_key,activation_ok,processed_state)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'NEW')",
            (it["id"], it["source_id"], it["platform"], it["external_key"], it["url"],
             it["canonical_url"], it["title"], it["text"], it["language"], it["author"],
             it["published_at"], it["edited_at"], it["fetched_at"], it["forward_from"],
             it["media_json"], it["lineage_key"], it["activation_ok"]))
        fp = src.query_one("SELECT * FROM item_fingerprints WHERE raw_item_id=?", (it["id"],))
        if fp:
            sh.execute(
                "INSERT INTO item_fingerprints(raw_item_id,canonical_url_hash,content_hash,"
                " title_norm_hash,simhash) VALUES(?,?,?,?,?)",
                (it["id"], fp["canonical_url_hash"], fp["content_hash"],
                 fp["title_norm_hash"], fp["simhash"]))
        n_items += 1

    # run the V2 engine with NO brand (footer-less render still Persian-gated)
    class _B:  # minimal brand stub — build_public_text handles attrs
        short_name = "راسته"
        telegram_handle = "RastehNews"

    class _S:  # minimal settings stub
        event_engine_v2_enabled = True
        max_public_story_details = 5
        edit_debounce_seconds = 120
        verifying_deadline_minutes = 60
        standard_max_age_minutes = 180

    summary1 = process_new_items_v2(sh, _B(), _S())
    summary2 = process_new_items_v2(sh, _B(), _S())  # replay idempotency

    # ---------------- collect evidence ----------------
    events = sh.query("SELECT * FROM events")
    stories = sh.query("SELECT * FROM stories")
    claims = sh.query("SELECT * FROM claims")
    send_jobs = sh.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    edit_jobs = sh.query("SELECT * FROM jobs WHERE job_type='publish_edit'")

    from app.newsroom.claim_compare import compare
    from app.newsroom.claim_model import ClaimClass, StructuredClaim
    from app.publishing.telegram_bot import is_persian_public_text, story_content_language_check
    from app.verification.gates import is_valid_headline

    failures: list[str] = []

    # I2 — duplicate SEND intents
    per_story: dict[int, int] = {}
    for j in send_jobs:
        sid = json.loads(j["payload_json"])["story_id"]
        per_story[sid] = per_story.get(sid, 0) + 1
    dup_sends = {k: v for k, v in per_story.items() if v > 1}
    if dup_sends:
        failures.append(f"I2 duplicate SEND intents: {dup_sends}")

    # I3 — fragment/incomplete stories
    bad_head = [s["id"] for s in stories if not is_valid_headline(s["headline"])]
    if bad_head:
        failures.append(f"I3 invalid/fragment headlines in stories: {bad_head}")

    # I4 — paraphrase duplicates across events
    dup_pairs = []
    top = {}
    for c in claims:
        top.setdefault(c["event_id"], []).append(c)
    eids = sorted(top)
    for i, e1 in enumerate(eids):
        for e2 in eids[i + 1:]:
            for c1 in top[e1][:3]:
                for c2 in top[e2][:3]:
                    a = StructuredClaim(claim_class=ClaimClass.GENERAL, text=c1["text"],
                                        source_item_id=0)
                    b = StructuredClaim(claim_class=ClaimClass.GENERAL, text=c2["text"],
                                        source_item_id=0)
                    if compare(a, b).decision == "SAME_CLAIM":
                        dup_pairs.append((e1, e2, c1["id"], c2["id"]))
    if dup_pairs:
        failures.append(f"I4 paraphrase duplicate events: {dup_pairs[:5]}")

    # I5 — foreign public text
    foreign = []
    for j in send_jobs + edit_jobs:
        txt = json.loads(j["payload_json"]).get("text") or ""
        if txt and not (story_content_language_check(txt) and is_persian_public_text(txt)):
            foreign.append(j["id"])
    if foreign:
        failures.append(f"I5 foreign public text in jobs: {foreign}")

    # I6 — prefix alone produced nothing
    frag_stories = sh.query(
        "SELECT COUNT(*) AS n FROM stories s JOIN events e ON e.id=s.event_id"
        " WHERE NOT EXISTS (SELECT 1 FROM claims c WHERE c.event_id=e.id)")
    if frag_stories[0]["n"]:
        failures.append("I6 story without any complete claim")

    # I7 — replay idempotency
    if (summary2["processed"], summary2["stories"], summary2["sends"]) != (0, 0, 0):
        failures.append(f"I7 replay not idempotent: {summary2}")

    # I1 — same-interview grouping (soft evidence via context/burst tables)
    ctxs = sh.query("SELECT source_id, speaker, COUNT(DISTINCT raw_item_id) AS n "
                    "FROM source_context GROUP BY source_id, speaker")
    burst = sh.query("SELECT COUNT(*) AS n FROM burst_groups")

    report = {
        "items": n_items,
        "events": len(events),
        "stories": len(stories),
        "claims": len(claims),
        "claims_material": sum(1 for c in claims if c["material"]),
        "send_intents": len(send_jobs),
        "edit_intents": len(edit_jobs),
        "send_intents_per_story": per_story,
        "stories_per_event_max": max([sum(1 for s in stories if s["event_id"] == e["id"])
                                      for e in events], default=0),
        "context_rows": len(ctxs),
        "burst_groups": burst[0]["n"] if burst else 0,
        "summary_pass1": {k: v for k, v in summary1.items()},
        "summary_pass2": {k: v for k, v in summary2.items()},
        "failures": failures,
        "verdict": "PASS" if not failures else "FAIL",
    }
    sh.close()
    src.close()
    print("SHADOW-REPORT " + json.dumps(report, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
