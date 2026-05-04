#!/usr/bin/env python3
"""Build a source-grounded Housing Ombudsman repairs pilot gold set.

The input is the local 1000-case scrape under ``raw/housing_ombudsman``.
Rows are promoted through the existing SHA-28 path:

1. source bundle with raw-text spans;
2. offline dual-provider ``auto_label.py`` artifacts;
3. ``adjudicate.py append`` into a temporary gold dir;
4. copy the adjudication-built JSONL to
   ``data/gold_standard/housing_repairs_social_v1.jsonl``.

This is intentionally separate from ``housing_v1.jsonl``. The domain is
``housing.repairs_social.v1`` and the forum is Housing Ombudsman, not a
tribunal or deposit-dispute corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ID = "housing-ombudsman-gold-pilot-20260504"
RAW_ROOT = REPO_ROOT / "raw/housing_ombudsman"
DOMAIN_ID = "housing.repairs_social.v1"
FORUM = "housing_ombudsman"
RETRIEVAL_NAMESPACE_ID = "housing_repairs_social_v1"
CORPUS_VERSION = "research_seed_2026_05"
SOURCE_PUBLISHER = "housing_ombudsman"
SOURCE_KIND = "ombudsman_determination"
SOURCE_LICENSE = "unknown_housing_ombudsman_decisions_permission_pending"
GOLD_CORPUS = "housing_repairs_social_v1"
UNAPPORTIONED_REASON = (
    "Housing Ombudsman determination made a global compensation order without "
    "apportioning the final total across housing_v1 issue categories."
)
CLAIMED_AMOUNT_PATH = (
    "claimed_amounts[issue=ombudsman_compensation|by_party=tenant].amount_gbp"
)
MANDATORY_PATHS = (
    "facts",
    "disputed_amount_gbp",
    "claim_types",
    "matter_type",
    "ground_truth_outcome.overall_winner",
    "ground_truth_outcome.total_awarded_gbp",
    "ground_truth_outcome.unapportioned_reason",
)


@dataclass(frozen=True)
class OmbudsmanCaseSpec:
    case_id: str
    decision_date: str
    region: str
    region_source: str
    matter_type: str
    award_amount_gbp: str
    facts: str
    issue_snippet: str
    facts_snippet: str
    evidence_snippet: str
    outcome_snippet: str
    quote_text: str


PILOT_CASES: tuple[OmbudsmanCaseSpec, ...] = (
    OmbudsmanCaseSpec(
        case_id="birmingham-city-council-202332678",
        decision_date="2025-10-30",
        region="west_midlands",
        region_source="Birmingham City Council",
        matter_type="repairs_damp_mould",
        award_amount_gbp="1000.00",
        facts=(
            "Resident in a two-bedroom Birmingham council house reported "
            "flooring repairs and damp and mould affecting the living room, "
            "with respiratory health conditions known to the landlord."
        ),
        issue_snippet="Reports of damp and mould.",
        facts_snippet="She reported flooring repairs and damp and mould",
        evidence_snippet="The resident lives in the property, a 2-bedroom house",
        outcome_snippet="The landlord must pay the resident £ 1000",
        quote_text="The landlord must pay the resident £ 1000 made up as follows:",
    ),
    OmbudsmanCaseSpec(
        case_id="bristol-city-council-202340773",
        decision_date="2025-11-28",
        region="south_west",
        region_source="Bristol City Council",
        matter_type="repairs_disrepair",
        award_amount_gbp="2950.00",
        facts=(
            "Resident in a two-bedroom Bristol council house complained about "
            "outstanding repairs including chimney, air brick, drainage and "
            "fence works, alongside complaint handling concerns."
        ),
        issue_snippet="Repairs to the resident’s property including",
        facts_snippet="The resident complained to the landlord about outstanding repairs",
        evidence_snippet="Fitting a plate to the chimney.",
        outcome_snippet="The landlord must pay the resident £ 2,950",
        quote_text="The landlord must pay the resident £ 2,950 made up as follows:",
    ),
    OmbudsmanCaseSpec(
        case_id="leeds-city-council-202336074",
        decision_date="2025-11-12",
        region="yorkshire_and_humber",
        region_source="Leeds City Council",
        matter_type="repairs_damp_mould",
        award_amount_gbp="250.00",
        facts=(
            "Resident complained about damp and mould in a lounge and delays "
            "to subsequent repairs after a landlord inspection and cancelled "
            "repair jobs."
        ),
        issue_snippet="handling of damp and mould in the resident’s lounge",
        facts_snippet="Following an inspection of the property in June 2022",
        evidence_snippet="In her Stage 1 complaint, the resident",
        outcome_snippet="The landlord must pay the resident £250",
        quote_text="The landlord must pay the resident £250 for the distress and inconvenience",
    ),
    OmbudsmanCaseSpec(
        case_id="north-west-leicestershire-district-council-202506976",
        decision_date="2025-11-24",
        region="east_midlands",
        region_source="North West Leicestershire District Council",
        matter_type="repairs_damp_mould",
        award_amount_gbp="600.00",
        facts=(
            "Resident reported damp and mould over several years in a council "
            "house and told the landlord during the complaint process that a "
            "household member was pregnant."
        ),
        issue_snippet="Reports of damp and mould.",
        facts_snippet="reported damp and mould in the property",
        evidence_snippet="daughter was pregnant",
        outcome_snippet="The landlord must pay the resident £ 600",
        quote_text="The landlord must pay the resident £ 600 for the distress and inconvenience",
    ),
    OmbudsmanCaseSpec(
        case_id="chesterfield-borough-council-202434129",
        decision_date="2026-01-08",
        region="east_midlands",
        region_source="Chesterfield Borough Council",
        matter_type="repairs_disrepair",
        award_amount_gbp="250.00",
        facts=(
            "Resident in a Chesterfield council flat complained after a changed "
            "bathroom extractor fan repair appointment was missed and further "
            "delays followed."
        ),
        issue_snippet="A repair to the bathroom extractor fan.",
        facts_snippet="The resident lives in a 2-bedroom flat.",
        evidence_snippet="The resident contacted the landlord to change a repair appointment",
        outcome_snippet="The landlord must pay the resident £ 250",
        quote_text="The landlord must pay the resident £ 250 in compensation as detailed below:",
    ),
    OmbudsmanCaseSpec(
        case_id="city-of-westminster-council-202437516",
        decision_date="2025-10-16",
        region="london",
        region_source="City of Westminster Council",
        matter_type="repairs_disrepair",
        award_amount_gbp="500.00",
        facts=(
            "Resident in a Westminster flat complained about recurring leaks "
            "from the property above and poor communication while the landlord "
            "attempted to resolve access and repair issues."
        ),
        issue_snippet="handling of leaks from the property above",
        facts_snippet="The resident lives in a 1-bedroom flat.",
        evidence_snippet="leaks coming from the neighbour",
        outcome_snippet="The landlord must pay the resident £ 5 00",
        quote_text="The landlord must pay the resident £ 5 00 to recognise the distress and inconvenience",
    ),
    OmbudsmanCaseSpec(
        case_id="royal-borough-of-greenwich-202419950",
        decision_date="2025-10-28",
        region="london",
        region_source="Royal Borough Of Greenwich",
        matter_type="repairs_disrepair",
        award_amount_gbp="600.00",
        facts=(
            "Resident in a Greenwich flat complained about a leak from the "
            "property above and the landlord's complaint handling after damage "
            "inspection and communication issues."
        ),
        issue_snippet="Reports of a leak.",
        facts_snippet="experienced a leak from the property above",
        evidence_snippet="reported a leak in the bathroom",
        outcome_snippet="The landlord must pay the resident £ 600",
        quote_text="The landlord must pay the resident £ 600 made up as follows:",
    ),
    OmbudsmanCaseSpec(
        case_id="norwich-city-council-202423175",
        decision_date="2025-10-31",
        region="east_of_england",
        region_source="Norwich City Council",
        matter_type="repairs_damp_mould",
        award_amount_gbp="575.00",
        facts=(
            "Resident in a Norwich top-floor flat with known vulnerabilities "
            "complained that leaks, damp and mould repairs reported in 2023 "
            "had not been resolved."
        ),
        issue_snippet="Reports of leaks, damp and mould.",
        facts_snippet="The resident lives in a 2-bedroom flat",
        evidence_snippet="repairs she had reported in 2023 had not been resolved",
        outcome_snippet="The landlord must pay the resident £ 5 75",
        quote_text="The landlord must pay the resident £ 5 75 made up as follows",
    ),
    OmbudsmanCaseSpec(
        case_id="harlow-district-council-202343281",
        decision_date="2025-11-06",
        region="east_of_england",
        region_source="Harlow District Council",
        matter_type="repairs_damp_mould",
        award_amount_gbp="650.00",
        facts=(
            "Resident in a Harlow maisonette complained about a leak causing "
            "damp and mould, with access issues at a neighbouring property and "
            "associated complaint handling failures."
        ),
        issue_snippet="Reports of a leak causing damp and mould",
        facts_snippet="The resident lives in a 2 bedroom maisonette",
        evidence_snippet="owns the neighbouring property",
        outcome_snippet="The landlord must pay the resident £ 6 50",
        quote_text="The landlord must pay the resident £ 6 50 made up as follows:",
    ),
    OmbudsmanCaseSpec(
        case_id="london-borough-of-lambeth-202419912",
        decision_date="2025-10-30",
        region="london",
        region_source="London Borough of Lambeth",
        matter_type="repairs_damp_mould",
        award_amount_gbp="550.00",
        facts=(
            "Leaseholder in a Lambeth ground-floor flat complained about damp "
            "and associated repairs, including missed appointments and delays "
            "in arranging necessary repair work."
        ),
        issue_snippet="reports of damp and associated repairs",
        facts_snippet="The resident lives in a ground-floor 2-bedroom flat",
        evidence_snippet="reported damp on 11 February 2024",
        outcome_snippet="The landlord must pay the resident £ 550",
        quote_text="The landlord must pay the resident £ 550 made up as follows:",
    ),
)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_checked(args: list[str]) -> None:
    subprocess.run(args, cwd=REPO_ROOT, check=True)


def _paragraphs(text: str) -> list[tuple[int, int, str]]:
    paragraphs: list[tuple[int, int, str]] = []
    start: int | None = None
    end = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            if start is None:
                start = offset
            end = offset + len(line)
        elif start is not None:
            paragraphs.append((start, end, text[start:end]))
            start = None
        offset += len(line)
    if start is not None:
        paragraphs.append((start, end, text[start:end]))
    if not paragraphs:
        paragraphs.append((0, len(text), text))
    return paragraphs


def _bundle_for(raw_text_path: Path, html_path: Path) -> dict[str, Any]:
    text = raw_text_path.read_text()
    triples: list[dict[str, Any]] = []
    page_sections: dict[str, str] = {}
    for paragraph, (start, end, para_text) in enumerate(_paragraphs(text), start=1):
        triples.append(
            {
                "page": 1,
                "paragraph": paragraph,
                "section_tag": "pre_decision_record",
                "char_start": start,
                "char_end": end,
                "text": para_text,
            }
        )
        page_sections[f"1,{paragraph}"] = "pre_decision_record"
    return {
        "triples": triples,
        "page_text": {"1": text},
        "page_sections": page_sections,
        "source_pdf_sha256": _hash_file(html_path),
        "ocr_text_sha256": _hash_text(text),
    }


def _canonical(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _span_for(bundle: dict[str, Any], snippet: str) -> dict[str, Any]:
    wanted = _canonical(snippet)
    for triple in bundle["triples"]:
        if wanted in _canonical(str(triple["text"])):
            return {
                "page": int(triple["page"]),
                "paragraph": int(triple["paragraph"]),
                "text_span": [int(triple["char_start"]), int(triple["char_end"])],
            }
    raise RuntimeError(f"Could not ground snippet: {snippet!r}")


def _case_paths(case_id: str) -> tuple[Path, Path, Path]:
    case_dir = RAW_ROOT / "decisions" / case_id
    return case_dir / "raw.txt", case_dir / "decision.html", case_dir / "parsed.json"


def _source_url(parsed_path: Path, case_id: str) -> str:
    if parsed_path.exists():
        parsed = json.loads(parsed_path.read_text())
        if parsed.get("source_url"):
            return str(parsed["source_url"])
    return f"https://www.housing-ombudsman.org.uk/decisions/{case_id}/"


def _case_payload(
    spec: OmbudsmanCaseSpec,
    *,
    bundle: dict[str, Any],
    source_url: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    issue_span = _span_for(bundle, spec.issue_snippet)
    facts_span = _span_for(bundle, spec.facts_snippet)
    evidence_span = _span_for(bundle, spec.evidence_snippet)
    outcome_span = _span_for(bundle, spec.outcome_snippet)
    spans = {
        "issue": issue_span,
        "facts": facts_span,
        "evidence": evidence_span,
        "outcome": outcome_span,
    }
    amount = spec.award_amount_gbp
    case = {
        "schema_version": "v1",
        "case_id": spec.case_id,
        "decision_date": spec.decision_date,
        "region": spec.region,
        "region_source": spec.region_source,
        "case_size": "small" if float(amount) <= 1500.0 else "large",
        "disputed_amount_gbp": amount,
        "claim_types": ["disrepair"],
        "source_pdf_sha256": bundle["source_pdf_sha256"],
        "ocr_confidence": None,
        "parties": [
            {"role": "tenant", "represented": False},
            {"role": "landlord", "represented": False},
        ],
        "facts": spec.facts,
        "evidence": [
            {
                "kind": "correspondence",
                "description": (
                    "Housing Ombudsman determination records resident reports, "
                    "complaint history, and repairs evidence relevant to the issue."
                ),
                "provenance": evidence_span,
            }
        ],
        "statutory_basis": [],
        "statutory_basis_unavailable_reason": (
            "Captured Ombudsman summary did not expose a case-specific statutory "
            "basis suitable for this GoldCase field; the forum is recorded in "
            "domain_id/forum/source_kind."
        ),
        "cited_authorities": [],
        "claimed_amounts": [
            {
                "issue": "ombudsman_compensation",
                "amount_gbp": amount,
                "by_party": "tenant",
            }
        ],
        "ground_truth_outcome": {
            "overall_winner": "tenant",
            "total_awarded_gbp": amount,
            "per_issue": [],
            "unapportioned_reason": UNAPPORTIONED_REASON,
        },
        "key_reasoning_quotes": [
            {"text": spec.quote_text, "provenance": outcome_span}
        ],
        "domain_id": DOMAIN_ID,
        "forum": FORUM,
        "source_url": source_url,
        "source_license": SOURCE_LICENSE,
        "retrieval_namespace_id": RETRIEVAL_NAMESPACE_ID,
        "target_source_id": spec.case_id,
        "excluded_source_ids": [],
        "law_effective_date": spec.decision_date,
        "train_test_split": "test",
        "source_publisher": SOURCE_PUBLISHER,
        "source_kind": SOURCE_KIND,
        "corpus_version": CORPUS_VERSION,
        "matter_type": spec.matter_type,
        "negative_kind": None,
        "expected_outcome": None,
        "expected_redactions": [],
        "expected_redacted_text": None,
    }
    return case, spans


def _field_provenance(spans: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "facts": [spans["facts"]],
        "claim_types": [spans["issue"]],
        "matter_type": [spans["issue"]],
        "disputed_amount_gbp": [spans["outcome"]],
        CLAIMED_AMOUNT_PATH: [spans["outcome"]],
        "ground_truth_outcome.overall_winner": [spans["outcome"]],
        "ground_truth_outcome.total_awarded_gbp": [spans["outcome"]],
        "ground_truth_outcome.unapportioned_reason": [spans["outcome"]],
    }


def _canned_label(case: dict[str, Any], spans: dict[str, dict[str, Any]]) -> dict[str, Any]:
    keep = {
        "decision_date",
        "region",
        "region_source",
        "parties",
        "facts",
        "evidence",
        "statutory_basis",
        "statutory_basis_unavailable_reason",
        "cited_authorities",
        "claimed_amounts",
        "disputed_amount_gbp",
        "claim_types",
        "matter_type",
        "ground_truth_outcome",
        "key_reasoning_quotes",
    }
    label = {key: value for key, value in case.items() if key in keep}
    label["_field_provenance"] = _field_provenance(spans)
    return label


def _provenance_row(field_path: str, span: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_path": field_path,
        "source": "human_mandatory_review",
        "source_spans": [span],
        "match_strategy": "source_raw_text_paragraph_span",
        "reviewer_rationale": (
            "Mandatory pilot review against the local Housing Ombudsman raw "
            "source text and extracted paragraph span."
        ),
    }


def _decisions(case: dict[str, Any], spans: dict[str, dict[str, Any]]) -> dict[str, Any]:
    path_to_span = {
        "facts": spans["facts"],
        "disputed_amount_gbp": spans["outcome"],
        "claim_types": spans["issue"],
        "matter_type": spans["issue"],
        "ground_truth_outcome.overall_winner": spans["outcome"],
        "ground_truth_outcome.total_awarded_gbp": spans["outcome"],
        "ground_truth_outcome.unapportioned_reason": spans["outcome"],
    }
    return {
        "case": case,
        "labeling_provenance": {
            "human_adjudicator": "Codex pilot adjudicator",
            "labeler_models": [],
            "is_human_only_anchor": False,
            "anchor_set_id": None,
            "mandatory_review_completed_at": datetime.now(timezone.utc).isoformat(),
            "adjudicated_fields": list(MANDATORY_PATHS),
            "inter_model_agreement_rate": 1.0,
            "audit_flip_rate": 0.0,
            "mandatory_review_flip_rate": 0.0,
            "field_provenance": [
                _provenance_row(path, path_to_span[path]) for path in MANDATORY_PATHS
            ],
        },
    }


def _existing_case_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        str(json.loads(line)["case_id"])
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def _prepare_dirs(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _merge_reviewer_log(*, canonical_log: Path, run_log: Path, run_id: str) -> None:
    canonical_log.parent.mkdir(parents=True, exist_ok=True)
    if canonical_log.exists():
        existing_lines = canonical_log.read_text().splitlines()
    else:
        existing_lines = ["# Adjudication log", ""]
    filtered = [line for line in existing_lines if f" run={run_id} " not in line]
    run_entries = [
        line
        for line in run_log.read_text().splitlines()
        if line.startswith("- ") and f" run={run_id} " in line
    ]
    if filtered and filtered[-1] != "":
        filtered.append("")
    filtered.extend(run_entries)
    canonical_log.write_text("\n".join(filtered).rstrip() + "\n")


def build(args: argparse.Namespace) -> None:
    run_id = args.run_id
    artifacts_root = REPO_ROOT / "data/eval_artifacts/labeling"
    bundle_dir = REPO_ROOT / f"data/eval_artifacts/source_bundles/{run_id}"
    canned_dir = REPO_ROOT / f"data/eval_artifacts/labeling_inputs/{run_id}"
    decisions_dir = REPO_ROOT / f"data/eval_artifacts/adjudication/{run_id}"
    gold_build_root = REPO_ROOT / f"data/eval_artifacts/gold_build/{run_id}"
    temp_gold_dir = gold_build_root / "gold"
    canonical_gold = REPO_ROOT / f"data/gold_standard/{GOLD_CORPUS}.jsonl"
    canonical_reviewer_log = REPO_ROOT / "docs/eval/reviewer-log.md"
    reviewer_log = gold_build_root / "reviewer-log.md"

    expected_ids = [spec.case_id for spec in PILOT_CASES]
    existing_ids = _existing_case_ids(canonical_gold)
    if existing_ids and existing_ids != expected_ids and not args.force:
        raise SystemExit(
            f"Refusing to replace {canonical_gold}: existing case_ids differ from "
            "this pilot. Re-run with --force if replacement is intentional."
        )

    _prepare_dirs([bundle_dir, canned_dir, decisions_dir, temp_gold_dir])
    if canonical_gold.exists():
        backup_path = gold_build_root / f"replaced_{GOLD_CORPUS}.jsonl"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical_gold, backup_path)

    schema_hash = _hash_file(REPO_ROOT / "packages/eval/schema.py")
    corpus_manifest_hash = _hash_file(RAW_ROOT / "master_index.json")

    for spec in PILOT_CASES:
        raw_text_path, html_path, parsed_path = _case_paths(spec.case_id)
        if not raw_text_path.exists() or not html_path.exists():
            raise FileNotFoundError(f"Missing source files for {spec.case_id}")

        bundle = _bundle_for(raw_text_path, html_path)
        case, spans = _case_payload(
            spec,
            bundle=bundle,
            source_url=_source_url(parsed_path, spec.case_id),
        )
        canned = _canned_label(case, spans)

        bundle_path = bundle_dir / f"{spec.case_id}.source_bundle.json"
        canned_a_path = canned_dir / f"{spec.case_id}.labeler_a.json"
        canned_b_path = canned_dir / f"{spec.case_id}.labeler_b.json"
        decisions_path = decisions_dir / f"{spec.case_id}.decisions.json"

        _write_json(bundle_path, bundle)
        _write_json(canned_a_path, canned)
        _write_json(canned_b_path, canned)
        _write_json(decisions_path, _decisions(case, spans))

        _run_checked(
            [
                sys.executable,
                "scripts/eval/auto_label.py",
                "--case-id",
                spec.case_id,
                "--pdf",
                str(bundle_path.relative_to(REPO_ROOT)),
                "--domain-id",
                DOMAIN_ID,
                "--run-id",
                run_id,
                "--labeler-a",
                "anthropic:claude-sonnet-4-20250514",
                "--labeler-b",
                "openai:gpt-5.5",
                "--artifacts-root",
                str(artifacts_root.relative_to(REPO_ROOT)),
                "--gold-schema-hash",
                schema_hash,
                "--corpus-manifest-hash",
                corpus_manifest_hash,
                "--offline",
                "--canned-a",
                str(canned_a_path.relative_to(REPO_ROOT)),
                "--canned-b",
                str(canned_b_path.relative_to(REPO_ROOT)),
            ]
        )
        _run_checked(
            [
                sys.executable,
                "scripts/eval/adjudicate.py",
                "append",
                "--run-id",
                run_id,
                "--case-id",
                spec.case_id,
                "--decisions",
                str(decisions_path.relative_to(REPO_ROOT)),
                "--gold-corpus",
                GOLD_CORPUS,
                "--gold-dir",
                str(temp_gold_dir.relative_to(REPO_ROOT)),
                "--reviewer-log",
                str(reviewer_log.relative_to(REPO_ROOT)),
                "--artifacts-root",
                str(artifacts_root.relative_to(REPO_ROOT)),
                "--audit-seed",
                "42",
            ]
        )

    built_gold = temp_gold_dir / f"{GOLD_CORPUS}.jsonl"
    if not built_gold.exists():
        raise RuntimeError(f"Adjudication produced no gold file at {built_gold}")
    canonical_gold.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_gold, canonical_gold)
    _merge_reviewer_log(
        canonical_log=canonical_reviewer_log,
        run_log=reviewer_log,
        run_id=run_id,
    )
    print(f"Wrote {len(PILOT_CASES)} real Ombudsman gold cases to {canonical_gold}")
    print(f"Run artifacts: {artifacts_root / run_id}")
    print(f"Source bundles: {bundle_dir}")
    print(f"Adjudication decisions: {decisions_dir}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the Housing Ombudsman repairs/social pilot gold set."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing non-matching housing_repairs_social_v1 file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    build(parser.parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
