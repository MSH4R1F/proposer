"""Repairs / social-housing repairs allowlist for Housing Ombudsman decisions.

Anything that isn't clearly a repairs/disrepair/damp/mould/heating/leak/hazard
or a complaint-handling failure tied to a kept repairs issue must be rejected.

The filter takes both the parsed metadata (categories, outcome) AND the raw
body text — categories alone aren't reliable enough on the live site, so we
additionally require body-text evidence in ambiguous cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .models import OmbudsmanCaseMetadata


# ---------------------------------------------------------------------------
# Keyword dictionaries
# ---------------------------------------------------------------------------

# KEEP signals — categories or body text that map to a repairs matter type.
REPAIRS_DAMP_MOULD = {
    "damp",
    "mould",
    "mold",
    "condensation",
    "fungus",
    "spore",
}
REPAIRS_DISREPAIR = {
    "disrepair",
    "repair",
    "repairs",
    "leak",
    "leaks",
    "leaking",
    "boiler",
    "heating",
    "hot water",
    "no hot water",
    "broken window",
    "structural",
    "roof",
    "guttering",
    "plumbing",
    "drainage",
    "infestation",
    "vermin",
    "pest",
    "asbestos",
    "hazard",
    "hazardous",
    "category 1 hazard",
    "hhsrs",
    "section 11",
    "s.11",
    "s11",
    "fitness for human habitation",
    "homes (fitness for human habitation)",
    "property condition",
    "property condition complaint",
    "decent homes standard",
    "awaab",
}
COMPLAINT_HANDLING = {
    "complaint handling",
    "complaints handling",
    "complaint handling code",
    "complaint response",
    "stage 1 response",
    "stage 2 response",
}

# REJECT signals — non-repairs matters that often appear under
# "complaint handling" boilerplate. We reject IF a clear KEEP signal is
# absent.
NON_REPAIRS_REJECT = {
    "service charge": "service_charges",
    "service charges": "service_charges",
    "ground rent": "service_charges",
    "leaseholder": "service_charges",
    "leasehold": "service_charges",
    "anti-social behaviour": "asb",
    "anti social behaviour": "asb",
    "asb": "asb",
    "noise nuisance": "asb",
    "harassment": "asb",
    "rehousing": "rehousing_only",
    "transfer request": "rehousing_only",
    "allocations": "rehousing_only",
    "succession": "succession",
    "tenancy succession": "succession",
    "rent arrears": "rent_arrears",
    "arrears of rent": "rent_arrears",
    "support services only": "support_only",
    "supported housing": "support_only",
    "tenancy management": "tenancy_management_only",
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class KeepReject:
    """Decision returned by :func:`keep_repairs_social_only`."""

    keep: bool
    matter_types: List[str] = field(default_factory=list)
    reject_reason: Optional[str] = None
    matched_keywords: List[str] = field(default_factory=list)
    excerpt: Optional[str] = None


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


def _scan(haystack: str, needles) -> List[str]:
    out: List[str] = []
    for n in needles:
        if n in haystack:
            out.append(n)
    return out


def _excerpt_for(text: str, keyword: str, span: int = 80) -> Optional[str]:
    if not keyword:
        return None
    idx = text.find(keyword)
    if idx < 0:
        return None
    start = max(0, idx - span)
    end = min(len(text), idx + len(keyword) + span)
    return text[start:end].strip()


def keep_repairs_social_only(
    metadata: OmbudsmanCaseMetadata, raw_text: str
) -> KeepReject:
    """Decide whether to keep an Ombudsman decision in the repairs corpus.

    KEEP iff (categories or body) match damp/mould/disrepair/leaks/hazards/
    heating/hot-water/repair-action/related property-condition signals,
    OR a complaint-handling-failure tied to one of those issues.

    REJECT (with a reason) for service charges, ASB, rehousing/allocation-only,
    support-only, succession, rent arrears, tenancy-management-only, or
    generic complaint-handling without a kept repairs issue.
    """
    cats_lower = " ".join(c.lower() for c in metadata.complaint_categories)
    body_lower = (raw_text or "").lower()

    # Scan categories and body separately. Body evidence is what determines
    # repairs membership: a generic category like "Repairs" or "Property
    # condition" alone is too weak — the live site applies those liberally
    # and we'd swallow non-repairs cases. Body keywords are what proves
    # the determination is actually about damp/mould/disrepair/etc.
    damp_body = _scan(body_lower, REPAIRS_DAMP_MOULD)
    disrepair_body = _scan(body_lower, REPAIRS_DISREPAIR)
    complaint_body = _scan(body_lower, COMPLAINT_HANDLING)

    damp_cats = _scan(cats_lower, REPAIRS_DAMP_MOULD)
    disrepair_cats = _scan(cats_lower, REPAIRS_DISREPAIR)
    complaint_cats = _scan(cats_lower, COMPLAINT_HANDLING)

    matter_types: List[str] = []
    matched_keywords: List[str] = []
    if damp_body:
        matter_types.append("repairs_damp_mould")
        matched_keywords.extend(damp_body)
    if disrepair_body:
        matter_types.append("repairs_disrepair")
        matched_keywords.extend(disrepair_body)
    has_repairs_signal = bool(damp_body or disrepair_body)

    # Complaint handling is only KEPT if tied to a kept body repairs signal.
    if complaint_body and has_repairs_signal:
        matter_types.append("complaint_handling_failure")
        matched_keywords.extend(complaint_body)

    # Look for non-repairs reject signals across both surfaces — categories
    # like "Service charges" or body mentions of "ground rent" both flag
    # the case as non-repairs.
    reject_hits = []
    for keyword, reason in NON_REPAIRS_REJECT.items():
        if keyword in body_lower or keyword in cats_lower:
            reject_hits.append((keyword, reason))

    # Decision tree:
    if has_repairs_signal:
        # Even if non-repairs signals are present, repairs evidence wins —
        # joint complaints exist and we keep them. The matter_types tag
        # tells downstream what the case is about.
        excerpt = _excerpt_for(body_lower, matched_keywords[0]) if matched_keywords else None
        # Dedup matter_types preserving order.
        seen = set()
        ordered: List[str] = []
        for m in matter_types:
            if m not in seen:
                seen.add(m)
                ordered.append(m)
        return KeepReject(
            keep=True,
            matter_types=ordered,
            matched_keywords=matched_keywords,
            excerpt=excerpt,
        )

    # No repairs signal. Reject — with a specific reason if we have one,
    # otherwise generic.
    if reject_hits:
        keyword, reason = reject_hits[0]
        return KeepReject(
            keep=False,
            reject_reason=f"non_repairs_{reason}",
            matched_keywords=[k for k, _ in reject_hits],
            excerpt=_excerpt_for(body_lower, keyword),
        )
    # Either body or category mention of complaint-handling alone, with no
    # repairs signal anywhere, is rejected.
    if complaint_body or complaint_cats:
        excerpt_anchor = (complaint_body or complaint_cats)[0]
        return KeepReject(
            keep=False,
            reject_reason="generic_complaint_handling_no_repairs",
            matched_keywords=complaint_body + complaint_cats,
            excerpt=_excerpt_for(body_lower, excerpt_anchor),
        )
    # Categories declared a repairs label but the body had no supporting
    # evidence (and no other reject signal). Treat as a weak signal and
    # reject conservatively — we'd rather miss real repairs than ingest
    # a non-repairs case under a misleading category.
    if damp_cats or disrepair_cats:
        return KeepReject(
            keep=False,
            reject_reason="category_only_no_body_evidence",
            matched_keywords=damp_cats + disrepair_cats,
            excerpt=None,
        )
    return KeepReject(
        keep=False,
        reject_reason="no_repairs_signal",
        matched_keywords=[],
        excerpt=None,
    )


__all__ = ["KeepReject", "keep_repairs_social_only"]
