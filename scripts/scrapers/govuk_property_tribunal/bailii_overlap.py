"""SHA-126: BAILII / GOV.UK overlap detection.

The BAILII Property Chamber feed and the GOV.UK Property Tribunal
publishing pipeline frequently emit the *same* decision under different
URLs / file formats. To avoid double-indexing, every accepted GOV.UK
record is checked against ``data/raw/bailii/master_index.json`` before
being committed to the master index.

The match algorithm is conservative — a single strong signal (case
reference, content hash, or asset URL hash) produces a ``duplicate``
verdict; multiple weak signals (year + address overlap) produce
``matched`` (= probably the same decision but not certainly so) and we
deweight without dropping. No matches -> ``govuk_only``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import GovUKPCMetadata, ScrapeRecord


# ---------------------------------------------------------------------------
# Buckets returned by overlap_bucket
# ---------------------------------------------------------------------------

BUCKET_DUPLICATE = "duplicate"
BUCKET_MATCHED = "matched"
BUCKET_GOVUK_ONLY = "govuk_only"
BUCKET_BAILII_ONLY = "bailii_only"
BUCKET_UNCERTAIN = "uncertain"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_case_ref(ref: Optional[str]) -> str:
    if not ref:
        return ""
    return re.sub(r"[^A-Z0-9]", "", ref.upper())


def _hash_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()


def _normalise_title(title: Optional[str]) -> str:
    if not title:
        return ""
    return re.sub(r"\s+", " ", title.lower()).strip()


def _address_tokens(address: Optional[str]) -> set:
    if not address:
        return set()
    tokens = re.findall(r"[A-Za-z0-9]+", address.lower())
    return {t for t in tokens if len(t) >= 3}


def _record_year(meta: GovUKPCMetadata) -> Optional[int]:
    if meta.decision_date is not None:
        return meta.decision_date.year
    if meta.public_timestamp is not None:
        return meta.public_timestamp.year
    return None


# ---------------------------------------------------------------------------
# Master-index loading
# ---------------------------------------------------------------------------


def load_bailii_index(path: Path) -> Dict[str, Any]:
    """Load and pre-index a BAILII master index for lookup.

    Returns a dict with the original ``cases`` list plus pre-computed
    indices keyed by normalised case reference, URL hashes, and year.
    """
    p = Path(path)
    if not p.is_file():
        return {"cases": [], "by_ref": {}, "by_url_hash": {}, "by_year_addr": {}, "title_year": {}}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"cases": [], "by_ref": {}, "by_url_hash": {}, "by_year_addr": {}, "title_year": {}}

    cases = data.get("cases") or data.get("records") or []
    by_ref: Dict[str, Dict[str, Any]] = {}
    by_url_hash: Dict[str, Dict[str, Any]] = {}
    title_year: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        ref_norm = _normalise_case_ref(case.get("case_reference"))
        if ref_norm:
            by_ref[ref_norm] = case
        for url_field in ("html_url", "pdf_url", "source_url"):
            uh = _hash_url(case.get(url_field))
            if uh:
                by_url_hash[uh] = case
        year = case.get("year")
        title = _normalise_title(case.get("title"))
        if isinstance(year, int) and title:
            title_year[(title, year)] = case
    return {
        "cases": cases,
        "by_ref": by_ref,
        "by_url_hash": by_url_hash,
        "title_year": title_year,
    }


# ---------------------------------------------------------------------------
# Per-record overlap classifier
# ---------------------------------------------------------------------------


def overlap_bucket(
    govuk: GovUKPCMetadata,
    bailii_index: Dict[str, Any],
) -> Tuple[Optional[str], str]:
    """Classify a single GOV.UK record against the BAILII master index.

    Returns ``(duplicate_of_source_id, bucket)`` where ``bucket`` is one
    of the ``BUCKET_*`` constants.  ``duplicate_of_source_id`` is the
    BAILII case_reference when a strong match is found, otherwise
    ``None``.
    """
    by_ref = bailii_index.get("by_ref") or {}
    by_url_hash = bailii_index.get("by_url_hash") or {}
    title_year = bailii_index.get("title_year") or {}

    # 1. Strong: case reference
    ref_norm = _normalise_case_ref(govuk.case_reference)
    if ref_norm and ref_norm in by_ref:
        return by_ref[ref_norm].get("case_reference"), BUCKET_DUPLICATE

    # 2. Strong: any URL hash (page url / asset urls)
    candidate_urls: List[str] = []
    if govuk.govuk_page_url:
        candidate_urls.append(govuk.govuk_page_url)
    if govuk.primary_asset_url:
        candidate_urls.append(govuk.primary_asset_url)
    for asset in govuk.assets or []:
        if asset.url:
            candidate_urls.append(asset.url)
    for url in candidate_urls:
        uh = _hash_url(url)
        if uh and uh in by_url_hash:
            return by_url_hash[uh].get("case_reference"), BUCKET_DUPLICATE

    # 3. Weak: title + year exact-match
    year = _record_year(govuk)
    title_norm = _normalise_title(govuk.title)
    if year is not None and title_norm:
        case = title_year.get((title_norm, year))
        if case is not None:
            return case.get("case_reference"), BUCKET_MATCHED

    # 4. Weaker: address overlap + same year
    if year is not None and govuk.address:
        addr_toks = _address_tokens(govuk.address)
        if addr_toks:
            for case in bailii_index.get("cases") or []:
                if case.get("year") != year:
                    continue
                ct = _normalise_title(case.get("title"))
                ct_toks = _address_tokens(ct)
                if addr_toks & ct_toks and len(addr_toks & ct_toks) >= 3:
                    return case.get("case_reference"), BUCKET_MATCHED

    return None, BUCKET_GOVUK_ONLY


# ---------------------------------------------------------------------------
# Aggregate report (used by scrape_summary.json)
# ---------------------------------------------------------------------------


def overlap_report(records: Iterable[ScrapeRecord]) -> Dict[str, int]:
    """Aggregate per-record buckets into a summary dict."""
    counts: Counter = Counter()
    for rec in records:
        bucket = rec.bailii_overlap_bucket or BUCKET_GOVUK_ONLY
        counts[bucket] += 1
    return dict(counts)


__all__ = [
    "BUCKET_DUPLICATE",
    "BUCKET_MATCHED",
    "BUCKET_GOVUK_ONLY",
    "BUCKET_BAILII_ONLY",
    "BUCKET_UNCERTAIN",
    "load_bailii_index",
    "overlap_bucket",
    "overlap_report",
]
