"""End-to-end orchestrator tests using ``run_dry`` (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.scrapers.employment_tribunal.config import ScraperConfig
from scripts.scrapers.employment_tribunal.govuk_scraper import (
    EmploymentTribunalScraper,
)


@pytest.fixture
def tmp_config(tmp_path: Path) -> ScraperConfig:
    cfg = ScraperConfig(project_root=tmp_path)
    # Tight pilot bound — fixtures only contain 4 decisions; we want all of
    # them through the pipeline.
    cfg.max_keep = 10
    return cfg


def _detail_pairs(fixtures_dir: Path):
    pairs = []
    for path in sorted((fixtures_dir / "detail").glob("*.html")):
        raw = path.read_text(encoding="utf-8")
        url = raw.splitlines()[0].strip()
        body = "\n".join(raw.splitlines()[1:])
        pairs.append((url, body))
    return pairs


class TestEndToEndDryRun:
    def test_pipeline_keeps_two_merits_cases(self, fixtures_dir, listing_html, tmp_config):
        scraper = EmploymentTribunalScraper(tmp_config)
        report = scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))

        # Fixture set:
        # - unfair_misconduct.html         → KEEP (claim succeeded)
        # - unfair_capability_partial.html → KEEP (partial)
        # - preliminary.html               → REJECT (preliminary_only)
        # - discrimination_led.html        → REJECT (withdrawal or not-lead)
        assert report.cases_seen == 4
        assert report.cases_kept == 2
        assert report.cases_excluded == 2

    def test_excluded_reasons_include_preliminary(self, fixtures_dir, listing_html, tmp_config):
        scraper = EmploymentTribunalScraper(tmp_config)
        report = scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))
        assert "preliminary_only" in report.excluded_reasons
        # discrimination_led may fire `unfair_dismissal_not_lead_issue` or
        # `withdrawal` depending on phrasing; just assert *something* fired.
        non_preliminary_excludes = {
            k: v for k, v in report.excluded_reasons.items() if k != "preliminary_only"
        }
        assert non_preliminary_excludes, "expected the discrimination-led row to be rejected"

    def test_country_counts_split_e_and_w_vs_scotland(self, fixtures_dir, listing_html, tmp_config):
        scraper = EmploymentTribunalScraper(tmp_config)
        report = scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))
        assert report.country_counts.get("england_and_wales", 0) >= 1
        assert report.country_counts.get("scotland", 0) >= 1

    def test_dedup_via_content_hash(self, fixtures_dir, listing_html, tmp_config):
        scraper = EmploymentTribunalScraper(tmp_config)
        pairs = _detail_pairs(fixtures_dir)
        # Run twice — second pass should not double-count kept rows.
        scraper.run_dry(listing_html, pairs)
        scraper2 = EmploymentTribunalScraper(tmp_config)
        report2 = scraper2.run_dry(listing_html, pairs)
        # On the second run the master index already has the kept rows; the
        # dedup short-circuit means no NEW kept rows in this report.
        assert report2.cases_kept == 0

    def test_max_keep_caps_output(self, fixtures_dir, listing_html, tmp_path):
        cfg = ScraperConfig(project_root=tmp_path)
        cfg.max_keep = 1
        scraper = EmploymentTribunalScraper(cfg)
        report = scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))
        assert report.cases_kept == 1

    def test_kept_case_directory_layout(self, fixtures_dir, listing_html, tmp_config):
        scraper = EmploymentTribunalScraper(tmp_config)
        scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))

        # Acme should be kept; check artifacts.
        case_dir = tmp_config.decisions_dir / "mx-acme-ltd-2024-misconduct"
        assert case_dir.exists()
        assert (case_dir / "decision.html").exists()
        assert (case_dir / "raw.txt").exists()
        assert (case_dir / "parsed.json").exists()
        assert (case_dir / "source_document.json").exists()

    def test_summary_written(self, fixtures_dir, listing_html, tmp_config):
        scraper = EmploymentTribunalScraper(tmp_config)
        scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))
        assert tmp_config.scrape_summary_path.exists()

    def test_pii_does_not_survive_to_committed_source_document(
        self, fixtures_dir, listing_html, tmp_config
    ):
        scraper = EmploymentTribunalScraper(tmp_config)
        scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))

        # The unfair_misconduct fixture embeds email + phone + postcode + NI
        # number in the body. None of those literals must appear in the
        # committed source_document.json.
        sd_path = (
            tmp_config.decisions_dir
            / "mx-acme-ltd-2024-misconduct"
            / "source_document.json"
        )
        sd_text = sd_path.read_text(encoding="utf-8")
        assert "claimant@example.com" not in sd_text
        assert "07700 900 123" not in sd_text
        assert "N1 1AA" not in sd_text
        assert "AB 12 34 56 C" not in sd_text

    def test_excluded_jsonl_carries_reason_codes(self, fixtures_dir, listing_html, tmp_config):
        scraper = EmploymentTribunalScraper(tmp_config)
        scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))

        excluded_text = tmp_config.excluded_path.read_text(encoding="utf-8")
        assert "preliminary_only" in excluded_text


class TestSha146YearWindowPostFilter:
    """SHA-146 pilot finding #2: ``--years`` must be enforced in code,
    not just in the URL. Belt-and-braces for the case where GOV.UK
    drops or renames the listing-page query params."""

    def test_out_of_window_decision_rejected(self, fixtures_dir, listing_html, tmp_path):
        # Acme is dated 2024-04-12; with a 2019-2023 window it's out.
        cfg = ScraperConfig(project_root=tmp_path)
        cfg.max_keep = 10
        cfg.years_from = 2019
        cfg.years_to = 2023
        scraper = EmploymentTribunalScraper(cfg)
        scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))

        excluded_text = cfg.excluded_path.read_text(encoding="utf-8")
        assert "out_of_year_window" in excluded_text
        # The misconduct case (2024-04-12) must be the one rejected; the
        # capability case (2023-09-21) stays in.
        assert "mx-acme-ltd-2024-misconduct" in excluded_text
        assert "mz-betacorp-2023-capability" not in excluded_text

    def test_in_window_decision_kept(self, fixtures_dir, listing_html, tmp_path):
        cfg = ScraperConfig(project_root=tmp_path)
        cfg.max_keep = 10
        cfg.years_from = 2023
        cfg.years_to = 2024
        scraper = EmploymentTribunalScraper(cfg)
        report = scraper.run_dry(listing_html, _detail_pairs(fixtures_dir))
        # Default fixtures: 2 in-window merits (2024 misconduct, 2023
        # capability), plus 1 preliminary 2024 (Stage-2 reject) and 1
        # discrimination-led 2024 (Stage-2 reject). Year filter must NOT
        # touch the two merits cases.
        assert report.cases_kept == 2
        out_of_window_count = report.excluded_reasons.get("out_of_year_window", 0)
        assert out_of_window_count == 0
