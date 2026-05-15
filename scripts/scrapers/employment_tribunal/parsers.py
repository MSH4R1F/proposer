"""HTML parsers for GOV.UK Employment Tribunal pages (SHA-145 / SHA-65a).

Two entry points:

* :func:`parse_listing_html` — paginate the public decisions index at
  ``/employment-tribunal-decisions`` (optionally filtered by the
  ``tribunal_decision_categories`` query parameter) and yield
  :class:`ListingEntry` rows.
* :func:`parse_detail_html` — given a decision detail page, return
  ``(ETCaseMetadata, body_text)`` for Stage-2 filtering and ingestion.

GOV.UK pages are template-stable: the listing uses ``div.gem-c-document-list``
or ``ul.gem-c-document-list``, and the detail page exposes both visible
labelled metadata and a structured ``<script type="application/ld+json">``
block. We treat selectors as best-effort with explicit fallbacks — unknown
labels go to :attr:`ETCaseMetadata.parser_diagnostics`, never raise.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import (
    Country,
    ETAttachment,
    ETCaseMetadata,
    KNOWN_OUTCOMES,
    ListingEntry,
)


# ---------------------------------------------------------------------------
# Outcome normalisation
# ---------------------------------------------------------------------------

# Map human phrases observed in GOV.UK ET decision pages to stable slugs.
# Order matters — longer phrases first so "no unfair dismissal" doesn't match
# "unfair dismissal".
_OUTCOME_PHRASE_TO_SLUG: Tuple[Tuple[str, str], ...] = (
    ("claim succeeds", "claim-succeeded"),
    ("claim succeeded", "claim-succeeded"),
    ("claim is well-founded", "claim-succeeded"),
    ("claim is well founded", "claim-succeeded"),
    ("claimant was unfairly dismissed", "claim-succeeded"),
    ("dismissal was unfair", "claim-succeeded"),
    ("dismissal is unfair", "claim-succeeded"),
    ("claim is dismissed", "claim-dismissed"),
    ("claim dismissed", "claim-dismissed"),
    ("claim does not succeed", "claim-dismissed"),
    ("dismissal was not unfair", "claim-dismissed"),
    ("dismissal was fair", "claim-dismissed"),
    ("partial success", "partial-success"),
    ("partially succeeded", "partial-success"),
    ("partly succeeds", "partial-success"),
    ("withdrawn", "withdrawn"),
    ("struck out", "struck-out"),
    ("strike out", "struck-out"),
    ("preliminary hearing", "preliminary"),
    ("default judgment", "default-judgment"),
    ("remedy hearing", "remedy-only"),
    ("remedy only", "remedy-only"),
    ("reconsideration", "reconsideration"),
)


def _normalize_outcome(raw: Optional[str]) -> Tuple[Optional[str], List[str]]:
    """Map a free-text outcome label to a stable slug.

    Returns ``(slug or None, diagnostics)``. Unrecognised labels never raise
    — they surface as ``unrecognised_outcome_label:<truncated raw>`` on the
    case's ``parser_diagnostics`` list so the QA pilot can review them.
    """
    if not raw:
        return None, []
    cleaned = re.sub(r"\s+", " ", raw.strip().lower())
    if cleaned in KNOWN_OUTCOMES:
        return cleaned, []
    for needle, slug in _OUTCOME_PHRASE_TO_SLUG:
        if needle in cleaned:
            return slug, []
    return None, [f"unrecognised_outcome_label:{raw[:80]}"]


def _outcome_phrase_from_body(body_text: str) -> Optional[str]:
    """Scan visible body text for a known outcome phrase.

    Returns the first matching phrase (longest-prefix-wins order from
    ``_OUTCOME_PHRASE_TO_SLUG``) so the caller can hand it to
    :func:`_normalize_outcome`. Used as the SHA-146 fallback when the
    labelled-field path returned no outcome.

    The phrase mapping is already ordered with longer phrases first
    (e.g. "claim is well-founded" before "claim succeeds"); preserving
    that order matters so a partial-success body doesn't get picked up
    by a generic "claim succeeded" earlier in the text.
    """
    if not body_text:
        return None
    haystack = re.sub(r"\s+", " ", body_text.lower())
    for needle, _slug in _OUTCOME_PHRASE_TO_SLUG:
        if needle in haystack:
            return needle
    return None


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_DATE_FORMATS = (
    "%d %B %Y",
    "%d %b %Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
)


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _abs_url(base_url: str, href: str) -> str:
    if not href:
        return href
    parsed = urlparse(href)
    if parsed.scheme:
        return href
    return urljoin(base_url + "/", href)


def _base_path_from_url(url: str) -> Optional[str]:
    """Extract the GOV.UK base path (e.g. ``/employment-tribunal-decisions/foo-v-bar``)."""
    if not url:
        return None
    parsed = urlparse(url)
    path = parsed.path or ""
    return path if path else None


def _case_ref_from_url(url: str) -> Optional[str]:
    """Stable case reference: the slug after ``/employment-tribunal-decisions/``."""
    if not url:
        return None
    m = re.search(r"/employment-tribunal-decisions/([^/?#]+)", url)
    if m:
        slug = m.group(1).strip()
        return slug or None
    return None


# Slugs GOV.UK exposes under /employment-tribunal-decisions/<slug> that are
# NOT decision pages: marketing widgets, feed endpoints, and pagination
# back-links. Stage-2 caught these as a backstop in the SHA-146 pilot; we
# now reject them at Stage-1 to keep `cases_seen` honest.
_NON_CASE_SLUGS = frozenset(
    {
        "employment-tribunal-decisions",
        "page",
        "email-signup",
        "feedback",
        "atom",
        "atom.xml",
    }
)


def _is_non_case_listing_href(href: str) -> bool:
    """Return True for listing-page anchors that don't lead to a decision page.

    Covers two SHA-146 pilot patterns:

    1. Filter / pagination links that target the index path itself with
       query strings (``?tribunal_decision_categories=…`` /
       ``?page=2`` / ``?keywords=…``).
    2. Anchors to non-case slugs under the index path
       (``/employment-tribunal-decisions/email-signup`` and friends).
       These are handled below via :data:`_NON_CASE_SLUGS` but we also
       short-circuit on common nav slugs here so the cheaper test fires
       first.
    """
    if not href:
        return True
    # Filter / pagination links targeting the index itself.
    if re.search(r"/employment-tribunal-decisions/?\?", href):
        return True
    if re.search(r"/employment-tribunal-decisions/?#", href):
        return True
    if re.fullmatch(r"[^?#]*?/employment-tribunal-decisions/?", href):
        return True
    # Atom feed.
    if href.rstrip("/").endswith("/employment-tribunal-decisions.atom"):
        return True
    return False


# ---------------------------------------------------------------------------
# Listing parser
# ---------------------------------------------------------------------------


def parse_listing_html(
    html: str, *, base_url: str = "https://www.gov.uk"
) -> List[ListingEntry]:
    """Parse a GOV.UK ET listing page into :class:`ListingEntry` rows.

    Tolerant of small markup drift: we look for any anchor whose href is
    ``/employment-tribunal-decisions/<slug>`` (excluding the index itself).
    Selectors fail closed — a page with zero matching anchors yields ``[]``
    rather than crashing.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: List[ListingEntry] = []
    seen_refs: set = set()

    anchors = soup.select('a[href*="/employment-tribunal-decisions/"]')
    for anchor in anchors:
        href = str(anchor.get("href") or "")
        if not href:
            continue
        # SHA-146 pilot finding: GOV.UK's ET landing page links to several
        # non-case slugs alongside the decision detail pages (email signup,
        # feedback survey, atom feed, etc) and to the index path itself
        # with various query strings (category / page / tribunal filter).
        # Stage-2 caught the noise as a backstop, but skipping at Stage-1
        # keeps `cases_seen` honest and avoids paying a detail fetch on
        # nav clutter.
        if _is_non_case_listing_href(href):
            continue
        case_ref = _case_ref_from_url(href)
        if not case_ref or case_ref in seen_refs:
            continue
        if case_ref.lower() in _NON_CASE_SLUGS:
            continue
        seen_refs.add(case_ref)

        # Pull listing-context fields from the nearest ancestor block.
        container = anchor.find_parent(["li", "article", "div"]) or anchor.parent
        title = anchor.get_text(" ", strip=True) or None

        listed_categories = _listing_categories(container)
        listed_date = _listing_date(container)
        country_hint = _country_from_text(
            anchor.get_text(" ", strip=True)
            + " "
            + (container.get_text(" ", strip=True) if isinstance(container, Tag) else "")
        )

        rows.append(
            ListingEntry(
                case_reference=case_ref,
                detail_url=_abs_url(base_url, href),
                base_path=_base_path_from_url(href),
                title=title,
                listed_date=listed_date,
                listed_categories=listed_categories,
                country_hint=country_hint,
            )
        )
    return rows


def _listing_categories(container) -> List[str]:
    """Pull the jurisdiction/category labels off a listing row."""
    if not isinstance(container, Tag):
        return []
    text_parts: List[str] = []
    # Common GOV.UK metadata markup: dl.gem-c-metadata or .govuk-summary-list.
    for el in container.select(
        "dd, .gem-c-metadata__definition, .govuk-summary-list__value, "
        ".govuk-tag, .gem-c-tag"
    ):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        for part in re.split(r"[;,]", text):
            cleaned = part.strip()
            if cleaned and cleaned.lower() not in {"jurisdiction code", "category"}:
                text_parts.append(cleaned)
    # Dedupe preserving order.
    seen: set = set()
    out: List[str] = []
    for cat in text_parts:
        if cat.lower() in seen:
            continue
        seen.add(cat.lower())
        out.append(cat)
    return out


def _listing_date(container) -> Optional[date]:
    if not isinstance(container, Tag):
        return None
    for sel in ("time[datetime]", "time", ".gem-c-document-list__item-metadata time"):
        el = container.select_one(sel)
        if el:
            dt_attr = el.get("datetime") or el.get_text(" ", strip=True)
            d = _parse_date(dt_attr)
            if d:
                return d
    return None


def _country_from_text(text: str) -> Country:
    t = (text or "").lower()
    if "scotland" in t or "edinburgh" in t or "glasgow" in t or "aberdeen" in t:
        return Country.SCOTLAND
    if "england" in t or "wales" in t or "london" in t or "manchester" in t:
        return Country.ENGLAND_AND_WALES
    return Country.UNKNOWN


def find_next_listing_page(
    html: str, *, base_url: str = "https://www.gov.uk"
) -> Optional[str]:
    """Find the URL of the next listing page, or ``None`` if there isn't one.

    GOV.UK's pagination markup on this listing (verified live 2026-05-15)
    is::

        <div class="govuk-pagination__next">
          <a href="/employment-tribunal-decisions?page=2&amp;…"
             class="govuk-link govuk-pagination__link" …>
            …<span class="govuk-pagination__link-title">Next page</span>…
          </a>
        </div>

    The element is a ``div``, NOT a ``li`` — the old selector list missed
    this and pagination stopped after page 1, capping every scrape at 50
    cases. We now match ``.govuk-pagination__next a`` (any wrapping
    element) and keep ``<link rel="next">`` / ``a[rel="next"]`` as
    secondary fallbacks for layout drift.
    """
    soup = BeautifulSoup(html, "html.parser")
    nxt = soup.select_one(
        ".govuk-pagination__next a, "
        "link[rel='next'], a[rel='next'], "
        "li.govuk-pagination__next a"
    )
    if nxt and nxt.get("href"):
        return _abs_url(base_url, str(nxt["href"]))
    return None


# ---------------------------------------------------------------------------
# Detail parser
# ---------------------------------------------------------------------------

_CASE_NUMBER_PATTERN = re.compile(r"\b(\d{7}/\d{4})\b")

_LABEL_DECISION_DATE = ("decision date", "judgment date", "date")
_LABEL_JURISDICTION_CODE = (
    "jurisdiction code",
    "jurisdiction",
    "tribunal decision category",
)
_LABEL_CASE_NUMBER = ("case number", "case numbers", "case reference")
# SHA-146 pilot finding: `"decision"` used to live here and was matched
# loosely against `"decision date"` on live GOV.UK pages, pulling the date
# string into `outcome_raw` and tripping every kept row's
# `parser_diagnostics`. The labelled-field path now uses only unambiguous
# outcome labels; everything else falls through to body-text phrase
# scanning in ``_derive_outcome_raw``.
_LABEL_OUTCOME = ("outcome", "judgment")
_LABEL_COUNTRY = ("country", "country of decision")


def parse_detail_html(
    html: str, source_url: str
) -> Tuple[ETCaseMetadata, str]:
    """Parse a GOV.UK ET decision page.

    Returns ``(metadata, body_text)``. ``body_text`` is the cleaned visible
    text (used by Stage-2 filter and by the SourceDocument bridge); the raw
    public attachment PDFs are *not* downloaded here — that lives in SHA-65b.
    Unknown outcome labels are recorded on ``metadata.parser_diagnostics``
    but never raise.
    """
    soup = BeautifulSoup(html, "html.parser")
    diagnostics: List[str] = []

    # Detect licence on the FULL soup before we strip non-content tags —
    # GOV.UK's OGL footer is the canonical signal, and removing <footer>
    # before licence detection would force every page to OGL-3.0-inferred.
    licence_observed = _detect_licence_from_footer(soup)

    # Drop script/style/nav before pulling visible text.
    for bad in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        if not (bad.name == "script" and (bad.get("type") or "").lower() == "application/ld+json"):
            bad.decompose()

    title = None
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True) or None

    labelled = _extract_labelled_fields(soup)

    jurisdiction_codes = _split_csv(_value_for(labelled, _LABEL_JURISDICTION_CODE)) or _all_jurisdiction_tags(soup)
    case_numbers = _split_csv(_value_for(labelled, _LABEL_CASE_NUMBER))
    decision_date = _parse_date(_value_for(labelled, _LABEL_DECISION_DATE))
    outcome_raw = _value_for(labelled, _LABEL_OUTCOME)

    body_text = _visible_text(soup)

    # SHA-146 pilot finding: GOV.UK ET pages are "landing-page + PDF" —
    # the HTML body rarely carries an explicit outcome label and the real
    # outcome lives in the PDF attachment. When the labelled-field path
    # returned nothing, fall back to scanning the visible body text for
    # the canonical outcome phrases the parser already knows about
    # (``_OUTCOME_PHRASE_TO_SLUG``). If a phrase matches, surface it as
    # ``outcome_raw`` so ``_normalize_outcome`` can map it; the
    # bare-decision-date string never becomes ``outcome_raw`` again.
    if not outcome_raw:
        body_match = _outcome_phrase_from_body(body_text)
        if body_match is not None:
            outcome_raw = body_match

    # Fall back: harvest case number(s) from body text using the canonical
    # ET pattern (7 digits / 4-digit year).
    if not case_numbers:
        case_numbers = sorted(set(_CASE_NUMBER_PATTERN.findall(body_text)))

    country = _country_from_labelled(labelled) or _country_from_text(body_text)

    outcome_normalized, outcome_diags = _normalize_outcome(outcome_raw)
    diagnostics.extend(outcome_diags)

    attachments = _parse_attachments(soup, source_url)

    case_reference = (
        _case_ref_from_url(source_url)
        or (case_numbers[0] if case_numbers else None)
        or "unknown"
    )

    metadata = ETCaseMetadata(
        case_reference=case_reference,
        title=title,
        source_url=source_url,
        base_path=_base_path_from_url(source_url),
        case_numbers=case_numbers,
        decision_date=decision_date,
        country=country,
        jurisdiction_codes=jurisdiction_codes,
        outcome_raw=outcome_raw,
        outcome_normalized=outcome_normalized,
        attachments=attachments,
        source_license_observed=licence_observed,
        parser_diagnostics=diagnostics,
    )
    return metadata, body_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in re.split(r"[;,]", value) if v.strip()]


def _value_for(labelled: Dict[str, str], candidate_keys: Iterable[str]) -> Optional[str]:
    for key in candidate_keys:
        v = labelled.get(key.lower())
        if v:
            return v
    for key, v in labelled.items():
        for cand in candidate_keys:
            if cand.lower() in key:
                return v
    return None


def _extract_labelled_fields(soup: BeautifulSoup) -> Dict[str, str]:
    """Pull ``label: value`` pairs from GOV.UK metadata markup.

    Looks at the patterns GOV.UK uses across the design system:

    * ``<dl class="gem-c-metadata"><dt>Label</dt><dd>Value</dd>``
    * ``<dl class="govuk-summary-list"><dt class="govuk-summary-list__key">``
    * Plain ``<dl>`` definition lists
    * ``<th>Label</th><td>Value</td>`` table rows
    """
    out: Dict[str, str] = {}

    # dl/dt/dd (covers gem-c-metadata + govuk-summary-list).
    for dl in soup.find_all("dl"):
        dts = dl.find_all(["dt"])
        dds = dl.find_all(["dd"])
        for dt, dd in zip(dts, dds):
            key = _clean_label(dt.get_text(" ", strip=True))
            val = _clean_value(dd.get_text(" ", strip=True))
            if key:
                out.setdefault(key, val)

    # Table-row markup.
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        key = _clean_label(cells[0].get_text(" ", strip=True))
        val = _clean_value(" ".join(c.get_text(" ", strip=True) for c in cells[1:]))
        if key:
            out.setdefault(key, val)

    return out


def _clean_label(text: str) -> str:
    return _clean_value(text).rstrip(":").lower()


def _clean_value(text: str) -> str:
    text = (text or "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _all_jurisdiction_tags(soup: BeautifulSoup) -> List[str]:
    """Fall-back jurisdiction-code extraction from .govuk-tag / .gem-c-tag chips."""
    tags: List[str] = []
    for el in soup.select(".govuk-tag, .gem-c-tag"):
        text = el.get_text(" ", strip=True)
        if text and text.lower() != "filter":
            tags.append(text)
    return tags


def _country_from_labelled(labelled: Dict[str, str]) -> Optional[Country]:
    val = _value_for(labelled, _LABEL_COUNTRY)
    if not val:
        return None
    lower = val.lower()
    if "scotland" in lower:
        return Country.SCOTLAND
    if "england" in lower or "wales" in lower:
        return Country.ENGLAND_AND_WALES
    return None


def _parse_attachments(soup: BeautifulSoup, source_url: str) -> List[ETAttachment]:
    """Find PDF / document attachments published on the page.

    GOV.UK exposes attachments under ``.gem-c-attachment``, ``.attachment``,
    or plain anchor links whose href ends in ``.pdf`` / ``.doc`` / ``.docx``.
    """
    attachments: List[ETAttachment] = []
    seen: set = set()

    selectors = (
        ".gem-c-attachment a[href]",
        ".attachment a[href]",
        'a[href$=".pdf"]',
        'a[href$=".PDF"]',
        'a[href$=".doc"]',
        'a[href$=".docx"]',
    )
    for sel in selectors:
        for anchor in soup.select(sel):
            href = str(anchor.get("href") or "")
            if not href:
                continue
            abs_url = _abs_url(source_url, href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            attachments.append(
                ETAttachment(
                    url=abs_url,
                    title=anchor.get_text(" ", strip=True) or None,
                    content_type=_guess_content_type(href),
                )
            )
    return attachments


def _guess_content_type(href: str) -> Optional[str]:
    lower = (href or "").lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".doc"):
        return "application/msword"
    if lower.endswith(".docx"):
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    return None


def _detect_licence_from_footer(soup: BeautifulSoup) -> str:
    """Look for licence statements on the page. Default to OGL-3.0.

    GOV.UK pages overwhelmingly declare OGL v3.0 in the footer or copyright
    block. If a page departs from that, we record what we saw verbatim so
    downstream code can refuse to publish snippets externally.
    """
    text = soup.get_text(" ", strip=True).lower()
    if "open government licence v3.0" in text or "open government licence v3" in text:
        return "OGL-3.0"
    if "open government licence" in text:
        return "OGL-unversioned"
    if "crown copyright" in text and "open government licence" not in text:
        return "crown_copyright_check"
    # Be conservative — assume OGL v3.0 (the public default) but flag that
    # this was inferred rather than confirmed by the page text.
    return "OGL-3.0-inferred"


def _visible_text(soup: BeautifulSoup) -> str:
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


__all__ = [
    "parse_listing_html",
    "parse_detail_html",
    "find_next_listing_page",
]
