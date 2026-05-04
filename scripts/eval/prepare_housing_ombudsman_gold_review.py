#!/usr/bin/env python3
"""Prepare the Housing Ombudsman stratified-50 manifest for gold review.

This script does not append to ``data/gold_standard``. It creates:

* source bundles suitable for ``scripts/eval/auto_label.py``;
* human review packets with source-grounded candidate fields;
* draft decision templates that intentionally remain non-appendable until a
  human reviewer converts deterministic provenance into human review entries.

The goal is to move ``data/eval/housing_ombudsman_stratified_50.jsonl`` from
"selection manifest" to "review queue" without pretending parser-derived labels
are thesis-grade gold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "data/eval/housing_ombudsman_stratified_50.jsonl"
DEFAULT_RUN_ID = "housing-ombudsman-stratified-50-review-20260504"
DOMAIN_ID = "housing.repairs_social.v1"
FORUM = "housing_ombudsman"
RETRIEVAL_NAMESPACE_ID = "housing_repairs_social_v1"
SOURCE_PUBLISHER = "housing_ombudsman"
SOURCE_KIND = "ombudsman_determination"
SOURCE_LICENSE = "unknown_housing_ombudsman_decisions_permission_pending"
GOLD_CORPUS = "housing_repairs_social_v1"
UNAPPORTIONED_REASON = (
    "Housing Ombudsman determination made a global compensation order without "
    "apportioning the final total across housing_v1 issue categories."
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
CLAIMED_AMOUNT_PATH = (
    "claimed_amounts[issue=ombudsman_compensation|by_party=tenant].amount_gbp"
)

_MONEY_RE = re.compile(r"\u00a3\s*([0-9][0-9\s,]*(?:\.[0-9]{1,2})?)")
_WHITESPACE_RE = re.compile(r"\s+")

_PRE_DECISION_HEADINGS = {
    "background",
    "what the complaint is about",
    "the complaint procedure",
    "referral to the ombudsman",
    "our investigation",
    "date",
    "what happened",
}
_REASONING_HEADINGS = {
    "our decision",
    "our decision (determination)",
    "summary of reasons",
    "what we found and why",
    "complaint",
    "finding",
    "learning",
    "knowledge information management (record keeping)",
    "communication",
}
_ORDER_HEADINGS = {
    "putting things right",
    "orders",
    "order",
    "recommendations",
    "recommendation",
}
_FACT_STARTS = {
    "background",
    "what the complaint is about",
    "the complaint procedure",
    "referral to the ombudsman",
}
_FACT_STOPS = {
    "our decision",
    "our decision (determination)",
    "summary of reasons",
    "putting things right",
    "orders",
    "what we found and why",
    "learning",
}


@dataclass(frozen=True)
class Paragraph:
    page: int
    paragraph: int
    section_tag: str
    char_start: int
    char_end: int
    text: str

    def provenance(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "paragraph": self.paragraph,
            "text_span": [self.char_start, self.char_end],
        }


@dataclass(frozen=True)
class MoneyCandidate:
    amount: Decimal
    score: int
    provenance: dict[str, Any]
    context: str


def _repo_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> str:
    return _hash_bytes(path.read_bytes())


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _clean_heading(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = _WHITESPACE_RE.sub(" ", text).strip().rstrip(":")
    return text.lower()


def _clean_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.replace("\xa0", " ")).strip()


def _section_for_heading(heading: str, current: str) -> str:
    if heading in _ORDER_HEADINGS:
        return "order"
    if heading in _PRE_DECISION_HEADINGS:
        return "pre_decision_record"
    if heading in _REASONING_HEADINGS:
        return "tribunal_reasoning"
    return current


def _paragraphs_from_raw_text(text: str) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    section_tag = "pre_decision_record"
    offset = 0
    paragraph_no = 1
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        start = offset
        end = offset + len(raw_line)
        offset = end
        if not line.strip():
            continue
        heading = _clean_heading(line)
        section_tag = _section_for_heading(heading, section_tag)
        paragraphs.append(
            Paragraph(
                page=1,
                paragraph=paragraph_no,
                section_tag=section_tag,
                char_start=start,
                char_end=end,
                text=line,
            )
        )
        paragraph_no += 1
    return paragraphs


def _bundle_for(raw_text_path: Path, html_path: Path | None) -> tuple[dict[str, Any], str, list[Paragraph]]:
    raw_text = raw_text_path.read_text()
    paragraphs = _paragraphs_from_raw_text(raw_text)
    page_sections = {
        f"{p.page},{p.paragraph}": p.section_tag for p in paragraphs
    }
    source_hash_path = html_path if html_path and html_path.exists() else raw_text_path
    bundle = {
        "triples": [
            {
                "page": p.page,
                "paragraph": p.paragraph,
                "section_tag": p.section_tag,
                "char_start": p.char_start,
                "char_end": p.char_end,
                "text": p.text,
            }
            for p in paragraphs
        ],
        "page_text": {"1": raw_text},
        "page_sections": page_sections,
        "source_pdf_sha256": _hash_file(source_hash_path),
        "ocr_text_sha256": _hash_text(raw_text),
    }
    return bundle, raw_text, paragraphs


def _paragraph_at_offset(paragraphs: list[Paragraph], offset: int) -> Paragraph:
    for p in paragraphs:
        if p.char_start <= offset <= p.char_end:
            return p
    return paragraphs[-1]


def _normalise_money(raw: str) -> Decimal | None:
    digits = re.sub(r"\s+", "", raw).replace(",", "")
    try:
        return Decimal(digits).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _score_amount_context(context: str) -> int:
    lower = context.lower()
    score = 0
    if "must pay the resident" in lower:
        score += 9
    if "compensation order" in lower:
        score += 6
    if "to recognise" in lower:
        score += 4
    if "compensation" in lower:
        score += 3
    if "distress and inconvenience" in lower:
        score += 2
    if "previously offered" in lower or "may deduct" in lower:
        score -= 4
    if "stage 1" in lower or "stage 2" in lower:
        score -= 2
    return score


def _amount_candidates(raw_text: str, paragraphs: list[Paragraph]) -> list[MoneyCandidate]:
    candidates: list[MoneyCandidate] = []
    for match in _MONEY_RE.finditer(raw_text):
        amount = _normalise_money(match.group(1))
        if amount is None:
            continue
        start = max(0, match.start() - 320)
        end = min(len(raw_text), match.end() + 320)
        context = _clean_text(raw_text[start:end])
        before = raw_text[max(0, match.start() - 140) : match.start()].lower()
        after = raw_text[match.end() : min(len(raw_text), match.end() + 120)].lower()
        score = _score_amount_context(context)
        if "deduct from this amount" in before or "previously offered" in after:
            score -= 8
        para = _paragraph_at_offset(paragraphs, match.start())
        candidates.append(
            MoneyCandidate(
                amount=amount,
                score=score,
                provenance={
                    "page": para.page,
                    "paragraph": para.paragraph,
                    "text_span": [match.start(), match.end()],
                },
                context=context,
            )
        )
    return sorted(candidates, key=lambda c: (c.score, c.amount), reverse=True)


def _best_amount(candidates: list[MoneyCandidate]) -> MoneyCandidate | None:
    if not candidates:
        return None
    positive = [c for c in candidates if c.score > 0]
    return positive[0] if positive else candidates[0]


def _first_paragraph_with(paragraphs: Iterable[Paragraph], needles: Iterable[str]) -> Paragraph | None:
    wanted = tuple(n.lower() for n in needles)
    for p in paragraphs:
        lower = p.text.lower()
        if any(n in lower for n in wanted):
            return p
    return None


def _draft_facts(paragraphs: list[Paragraph]) -> tuple[str, dict[str, Any]]:
    collecting = False
    selected: list[Paragraph] = []
    for p in paragraphs:
        heading = _clean_heading(p.text)
        if heading in _FACT_STARTS:
            collecting = True
            continue
        if collecting and heading in _FACT_STOPS:
            break
        if collecting and p.section_tag == "pre_decision_record":
            selected.append(p)
        if len(" ".join(x.text for x in selected)) >= 700:
            break

    if not selected:
        selected = [p for p in paragraphs if p.section_tag == "pre_decision_record"][:8]

    text = _clean_text(" ".join(p.text for p in selected))
    if len(text) > 700:
        text = text[:697].rsplit(" ", 1)[0] + "..."
    provenance = selected[0].provenance() if selected else paragraphs[0].provenance()
    if len(text) < 50:
        text = "REVIEW_REQUIRED: extract a pre-decision factual summary from the source text."
    return text, provenance


def _matter_type(row: dict[str, Any]) -> str:
    primary = row.get("primary_matter_type")
    if primary:
        return str(primary)
    matter_types = row.get("matter_types") or []
    return str(matter_types[0]) if matter_types else "repairs_disrepair"


def _draft_winner(row: dict[str, Any], amount: Decimal | None) -> str:
    outcome = str(row.get("outcome_normalized") or "").lower()
    if amount is not None and amount > 0:
        return "tenant"
    if outcome in {"outside-jurisdiction", "no-maladministration"}:
        return "landlord"
    if outcome == "unknown":
        return "split"
    return "tenant"


def _case_size(amount: Decimal) -> str:
    return "small" if amount <= Decimal("1500.00") else "large"


def _infer_region(landlord_name: str) -> tuple[str | None, str]:
    """Best-effort hint only; human review must confirm this field."""
    text = landlord_name.lower()
    region_keywords = {
        "london": ("london", "landlord_name_keyword"),
        "greenwich": ("london", "landlord_name_keyword"),
        "lambeth": ("london", "landlord_name_keyword"),
        "westminster": ("london", "landlord_name_keyword"),
        "lewisham": ("london", "landlord_name_keyword"),
        "southwark": ("london", "landlord_name_keyword"),
        "hackney": ("london", "landlord_name_keyword"),
        "camden": ("london", "landlord_name_keyword"),
        "croydon": ("london", "landlord_name_keyword"),
        "ealing": ("london", "landlord_name_keyword"),
        "hammersmith": ("london", "landlord_name_keyword"),
        "hounslow": ("london", "landlord_name_keyword"),
        "islington": ("london", "landlord_name_keyword"),
        "redbridge": ("london", "landlord_name_keyword"),
        "birmingham": ("west_midlands", "landlord_name_keyword"),
        "coventry": ("west_midlands", "landlord_name_keyword"),
        "walsall": ("west_midlands", "landlord_name_keyword"),
        "bristol": ("south_west", "landlord_name_keyword"),
        "plymouth": ("south_west", "landlord_name_keyword"),
        "leeds": ("yorkshire_and_humber", "landlord_name_keyword"),
        "sheffield": ("yorkshire_and_humber", "landlord_name_keyword"),
        "norwich": ("east_of_england", "landlord_name_keyword"),
        "harlow": ("east_of_england", "landlord_name_keyword"),
        "cambridge": ("east_of_england", "landlord_name_keyword"),
        "leicestershire": ("east_midlands", "landlord_name_keyword"),
        "chesterfield": ("east_midlands", "landlord_name_keyword"),
        "nottingham": ("east_midlands", "landlord_name_keyword"),
        "manchester": ("north_west", "landlord_name_keyword"),
        "liverpool": ("north_west", "landlord_name_keyword"),
        "newcastle": ("north_east", "landlord_name_keyword"),
        "cardiff": ("wales", "landlord_name_keyword"),
        "swansea": ("wales", "landlord_name_keyword"),
    }
    for key, value in region_keywords.items():
        if key in text:
            return value
    return None, "needs_human_review"


def _field_provenance(path: str, span: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_path": path,
        "source": "deterministic_manifest",
        "source_spans": [span],
        "match_strategy": "review_packet_candidate_span",
        "reviewer_rationale": (
            "DRAFT ONLY: human reviewer must verify this source span and change "
            "source to human_mandatory_review before append."
        ),
    }


def _draft_decision(
    row: dict[str, Any],
    *,
    bundle: dict[str, Any],
    paragraphs: list[Paragraph],
    facts: str,
    facts_span: dict[str, Any],
    amount: Decimal,
    amount_span: dict[str, Any],
    quote_text: str,
    quote_span: dict[str, Any],
) -> dict[str, Any]:
    landlord_name = str(row.get("landlord_name") or "")
    region, region_source = _infer_region(landlord_name)
    winner = _draft_winner(row, amount)
    decision_date = row.get("decision_date")
    case_payload = {
        "schema_version": "v1",
        "case_id": row["case_id"],
        "decision_date": decision_date,
        "region": region or "london",
        "region_source": (
            f"{landlord_name} ({region_source}; REVIEW_REQUIRED)"
            if landlord_name
            else "REVIEW_REQUIRED"
        ),
        "case_size": _case_size(amount),
        "disputed_amount_gbp": str(amount),
        "claim_types": ["disrepair"],
        "source_pdf_sha256": bundle["source_pdf_sha256"],
        "ocr_confidence": None,
        "parties": [
            {"role": "tenant", "represented": False},
            {"role": "landlord", "represented": False},
        ],
        "facts": facts,
        "evidence": [
            {
                "kind": "ombudsman_record",
                "description": (
                    "Housing Ombudsman determination records the resident's "
                    "complaint history, repair reports, and landlord response."
                ),
                "provenance": facts_span,
            }
        ],
        "statutory_basis": [],
        "statutory_basis_unavailable_reason": (
            "Housing Ombudsman repair/social determination; statutory basis is "
            "not extracted into this GoldCase field in the draft review packet."
        ),
        "cited_authorities": [],
        "claimed_amounts": [
            {
                "issue": "ombudsman_compensation",
                "amount_gbp": str(amount),
                "by_party": "tenant",
            }
        ],
        "ground_truth_outcome": {
            "overall_winner": winner,
            "total_awarded_gbp": str(amount),
            "per_issue": [],
            "unapportioned_reason": UNAPPORTIONED_REASON,
        },
        "key_reasoning_quotes": [
            {"text": quote_text, "provenance": quote_span}
        ],
        "domain_id": DOMAIN_ID,
        "forum": FORUM,
        "source_url": row.get("source_url"),
        "source_license": row.get("source_license") or SOURCE_LICENSE,
        "retrieval_namespace_id": RETRIEVAL_NAMESPACE_ID,
        "target_source_id": row.get("target_source_id"),
        "excluded_source_ids": [],
        "law_effective_date": decision_date,
        "train_test_split": row.get("train_test_split") or "test",
        "source_publisher": SOURCE_PUBLISHER,
        "source_kind": SOURCE_KIND,
        "corpus_version": row.get("corpus_version"),
        "matter_type": _matter_type(row),
        "negative_kind": None,
        "expected_outcome": None,
        "expected_redactions": [],
        "expected_redacted_text": None,
    }
    path_to_span = {
        "facts": facts_span,
        "disputed_amount_gbp": amount_span,
        "claim_types": quote_span,
        "matter_type": quote_span,
        "ground_truth_outcome.overall_winner": quote_span,
        "ground_truth_outcome.total_awarded_gbp": amount_span,
        "ground_truth_outcome.unapportioned_reason": quote_span,
        CLAIMED_AMOUNT_PATH: amount_span,
    }
    return {
        "_review_instructions": (
            "Draft only. Verify every candidate field against the review packet "
            "and source text. Before appending, set human_adjudicator, "
            "mandatory_review_completed_at, adjudicated_fields, flip rates, and "
            "change mandatory field_provenance sources from deterministic_manifest "
            "to human_mandatory_review for confirmed cells."
        ),
        "_review_status": "needs_human_review",
        "case": case_payload,
        "labeling_provenance": {
            "human_adjudicator": None,
            "labeler_models": [],
            "is_human_only_anchor": False,
            "anchor_set_id": None,
            "mandatory_review_completed_at": None,
            "adjudicated_fields": [],
            "inter_model_agreement_rate": 0.0,
            "audit_flip_rate": 0.0,
            "mandatory_review_flip_rate": 0.0,
            "field_provenance": [
                _field_provenance(path, span) for path, span in path_to_span.items()
            ],
        },
        "_source_bundle_preview": {
            "paragraph_count": len(paragraphs),
            "section_counts": dict(Counter(p.section_tag for p in paragraphs)),
        },
    }


def _quote_from_candidate(
    row: dict[str, Any],
    paragraphs: list[Paragraph],
    best_amount: MoneyCandidate | None,
) -> tuple[str, dict[str, Any]]:
    if best_amount is not None:
        return best_amount.context[:1000], best_amount.provenance
    outcome_para = _first_paragraph_with(
        paragraphs,
        [
            str(row.get("outcome_raw") or ""),
            "maladministration",
            "service failure",
            "reasonable redress",
            "outside jurisdiction",
        ],
    )
    if outcome_para is not None:
        return _clean_text(outcome_para.text), outcome_para.provenance()
    return _clean_text(paragraphs[0].text), paragraphs[0].provenance()


def _review_markdown(
    row: dict[str, Any],
    *,
    bundle_path: Path,
    raw_text_path: Path,
    draft_path: Path,
    facts: str,
    amount_candidates: list[MoneyCandidate],
    draft: dict[str, Any],
) -> str:
    case = draft["case"]
    top_amounts = amount_candidates[:8]
    amount_rows = "\n".join(
        f"- score={c.score} amount={c.amount} span={c.provenance} context={c.context[:500]}"
        for c in top_amounts
    ) or "- No money candidates found."
    return f"""# Housing Ombudsman Gold Review Packet

Case: `{row['case_id']}`
Source slug: `{row.get('source_slug')}`
Target source ID: `{row.get('target_source_id')}`
Title: {row.get('title')}
URL: {row.get('source_url')}

## Manifest Strata

- Outcome raw: `{row.get('outcome_raw')}`
- Outcome normalized: `{row.get('outcome_normalized')}`
- Matter types: `{', '.join(row.get('matter_types') or [])}`
- Primary matter type: `{row.get('primary_matter_type')}`
- Decision date: `{row.get('decision_date')}`
- Landlord: `{row.get('landlord_name')}`

## Candidate Gold Fields

- Draft winner: `{case['ground_truth_outcome']['overall_winner']}`
- Draft total awarded: `{case['ground_truth_outcome']['total_awarded_gbp']}`
- Draft region: `{case['region']}` from `{case['region_source']}`
- Draft matter type: `{case['matter_type']}`
- Draft facts: {facts}

## Money Candidates

{amount_rows}

## Files

- Source bundle: `{bundle_path.relative_to(REPO_ROOT)}`
- Raw text: `{raw_text_path.relative_to(REPO_ROOT)}`
- Draft decision template: `{draft_path.relative_to(REPO_ROOT)}`

## Reviewer Instructions

1. Run dual-provider auto-labeling for this case or for the whole run using
   `commands.sh`.
2. Open this packet and the raw text side by side.
3. Verify the mandatory fields: `facts`, `disputed_amount_gbp`, `claim_types`,
   `matter_type`, `overall_winner`, `total_awarded_gbp`, and
   `unapportioned_reason`.
4. Edit the draft decision template with the reviewed values and convert
   confirmed mandatory `field_provenance[].source` values from
   `deterministic_manifest` to `human_mandatory_review`.
5. Append only after review with `scripts/eval/adjudicate.py append`.
"""


def _commands(rows: list[dict[str, Any]], *, run_id: str, bundle_dir: Path) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Requires ANTHROPIC_API_KEY and OPENAI_API_KEY.",
        "# Runs dual-provider pre-adjudication labeling; it does not append gold.",
        "",
    ]
    schema_hash = _hash_file(REPO_ROOT / "packages/eval/schema.py")
    corpus_manifest = REPO_ROOT / "raw/housing_ombudsman/master_index.json"
    corpus_hash = _hash_file(corpus_manifest) if corpus_manifest.exists() else "UNSET"
    for row in rows:
        case_id = row["case_id"]
        bundle = bundle_dir / f"{case_id}.source_bundle.json"
        lines.extend(
            [
                "venv/bin/python scripts/eval/auto_label.py \\",
                f"  --case-id {case_id} \\",
                f"  --pdf {bundle.relative_to(REPO_ROOT)} \\",
                f"  --domain-id {DOMAIN_ID} \\",
                f"  --run-id {run_id} \\",
                "  --labeler-a anthropic:claude-sonnet-4-20250514 \\",
                "  --labeler-b openai:gpt-5.5 \\",
                "  --artifacts-root data/eval_artifacts/labeling \\",
                f"  --gold-schema-hash {schema_hash} \\",
                f"  --corpus-manifest-hash {corpus_hash}",
                "",
            ]
        )
    return "\n".join(lines)


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _repo_path(args.manifest)
    rows = _load_jsonl(manifest_path)
    if args.limit is not None:
        rows = rows[: args.limit]
    run_id = args.run_id
    bundle_dir = REPO_ROOT / f"data/eval_artifacts/source_bundles/{run_id}"
    packet_dir = REPO_ROOT / f"data/eval_artifacts/gold_review_packets/{run_id}"
    draft_dir = packet_dir / "draft_decisions"

    if args.force:
        for path in (bundle_dir, packet_dir):
            if path.exists():
                shutil.rmtree(path)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    draft_dir.mkdir(parents=True, exist_ok=True)

    outcome_counts: Counter[str] = Counter()
    matter_counts: Counter[str] = Counter()
    section_counts: Counter[str] = Counter()
    amount_found = 0
    region_hints = 0
    packets: list[dict[str, Any]] = []

    for row in rows:
        raw_text_path = _repo_path(row["raw_text_path"])
        storage_path = _repo_path(row["source_storage_path"])
        html_path = storage_path / "decision.html"
        bundle, raw_text, paragraphs = _bundle_for(raw_text_path, html_path)
        candidates = _amount_candidates(raw_text, paragraphs)
        best = _best_amount(candidates)
        amount = best.amount if best is not None else Decimal("0.00")
        amount_span = best.provenance if best is not None else paragraphs[0].provenance()
        if best is not None:
            amount_found += 1

        facts, facts_span = _draft_facts(paragraphs)
        quote_text, quote_span = _quote_from_candidate(row, paragraphs, best)
        draft = _draft_decision(
            row,
            bundle=bundle,
            paragraphs=paragraphs,
            facts=facts,
            facts_span=facts_span,
            amount=amount,
            amount_span=amount_span,
            quote_text=quote_text,
            quote_span=quote_span,
        )
        if _infer_region(str(row.get("landlord_name") or ""))[0] is not None:
            region_hints += 1

        case_id = row["case_id"]
        selection = int(row.get("selection_index") or len(packets) + 1)
        bundle_path = bundle_dir / f"{case_id}.source_bundle.json"
        draft_path = draft_dir / f"{selection:02d}-{case_id}.draft_decision.json"
        packet_path = packet_dir / f"{selection:02d}-{case_id}.review.md"

        _write_json(bundle_path, bundle)
        _write_json(draft_path, draft)
        packet_path.write_text(
            _review_markdown(
                row,
                bundle_path=bundle_path,
                raw_text_path=raw_text_path,
                draft_path=draft_path,
                facts=facts,
                amount_candidates=candidates,
                draft=draft,
            )
        )

        outcome_counts[str(row.get("outcome_normalized") or "unknown")] += 1
        matter_counts[_matter_type(row)] += 1
        section_counts.update(p.section_tag for p in paragraphs)
        packets.append(
            {
                "case_id": case_id,
                "selection_index": selection,
                "source_slug": row.get("source_slug"),
                "target_source_id": row.get("target_source_id"),
                "bundle_path": str(bundle_path.relative_to(REPO_ROOT)),
                "review_packet_path": str(packet_path.relative_to(REPO_ROOT)),
                "draft_decision_path": str(draft_path.relative_to(REPO_ROOT)),
                "draft_amount_gbp": str(amount),
                "draft_winner": draft["case"]["ground_truth_outcome"]["overall_winner"],
                "amount_candidate_count": len(candidates),
                "top_amount_score": best.score if best is not None else None,
            }
        )

    commands_path = packet_dir / "commands.sh"
    commands_path.write_text(_commands(rows, run_id=run_id, bundle_dir=bundle_dir))
    commands_path.chmod(0o755)

    summary = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path.relative_to(REPO_ROOT)),
        "cases": len(rows),
        "bundle_dir": str(bundle_dir.relative_to(REPO_ROOT)),
        "packet_dir": str(packet_dir.relative_to(REPO_ROOT)),
        "draft_decisions_dir": str(draft_dir.relative_to(REPO_ROOT)),
        "commands_path": str(commands_path.relative_to(REPO_ROOT)),
        "gold_corpus": GOLD_CORPUS,
        "append_status": "not_appended_needs_human_review",
        "amount_candidate_cases": amount_found,
        "region_hint_cases": region_hints,
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "matter_type_counts": dict(sorted(matter_counts.items())),
        "source_section_counts": dict(sorted(section_counts.items())),
        "packets": packets,
    }
    _write_json(packet_dir / "summary.json", summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare Housing Ombudsman stratified eval rows for gold review "
            "without appending parser-derived labels to data/gold_standard."
        )
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear existing generated source bundles and review packets first.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    summary = prepare(parser.parse_args(argv))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
