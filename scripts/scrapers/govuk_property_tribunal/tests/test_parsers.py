"""Tests for SHA-126 GOV.UK search/content/HTML parsers."""

from __future__ import annotations

from scripts.scrapers.govuk_property_tribunal.config import RRO_SUB_CATEGORY
from scripts.scrapers.govuk_property_tribunal.models import ArtefactKind
from scripts.scrapers.govuk_property_tribunal.parsers import (
    parse_content_api,
    parse_decision_html,
    parse_search_response,
)


SEARCH_PAYLOAD = {
    "results": [
        {
            "title": "RRO decision: 1 Test Road, London - Housing Act 2004 s.72(1)",
            "link": "/residential-property-tribunal-decisions/lon-00ag-hmf-2023-0001",
            "description": "Tribunal decision on a rent repayment order application.",
            "public_timestamp": "2023-06-15T08:30:00Z",
            "content_id": "abc-123",
            "content_purpose_supergroup": "transparency",
            "document_type": "residential_property_tribunal_decision",
            "sub_categories": [RRO_SUB_CATEGORY],
        },
        {
            # Out-of-scope: leasehold service charges (will be filtered out
            # downstream, but the parser still emits the row).
            "title": "Leasehold service charge dispute",
            "link": "/residential-property-tribunal-decisions/leasehold-x",
            "sub_categories": ["leasehold-and-statutory-and-residential-property-tribunal"],
        },
    ],
    "total": 2,
    "start": 0,
}


CONTENT_PAYLOAD = {
    "title": "RRO decision: 1 Test Road, London RPT - Housing Act 2004 s.72(1)",
    "base_path": "/residential-property-tribunal-decisions/lon-00ag-hmf-2023-0001",
    "content_id": "abc-123",
    "public_updated_at": "2023-06-15T08:30:00Z",
    "first_published_at": "2023-06-15T08:30:00Z",
    "details": {
        "public_updated_at": "2023-06-15T08:30:00Z",
        "body": (
            "<p>Case reference: LON/00AG/HMF/2023/0001</p>"
            "<p>The respondent committed an offence under section 72(1) of the "
            "Housing Act 2004 by having control of an HMO that was required to "
            "be licensed but was not licensed.</p>"
            "<p>The tribunal awards a rent repayment order in the sum of £6,000.</p>"
        ),
        "attachments": [
            {
                "url": "/government/uploads/decision-1.pdf",
                "filename": "decision-1.pdf",
                "content_type": "application/pdf",
                "title": "Decision",
                "public_updated_at": "2023-06-15T08:30:00Z",
            }
        ],
    },
}


HTML_DECISION = """
<html>
  <head><title>RRO Decision: LON/00BG/HMF/2024/0042</title></head>
  <body>
    <h1>LON/00BG/HMF/2024/0042 - 17 Example Street, London</h1>
    <dl>
      <dt>Address</dt><dd>17 Example Street, London E1 7AB</dd>
      <dt>Parties</dt><dd>Smith and Jones</dd>
    </dl>
    <p>The respondent committed an offence under section 72(1) of the Housing Act 2004.</p>
  </body>
</html>
"""


def test_parse_search_response_flattens_results():
    hits = parse_search_response(SEARCH_PAYLOAD)
    assert len(hits) == 2
    first = hits[0]
    assert first.title.startswith("RRO decision")
    assert first.link.startswith("/residential-property-tribunal-decisions/")
    assert RRO_SUB_CATEGORY in first.sub_categories
    assert first.public_timestamp is not None
    assert first.public_timestamp.year == 2023


def test_parse_content_api_extracts_metadata_and_assets():
    meta = parse_content_api(CONTENT_PAYLOAD)
    assert meta.case_reference == "LON/00AG/HMF/2023/0001"
    assert meta.base_path.endswith("lon-00ag-hmf-2023-0001")
    assert meta.govuk_page_url.startswith("https://www.gov.uk/")
    assert meta.decision_date is not None
    assert meta.decision_date.year == 2023
    assert meta.tribunal_region == "London"
    # Assets
    assert len(meta.assets) == 1
    assert meta.assets[0].kind == ArtefactKind.PDF
    assert meta.primary_artefact_kind == ArtefactKind.PDF
    assert meta.primary_asset_url and meta.primary_asset_url.endswith("decision-1.pdf")
    # Body text was cleaned
    assert "section 72(1)" in (meta.raw_text or "")
    assert "<p>" not in (meta.raw_text or "")
    assert meta.content_sha256 is not None


def test_parse_decision_html_fallback():
    meta, body = parse_decision_html(
        HTML_DECISION,
        "https://www.gov.uk/residential-property-tribunal-decisions/lon-00bg-hmf-2024-0042",
    )
    assert meta.case_reference == "LON/00BG/HMF/2024/0042"
    assert meta.address and "Example Street" in meta.address
    assert "section 72(1)" in body
    assert meta.primary_artefact_kind == ArtefactKind.HTML
    assert meta.content_sha256 is not None
