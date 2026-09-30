"""Independent evidence auditor: runs AFTER generation, BEFORE publishing.

Every factual body paragraph must map to claim IDs; numbers appearing in a paragraph
must exist in the referenced claims. Unsupported paragraphs are removed (once);
if nothing survives, the story is rejected.
"""
from __future__ import annotations

import logging
from typing import Any

from app.verification.gates import numbers_in
from .models import StoryDraft

log = logging.getLogger("akh.auditor")


def audit_draft(draft: StoryDraft, claims: list[dict[str, Any]]) -> tuple[StoryDraft, list[str]]:
    issues: list[str] = []
    claims_by_id = {str(c["id"]): c for c in claims}
    publishable_states = {"CONFIRMED", "CORROBORATED"}

    kept_paragraphs = []
    for p in draft.body:
        refs = [str(r) for r in p.claim_refs]
        valid_refs = [r for r in refs if r in claims_by_id]
        if not valid_refs:
            issues.append(f"paragraph dropped: no valid claim refs ({refs or 'none'})")
            continue
        unsupported_numbers = set()
        para_nums = numbers_in(p.text)
        ref_nums: set[str] = set()
        for r in valid_refs:
            ref_nums |= numbers_in(claims_by_id[r]["text"])
        if para_nums and not (para_nums & ref_nums):
            unsupported_numbers = para_nums
        if unsupported_numbers:
            issues.append(
                f"paragraph dropped: numbers {sorted(unsupported_numbers)} not in referenced claims"
            )
            continue
        # definite phrasing on unconfirmed claims is not allowed: require ≥1 publishable ref
        if not any(claims_by_id[r]["state"] in publishable_states for r in valid_refs):
            if para_nums or any(w in p.text for w in ("تأیید شد", "confirmed", "مسلم")):
                issues.append(f"paragraph dropped: unconfirmed definite phrasing (refs {valid_refs})")
                continue
        kept_paragraphs.append(p)

    draft.body = kept_paragraphs
    if not draft.body:
        issues.append("REJECTED: no supported paragraphs remain")
    return draft, issues
