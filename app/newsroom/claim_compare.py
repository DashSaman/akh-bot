"""P3-C — multi-stage claim comparison + provenance-safe resolve/insert.

Decision states: SAME_CLAIM / NEW_CLAIM / POTENTIAL_CONTRADICTION / AMBIGUOUS_CLAIM.
Jaccard alone never decides. Semantic-critical signals (negation, numbers, actor,
target, location, certainty) block or distinguish. Deterministic — 0 AI.
Input = StructuredClaim (P3-A). No Telegram re-parsing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.newsroom.claim_model import (
    ClaimClass, StructuredClaim, normalize,
)

States = ("SAME_CLAIM", "NEW_CLAIM", "POTENTIAL_CONTRADICTION", "AMBIGUOUS_CLAIM")


@dataclass
class ClaimDecision:
    decision: str
    matched: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    score_components: dict[str, float] = field(default_factory=dict)


_NEG = ("نخواهد", "نمی", "نیست", "نکرد", "نشد", "نه", "لغو", "تکذیب")
_MODAL = ("ممکن است", "احتمال دارد", "گفته می\u200cشود", "خواهد")


def _tokens(text: str) -> set[str]:
    t = normalize(text or "").lower()
    return {w for w in re.split(r"\s+", t) if len(w) > 1}


# light words that must never drive a paraphrase-merge decision (§15 counts
# CONTENT overlap only — negation/numbers/names are never in this set)
_STOP = {"و", "است", "به", "از", "را", "با", "این", "که", "در", "برای", "آن",
         "ها", "شد", "شده", "می", "کرد", "کند", "او", "وی", "هم", "نیز", "بر",
         "های", "تا", "همچنان"}


def _content_overlap(a: str, b: str) -> int:
    return len((_tokens(a) & _tokens(b)) - _STOP)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _containment(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _neg(text: str) -> bool:
    t = normalize(text or "")
    return any(n in t for n in _NEG)


def compare(claim: StructuredClaim, existing: StructuredClaim) -> ClaimDecision:
    """Multi-stage comparison. Stage A exact fp; B structured fields; C lexical;
    D semantic-lite guards (negation/number/actor/target/location/certainty)."""
    conflicts: list[str] = []
    matched: list[str] = []

    # Stage A — exact structural fingerprint
    if claim.fingerprint and claim.fingerprint == existing.fingerprint:
        return ClaimDecision("SAME_CLAIM", matched=["fingerprint_exact"],
                             reason_codes=["STAGE_A_EXACT"])

    # Stage B — structured field compatibility
    same_actor = bool(claim.actor and existing.actor
                      and normalize(claim.actor) == normalize(existing.actor))
    diff_actor = bool(claim.actor and existing.actor
                      and normalize(claim.actor) != normalize(existing.actor))
    same_loc = bool(claim.location and existing.location
                    and normalize(claim.location) == normalize(existing.location))
    diff_loc = bool(claim.location and existing.location
                    and normalize(claim.location) != normalize(existing.location))
    num_a = set(claim.quantity.split("، ")) if claim.quantity else set()
    num_b = set(existing.quantity.split("، ")) if existing.quantity else set()
    numbers_conflict = bool(num_a and num_b and not (num_a & num_b))
    neg_diff = claim.negation != existing.negation
    modal_diff = claim.certainty != existing.certainty and "REPORTED" in (
        claim.certainty, existing.certainty)
    if same_actor:
        matched.append("actor")
    if same_loc:
        matched.append("location")

    # Stage D guards (semantic-lite) — checked BEFORE lexical so critical diffs block
    # NEGATION_DIFFERS requires near-identity (≥4 shared content tokens): a
    # polarity flip of the SAME assertion is a contradiction; two different
    # sentences of one speaker (interviews mix polarity normally) are not.
    if neg_diff and _content_overlap(claim.text, existing.text) >= 4:
        conflicts.append("NEGATION_DIFFERS")
    if numbers_conflict:
        conflicts.append("NUMBERS_DIFFER")
    if diff_actor:
        conflicts.append("ACTOR_DIFFERS")
    if diff_loc and claim.claim_class in (ClaimClass.ATTACK, ClaimClass.CASUALTY,
                                          ClaimClass.INTERNET):
        conflicts.append("LOCATION_CONFLICT")
    if modal_diff and "REPORTED" in (claim.certainty, existing.certainty):
        conflicts.append("CERTAINTY_DIFFERS")

    if conflicts:
        return ClaimDecision("POTENTIAL_CONTRADICTION", matched=matched,
                             conflicts=conflicts,
                             reason_codes=["STAGE_D_SEMANTIC_GUARD"])

    # Stage C — lexical similarity (jaccard + containment, not alone decisive)
    jc = _jaccard(_tokens(claim.text), _tokens(existing.text))
    ct = _containment(_tokens(claim.text), _tokens(existing.text))
    content_overlap = _content_overlap(claim.text, existing.text)
    # paraphrase convergence needs BOTH an absolute count AND a ratio floor:
    # 3 shared light-word-free tokens of a 20-token report (0.19) is nothing,
    # 4 of 9 in a short claim (0.57) is a real paraphrase
    min_len = min(len(_tokens(claim.text) - _STOP), len(_tokens(existing.text) - _STOP))
    key_overlap = content_overlap if content_overlap >= max(3, 0.25 * max(1, min_len)) else 0
    comps = {"jaccard": round(jc, 3), "containment": round(ct, 3)}
    if jc >= 0.55 or ct >= 0.8 or key_overlap >= 3:
        # safe paraphrase: same actor (or both unknown), same certainty class
        if (same_actor or (not claim.actor and not existing.actor)) \
                and claim.certainty == existing.certainty:
            return ClaimDecision("SAME_CLAIM", matched=["actor", "lexical"],
                                 reason_codes=["STAGE_C_PARAPHRASE"],
                                 score_components=comps)
    if jc >= 0.40:
        return ClaimDecision("AMBIGUOUS_CLAIM", matched=matched,
                             reason_codes=["STAGE_C_LEXICAL_BAND"],
                             score_components=comps)
    return ClaimDecision("NEW_CLAIM", reason_codes=["STAGE_C_BELOW_BAND"],
                         score_components=comps)


def resolve_or_insert_claim(db, event_id: int, claim: StructuredClaim,
                            source_item_id: int) -> tuple[int, ClaimDecision]:
    """Bounded compare within SAME event; provenance-safe; idempotent.
    Returns (claim_id, decision). Never discards evidence."""
    row = db.query_one(
        "SELECT id, text, actor, predicate, object, location, quantity, certainty,"
        " negation, claim_class, fingerprint FROM claims WHERE event_id=? LIMIT 50",
        (event_id,))
    # bounded compare loop
    existing_rows = db.query(
        "SELECT id, text, actor, predicate, object, location, quantity, certainty,"
        " negation, claim_class, fingerprint, source_item_id FROM claims"
        " WHERE event_id=? LIMIT 50", (event_id,))
    best: tuple[int, ClaimDecision] | None = None
    for ex in existing_rows:
        ex_claim = StructuredClaim(
            claim_class=ClaimClass(ex["claim_class"]) if ex["claim_class"]
            in (ClaimClass.QUOTE.value, ClaimClass.ATTACK.value, ClaimClass.CASUALTY.value,
                ClaimClass.MARKET.value, ClaimClass.INTERNET.value,
                ClaimClass.GENERAL.value) else ClaimClass.GENERAL,
            text=ex["text"], source_item_id=ex["source_item_id"] or 0,
            actor=ex["actor"], predicate=ex["predicate"], object_=ex["object"],
            location=ex["location"], quantity=ex["quantity"],
            certainty=ex["certainty"] or "ASSERTED",
            negation=bool(ex["negation"]), fingerprint=ex["fingerprint"] or "")
        decision = compare(claim, ex_claim)
        if decision.decision == "SAME_CLAIM":
            best = (int(ex["id"]), decision)
            break
        if decision.decision == "POTENTIAL_CONTRADICTION":
            best = best or (int(ex["id"]), decision)
    if best and best[1].decision == "SAME_CLAIM":
        claim_id = best[0]
        db.execute(
            "INSERT OR IGNORE INTO claim_source_items(claim_id, source_item_id, created_at)"
            " VALUES(?,?,datetime('now'))", (claim_id, source_item_id))
        return claim_id, best[1]
    # NEW / POTENTIAL_CONTRADICTION / AMBIGUOUS → insert DISTINCT claim
    cur = db.execute(
        "INSERT INTO claims(event_id,text,state,actor,predicate,object,location,"
        "quantity,attribution,certainty,negation,claim_class,fingerprint,source_item_id,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
        (event_id, claim.text, "UNVERIFIED", claim.actor, claim.predicate,
         claim.object_, claim.location, claim.quantity, claim.attribution,
         claim.certainty, int(claim.negation), claim.claim_class.value,
         claim.fingerprint, source_item_id))
    claim_id = int(cur.lastrowid)
    db.execute("INSERT OR IGNORE INTO claim_source_items(claim_id, source_item_id, created_at)"
               " VALUES(?,?,datetime('now'))", (claim_id, source_item_id))
    decision = best[1] if (best and best[1].decision == "POTENTIAL_CONTRADICTION") \
        else ClaimDecision("NEW_CLAIM")
    return claim_id, decision
