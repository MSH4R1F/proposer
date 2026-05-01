"""Build the 10-case synthetic corpus fixture (synthetic_corpus_10.jsonl).

Run this script to regenerate:
    python packages/eval/tests/fixtures/_build_synthetic_corpus.py

The fixture exercises every claim type, both apportioned and unapportioned
paths, the train/test split, and a leakage-positive case (so audits can be
demonstrated end-to-end on a controlled corpus).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval.schema import GoldCase  # noqa: E402


def _base_case(
    *,
    case_id: str,
    decision_date: str,
    region: str,
    region_source: str,
    claim_types: list,
    disputed: str = "300.00",
    case_size: str = "small",
    facts: str = (
        "Synthetic fixture case for testing the dataset loader and downstream "
        "metric harness. Tenant disputed a portion of the deposit retained by "
        "the landlord at end of tenancy."
    ),
    cited_authorities: list = None,
    sha256_byte: str = "0",
) -> dict:
    return {
        "schema_version": "v1",
        "case_id": case_id,
        "decision_date": decision_date,
        "region": region,
        "region_source": region_source,
        "case_size": case_size,
        "disputed_amount_gbp": disputed,
        "claim_types": claim_types,
        "source_pdf_sha256": sha256_byte * 64,
        "ocr_confidence": 0.9,
        "parties": [
            {"role": "tenant", "represented": False},
            {"role": "landlord", "represented": True},
        ],
        "facts": facts,
        "evidence": [
            {
                "kind": "invoice",
                "description": "Cleaning invoice retained by landlord.",
                "provenance": {"page": 1, "paragraph": 5},
            }
        ],
        "statutory_basis": [
            {
                "statute": "Housing Act 2004",
                "section": "s.213",
                "provenance": {"page": 1, "paragraph": 9},
            }
        ],
        "cited_authorities": cited_authorities or [],
        "claimed_amounts": [
            {
                "issue": "primary_issue",
                "amount_gbp": disputed,
                "by_party": "landlord",
            }
        ],
        "ground_truth_outcome": {
            "overall_winner": "tenant",
            "total_awarded_gbp": "100.00",
            "per_issue": [
                {
                    "issue": "primary_issue",
                    "winner": "tenant",
                    "awarded_gbp": "100.00",
                }
            ],
        },
        "key_reasoning_quotes": [
            {
                "text": "I find on the balance of probabilities that the deduction was disproportionate.",
                "provenance": {"page": 2, "paragraph": 14},
            }
        ],
    }


def build_corpus() -> list:
    """Return 10 synthetic cases that span the design space."""
    cases: list = []

    # 1. cleaning, train, london
    cases.append(_base_case(
        case_id="SYN-CLEANING-2020-001",
        decision_date="2020-04-15",
        region="london",
        region_source="London",
        claim_types=["cleaning"],
        sha256_byte="1",
    ))

    # 2. damages, train, north_west
    cases.append(_base_case(
        case_id="SYN-DAMAGES-2021-002",
        decision_date="2021-08-22",
        region="north_west",
        region_source="North West",
        claim_types=["damages"],
        sha256_byte="2",
    ))

    # 3. deposit_non_protection, train, wales
    cases.append(_base_case(
        case_id="SYN-DEPOSIT-2022-003",
        decision_date="2022-03-11",
        region="wales",
        region_source="Wales",
        claim_types=["deposit_non_protection"],
        sha256_byte="3",
    ))

    # 4. disrepair, train, scotland
    cases.append(_base_case(
        case_id="SYN-DISREPAIR-2022-004",
        decision_date="2022-11-30",
        region="scotland",
        region_source="Scotland",
        claim_types=["disrepair"],
        sha256_byte="4",
    ))

    # 5. end_of_tenancy, test, south_east
    cases.append(_base_case(
        case_id="SYN-EOT-2023-005",
        decision_date="2023-05-18",
        region="south_east",
        region_source="South East",
        claim_types=["end_of_tenancy"],
        sha256_byte="5",
    ))

    # 6. multi-type [cleaning, damages], test, london
    cases.append(_base_case(
        case_id="SYN-MULTI-2023-006",
        decision_date="2023-09-04",
        region="london",
        region_source="Greater London",
        claim_types=["cleaning", "damages"],
        sha256_byte="6",
    ))

    # 7. multi-type [disrepair, end_of_tenancy], test, yorkshire
    cases.append(_base_case(
        case_id="SYN-MULTI-2024-007",
        decision_date="2024-02-12",
        region="yorkshire_and_humber",
        region_source="Yorkshire and the Humber",
        claim_types=["disrepair", "end_of_tenancy"],
        sha256_byte="7",
    ))

    # 8. large case (disputed > £1500), train
    cases.append(_base_case(
        case_id="SYN-LARGE-2021-008",
        decision_date="2021-12-01",
        region="east_of_england",
        region_source="East of England",
        claim_types=["damages"],
        disputed="2400.00",
        case_size="large",
        sha256_byte="8",
    ))

    # 9. unapportioned outcome, test
    case_9 = _base_case(
        case_id="SYN-UNAPPORT-2024-009",
        decision_date="2024-06-30",
        region="south_west",
        region_source="South West",
        claim_types=["damages", "cleaning"],
        sha256_byte="9",
    )
    case_9["ground_truth_outcome"] = {
        "overall_winner": "split",
        "total_awarded_gbp": "150.00",
        "per_issue": [],
        "unapportioned_reason": "Tribunal gave a global figure without per-issue breakdown.",
    }
    cases.append(case_9)

    # 10. case with cited_authorities (clean, train), exercising leakage-clean path
    case_10 = _base_case(
        case_id="SYN-AUTH-2022-010",
        decision_date="2022-07-19",
        region="west_midlands",
        region_source="West Midlands",
        claim_types=["deposit_non_protection"],
        cited_authorities=[
            {
                "name": "Howard de Walden Estates Ltd v Aggio",
                "court": "UKSC",
                "cited_date": "2008-06-25",
                "provenance": {"page": 2, "paragraph": 8},
            },
            {
                "name": "Superstrike Ltd v Rodrigues",
                "court": "EWCA Civ",
                "cited_date": "2013-06-14",
            },
        ],
        sha256_byte="a",
    )
    cases.append(case_10)

    return cases


def main() -> None:
    cases = build_corpus()
    # Validate every case before writing.
    for c in cases:
        GoldCase.model_validate(c)

    out = _HERE.parent / "synthetic_corpus_10.jsonl"
    with out.open("w") as f:
        for c in cases:
            # Round-trip through GoldCase to canonicalise the JSON
            gc = GoldCase.model_validate(c)
            f.write(gc.model_dump_json())
            f.write("\n")
    print(f"Wrote {len(cases)} cases to {out}")


if __name__ == "__main__":
    main()
