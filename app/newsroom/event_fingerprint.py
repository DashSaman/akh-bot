"""P3-B — multi-signal EventFingerprint + bounded candidate matcher.

Identity is NEVER headline text, raw source text, time alone, source priority,
or source trust. Fingerprint is descriptive comparison metadata — NOT a global
unique key (two real events may legitimately produce similar fingerprints).
Deterministic only: 0 AI, no random, no iteration-order dependence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.newsroom.claim_model import normalize

EVENT_TYPES = ("INTERVIEW", "PRESS_CONFERENCE", "SPEECH", "LIVE_INCIDENT",
               "MILITARY_STRIKE", "POLITICAL_ANNOUNCEMENT", "MARKET_MOVE",
               "INTERNET_OUTAGE", "GENERAL_NEWS")

# §23 continuation policy per event type (minutes; configurable by owner later)
CONTINUATION_MINUTES = {
    "INTERVIEW": 240, "PRESS_CONFERENCE": 240, "SPEECH": 240,
    "LIVE_INCIDENT": 120, "MILITARY_STRIKE": 45, "POLITICAL_ANNOUNCEMENT": 120,
    "MARKET_MOVE": 30, "INTERNET_OUTAGE": 180, "GENERAL_NEWS": 90,
}

# §14 explicit second-occurrence markers (fa) — force CREATE_NEW
SECOND_OCCURRENCE_RE = re.compile(
    r"(حمله دوم|حمله دیگری|حادثه\u200cای دیگر|دور جدید|حمله جداگانه|"
    "حمله مجدد|another (strike|attack|wave)|second (strike|attack))", re.IGNORECASE)

_TYPED_HINTS = (
    ("LIVE_INCIDENT", ("انفجار", "انفجاری", "آتش‌سوزی", "explosion")),
    ("MILITARY_STRIKE", ("حمله موشکی", "حمله پهپادی", "حمله هوایی", "موشک", "پهپاد",
                         "strike", "missile", "drone")),
    ("INTERNET_OUTAGE", ("قطعی اینترنت", "اختلال اینترنت", "فیلترینگ", "اینترنت",
                         "internet outage", "اختلال")),
    ("MARKET_MOVE", ("دلار", "ارز", "طلا", "سکه", "بورس", "شاخص", "dollar", "currency")),
    ("INTERVIEW", ("مصاحبه", "مجله", "interview")),
    ("PRESS_CONFERENCE", ("نشست خبری", "کنفرانس خبری", "press conference")),
    ("SPEECH", ("نطق", "سخنرانی", "speech")),
    ("POLITICAL_ANNOUNCEMENT", ("اعلام کرد", "اعلام می‌کند", "اعلام کرد", "دستور داد", "اعلامیه", "تحریم‌های جدید", "announcement")),
)

_STOP = {"از", "به", "با", "در", "که", "و", "این", "برای", "است", "را", "های",
         "the", "a", "an", "of", "to", "in", "on", "and", "is", "are"}


def detect_event_type(text: str) -> str:
    t = (text or "").lower()
    for name, kws in _TYPED_HINTS:
        if any(k.lower() in t for k in kws):
            return name
    return "GENERAL_NEWS"


def detect_second_occurrence(text: str) -> bool:
    return bool(SECOND_OCCURRENCE_RE.search(text or ""))


def temporal_bucket(ts: str | None) -> str:
    """Coarse 15-minute bucket — a *feature*, never identity."""
    if not ts:
        return ""
    import datetime

    try:
        dt = datetime.datetime.fromisoformat(ts)
        return dt.strftime("%Y%m%d%H") + f"{dt.minute // 15}"
    except (TypeError, ValueError):
        return ""


def tokens(text: str) -> set[str]:
    t = normalize(text or "").lower()
    return {w for w in re.split(r"\s+", t) if len(w) > 1 and w not in _STOP}


@dataclass
class EventFingerprint:
    primary_actors: list[str] = field(default_factory=list)
    predicate_tokens: set[str] = field(default_factory=set)
    object_tokens: set[str] = field(default_factory=set)
    location: str | None = None
    event_type: str = "GENERAL_NEWS"
    topic: str = ""
    conversation_context_ref: str | None = None
    temporal_bucket: str = ""
    explicit_occurrence_id: str | None = None
    occurred_at: str | None = None        # last known occurrence timestamp
    second_occurrence: bool = False       # explicit «حمله دوم/دور جدید» marker

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary_actors": self.primary_actors, "predicate_tokens":
            sorted(self.predicate_tokens), "object_tokens": sorted(self.object_tokens),
            "location": self.location, "event_type": self.event_type, "topic":
            self.topic, "conversation_context_ref": self.conversation_context_ref,
            "temporal_bucket": self.temporal_bucket,
            "explicit_occurrence_id": self.explicit_occurrence_id,
            "occurred_at": self.occurred_at, "second_occurrence": self.second_occurrence,
        }

    def to_json(self) -> str:
        import json

        return json.dumps(self.as_dict(), ensure_ascii=False)


@dataclass
class MatchDecision:
    decision: str                                   # ATTACH_EXISTING / CREATE_NEW / AMBIGUOUS_EVENT
    candidate_event_id: int | None = None
    matched: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    score_components: dict[str, float] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)


_LOCATION_KEYWORDS = ("بغداد", "تهران", "اسرائیل", "عراق", "سوریه", "لبنان", "یمن",
                      "شیراز", "اصفهان", "کرمانشاه", "american", "iran", "iraq",
                      "israel", "tehran", "baghdad", "shiraz")
LOCATION_RE = re.compile("|".join(_LOCATION_KEYWORDS), re.IGNORECASE)


def extract_fingerprint(text: str, *, actor: str | None = None,
                        occurred_at: str | None = None,
                        conversation_context_ref: str | None = None,
                        explicit_occurrence_id: str | None = None) -> EventFingerprint:
    """Build a fingerprint from structured-ish text features (§31: consumes
    P3-A-compatible normalized fields; never re-parses Telegram markup)."""
    body = text or ""
    # hard conflicts take precedence over type hints
    second = detect_second_occurrence(body)
    etype = "LIVE_INCIDENT" if second else detect_event_type(body)
    toks = tokens(body)
    predicate = toks
    loc_m = LOCATION_RE.search(body)
    actors = {normalize(actor).lower()} if actor else set()
    # actor fallback: leading proper-noun-ish first token(s) before first verb-ish word
    if not actors or None in actors:
        actors.discard(None)
    return EventFingerprint(
        primary_actors=sorted(a for a in actors if a),
        predicate_tokens=predicate,
        object_tokens=set(),
        location=loc_m.group(0).lower() if loc_m else None,
        event_type=etype,
        topic=",".join(sorted(toks))[:120],
        conversation_context_ref=conversation_context_ref,
        temporal_bucket=temporal_bucket(occurred_at),
        explicit_occurrence_id=explicit_occurrence_id,
        occurred_at=occurred_at,
        second_occurrence=second,
    )


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _containment(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def hard_conflicts(fp: EventFingerprint, cand: EventFingerprint,
                   fp_ts: str | None = None) -> list[str]:
    """§14: force CREATE_NEW regardless of score."""
    conflicts = []
    if fp.explicit_occurrence_id and cand.explicit_occurrence_id \
            and fp.explicit_occurrence_id != cand.explicit_occurrence_id:
        conflicts.append("OCCURRENCE_ID_DIFFERS")
    if fp.second_occurrence and cand.occurred_at and fp.occurred_at \
            and cand.occurred_at < fp.occurred_at:
        conflicts.append("EXPLICIT_SECOND_OCCURRENCE")
    if fp.location and cand.location and fp.location != cand.location \
            and fp.event_type in ("MILITARY_STRIKE", "LIVE_INCIDENT", "INTERNET_OUTAGE"):
        conflicts.append("LOCATION_CONFLICT")
    if fp.event_type != cand.event_type and (
            "MILITARY_STRIKE" in (fp.event_type, cand.event_type)
            or "INTERNET_OUTAGE" in (fp.event_type, cand.event_type)
            or {fp.event_type, cand.event_type} == {"INTERVIEW", "POLITICAL_ANNOUNCEMENT"}
            or {fp.event_type, cand.event_type} == {"PRESS_CONFERENCE", "POLITICAL_ANNOUNCEMENT"}):
        conflicts.append("EVENT_TYPE_CONFLICT")
    if _verb_conflict(fp, cand):
        conflicts.append("PREDICATE_CONFLICT")
    # type-specific continuation window exceeded (§23) — time as gate, not identity
    mins = CONTINUATION_MINUTES.get(fp.event_type, 90)
    ts = fp_ts or fp.occurred_at or cand.occurred_at
    if ts and cand.occurred_at:
        try:
            import datetime

            delta = (datetime.datetime.fromisoformat(cand.occurred_at)
                     - datetime.datetime.fromisoformat(ts)).total_seconds() / 60
            if abs(delta) > mins:
                conflicts.append("CONTINUATION_WINDOW_EXCEEDED")
        except (TypeError, ValueError):
            pass
    return conflicts


_VERB_CONFLICT = ({"توافق", "صحبت", "مصاحبه", "تایم"}, {"تحریم", "اعمال", "اعلام"})


def _verb_conflict(fp: EventFingerprint, cand: EventFingerprint) -> bool:
    for ga, gb in ((_VERB_CONFLICT[0], _VERB_CONFLICT[1]), (_VERB_CONFLICT[1], _VERB_CONFLICT[0])):
        if (ga & fp.predicate_tokens) and (gb & cand.predicate_tokens):
            return True
    return False


def score(fp: EventFingerprint, cand: EventFingerprint, fp_ts: str | None = None) -> dict[str, float]:
    comps: dict[str, float] = {}
    comps["actors"] = _jaccard(set(fp.primary_actors), set(cand.primary_actors))
    comps["predicate"] = max(_jaccard(fp.predicate_tokens, cand.predicate_tokens),
                             _containment(fp.predicate_tokens, cand.predicate_tokens))
    comps["location"] = 1.0 if (fp.location and fp.location == cand.location) else (
        0.0 if (fp.location and cand.location and fp.location != cand.location) else 0.5)
    comps["event_type"] = 1.0 if fp.event_type == cand.event_type else 0.0
    comps["context"] = 1.0 if (fp.conversation_context_ref
                               and fp.conversation_context_ref == cand.conversation_context_ref) else 0.0
    comps["occurrence"] = 1.0 if (fp.explicit_occurrence_id
                                  and fp.explicit_occurrence_id == cand.explicit_occurrence_id) else 0.0
    if fp.location and fp.location == cand.location and fp.event_type == cand.event_type             and fp.event_type in ("LIVE_INCIDENT", "MILITARY_STRIKE"):
        comps["incident_pair"] = 1.0
    if fp_ts and cand.occurred_at:
        try:
            import datetime

            delta = abs((datetime.datetime.fromisoformat(cand.occurred_at)
                         - datetime.datetime.fromisoformat(fp_ts)).total_seconds())
            comps["temporal"] = max(0.0, 1.0 - delta / (6 * 3600))
        except (TypeError, ValueError):
            comps["temporal"] = 0.5
    else:
        comps["temporal"] = 0.5
    return comps


ATTACH_THRESHOLD = 0.62
AMBIGUOUS_BAND = 0.12


def decide(fp: EventFingerprint, candidates: list[tuple[int, EventFingerprint]],
           fp_ts: str | None = None) -> MatchDecision:
    """§5 three-way pure decision — no side effects, deterministic (§43/§44)."""
    if not candidates:
        return MatchDecision("CREATE_NEW", reason_codes=["NO_CANDIDATES"])
    best_id, best_cand, best_total, best_comps, best_conflicts = None, None, -1.0, {}, []
    for cid, cand in candidates:
        conflicts = hard_conflicts(fp, cand, fp_ts)
        if conflicts:
            continue  # hard conflict ⇒ cannot attach this candidate
        comps = score(fp, cand, fp_ts)
        total = (0.30 * comps["actors"] + 0.25 * comps["predicate"]
                 + 0.15 * comps["location"] + 0.15 * comps["event_type"]
                 + 0.10 * comps["temporal"] + 0.05 * comps["context"]
                 + 0.10 * comps.get("incident_pair", 0.0)
                 + (0.10 if comps["occurrence"] else 0.0))
        # same-location + same-type + inside continuation ⇒ strong incident pair
        if fp.location and fp.location == cand.location                 and fp.event_type == cand.event_type                 and fp.event_type in ("LIVE_INCIDENT", "MILITARY_STRIKE"):
            total += 0.25
        if total > best_total:
            best_id, best_cand, best_total, best_comps = cid, cand, total, comps
    if best_id is None:
        allc = []
        for cid, cand in candidates:
            allc.extend(hard_conflicts(fp, cand, fp_ts))
        return MatchDecision("CREATE_NEW", reason_codes=["ALL_CANDIDATES_CONFLICT"]
                             + sorted(set(allc)))
    matched = [k for k, v in best_comps.items() if v >= 0.6]
    if best_total >= ATTACH_THRESHOLD:
        return MatchDecision("ATTACH_EXISTING", candidate_event_id=best_id,
                             matched=matched, score_components=best_comps)
    runner_up = None
    for cid, cand in candidates:
        if cid == best_id:
            continue
        if not hard_conflicts(fp, cand, fp_ts):
            runner_up = score(fp, cand, fp_ts)
            break
    if runner_up and best_total < ATTACH_THRESHOLD:
        runner_total = (0.30 * runner_up["actors"] + 0.25 * runner_up["predicate"]
                        + 0.15 * runner_up["location"] + 0.15 * runner_up["event_type"]
                        + 0.10 * runner_up["temporal"])
        if abs(best_total - runner_total) <= AMBIGUOUS_BAND:
            return MatchDecision("AMBIGUOUS_EVENT", candidate_event_id=best_id,
                                 matched=matched, score_components=best_comps,
                                 reason_codes=["SCORE_IN_AMBIGUOUS_BAND"])
    return MatchDecision("CREATE_NEW", reason_codes=["BELOW_ATTACH_THRESHOLD"],
                         score_components=best_comps)
