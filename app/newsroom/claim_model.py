"""Structured claim model (P3-A) — atomic assertion with explicit fields.

Stores NO Telegram markup, NO footer/presentation, NO preformatted public blob.
Fingerprint is structural metadata only in P3-A (P3-C owns comparison decisions).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from enum import Enum


class ClaimClass(str, Enum):
    QUOTE = "QUOTE"
    ATTACK = "ATTACK"
    CASUALTY = "CASUALTY"
    MARKET = "MARKET"
    INTERNET = "INTERNET"
    GENERAL = "GENERAL"


_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ZWNJ = "\u200c"

# semantically-critical tokens — never normalized away
_NEGATION_TOKENS = ("نخواهد", "نمی‌", "نمی ", "نیست", "نیستند", "نه",
                    "نکرد", "نشد", "لغو", "تکذیب", "لا ")
_CERTAINTY_REPORTED = ("گفته می\u200cشود", "احتمال دارد", "ممکن است", "به گزارش", "به نقل از")
_CERTAINTY_ATTRIBUTED = ("اعلام کرد", "تأیید کرد", "گفت", "اظهار کرد")

_ATTACK_KW = ("حمله", "حمله موشکی", "پهپاد", "پهپادی", "حمله هوایی", "بمباران", "درگیری",
              "حمله پهپادی", "شلیک", "انفجار", "استهداف", "هدف قرار")
_CASUALTY_KW = ("کشته", "زخمی", "تلفات", "جان باخت", "شهید", "جراحت")
_MARKET_KW = ("دلار", "ارز", "طلا", "سکه", "بورس", "شاخص", "نفت", "تومان")
_INTERNET_KW = ("اینترنت", "فیلترینگ", "قطعی اینترنت", "اختلال اینترنت", "مخابرات", "پهنای باند")
_QUOTE_KW = ("گفت", "اظهار کرد", "اعلام کرد", "خبر داد", "هشدار داد", "تأکید کرد", "افزود")


def normalize(text: str) -> str:
    """Safe normalization: unify ar/fa variants + ZWNJ→space; preserve
    digits (translated to ASCII), negation, names, modals."""
    t = (text or "").translate(_FA_DIGITS)
    t = t.replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _contains(text: str, kws) -> bool:
    t = normalize(text)
    return any(normalize(k) in t for k in kws)


def detect_class(text: str) -> ClaimClass:
    if _contains(text, _ATTACK_KW):
        return ClaimClass.ATTACK
    if _contains(text, _CASUALTY_KW):
        return ClaimClass.CASUALTY
    if _contains(text, _INTERNET_KW):
        return ClaimClass.INTERNET
    if _contains(text, _MARKET_KW):
        return ClaimClass.MARKET
    if _contains(text, _QUOTE_KW):
        return ClaimClass.QUOTE
    return ClaimClass.GENERAL


def has_negation(text: str) -> bool:
    t = normalize(text)
    return any(k.strip() and k.strip() in t for k in _NEGATION_TOKENS)


def certainty_of(text: str) -> str:
    if _contains(text, _CERTAINTY_REPORTED):
        return "REPORTED"
    if _contains(text, _CERTAINTY_ATTRIBUTED):
        return "ATTRIBUTED"
    return "ASSERTED"


def numbers_of(text: str) -> list[str]:
    return sorted(set(re.findall(r"\d+(?:[.,]\d+)*", normalize(text))))


@dataclass
class StructuredClaim:
    """Atomic structured assertion. Public rendering never reads this directly
    (P3-B+); this is the canonical evidence-level representation."""
    claim_class: ClaimClass
    text: str                       # original claim sentence (evidence verbatim)
    source_item_id: int             # provenance — an orphan claim is invalid
    actor: str | None = None        # may be None when genuinely unattributed
    predicate: str | None = None
    object_: str | None = None
    qualifiers: str | None = None
    location: str | None = None
    time_ref: str | None = None
    quantity: str | None = None     # critical numbers preserved verbatim (fa normalized)
    attribution: str | None = None  # who reported/said it
    certainty: str = "ASSERTED"     # ASSERTED / REPORTED / ATTRIBUTED
    negation: bool = False
    fingerprint: str = ""
    extra: dict = field(default_factory=dict)

    def compute_fingerprint(self) -> str:
        """Structural fingerprint: actor|predicate|object|location|numbers|negation|class.
        Numbers/negation/class are NEVER normalized away (P3-C needs the signal)."""
        parts = [
            normalize(self.actor or ""),
            normalize(self.predicate or ""),
            normalize(self.object_ or ""),
            normalize(self.location or ""),
            ",".join(numbers_of(self.text)),
            "NEG" if (self.negation or has_negation(self.text)) else "POS",
            self.claim_class.value if isinstance(self.claim_class, ClaimClass) else str(self.claim_class),
        ]
        self.fingerprint = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
        return self.fingerprint

    def to_dict(self) -> dict:
        d = asdict(self)
        d["claim_class"] = self.claim_class.value
        return d

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class CompletenessResult:
    state: str                      # COMPLETE / CONTEXT_ONLY / INCOMPLETE
    reason_code: str = ""
    missing_slots: list[str] = field(default_factory=list)
    publishable: bool = False


# §10/§12: prefixes & connective fragments — never claims, deterministic rules
_PREFIX_RE = re.compile(
    r"^[^a-zA-Z\u0600-\u06FF]*"                       # leading emoji/punct
    r"[\u0600-\u06FF\w .'\-]{0,60}?"                  # speaker/context label
    r"\s*[:：]\s*$"                                    # ends with colon, nothing else
)
_CONNECTIVE_STARTS = ("در همین حال", "در ادامه", "همچنین", "جزئیات بیشتر",
                      "و تأکید کرد", "افزود:", "گفت:", "خبر فوری", "عاجل",
                      "BREAKING", "فوری:")
_MIN_MEANINGFUL_TOKENS = 5


def is_prefix_fragment(text: str) -> bool:
    """Speaker/context label ending with ':' or known connective openers."""
    t = (text or "").strip()
    if not t:
        return True
    if t.endswith(":") or t.endswith("："):
        return True
    for c in _CONNECTIVE_STARTS:
        if t.startswith(c) and len(t) <= 60:
            return True
    return bool(_PREFIX_RE.match(t)) or normalize(t) in {
        "عاجل", "فوری", "breaking", "خبر فوری", "در همین حال", "جزئیات بیشتر"}


# speaker labels that carry no identity («فوری:», «عاجل:») — never an actor
_EMPTY_LABELS = {"عاجل", "فوری", "breaking", "خبر فوری", "مهم", "هشدار", "ویژه"}


def _is_identity_label(label: str) -> bool:
    """A label is an identity ONLY when it is neither an empty marker nor a
    connective phrase («در ادامه افزود:» is a verb turn, not a speaker)."""
    lb = (label or "").strip().lower()
    if not lb or lb in _EMPTY_LABELS:
        return False
    return not any(lb.startswith(c.rstrip(":：").lower()) for c in _CONNECTIVE_STARTS)

_LEADING_LABEL_RE = re.compile(
    r"^([\u0600-\u06FF\w][\u0600-\u06FF\w .'\-]{1,38}?)\s*[:：]\s*(.*)$", re.S)


def extract_structured(text: str, source_item_id: int,
                       speaker_hint: str | None = None) -> StructuredClaim:
    """Deterministic extractor: populates structured fields from text without
    inventing content. Single general claim when reliable split is impossible
    (atomicity §15 — no aggressive splitting)."""
    body = text or ""
    speaker = None
    if is_prefix_fragment(body.split("\n", 1)[0]) and "\n" in body:
        first, rest = body.split("\n", 1)
        speaker = first.strip().rstrip(":：").strip()
        body = rest.strip()
    else:
        # leading «ترامپ: …» label WITH content on the first line — the label
        # is the explicit speaker; the content is the claim text
        m = _LEADING_LABEL_RE.match(body)
        if m and _is_identity_label(m.group(1)) \
                and (m.group(2).strip() or "\n" in body):
            speaker = m.group(1).strip()
            body = m.group(2).strip()
    cls = detect_class(body)
    nums = numbers_of(body)
    time_ref = None
    for marker in ("امروز", "دیروز", "امشب", "صبح امروز", "چند ساعت", "ساعات آینده"):
        if marker in body:
            time_ref = marker
            break
    claim = StructuredClaim(
        claim_class=cls, text=body, source_item_id=source_item_id,
        actor=speaker or (speaker_hint or None),
        predicate=body[:80] if body else None,
        object_=None,
        time_ref=time_ref,
        quantity="، ".join(nums) if nums else None,
        certainty=certainty_of(body),
        negation=has_negation(body),
    )
    claim.compute_fingerprint()
    return claim
