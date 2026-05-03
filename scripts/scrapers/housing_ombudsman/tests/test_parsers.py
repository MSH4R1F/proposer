"""Tests for the Housing Ombudsman HTML parsers.

We synthesise minimal fixtures inline. The shapes are based on the live
site's class names (``.decision-card``, Drupal ``field--name-...``)
but adjusted to be small and deterministic.
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.scrapers.housing_ombudsman.parsers import (
    parse_detail_html,
    parse_listing_html,
)


LISTING_HTML = """\
<html><body>
<main>
  <div class="view-decisions">
    <div class="decision-card">
      <h3><a href="/decisions/202300001/">Resident vs Acme Housing</a></h3>
      <span class="landlord">Acme Housing</span>
      <span class="outcome">Maladministration</span>
      <time class="date">12 March 2024</time>
      <span class="categories">Property condition; Complaint handling</span>
    </div>
    <div class="decision-card">
      <h3><a href="/decisions/202300002/">Resident vs Beta Trust</a></h3>
      <span class="landlord">Beta Housing Trust</span>
      <span class="outcome">No maladministration</span>
      <time class="date">5 February 2024</time>
      <span class="categories">Service charges</span>
    </div>
  </div>
  <ul class="pager">
    <li class="pager__item--next"><a href="/decisions/?page=2">Next</a></li>
  </ul>
</main>
</body></html>
"""


DETAIL_HTML = """\
<html><body>
<main>
  <h1>Determination 202300001</h1>
  <dl>
    <dt>Case reference</dt><dd>202300001</dd>
    <dt>Landlord</dt><dd>Acme Housing</dd>
    <dt>Decision date</dt><dd>12 March 2024</dd>
    <dt>Category</dt><dd>Property condition; Complaint handling</dd>
    <dt>Outcome</dt><dd>Maladministration</dd>
  </dl>
  <p>The resident reported persistent damp and mould in their bedroom.
  The landlord cited the duty under section 11 of the Landlord and Tenant Act 1985
  but failed to inspect for 14 weeks. Awaab's Law was referenced in correspondence.</p>
  <h2>Orders</h2>
  <ul>
    <li>Apologise within 4 weeks</li>
    <li>Pay £400 compensation</li>
  </ul>
  <h2>Recommendations</h2>
  <ul>
    <li>Review damp and mould policy</li>
  </ul>
</main>
</body></html>
"""


class TestParseListing:
    def test_extracts_two_rows(self):
        rows = parse_listing_html(LISTING_HTML)
        assert len(rows) == 2
        refs = sorted(r.case_reference for r in rows)
        assert refs == ["202300001", "202300002"]

    def test_listing_fields_populated(self):
        rows = parse_listing_html(LISTING_HTML)
        first = next(r for r in rows if r.case_reference == "202300001")
        assert first.detail_url.endswith("/decisions/202300001/")
        assert first.listed_landlord == "Acme Housing"
        assert first.listed_outcome_raw == "Maladministration"
        assert first.listed_date == date(2024, 3, 12)
        assert "Property condition" in first.listed_categories


class TestParseDetail:
    def test_metadata_extracted(self):
        meta, raw = parse_detail_html(
            DETAIL_HTML, source_url="https://x/decisions/202300001/"
        )
        assert meta.case_reference == "202300001"
        assert meta.landlord_name == "Acme Housing"
        assert meta.decision_date == date(2024, 3, 12)
        assert "Property condition" in meta.complaint_categories
        assert meta.outcome_raw and "maladministration" in meta.outcome_raw.lower()
        assert meta.outcome_normalized == "maladministration"

    def test_orders_and_recommendations(self):
        meta, _raw = parse_detail_html(
            DETAIL_HTML, source_url="https://x/decisions/202300001/"
        )
        assert any("apolog" in o.lower() for o in meta.orders)
        assert any("compensation" in o.lower() for o in meta.orders)
        assert any("damp and mould" in r.lower() for r in meta.recommendations)

    def test_temporal_marker_awaab(self):
        meta, _raw = parse_detail_html(
            DETAIL_HTML, source_url="https://x/decisions/202300001/"
        )
        assert meta.temporal_markers.get("awaabs_law_referenced") is True

    def test_unknown_outcome_diagnostics(self):
        html = DETAIL_HTML.replace(
            "<dd>Maladministration</dd>", "<dd>Some bizarre outcome</dd>"
        )
        meta, _raw = parse_detail_html(
            html, source_url="https://x/decisions/202300001/"
        )
        assert meta.outcome_normalized is None
        assert any("unrecognised_outcome_label" in d for d in meta.parser_diagnostics)
        # Still extracted otherwise.
        assert meta.case_reference == "202300001"

    def test_raw_text_contains_body(self):
        _meta, raw = parse_detail_html(
            DETAIL_HTML, source_url="https://x/decisions/202300001/"
        )
        assert "damp and mould" in raw.lower()
