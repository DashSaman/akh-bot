"""P3-E — story evolution: ONE Story per Event; content built ONLY from
structured claims (§22), never from raw fragments.

Selection:
- headline  = strongest meaningful claim (verification-ordered, must pass
  is_valid_headline — a speaker label/fragment is never a headline)
- lead      = concise context only when it adds information
- details   = selected distinct important claims, capped at
  MAX_PUBLIC_STORY_DETAILS — sources lines are never appended forever

Evolution (§20): new unique/material claim → Story fields update +
StoryVersion++ via StoriesRepo.set_lifecycle; the publication layer owns
SEND vs EDIT (jobs/runner publish_send / publish_edit).

Hard invariants (INV-012, plan §21):
- an Event with no public Telegram publication → SEND once
- an already-published Event → EDIT the SAME Telegram message only
- fragments (CONTEXT_ONLY/INCOMPLETE) never publish alone (GATE-03)
"""
from __future__ import annotations

from app.newsroom.claim_model import normalize
from app.verification.gates import extract_headline, is_valid_headline, split_speaker_label

_STATE_RANK = {"CONFIRMED": 0, "CORROBORATED": 1, "UNVERIFIED": 2,
               "SINGLE_SOURCE": 3, "CONFLICTING": 4}

# connective openers that may prefix a quote line — stripped from details,
# never from evidence (the claim row keeps the verbatim text)
_CONNECTIVE_PREFIX = ("در همین حال", "در ادامه افزود:", "در ادامه", "همچنین گفت:",
                      "همچنین", "و تأکید کرد", "افزود:", "گفت:")


def _informative(text: str) -> int:
    return len({w for w in normalize(text or "").split() if len(w) > 2})


def _is_persian_claim(text: str) -> bool:
    """Content-level Persian check for claim text (never fooled by footers:
    Arabic morphology / Hebrew / Latin-dominant all fail)."""
    from app.publishing.telegram_bot import is_persian_public_text
    return is_persian_public_text(text or "")


def select_headline(claims: list[dict]) -> str:
    """Strongest meaningful claim → headline; "" when nothing qualifies
    (caller must HOLD — a fragment never publishes).

    §FA-FIRST (owner 2026-10-04): if a Persian claim exists at the best
    verification tier, the Persian headline wins immediately — the story
    publishes without waiting for the translation queue, and the foreign
    item stays as corroborating evidence. Language never outranks trust."""
    ranked = sorted(
        claims,
        key=lambda c: (_STATE_RANK.get(c.get("state") or "UNVERIFIED", 2),
                       -_informative(c.get("text") or "")),
    )
    # Persian preference applies WITHIN the best verification tier only —
    # language never outranks trust (priority != trust invariant).
    best_rank = min((_STATE_RANK.get(c.get("state") or "UNVERIFIED", 2)
                     for c in ranked), default=2)
    top_tier = [c for c in ranked
                if _STATE_RANK.get(c.get("state") or "UNVERIFIED", 2)
                == best_rank]
    persian = [c for c in top_tier if _is_persian_claim(c.get("text") or "")]
    for subset in (persian, ranked):
        for c in subset:
            text = (c.get("text") or "").strip()
            if not text:
                continue
            cand = extract_headline("", text) or text.split("\n", 1)[0].strip()
            if is_valid_headline(cand):
                return cand[:140]
    return ""


def select_details(claims: list[dict], headline_claim_text: str | None,
                   max_details: int) -> list[str]:
    """Distinct meaningful claim bodies (speaker labels stripped), capped.
    Recency-aware: within a verification tier the NEWEST claim wins — a story
    must carry its latest state, and details never grow unbounded."""
    seen_tokens: list[set[str]] = []
    details: list[str] = []
    for c in sorted(claims, key=lambda c: (_STATE_RANK.get(c.get("state") or "UNVERIFIED", 2),
                                           -(c.get("id") or 0),
                                           -_informative(c.get("text") or ""))):
        text = (c.get("text") or "").strip()
        if not text:
            continue
        _, body = split_speaker_label(text)
        body = (body or text).strip()
        for pref in _CONNECTIVE_PREFIX:
            if body.startswith(pref):
                body = body[len(pref):].lstrip(" :：").strip()
                break
        if not body:
            continue
        if headline_claim_text and normalize(body) == normalize(headline_claim_text):
            continue
        toks = {w for w in normalize(body).split() if len(w) > 2}
        if any(len(toks & s) / max(1, len(toks | s)) >= 0.6 for s in seen_tokens):
            continue  # restatement of an already-selected detail
        if body and is_valid_headline(body) or len(body.split()) >= 5:
            details.append(body)
            seen_tokens.append(toks)
        if len(details) >= max_details:
            break
    return details


def build_v2_content(event: dict, claims: list[dict], *,
                     max_details: int) -> dict | None:
    """Deterministic public content for one Event from structured claims.
    Returns {headline, lead, details, body, lifecycle} or None when nothing
    meaningful exists (caller holds the event — CONTENT_QUALITY_HOLD)."""
    headline = select_headline(claims)
    if not headline:
        return None
    details = select_details(claims, headline, max_details)
    verified = any((c.get("state") in ("CONFIRMED", "CORROBORATED")) for c in claims)
    conflicting = any((c.get("state") == "CONFLICTING") for c in claims)
    lifecycle = "CONFIRMED" if (verified and not conflicting) else (
        "CONFLICTING" if conflicting else "PROVISIONAL")
    lead = ""
    return {
        "headline": headline,
        "lead": lead,
        "details": details,
        "body": headline + "\n\n" + "\n".join(details) if details else headline,
        "lifecycle": lifecycle,
    }


def render_v2_public_text(content: dict, brand, source_names: str) -> str:
    """Canonical renderer (CORE-002/003): build_public_text with source
    attribution — identical contract to the V1 pipeline path."""
    from app.publishing.telegram_bot import build_public_text

    body = content["headline"]
    if content["details"]:
        body += "\n\n" + "\n".join(content["details"])
    return build_public_text(content["lifecycle"], body, brand, "hidden", True,
                             source_names=source_names)
