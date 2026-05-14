"""Tests for the listing + detail parsers."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.scrapers.employment_tribunal.models import Country
from scripts.scrapers.employment_tribunal.parsers import (
    find_next_listing_page,
    parse_detail_html,
    parse_listing_html,
)


class TestListingParser:
    def test_finds_all_decision_anchors(self, listing_html: str):
        rows = parse_listing_html(listing_html)
        # 4 decisions in the fixture, all unique.
        case_refs = [r.case_reference for r in rows]
        assert len(case_refs) == 4
        assert len(set(case_refs)) == 4
        assert "mx-acme-ltd-2024-misconduct" in case_refs
        assert "ms-delta-2024-discrimination-led" in case_refs

    def test_listing_carries_jurisdiction_label(self, listing_html: str):
        rows = parse_listing_html(listing_html)
        unfair_rows = [r for r in rows if "Unfair Dismissal" in r.listed_categories]
        # All 4 fixture rows carry "Unfair Dismissal" — Stage-1 invariant.
        assert len(unfair_rows) == 4

    def test_listing_parses_dates(self, listing_html: str):
        rows = parse_listing_html(listing_html)
        acme = next(r for r in rows if r.case_reference == "mx-acme-ltd-2024-misconduct")
        assert acme.listed_date == date(2024, 4, 12)

    def test_listing_country_hint_recovers_scotland(self, listing_html: str):
        rows = parse_listing_html(listing_html)
        beta = next(r for r in rows if r.case_reference == "mz-betacorp-2023-capability")
        assert beta.country_hint == Country.SCOTLAND

    def test_listing_absolute_urls(self, listing_html: str):
        rows = parse_listing_html(listing_html)
        for r in rows:
            assert r.detail_url.startswith("https://www.gov.uk/employment-tribunal-decisions/")

    def test_listing_handles_empty_html(self):
        assert parse_listing_html("<html></html>") == []

    def test_find_next_listing_page_absent(self, listing_html: str):
        # Fixture has no next-link; parser returns None rather than crashing.
        assert find_next_listing_page(listing_html) is None

    def test_find_next_listing_page_present(self):
        html = """
        <html><head>
            <link rel="next" href="/employment-tribunal-decisions?page=2">
        </head><body></body></html>
        """
        nxt = find_next_listing_page(html)
        assert nxt == "https://www.gov.uk/employment-tribunal-decisions?page=2"


class TestDetailParser:
    def test_parses_case_number(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, text = parse_detail_html(body, url)
        assert "2200001/2024" in metadata.case_numbers

    def test_parses_decision_date(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, _ = parse_detail_html(body, url)
        assert metadata.decision_date == date(2024, 4, 12)

    def test_normalises_outcome_claim_succeeded(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, _ = parse_detail_html(body, url)
        # "claim is well-founded" + "claimant was unfairly dismissed" both
        # map to claim-succeeded; first-match-wins is deterministic.
        assert metadata.outcome_normalized == "claim-succeeded"

    def test_normalises_outcome_partial(self, detail_unfair_capability_partial):
        url, body = detail_unfair_capability_partial
        metadata, _ = parse_detail_html(body, url)
        assert metadata.outcome_normalized == "partial-success"

    def test_outcome_unrecognised_is_diagnostic_not_failure(self):
        # Page with a labelled outcome we can't normalise. Uses the
        # `Outcome` label (still hooked to `_LABEL_OUTCOME`); the
        # `Decision` label is intentionally no longer hooked post-SHA-146
        # because it collided with `Decision date` on live GOV.UK pages.
        url = "https://www.gov.uk/employment-tribunal-decisions/zz-unknown-outcome"
        html = """
        <html><body><main><article>
          <h1>Zz Test v Anon</h1>
          <dl>
            <dt>Decision date</dt><dd>1 January 2024</dd>
            <dt>Outcome</dt><dd>Something the parser has never seen before</dd>
          </dl>
          <p>section 98 ERA 1996 referenced.</p>
        </article></main></body></html>
        """
        metadata, _ = parse_detail_html(html, url)
        # Outcome stays raw; diagnostics record the mismatch.
        assert metadata.outcome_normalized is None
        assert any("unrecognised_outcome_label" in d for d in metadata.parser_diagnostics)

    def test_attachments_extracted(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, _ = parse_detail_html(body, url)
        urls = [a.url for a in metadata.attachments]
        assert any(u.endswith("mx-acme-judgment.pdf") for u in urls)
        pdf = next(a for a in metadata.attachments if a.url.endswith(".pdf"))
        assert pdf.content_type == "application/pdf"

    def test_country_england_and_wales(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, _ = parse_detail_html(body, url)
        assert metadata.country == Country.ENGLAND_AND_WALES

    def test_country_scotland(self, detail_unfair_capability_partial):
        url, body = detail_unfair_capability_partial
        metadata, _ = parse_detail_html(body, url)
        assert metadata.country == Country.SCOTLAND

    def test_licence_detected_when_v3_explicit(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, _ = parse_detail_html(body, url)
        assert metadata.source_license_observed == "OGL-3.0"

    def test_licence_inferred_when_footer_silent(self):
        url = "https://www.gov.uk/employment-tribunal-decisions/silent-footer"
        html = """
        <html><body><main><article>
          <h1>Silent footer case</h1>
          <p>section 98 ERA 1996 reasoning here.</p>
        </article></main></body></html>
        """
        metadata, _ = parse_detail_html(html, url)
        # No licence string anywhere — record what we did.
        assert metadata.source_license_observed == "OGL-3.0-inferred"

    def test_body_text_is_non_empty(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        _, text = parse_detail_html(body, url)
        assert "section 98" in text.lower()
        assert text.strip()

    def test_case_ref_from_url_slug(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, _ = parse_detail_html(body, url)
        assert metadata.case_reference == "mx-acme-ltd-2024-misconduct"

    def test_base_path_persisted(self, detail_unfair_misconduct):
        url, body = detail_unfair_misconduct
        metadata, _ = parse_detail_html(body, url)
        assert metadata.base_path == "/employment-tribunal-decisions/mx-acme-ltd-2024-misconduct"


class TestPreliminaryDecisionStillParseable:
    """Preliminary pages must parse — they're rejected at Stage 2, not parse time."""

    def test_preliminary_parses_without_error(self, detail_preliminary):
        url, body = detail_preliminary
        metadata, text = parse_detail_html(body, url)
        assert "preliminary" in text.lower()
        # Parser shouldn't pre-empt the filter; it normalises the outcome to
        # "preliminary" so Stage 2 can reject by reason code.
        assert metadata.outcome_normalized in {"preliminary", None}


# ---------------------------------------------------------------------------
# SHA-146 pilot follow-up: outcome extraction, listing nav clutter
# ---------------------------------------------------------------------------


class TestSha146OutcomeFix:
    """Live GOV.UK ET pages have `Decision date` but no `Decision` label,
    and the outcome usually lives in narrative body text (or in the PDF).
    The parser must NOT misbind `decision` -> `decision date`."""

    def test_decision_date_label_does_not_leak_into_outcome(self):
        url = "https://www.gov.uk/employment-tribunal-decisions/zz-livestyle"
        html = """
        <html><body><main><article>
          <h1>Zz Live-Style v Co</h1>
          <dl class="govuk-summary-list">
            <dt>Decision date</dt><dd>8 April 2026</dd>
            <dt>Jurisdiction code</dt><dd>Unfair Dismissal</dd>
          </dl>
          <p>Read the full decision in Zz Live-Style v Co.</p>
        </article></main></body></html>
        """
        metadata, _ = parse_detail_html(html, url)
        # Pre-SHA-146-fix: `outcome_raw` was "8 April 2026" + diagnostic.
        # Post-fix: no labelled-field hook for `decision`, body has no
        # outcome phrase -> `outcome_raw` stays None.
        assert metadata.outcome_raw is None
        assert metadata.outcome_normalized is None
        assert metadata.parser_diagnostics == []

    def test_outcome_picked_up_from_body_when_no_label(self):
        url = "https://www.gov.uk/employment-tribunal-decisions/zz-body-outcome"
        html = """
        <html><body><main><article>
          <h1>Zz Body-Outcome v Co</h1>
          <dl class="govuk-summary-list">
            <dt>Decision date</dt><dd>15 March 2024</dd>
          </dl>
          <p>The tribunal applied section 98 ERA 1996 and found that the
             dismissal was unfair.</p>
        </article></main></body></html>
        """
        metadata, _ = parse_detail_html(html, url)
        assert metadata.outcome_normalized == "claim-succeeded"

    def test_outcome_label_still_honoured_when_present(self):
        # The `Outcome` label remains hooked — only `Decision` was
        # de-hooked. A page that does carry `Outcome` still wins.
        url = "https://www.gov.uk/employment-tribunal-decisions/zz-labelled-outcome"
        html = """
        <html><body><main><article>
          <h1>Zz Labelled v Co</h1>
          <dl>
            <dt>Decision date</dt><dd>15 March 2024</dd>
            <dt>Outcome</dt><dd>Claim succeeds</dd>
          </dl>
          <p>section 98 ERA 1996 reasoning.</p>
        </article></main></body></html>
        """
        metadata, _ = parse_detail_html(html, url)
        assert metadata.outcome_normalized == "claim-succeeded"


class TestSha146ListingNoiseFix:
    """Live GOV.UK ET listing pages include nav clutter under
    /employment-tribunal-decisions/<slug> that is NOT a case page."""

    def test_email_signup_slug_skipped(self):
        html = """
        <html><body><main>
          <ul>
            <li><a href="/employment-tribunal-decisions/mx-acme-ltd-2024">Mx A v Acme Ltd</a></li>
            <li><a href="/employment-tribunal-decisions/email-signup">Get an email when a new ET decision is published</a></li>
            <li><a href="/employment-tribunal-decisions/feedback">Give feedback on this page</a></li>
          </ul>
        </main></body></html>
        """
        rows = parse_listing_html(html)
        case_refs = [r.case_reference for r in rows]
        assert "mx-acme-ltd-2024" in case_refs
        assert "email-signup" not in case_refs
        assert "feedback" not in case_refs

    def test_filter_index_self_link_skipped(self):
        # Pagination / facet self-links — the index path itself with
        # query strings or fragments must not be parsed as a case.
        html = """
        <html><body><main>
          <a href="/employment-tribunal-decisions?tribunal_decision_categories=unfair-dismissal">Unfair dismissal</a>
          <a href="/employment-tribunal-decisions/?page=2">Next page</a>
          <a href="/employment-tribunal-decisions/mr-real-case-2024">Mr R v Real Co</a>
        </main></body></html>
        """
        rows = parse_listing_html(html)
        case_refs = [r.case_reference for r in rows]
        assert case_refs == ["mr-real-case-2024"]

    def test_atom_feed_link_skipped(self):
        html = """
        <html><body><main>
          <a href="/employment-tribunal-decisions.atom">Atom feed</a>
          <a href="/employment-tribunal-decisions/atom">Atom feed alt</a>
          <a href="/employment-tribunal-decisions/ms-real-case-2024">Ms R v Real Co</a>
        </main></body></html>
        """
        rows = parse_listing_html(html)
        case_refs = [r.case_reference for r in rows]
        assert "ms-real-case-2024" in case_refs
        assert "atom" not in case_refs


class TestSha146DateFilterUrl:
    """The --years flag must propagate into the listing URL's date params."""

    def test_listing_start_url_contains_decision_date_params(self):
        from scripts.scrapers.employment_tribunal.config import ScraperConfig
        from scripts.scrapers.employment_tribunal.downloader import ETDownloader

        cfg = ScraperConfig()
        cfg.years_from = 2019
        cfg.years_to = 2024
        dl = ETDownloader(cfg)
        url = dl.listing_start_url()
        # GOV.UK finder param shape: `decision_date_from[year]=YYYY`. The
        # bracket characters are urlencoded; assert on the decoded params
        # for readability.
        from urllib.parse import urlparse, parse_qs

        q = parse_qs(urlparse(url).query)
        assert q.get("tribunal_decision_categories") == ["unfair-dismissal"]
        assert q.get("decision_date_from[year]") == ["2019"]
        assert q.get("decision_date_to[year]") == ["2024"]

    def test_listing_start_url_respects_custom_window(self):
        from scripts.scrapers.employment_tribunal.config import ScraperConfig
        from scripts.scrapers.employment_tribunal.downloader import ETDownloader

        cfg = ScraperConfig()
        cfg.years_from = 2022
        cfg.years_to = 2023
        dl = ETDownloader(cfg)
        url = dl.listing_start_url()
        from urllib.parse import urlparse, parse_qs

        q = parse_qs(urlparse(url).query)
        assert q.get("decision_date_from[year]") == ["2022"]
        assert q.get("decision_date_to[year]") == ["2023"]
