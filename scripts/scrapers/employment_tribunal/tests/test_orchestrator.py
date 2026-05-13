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
