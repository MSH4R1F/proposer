"""Tests for SHA-126 BAILII / GOV.UK overlap detection."""

from __future__ import annotations

import json
from datetime import date

from scripts.scrapers.govuk_property_tribunal.bailii_overlap import (
    BUCKET_DUPLICATE,
    BUCKET_GOVUK_ONLY,
    BUCKET_MATCHED,
    load_bailii_index,
    overlap_bucket,
    overlap_report,
)
from scripts.scrapers.govuk_property_tribunal.models import (
    ArtefactKind,
    FilterDecision,
    GovUKAsset,
    GovUKPCMetadata,
    ScrapeRecord,
)


def _bailii_index(tmp_path):
    p = tmp_path / "master_index.json"
    p.write_text(
        json.dumps(
            {
                "exported_at": "2026-01-01T00:00:00",
                "total_cases": 2,
                "cases": [
                    {
                        "case_reference": "LON/00AG/HMF/2023/0001",
                        "year": 2023,
                        "html_url": "https://www.bailii.org/uk/cases/UKFTT/PC/2023/LON_00AG_HMF_2023_0001.html",
                        "pdf_url": "https://www.bailii.org/uk/cases/UKFTT/PC/2023/LON_00AG_HMF_2023_0001.pdf",
                        "title": "1 Test Road, London (HMO licensing)",
                    },
                    {
                        "case_reference": "BIR_OTHER_2022_0099",
                        "year": 2022,
                        "html_url": "https://www.bailii.org/uk/cases/UKFTT/PC/2022/BIR_OTHER_2022_0099.html",
                        "title": "Some other tribunal case",
                    },
                ],
            }
        )
    )
    return load_bailii_index(p)


def _govuk(case_ref: str, *, asset_url: str | None = None, title="") -> GovUKPCMetadata:
    assets = []
    if asset_url:
        assets.append(GovUKAsset(url=asset_url, kind=ArtefactKind.PDF, filename="x.pdf"))
    return GovUKPCMetadata(
        case_reference=case_ref,
        title=title or "RRO Decision",
        govuk_page_url=f"https://www.gov.uk/decisions/{case_ref}",
        base_path=f"/decisions/{case_ref}",
        decision_date=date(2023, 6, 1),
        primary_asset_url=asset_url,
        primary_artefact_kind=ArtefactKind.PDF if asset_url else ArtefactKind.HTML,
        assets=assets,
    )


def test_overlap_duplicate_by_case_reference(tmp_path):
    idx = _bailii_index(tmp_path)
    meta = _govuk("LON/00AG/HMF/2023/0001")
    dup, bucket = overlap_bucket(meta, idx)
    assert bucket == BUCKET_DUPLICATE
    assert dup == "LON/00AG/HMF/2023/0001"


def test_overlap_duplicate_by_url_hash(tmp_path):
    idx = _bailii_index(tmp_path)
    meta = _govuk(
        "OTHER/REF/9999",
        asset_url="https://www.bailii.org/uk/cases/UKFTT/PC/2023/LON_00AG_HMF_2023_0001.pdf",
    )
    dup, bucket = overlap_bucket(meta, idx)
    assert bucket == BUCKET_DUPLICATE
    assert dup == "LON/00AG/HMF/2023/0001"


def test_overlap_govuk_only(tmp_path):
    idx = _bailii_index(tmp_path)
    meta = _govuk("BRAND_NEW_2024_0001", title="Wholly new RRO decision")
    dup, bucket = overlap_bucket(meta, idx)
    assert bucket == BUCKET_GOVUK_ONLY
    assert dup is None


def test_overlap_report_aggregates_buckets():
    records = [
        ScrapeRecord(
            case_reference="A",
            govuk_page_url="https://x",
            base_path="/a",
            title="A",
            filter_decision=FilterDecision.ACCEPT,
            bailii_overlap_bucket=BUCKET_DUPLICATE,
        ),
        ScrapeRecord(
            case_reference="B",
            govuk_page_url="https://x",
            base_path="/b",
            title="B",
            filter_decision=FilterDecision.ACCEPT,
            bailii_overlap_bucket=BUCKET_GOVUK_ONLY,
        ),
        ScrapeRecord(
            case_reference="C",
            govuk_page_url="https://x",
            base_path="/c",
            title="C",
            filter_decision=FilterDecision.ACCEPT,
            bailii_overlap_bucket=BUCKET_GOVUK_ONLY,
        ),
    ]
    report = overlap_report(records)
    assert report[BUCKET_DUPLICATE] == 1
    assert report[BUCKET_GOVUK_ONLY] == 2
