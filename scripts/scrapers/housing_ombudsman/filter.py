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
    haystack = f"{cats_lower}\n{body_lower}"

    matched_damp = _scan(haystack, REPAIRS_DAMP_MOULD)
    matched_disrepair = _scan(haystack, REPAIRS_DISREPAIR)
    matched_complaint = _scan(haystack, COMPLAINT_HANDLING)

    matter_types: List[str] = []
    matched_keywords: List[str] = []
    if matched_damp:
        matter_types.append("repairs_damp_mould")
        matched_keywords.extend(matched_damp)
    if matched_disrepair:
        matter_types.append("repairs_disrepair")
        matched_keywords.extend(matched_disrepair)
    has_repairs_signal = bool(matched_damp or matched_disrepair)

    # Complaint handling is only KEPT if tied to a kept repairs signal.
    if matched_complaint and has_repairs_signal:
        matter_types.append("complaint_handling_failure")
        matched_keywords.extend(matched_complaint)

    # Look for non-repairs reject signals.
    reject_hits = []
    for keyword, reason in NON_REPAIRS_REJECT.items():
        if keyword in haystack:
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
    if matched_complaint:
        return KeepReject(
            keep=False,
            reject_reason="generic_complaint_handling_no_repairs",
            matched_keywords=matched_complaint,
            excerpt=_excerpt_for(body_lower, matched_complaint[0]),
        )
    return KeepReject(
        keep=False,
        reject_reason="no_repairs_signal",
        matched_keywords=[],
        excerpt=None,
    )


__all__ = ["KeepReject", "keep_repairs_social_only"]
