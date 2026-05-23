#!/usr/bin/env python3
"""Ombudsman-specific leakage guard for the housing facts/factor extractors.

The Housing Ombudsman equivalent of tribunal-finding leakage is any
phrase that states the Ombudsman's *determination* or the landlord's
adjudicated fault, rather than reciting pre-decision events:

* determination verbs: "we found maladministration", "there was service
  failure", "we have determined", "the landlord failed to ...",
* remedy/compensation ORDERED by the Ombudsman (vs. an offer the
  landlord made before the determination, which is a pre-decision fact),
* "Our decision (determination)", "Summary of reasons", "Putting things
  right", "Orders" section voice,
* "reasonable redress" / "no maladministration" / "outside our
  jurisdiction" as a finding.

A pre-decision compensation OFFER by the landlord ("the landlord offered
£X in its stage 2 response") is allowed — it is a fact about the
landlord's conduct, not an Ombudsman order. The guard therefore targets
the *Ombudsman-voice* and *ordered-remedy* phrasings specifically.
"""
from __future__ import annotations

import re

_LEAKAGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # --- Ombudsman determination voice ("we"/"this Service"/"the Ombudsman") ---
    re.compile(r"\b(?:we|this service|the ombudsman|the service)\s+(?:found|find|have found|determined?|have determined|concluded?|decide[ds]?|have decided|consider(?:ed)? there (?:was|were))\b", re.IGNORECASE),
    re.compile(r"\bour (?:decision|determination|investigation found|finding)\b", re.IGNORECASE),
    re.compile(r"\bour decision \(determination\)\b", re.IGNORECASE),
    re.compile(r"\bsummary of reasons\b", re.IGNORECASE),
    re.compile(r"\bputting things right\b", re.IGNORECASE),
    re.compile(r"\bdetermination\b", re.IGNORECASE),
    # --- Outcome findings stated as conclusions ---
    re.compile(r"\bthere (?:was|were) (?:severe )?maladministration\b", re.IGNORECASE),
    re.compile(r"\bthere (?:was|were) (?:a )?service failure\b", re.IGNORECASE),
    re.compile(r"\bthere (?:was|were) reasonable redress\b", re.IGNORECASE),
    re.compile(r"\b(?:finding|found|was) (?:of |a finding of )?reasonable redress\b", re.IGNORECASE),
    re.compile(r"\bno maladministration\b", re.IGNORECASE),
    re.compile(r"\b(?:severe )?maladministration (?:in|with|by) the landlord\b", re.IGNORECASE),
    re.compile(r"\bwe (?:make|made|can make) (?:an? )?order", re.IGNORECASE),
    re.compile(r"\bamounts? to (?:severe )?maladministration\b", re.IGNORECASE),
    # --- Adjudicated landlord fault (Ombudsman conclusion, not recital) ---
    # NOTE: a resident-attributed allegation ("she complains the landlord
    # failed to ...") is a pre-decision fact and is allowed; only the
    # bare Ombudsman-voice assertion is leakage. The negative lookbehind
    # excludes the common attribution verbs.
    re.compile(r"(?<!complains )(?<!complained )(?<!says )(?<!said )(?<!alleges )(?<!alleged )(?<!reported )(?<!stated )\bthe landlord(?:'s)? (?:failed|failure[ds]?) to\b", re.IGNORECASE),
    re.compile(r"\bthis (?:was|amounted to) (?:a )?(?:record[\- ]keeping )?(?:failure|maladministration|service failure)\b", re.IGNORECASE),
    re.compile(r"\bwas (?:a )?(?:serious )?failing\b", re.IGNORECASE),
    # --- Jurisdiction disposition ---
    re.compile(r"\boutside (?:our|the ombudsman's|this service's) (?:jurisdiction|remit)\b", re.IGNORECASE),
    re.compile(r"\b(?:is|was|are|were|fall[s]?) outside (?:our )?jurisdiction\b", re.IGNORECASE),
    re.compile(r"\bwe (?:cannot|are unable to|will not) (?:investigate|determine|consider)\b", re.IGNORECASE),
    re.compile(r"\bbetter suited to a court\b", re.IGNORECASE),
    # --- Remedy ORDERED by the Ombudsman (vs. landlord's pre-decision offer) ---
    re.compile(r"\bthe landlord (?:must|is ordered to|is to) pay\b", re.IGNORECASE),
    re.compile(r"\bwe order(?:ed)? the landlord\b", re.IGNORECASE),
    re.compile(r"\bcompensation order\b", re.IGNORECASE),
    re.compile(r"\b(?:ordered|orders) (?:the landlord )?to pay\b", re.IGNORECASE),
    re.compile(r"\border(?:s|ed)?:\s", re.IGNORECASE),
    re.compile(r"\bwe recommend\b", re.IGNORECASE),
    re.compile(r"\bour recommendations?\b", re.IGNORECASE),
    # --- Tribunal-style finding verbs (defensive; rare in ombudsman text) ---
    re.compile(r"\bthe tribunal (?:finds?|found|holds?|held|concludes?)\b", re.IGNORECASE),
    re.compile(r"\b(?:we|I) (?:find|hold|conclude|determine)\b", re.IGNORECASE),
)


def detect_leakage(text: str) -> list[str]:
    """Return the leakage phrases that fired against *text* (deduped, order-preserving)."""
    if not text:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for p in _LEAKAGE_PATTERNS:
        m = p.search(text)
        if m:
            frag = m.group(0).strip()
            key = frag.lower()
            if key not in seen:
                seen.add(key)
                hits.append(frag)
    return hits


__all__ = ["detect_leakage"]
