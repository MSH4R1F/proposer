"""SHA-138: GOV.UK search/content/HTML parsers for MNR rent-determination decisions.

Three layers of parser, all returning the typed models in :mod:`models`:

* :func:`parse_search_response` — flatten ``/api/search.json`` JSON into
  :class:`GovUKSearchHit` rows.
* :func:`parse_content_api` — flatten ``/api/content/<base_path>`` JSON
  into :class:`GovUKPCMetadata`, populating the rent-determination fields.
* :func:`parse_decision_html` — fallback HTML decision-page parser used
  when the content API is unavailable or empty.

Decided-rent extraction is in :func:`extract_rent_determination`.

Heavy lifting (PDFs) is delegated to
:class:`rag_engine.extractors.pdf_extractor.PDFExtractor`. We do NOT roll
our own PDF parser per Phase 0 conventions.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import GOVUK_BASE
from .models import ArtefactKind, GovUKAsset, GovUKPCMetadata, GovUKSearchHit, RentPeriod


# ---------------------------------------------------------------------------
# Decided-rent extraction (MNR-specific)
# ---------------------------------------------------------------------------


@dataclass
class RentExtraction:
    """Outcome of running the rent extractor over a decision body."""

    decided_rent_amount: Optional[float] = None
    decided_rent_period: RentPeriod = RentPeriod.UNKNOWN
    landlord_proposed_rent_amount: Optional[float] = None
    existing_rent_amount: Optional[float] = None
    statute_basis: Optional[str] = None


_PERIOD_TOKEN_TO_ENUM = {
    "per week": RentPeriod.PER_WEEK,
    "a week": RentPeriod.PER_WEEK,
    "weekly": RentPeriod.PER_WEEK,
    "pw": RentPeriod.PER_WEEK,
    "p.w": RentPeriod.PER_WEEK,
    "p/w": RentPeriod.PER_WEEK,
    "per fortnight": RentPeriod.PER_FORTNIGHT,
    "every two weeks": RentPeriod.PER_FORTNIGHT,
    "fortnightly": RentPeriod.PER_FORTNIGHT,
    "per calendar month": RentPeriod.PER_CALENDAR_MONTH,
    "a calendar month": RentPeriod.PER_CALENDAR_MONTH,
    "pcm": RentPeriod.PER_CALENDAR_MONTH,
    "p.c.m": RentPeriod.PER_CALENDAR_MONTH,
    "p/cm": RentPeriod.PER_CALENDAR_MONTH,
    "per lunar month": RentPeriod.PER_LUNAR_MONTH,
    "lunar monthly": RentPeriod.PER_LUNAR_MONTH,
    "per month": RentPeriod.PER_CALENDAR_MONTH,  # default month → CM
    "a month": RentPeriod.PER_CALENDAR_MONTH,
    "monthly": RentPeriod.PER_CALENDAR_MONTH,
    "pm": RentPeriod.PER_CALENDAR_MONTH,
    "per quarter": RentPeriod.PER_QUARTER,
    "quarterly": RentPeriod.PER_QUARTER,
    "per annum": RentPeriod.PER_ANNUM,
    "per year": RentPeriod.PER_ANNUM,
    "annually": RentPeriod.PER_ANNUM,
    "a year": RentPeriod.PER_ANNUM,
    "p.a": RentPeriod.PER_ANNUM,
    "pa": RentPeriod.PER_ANNUM,
}


# Period regex: tolerant on whitespace + optional trailing punctuation.
# Order matters — longer alternatives MUST come first so e.g. "per
# calendar month" wins over "per month".
_PERIOD_REGEX = re.compile(
    r"(?P<period>"
    r"per\s+calendar\s+month|a\s+calendar\s+month|"
    r"per\s+lunar\s+month|lunar\s+monthly|"
    r"per\s+fortnight|every\s+two\s+weeks|fortnightly|"
    r"per\s+month|a\s+month|monthly|"
    r"per\s+week|a\s+week|weekly|"
    r"per\s+quarter|quarterly|"
    r"per\s+annum|per\s+year|annually|a\s+year|"
    r"p\.?c\.?m\.?|p\.?w\.?|p\.?a\.?|p\s*/\s*cm|p\s*/\s*w|pcm|pw|pm|pa"
    r")",
    re.IGNORECASE,
)


_AMOUNT_REGEX = r"£\s*([\d]{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"


def _normalise_amount(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = raw.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _resolve_period(period_text: str) -> RentPeriod:
    if not period_text:
        return RentPeriod.UNKNOWN
    key = re.sub(r"\s+", " ", period_text.strip().lower()).rstrip(".")
    # Try the cleaned key, then strip dots / slashes for the abbreviations.
    if key in _PERIOD_TOKEN_TO_ENUM:
        return _PERIOD_TOKEN_TO_ENUM[key]
    cleaned = key.replace(".", "").replace("/", "")
    return _PERIOD_TOKEN_TO_ENUM.get(cleaned, RentPeriod.UNKNOWN)


# Decided-rent triggers: phrases that introduce the tribunal-set rent.
# The amount + period must appear within ~120 chars of the trigger.
_DECIDED_RENT_TRIGGERS = [
    re.compile(
        r"(?:tribunal|committee)\s+(?:determine[sd]?|fixe[sd]?|set[s]?|decide[sd]?|"
        r"assesse[sd]?|conclude[sd]?\s+that\s+the\s+(?:open[\-\s]?market\s+)?rent\s+(?:is|should\s+be)|"
        r"determines?\s+the\s+rent\s+(?:to\s+be|is|at)|"
        r"determined?\s+(?:a\s+)?rent\s+(?:of|at)|"
        r"determined?\s+the\s+(?:open[\-\s]?market\s+)?rent\s+(?:to\s+be|at|is))",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"\bnew\s+rent\s+(?:will\s+be|of|is|shall\s+be|at)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:open[\-\s]?market\s+)?rent\s+(?:is|shall\s+be)\s+(?:set\s+at\s+)?",
        re.IGNORECASE,
    ),
    re.compile(r"\bdecision[:\.]?\s*(?:the\s+)?rent\b", re.IGNORECASE),
]

_LANDLORD_NOTICE_TRIGGERS = [
    re.compile(
        r"\b(?:landlord|lessor)(?:'s|s)?\s+(?:proposed|notice|s\.?\s*13\s+notice|"
        r"requested|sought|asked\s+for|served\s+a\s+notice\s+for)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnew\s+rent\s+(?:proposed|in\s+the\s+(?:s\.?\s*13\s+)?notice)\b",
        re.IGNORECASE,
    ),
    # Most common phrasing: "section 13 notice proposing £X" or
    # "s.13 notice ... proposing £X".
    re.compile(
        r"\bs(?:ection|\.)?\s*13\s+notice[^.]{0,120}?proposing\b",
        re.IGNORECASE,
    ),
    # Generic: "proposed/proposing a rent of £X" or "proposing £X".
    re.compile(
        r"\b(?:proposed|proposing)\s+(?:a\s+)?(?:new\s+)?rent\b",
        re.IGNORECASE,
    ),
]

_EXISTING_RENT_TRIGGERS = [
    re.compile(
        r"\b(?:existing|current|previous|former|passing)\s+rent\b",
        re.IGNORECASE,
    ),
    re.compile(r"\brent\s+(?:is\s+)?currently\b", re.IGNORECASE),
]

# Statute patterns match both "HA 1988 s.14" and "section 14 of the HA 1988" orders.
_STATUTE_PATTERNS = [
    (
        "Housing Act 1988 s.14",
        [
            re.compile(
                r"housing\s+act\s+1988[^.]{0,40}?(?:s\.?\s*|section\s+|ss\.?\s*)14\b",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"(?:s\.?\s*|section\s+)14[^.]{0,80}?of\s+the\s+housing\s+act\s+1988",
                re.IGNORECASE | re.DOTALL,
            ),
        ],
    ),
    (
        "Housing Act 1988 s.13",
        [
            re.compile(
                r"housing\s+act\s+1988[^.]{0,40}?(?:s\.?\s*|section\s+|ss\.?\s*)13\b",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"(?:s\.?\s*|section\s+)13[^.]{0,80}?of\s+the\s+housing\s+act\s+1988",
                re.IGNORECASE | re.DOTALL,
            ),
        ],
    ),
    (
        "Rent Act 1977 s.70",
        [
            re.compile(
                r"rent\s+act\s+1977[^.]{0,40}?(?:s\.?\s*|section\s+)70\b",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"(?:s\.?\s*|section\s+)70[^.]{0,80}?of\s+the\s+rent\s+act\s+1977",
                re.IGNORECASE | re.DOTALL,
            ),
        ],
    ),
]


def _amount_period_after(text: str, start: int, window: int = 220) -> Optional[Tuple[float, RentPeriod, int]]:
    """Find the first ``£X ... per period`` in ``text[start:start+window]``.

    Returns ``(amount, period, end_offset)`` or ``None``.
    """
    chunk = text[start : start + window]
    money = re.search(_AMOUNT_REGEX, chunk)
    if not money:
        return None
    amount = _normalise_amount(money.group(1))
    if amount is None:
        return None
    # Look for a period token after the amount (within the same chunk).
    period_window = chunk[money.end() : money.end() + 80]
    period_match = _PERIOD_REGEX.search(period_window)
    if period_match:
        period = _resolve_period(period_match.group("period"))
        return amount, period, start + money.end() + period_match.end()
    # Allow a period that immediately precedes the amount (e.g. "monthly rent of £950").
    pre_chunk = text[max(0, start - 40) : start + money.start()]
    pre_period = list(_PERIOD_REGEX.finditer(pre_chunk))
    if pre_period:
        period = _resolve_period(pre_period[-1].group("period"))
        return amount, period, start + money.end()
    return amount, RentPeriod.UNKNOWN, start + money.end()


def extract_rent_determination(body_text: str) -> RentExtraction:
    """Heuristic extractor for the MNR tribunal-set rent + companion figures.

    Looks for trigger phrases that introduce the decided rent, the
    landlord's notice rent, and the existing rent. Captures the first
    plausible ``£X per <period>`` token within ~220 chars after each
    trigger. Returns a ``RentExtraction`` with whatever it could pull —
    ``decided_rent_amount`` may be ``None`` on weakly-formatted decisions.
    """
    out = RentExtraction()
    if not body_text:
        return out

    # Decided rent ----------------------------------------------------------
    for pattern in _DECIDED_RENT_TRIGGERS:
        for trigger_match in pattern.finditer(body_text):
            hit = _amount_period_after(body_text, trigger_match.end())
            if hit is not None and hit[0] > 0:
                out.decided_rent_amount = hit[0]
                out.decided_rent_period = hit[1]
                break
        if out.decided_rent_amount is not None:
            break

    # If still empty: take the *last* "£X per week/month" in the body —
    # tribunals customarily restate the decided figure at the end.
    if out.decided_rent_amount is None:
        candidates = []
        for amt_match in re.finditer(_AMOUNT_REGEX, body_text):
            tail = body_text[amt_match.end() : amt_match.end() + 80]
            period_match = _PERIOD_REGEX.search(tail)
            if not period_match:
                continue
            amount = _normalise_amount(amt_match.group(1))
            if amount is None:
                continue
            candidates.append((amount, _resolve_period(period_match.group("period"))))
        if candidates:
            out.decided_rent_amount, out.decided_rent_period = candidates[-1]

    # Landlord-proposed rent (s.13 notice) ---------------------------------
    for pattern in _LANDLORD_NOTICE_TRIGGERS:
        for trigger_match in pattern.finditer(body_text):
            hit = _amount_period_after(body_text, trigger_match.end())
            if hit is not None and hit[0] > 0:
                out.landlord_proposed_rent_amount = hit[0]
                break
        if out.landlord_proposed_rent_amount is not None:
            break

    # Existing rent ---------------------------------------------------------
    for pattern in _EXISTING_RENT_TRIGGERS:
        for trigger_match in pattern.finditer(body_text):
            hit = _amount_period_after(body_text, trigger_match.end())
            if hit is not None and hit[0] > 0:
                out.existing_rent_amount = hit[0]
                break
        if out.existing_rent_amount is not None:
            break

    # Statute basis ---------------------------------------------------------
    for label, patterns in _STATUTE_PATTERNS:
        if any(p.search(body_text) for p in patterns):
            out.statute_basis = label
            break

    return out


# ---------------------------------------------------------------------------
# /api/search.json
# ---------------------------------------------------------------------------


def parse_search_response(payload: Dict[str, Any]) -> List[GovUKSearchHit]:
    """Read GOV.UK ``/api/search.json`` shape into a list of search hits.

    The endpoint returns ``{"results": [...], "total": N, "start": ...}``.
    Each row is sparse — only ``link`` and ``title`` are guaranteed — so
    every other field is wrapped in ``.get(...)`` to keep this resilient
    to GOV.UK adding new shapes.
    """
    if not isinstance(payload, dict):
        raise TypeError("search payload must be a JSON object")

    rows = payload.get("results") or []
    hits: List[GovUKSearchHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        link = row.get("link") or ""
        title = row.get("title") or ""
        if not link or not title:
            continue

        sub_categories = row.get("sub_categories") or []
        if isinstance(sub_categories, str):
            sub_categories = [sub_categories]

        public_ts = row.get("public_timestamp")
        public_dt: Optional[datetime] = None
        if isinstance(public_ts, str):
            try:
                public_dt = datetime.fromisoformat(public_ts.replace("Z", "+00:00"))
            except ValueError:
                public_dt = None

        hits.append(
            GovUKSearchHit(
                title=title,
                link=link,
                description=row.get("description"),
                public_timestamp=public_dt,
                content_id=row.get("content_id"),
                content_purpose_supergroup=row.get("content_purpose_supergroup"),
                document_type=row.get("document_type"),
                sub_categories=[str(s) for s in sub_categories],
            )
        )
    return hits


# ---------------------------------------------------------------------------
# /api/content/<base_path>
# ---------------------------------------------------------------------------


_CASE_REF_PATTERNS = [
    # Property Chamber numbers like CHI/00ML/HMF/2023/0001 or LON/12HE/HMF/2023/1234
    re.compile(
        r"\b([A-Z]{2,4}/\d{2}[A-Z]{2}/[A-Z]{3,5}/\d{4}/\d{3,5})\b"
    ),
    # Legacy MAN/LON style without slashes (rare)
    re.compile(r"\b([A-Z]{3}/\d{4}/\d{3,5})\b"),
]


def _extract_case_reference(*, title: str, base_path: str, body_text: str = "") -> str:
    """Best-effort case-reference extraction.

    Tries (in order): explicit Property Chamber pattern in title, in body,
    fallback to a slug derived from the GOV.UK ``base_path``.
    """
    for source in (title, body_text):
        if not source:
            continue
        for pat in _CASE_REF_PATTERNS:
            m = pat.search(source)
            if m:
                return m.group(1)
    # Fallback: the path slug, with leading slash stripped.
    slug = (base_path or "").strip("/").replace("/", "_")
    return slug or "unknown"


def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s or not isinstance(s, str):
        return None
    try:
        # Accept "2023-04-12" or "2023-04-12T08:30:00Z".
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _detect_kind(filename: Optional[str], content_type: Optional[str]) -> ArtefactKind:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return ArtefactKind.PDF
    if name.endswith(".docx") or name.endswith(".doc"):
        return ArtefactKind.DOCX
    if name.endswith(".html") or name.endswith(".htm"):
        return ArtefactKind.HTML
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return ArtefactKind.PDF
    if "wordprocessing" in ct or "msword" in ct:
        return ArtefactKind.DOCX
    if "html" in ct:
        return ArtefactKind.HTML
    if "json" in ct:
        return ArtefactKind.JSON
    # Default to HTML — GOV.UK pages are HTML when no attachment.
    return ArtefactKind.HTML


def _absolute_url(maybe_relative: str) -> str:
    if not maybe_relative:
        return maybe_relative
    if maybe_relative.startswith("http://") or maybe_relative.startswith("https://"):
        return maybe_relative
    return urljoin(GOVUK_BASE + "/", maybe_relative.lstrip("/"))


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Drop scripts/styles, keep ``<br>`` as newlines.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Collapse runs of blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_content_api(payload: Dict[str, Any]) -> GovUKPCMetadata:
    """Parse one ``/api/content/<base_path>`` response into metadata.

    Handles the standard ``residential_property_tribunal_decision`` shape
    plus a few common variants. Missing fields are tolerated; the goal is
    a *best effort* metadata bag that the filter can decide on.
    """
    if not isinstance(payload, dict):
        raise TypeError("content payload must be a JSON object")

    base_path = payload.get("base_path") or ""
    title = payload.get("title") or ""
    govuk_url = _absolute_url(base_path)

    details = payload.get("details") or {}
    body_html = ""
    body_field = details.get("body")
    if isinstance(body_field, str):
        body_html = body_field
    elif isinstance(body_field, list):
        # GOV.UK sometimes ships ``body`` as ``[{content_type, content}]``.
        for entry in body_field:
            if isinstance(entry, dict) and "html" in (entry.get("content_type") or ""):
                body_html = entry.get("content") or ""
                break

    body_text = _html_to_text(body_html)

    raw_attachments = details.get("attachments") or []
    assets: List[GovUKAsset] = []
    primary_asset_url: Optional[str] = None
    primary_kind: Optional[ArtefactKind] = None
    decision_date: Optional[date] = None

    for att in raw_attachments:
        if not isinstance(att, dict):
            continue
        url = att.get("url") or att.get("href") or ""
        if not url:
            continue
        url = _absolute_url(url)
        kind = _detect_kind(att.get("filename") or url, att.get("content_type"))
        assets.append(
            GovUKAsset(
                url=url,
                kind=kind,
                filename=att.get("filename"),
                content_type=att.get("content_type"),
                title=att.get("title"),
            )
        )
        # Pick the first PDF as primary; HTML body wins only if no PDF.
        if primary_asset_url is None or (
            primary_kind != ArtefactKind.PDF and kind == ArtefactKind.PDF
        ):
            primary_asset_url = url
            primary_kind = kind
        # Decision date — try ``public_updated_at`` on first attachment.
        if decision_date is None:
            decision_date = (
                _parse_iso_date(att.get("public_updated_at"))
                or _parse_iso_date(att.get("created_at"))
                or _parse_iso_date(att.get("attachment_updated_at"))
            )

    if decision_date is None:
        decision_date = (
            _parse_iso_date(details.get("public_updated_at"))
            or _parse_iso_date(payload.get("public_updated_at"))
            or _parse_iso_date(payload.get("first_published_at"))
        )

    if primary_asset_url is None:
        primary_asset_url = govuk_url
        primary_kind = ArtefactKind.HTML

    case_ref = _extract_case_reference(
        title=title, base_path=base_path, body_text=body_text
    )

    # Tribunal region is often in the GOV.UK ``primary_publishing_organisation``
    # links or the title (e.g. "London RPT"). Best-effort, none-on-miss.
    tribunal_region = None
    title_lc = (title or "").lower()
    for region in (
        "london",
        "midlands",
        "northern",
        "southern",
        "eastern",
        "western",
        "wales",
        "south west",
        "south east",
        "north west",
        "north east",
    ):
        if region in title_lc:
            tribunal_region = region.title()
            break

    content_sha = (
        hashlib.sha256(body_text.encode("utf-8")).hexdigest() if body_text else None
    )

    rent = extract_rent_determination(body_text)

    return GovUKPCMetadata(
        case_reference=case_ref,
        title=title,
        govuk_page_url=govuk_url,
        base_path=base_path,
        content_id=payload.get("content_id"),
        decision_date=decision_date,
        public_timestamp=_parse_iso_dt(payload.get("public_updated_at"))
        or _parse_iso_dt(payload.get("first_published_at")),
        tribunal_region=tribunal_region,
        assets=assets,
        primary_asset_url=primary_asset_url,
        primary_artefact_kind=primary_kind,
        raw_text=body_text or None,
        content_sha256=content_sha,
        decided_rent_amount=rent.decided_rent_amount,
        decided_rent_period=rent.decided_rent_period,
        landlord_proposed_rent_amount=rent.landlord_proposed_rent_amount,
        existing_rent_amount=rent.existing_rent_amount,
        statute_basis=rent.statute_basis,
    )


def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Fallback HTML decision-page parser
# ---------------------------------------------------------------------------


def parse_decision_html(html: str, source_url: str) -> Tuple[GovUKPCMetadata, str]:
    """Parse a stand-alone GOV.UK decision HTML page.

    Returns the parsed metadata plus the cleaned body text. This path is
    used when the content API does not have body content (e.g. some older
    decisions are HTML-only).
    """
    soup = BeautifulSoup(html or "", "html.parser")

    title = ""
    for selector in ("h1", "title"):
        node = soup.find(selector)
        if node and node.get_text(strip=True):
            title = node.get_text(strip=True)
            break

    body_text = _html_to_text(html)
    base_path = source_url
    if source_url.startswith(GOVUK_BASE):
        base_path = source_url[len(GOVUK_BASE):] or "/"

    case_ref = _extract_case_reference(
        title=title, base_path=base_path, body_text=body_text
    )

    address = None
    parties = None
    # Heuristic: GOV.UK property tribunal pages often have a definition list
    # with "Address" and "Parties" terms. If present, lift them.
    for dt_node in soup.find_all("dt"):
        label = dt_node.get_text(strip=True).lower()
        dd = dt_node.find_next_sibling("dd")
        if dd is None:
            continue
        value = dd.get_text(" ", strip=True)
        if label.startswith("address") and not address:
            address = value
        elif label.startswith("parties") and not parties:
            parties = value

    content_sha = (
        hashlib.sha256(body_text.encode("utf-8")).hexdigest() if body_text else None
    )

    rent = extract_rent_determination(body_text)
    meta = GovUKPCMetadata(
        case_reference=case_ref,
        title=title or case_ref,
        govuk_page_url=source_url,
        base_path=base_path,
        address=address,
        primary_asset_url=source_url,
        primary_artefact_kind=ArtefactKind.HTML,
        raw_text=body_text or None,
        content_sha256=content_sha,
        decided_rent_amount=rent.decided_rent_amount,
        decided_rent_period=rent.decided_rent_period,
        landlord_proposed_rent_amount=rent.landlord_proposed_rent_amount,
        existing_rent_amount=rent.existing_rent_amount,
        statute_basis=rent.statute_basis,
    )
    if parties:
        # Best-effort split on " and " or "v"
        for sep in (" v ", " v. ", " and "):
            if sep in parties.lower():
                left, _, right = parties.partition(sep)
                meta.landlord = left.strip() or None
                meta.tenant = right.strip() or None
                break

    return meta, body_text


# ---------------------------------------------------------------------------
# PDF helper (delegates to rag_engine)
# ---------------------------------------------------------------------------


def extract_pdf_text(pdf_path: Path) -> Tuple[str, Dict[str, Any]]:
    """Thin pass-through to :class:`rag_engine.extractors.pdf_extractor.PDFExtractor`.

    Kept here so the scraper / tests can monkey-patch one symbol if the
    underlying extractor is unavailable in some environments. Do NOT
    write PDF parsing code in this module.
    """
    from rag_engine.extractors.pdf_extractor import PDFExtractor

    extractor = PDFExtractor()
    return extractor.extract_from_pdf(pdf_path)


__all__ = [
    "extract_pdf_text",
    "extract_rent_determination",
    "parse_content_api",
    "parse_decision_html",
    "parse_search_response",
    "RentExtraction",
]
