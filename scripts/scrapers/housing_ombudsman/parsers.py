"""HTML parsers for the Housing Ombudsman site (SHA-125).

Two entry points:

* :func:`parse_listing_html` — paginates the public decisions index
  (``/decisions/``) and yields a :class:`ListingEntry` per row.
* :func:`parse_detail_html` — given a detail page, returns
  ``(OmbudsmanCaseMetadata, raw_text)`` for downstream filtering and
  ingestion.

The site's HTML is BeautifulSoup-friendly and uses fairly stable class
names for the decision cards and metadata blocks. We treat selectors as
*best-effort*: when something goes missing, we record a diagnostic on
the case and keep going. We never fail the whole scrape on a single
unrecognised label — unknown outcomes go to ``parser_diagnostics``.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import KNOWN_OUTCOMES, ListingEntry, OmbudsmanCaseMetadata


# ---------------------------------------------------------------------------
# Outcome normalisation
# ---------------------------------------------------------------------------

_OUTCOME_TEXT_TO_SLUG = {
    "severe maladministration": "severe-maladministration",
    "maladministration": "maladministration",
    "partial maladministration": "partial-maladministration",
    "no maladministration": "no-maladministration",
    "service failure": "maladministration",
}


def _normalize_outcome(raw: Optional[str]) -> Tuple[Optional[str], List[str]]:
    """Normalise a free-text outcome label.

    Returns ``(slug or None, diagnostics)``. ``slug`` is one of
    :data:`KNOWN_OUTCOMES`; if the label is unrecognised, slug is
    ``None`` and a diagnostic line is added.
    """
    if not raw:
        return None, []
    cleaned = raw.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Try literal slug forms first.
    if cleaned in KNOWN_OUTCOMES:
        return cleaned, []
    # Try mapping from human text.
    for needle, slug in _OUTCOME_TEXT_TO_SLUG.items():
        if needle in cleaned:
            return slug, []
    return None, [f"unrecognised_outcome_label:{raw[:80]}"]


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
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Try ISO 8601 timestamp.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Listing parser
# ---------------------------------------------------------------------------


def _abs_url(base_url: str, href: str) -> str:
    if not href:
        return href
    parsed = urlparse(href)
    if parsed.scheme:
        return href
    return urljoin(base_url, href)


def parse_listing_html(
    html: str, *, base_url: str = "https://www.housing-ombudsman.org.uk"
) -> List[ListingEntry]:
    """Parse a single listing page into :class:`ListingEntry` rows.

    The Housing Ombudsman site uses repeated decision cards. We look
    for any block that contains an anchor whose href looks like
    ``/decisions/<reference>/`` and a visible "Case reference"
    metadata field. This is intentionally tolerant of small markup
    drift — selectors fail closed (zero rows) rather than crash.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: List[ListingEntry] = []

    # Strategy 1: explicit decision cards.
    cards = soup.select(".decision-card, .decision, .views-row, article")
    if not cards:
        # Fallback: any anchor that points at /decisions/<digits>/.
        anchors = soup.select('a[href*="/decisions/"]')
        cards = [a.find_parent() or a for a in anchors]

    seen_refs = set()
    for card in cards:
        if not isinstance(card, Tag):
            continue
        link = card.select_one('a[href*="/decisions/"]')
        if not link or not link.get("href"):
            continue
        href = str(link["href"])
        # Only keep links that look like detail pages, not the index.
        m = re.search(r"/decisions/(?P<ref>[A-Za-z0-9_\-]+)/?(?:$|[?#])", href)
        if not m:
            continue
        case_ref = m.group("ref").strip()
        if not case_ref or case_ref in seen_refs:
            continue
        # Skip listing-page anchors that just link back to /decisions/.
        if case_ref.lower() in {"decisions", "page"}:
            continue
        seen_refs.add(case_ref)

        title = link.get_text(" ", strip=True) or None
        landlord = _select_text(card, ".landlord, .field--name-field-landlord")
        listed_outcome_raw = _select_text(card, ".outcome, .field--name-field-outcome")
        date_text = _select_text(card, ".date, time, .field--name-field-decision-date")
        listed_date = _parse_date(date_text)
        # Categories are sometimes a comma-separated list.
        cats_text = _select_text(card, ".categories, .field--name-field-category")
        categories: List[str] = []
        if cats_text:
            categories = [c.strip() for c in re.split(r"[;,]", cats_text) if c.strip()]

        rows.append(
            ListingEntry(
                case_reference=case_ref,
                detail_url=_abs_url(base_url, href),
                listed_date=listed_date,
                listed_title=title,
                listed_landlord=landlord,
                listed_outcome_raw=listed_outcome_raw,
                listed_categories=categories,
            )
        )

    return rows


def _select_text(node: Tag, selector: str) -> Optional[str]:
    el = node.select_one(selector)
    if not el:
        return None
    text = el.get_text(" ", strip=True)
    return text or None


def find_next_listing_page(
    html: str, *, base_url: str = "https://www.housing-ombudsman.org.uk"
) -> Optional[str]:
    """Find the URL of the next listing page, or ``None`` if last."""
    soup = BeautifulSoup(html, "html.parser")
    # Common Drupal pager markup.
    nxt = soup.select_one(
        "li.pager__item--next a, a.pager__item--next, a[rel='next']"
    )
    if nxt and nxt.get("href"):
        return _abs_url(base_url, str(nxt["href"]))
    return None


# ---------------------------------------------------------------------------
# Detail parser
# ---------------------------------------------------------------------------

# Common labels that introduce orders / recommendations sections.
_ORDERS_HEADERS = (
    "orders",
    "the orders",
    "order",
)
_RECS_HEADERS = (
    "recommendations",
    "recommendation",
)

_LABEL_DECISION_DATE = ("decision date", "date of determination", "date")
_LABEL_LANDLORD = ("landlord", "respondent")
_LABEL_CATEGORY = ("category", "categories", "complaint category", "complaint about")
_LABEL_OUTCOME = ("outcome", "determination", "decision")
_LABEL_CASE_REF = ("case reference", "reference", "case number")


def parse_detail_html(
    html: str, source_url: str
) -> Tuple[OmbudsmanCaseMetadata, str]:
    """Parse a Housing Ombudsman detail page.

    Returns ``(metadata, raw_text)``. Unknown outcome labels do NOT
    raise — they are appended to ``metadata.parser_diagnostics`` and
    ``outcome_normalized`` is left as ``None`` so the case can still
    be filtered/kept.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Drop scripts/styles before extracting visible text.
    for bad in soup(["script", "style", "noscript"]):
        bad.decompose()

    title = None
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True) or None

    # Pull labelled metadata out of dl/dt/dd, definition lists, or
    # field--label / field--item pairs (Drupal pattern).
    labelled = _extract_labelled_fields(soup)

    diagnostics: List[str] = []

    case_reference = (
        _value_for(labelled, _LABEL_CASE_REF)
        or _case_ref_from_url(source_url)
        or "unknown"
    )

    landlord_name = _value_for(labelled, _LABEL_LANDLORD)
    decision_date = _parse_date(_value_for(labelled, _LABEL_DECISION_DATE))
    outcome_raw = _value_for(labelled, _LABEL_OUTCOME)

    cats_text = _value_for(labelled, _LABEL_CATEGORY) or ""
    complaint_categories: List[str] = []
    if cats_text:
        complaint_categories = [
            c.strip() for c in re.split(r"[;,]", cats_text) if c.strip()
        ]

    outcome_normalized, outcome_diags = _normalize_outcome(outcome_raw)
    diagnostics.extend(outcome_diags)

    # Visible body text for ingestion + filtering.
    raw_text = _visible_text(soup)

    # Orders / recommendations: scan headings.
    orders = _list_after_heading(soup, _ORDERS_HEADERS)
    recommendations = _list_after_heading(soup, _RECS_HEADERS)

    temporal_markers = {}
    if (
        "awaab" in raw_text.lower()
        or re.search(r"s\.?\s?10A\b|section\s*10A\b", raw_text, re.IGNORECASE)
        or ("Landlord and Tenant Act 1985" in raw_text and "10A" in raw_text)
    ):
        temporal_markers["awaabs_law_referenced"] = True

    metadata = OmbudsmanCaseMetadata(
        case_reference=case_reference,
        decision_date=decision_date,
        landlord_name=landlord_name,
        complaint_categories=complaint_categories,
        outcome_raw=outcome_raw,
        outcome_normalized=outcome_normalized,
        orders=orders,
        recommendations=recommendations,
        source_url=source_url,
        title=title,
        temporal_markers=temporal_markers,
        parser_diagnostics=diagnostics,
    )
    return metadata, raw_text


def _case_ref_from_url(url: str) -> Optional[str]:
    m = re.search(r"/decisions/(?P<ref>[A-Za-z0-9_\-]+)/?", url or "")
    if m:
        ref = m.group("ref").strip()
        if ref and ref.lower() not in {"decisions", "page"}:
            return ref
    return None


def _extract_labelled_fields(soup: BeautifulSoup) -> dict:
    """Pull ``label: value`` pairs out of common metadata markup.

    Looks for:

    * ``<dl><dt>Label</dt><dd>Value</dd>``
    * ``<div class="field"><div class="field__label">Label</div>``
      ``<div class="field__item">Value</div></div>``
    * ``<strong>Label</strong> Value`` patterns inside the case header.
    """
    out: dict = {}

    # Definition lists.
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            key = dt.get_text(" ", strip=True).rstrip(":").lower()
            val = dd.get_text(" ", strip=True)
            if key:
                out[key] = val

    # Drupal field markup.
    for field in soup.select("div.field, .field"):
        label_el = field.select_one(".field__label, .field-label")
        item_el = field.select_one(".field__item, .field-items, .field-item")
        if label_el and item_el:
            key = label_el.get_text(" ", strip=True).rstrip(":").lower()
            val = item_el.get_text(" ", strip=True)
            if key:
                out.setdefault(key, val)

    # <strong>Label</strong> Value pattern.
    for strong in soup.find_all("strong"):
        key = strong.get_text(" ", strip=True).rstrip(":").lower()
        if not key:
            continue
        sibling_text = ""
        for sib in strong.next_siblings:
            if isinstance(sib, Tag):
                sibling_text += " " + sib.get_text(" ", strip=True)
                break
            if isinstance(sib, str):
                sibling_text += " " + sib.strip()
                if sibling_text.strip():
                    break
        sibling_text = sibling_text.strip()
        if sibling_text:
            out.setdefault(key, sibling_text)

    return out


def _value_for(labelled: dict, candidate_keys) -> Optional[str]:
    for key in candidate_keys:
        v = labelled.get(key.lower())
        if v:
            return v
    # Loose-match: any labelled key that *contains* one of the candidate
    # tokens (e.g. "decision_date" matches "date").
    for key, v in labelled.items():
        for cand in candidate_keys:
            if cand.lower() in key:
                return v
    return None


def _visible_text(soup: BeautifulSoup) -> str:
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)
    # Collapse runs of blank lines.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _list_after_heading(soup: BeautifulSoup, headers) -> List[str]:
    """Find a heading whose text matches ``headers`` and return the next
    list's items as a list of strings. Returns ``[]`` if not found.
    """
    headers_lower = tuple(h.lower() for h in headers)
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "strong"]):
        txt = tag.get_text(" ", strip=True).rstrip(":").lower()
        if txt in headers_lower:
            # Walk forward to the next list element.
            for sib in tag.find_all_next():
                if isinstance(sib, Tag) and sib.name in ("ul", "ol"):
                    return [
                        li.get_text(" ", strip=True)
                        for li in sib.find_all("li")
                        if li.get_text(" ", strip=True)
                    ]
                if isinstance(sib, Tag) and sib.name in ("h1", "h2", "h3", "h4"):
                    break
            return []
    return []


__all__ = [
    "parse_listing_html",
    "parse_detail_html",
    "find_next_listing_page",
]
