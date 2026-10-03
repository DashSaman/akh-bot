"""P3-F — material update rules (§23): which NEW claims justify editing the
public message, and which are stored as evidence only.

MATERIAL (any hit):
  M0 FIRST_CLAIM          — the event has no claims yet → initial story
  M1 NEW_NUMBERS          — new casualty/market figure not present before
  M2 NEW_TARGET           — new location/target the event never mentioned
  M3 OFFICIAL_CONFIRMATION— official actor confirming / announcing
  M4 STATUS_TRANSITION    — negation flip or explicit status keyword
                            (لغو / متوقف / برقرار / آزاد …)

NON-MATERIAL: paraphrase / restatement / minor wording-context additions —
these are usually SAME_CLAIM after dedup anyway; a NEW_CLAIM without any
material signal stays evidence-only (provenance kept, message untouched).

Deterministic, no AI. Priority is speed — never trust (INV-006).
"""
from __future__ import annotations

from app.newsroom.claim_model import StructuredClaim, has_negation, normalize, numbers_of
from app.verification.gates import numbers_in

# explicit correction markers — a published fact is being fixed (§24: bypasses
# the edit debounce entirely)
_CORRECTION_KW = ("تصحیح", "اصلاح می", "تکذیب", "خلاف واقع", "اشتباه", "خطا")

# explicit status-transition verbs (fa) — a state the world is in changes
_STATUS_KW = ("لغو شد", "لغو", "متوقف", "برقرار", "از سر گرفته", "آزاد شد",
              "آتش‌بس", "سقوط", "استعفا", "انتقال", "افتاد", "کاهش یافت",
              "افزایش یافت", "توافق شد", "منعقد")

# official/primary actor markers — confirmation by these is material
_OFFICIAL_KW = ("ارتش", "وزارت", "وزیر", "کاخ سفید", "سخنگو", "فرمانده",
                "centcom", "idf", "پنتاگون", "شورای امنیت", "آژانس",
                "دولت", "رئیس‌جمهور", "نخست‌وزیر", "سازمان", "ایرنا",
                "رسمی", "اضلاعیه", "اطلاعیه")


def _num_set(text: str) -> set[str]:
    return set(numbers_of(text)) | numbers_in(text)


def _content_tokens(text: str) -> set[str]:
    from app.newsroom.event_fingerprint import tokens

    return tokens(text or "")


def is_material_update(claim: StructuredClaim,
                       prior_claims: list[StructuredClaim]) -> tuple[bool, list[str]]:
    """Deterministic materiality of one NEW_CLAIM against the event's priors.
    Returns (material, reasons). Never mutates anything."""
    if not prior_claims:
        return True, ["FIRST_CLAIM"]

    reasons: list[str] = []
    prior_text = " ".join(p.text or "" for p in prior_claims)
    prior_nums: set[str] = set()
    for p in prior_claims:
        prior_nums |= _num_set(p.text or "")
    new_nums = _num_set(claim.text or "")
    # M1 — new figures (casualties/market) the event never carried
    fresh_nums = {n for n in new_nums if n not in prior_nums and len(n) >= 2}
    if fresh_nums and claim.claim_class.value in ("CASUALTY", "MARKET", "ATTACK",
                                                  "GENERAL", "QUOTE"):
        reasons.append("NEW_NUMBERS:" + ",".join(sorted(fresh_nums)))
    # M2 — new target/location
    prior_locs = {normalize(p.location or "").lower() for p in prior_claims if p.location}
    if claim.location and normalize(claim.location).lower() not in prior_locs:
        reasons.append("NEW_TARGET")
    else:
        new_toks = _content_tokens(claim.text or "")
        old_toks = _content_tokens(prior_text)
        from app.newsroom.burst import _WEAK_TOKENS

        fresh_toks = {t for t in new_toks - old_toks if t not in _WEAK_TOKENS
                      and not t.isdigit() and len(t) > 2}
        if claim.claim_class.value == "ATTACK" and len(fresh_toks) >= 2:
            reasons.append("NEW_TARGET")
    # M3 — official confirmation/announcement
    t = normalize(claim.text or "")
    if claim.certainty == "ATTRIBUTED" and any(k in t for k in _OFFICIAL_KW):
        reasons.append("OFFICIAL_CONFIRMATION")
    # M4 — status transition / negation flip
    if any(k in t for k in _STATUS_KW):
        reasons.append("STATUS_TRANSITION")
    elif bool(has_negation(claim.text or "")) != any(has_negation(p.text or "") for p in prior_claims):
        reasons.append("STATUS_TRANSITION")
    # M6 — explicit correction of an already-published fact (debounce bypass)
    if any(k in t for k in _CORRECTION_KW):
        reasons.append("CORRECTION")
    return (bool(reasons), reasons)
