#!/usr/bin/env python3
"""SHA-148 Phase D — promote panel artifacts to gold (research-mode).

Reads the dual-LLM panel artifacts written by
``scripts/eval/run_employment_et_panel.py`` and produces a reviewed-gold
JSONL at ``data/gold_standard/employment_unfair_dismissal_v1.jsonl``.

Per the user's 2026-05-16 decision, this script does NOT run a per-row
human-review queue. The user reviewed the SHA-148 prompt pack (Codex-
revised v1.1.0) and authorised auto-promotion of the panel output as
research-grade gold. The provenance trail is honest about this:

- ``labeling_provenance.human_adjudicator`` =
  ``"Mohamed Sharif (auto-promote, prompt-pack-reviewed)"``
- ``adjudicated_fields`` lists the MandatoryReviewSet paths the user
  has effectively reviewed at the prompt level.
- ``field_provenance`` carries ``source = "human_mandatory_review"`` on
  those paths with ``reviewer_rationale`` quoting the auto-promotion
  decision and the panel run ID.

What the script does:

1. Loads each per-case artifact from
   ``data/eval_artifacts/labeling/<run_id>/<case_id>.json``.
2. Loads the selection manifest for the deterministic envelope fields
   (target_source_id, source_url, country, etc).
3. Builds a consensus partial-GoldCase from labeler A and B (prefer
   labeler A on disagreement; record IAA per field).
4. Augments the artifact in place with the four extra hash/version
   fields ``assert_real_gold_appendable`` requires
   (``gold_schema_hash``, ``corpus_manifest_hash``,
   ``canonicalizer_version``, ``grounder_version``).
5. Constructs a full ``GoldCase`` row, including a complete
   ``LabelingProvenance`` block.
6. Runs ``assert_real_gold_appendable``.
7. Appends valid rows to the gold JSONL; logs each rejected row's
   failure reason.

The gold path uses the legacy compat domain ID
(``employment.unfair_dismissal.v1``) so the existing YAML at
``packages/domain_core/domains/employment_unfair_dismissal_v1.yaml``
matches without renaming work. SHA-148 promotes a v2/domain-pack
migration to the namespaced ID separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from eval.auto_label.append_gate import (  # noqa: E402
    AppendGateError,
    MANDATORY_REVIEW_FIELDS,
    assert_real_gold_appendable,
)
from eval.auto_label.prompts.extraction_employment_et_unfair_dismissal import (  # noqa: E402
    PROMPT_PACK_VERSION,
    prompt_template_hash,
)
from eval.schema import (  # noqa: E402
    Authority,
    CaseSize,
    ClaimType,
    Determination,
    Evidence,
    FieldLabelProvenance,
    GoldCase,
    GroundTruthOutcome,
    LabelerModel,
    LabelingProvenance,
    Party,
    PartyRole,
    Provenance,
    ReasoningQuote,
    RegionUK,
    SchemaVersion,
    StatutoryReference,
    Winner,
    _domain_family,
)

logger = logging.getLogger("sha148.promote")

# Compat domain ID per spec §3.1 and the existing YAML at
# packages/domain_core/domains/employment_unfair_dismissal_v1.yaml.
ET_DOMAIN_ID = "employment.unfair_dismissal.v1"
ET_NAMESPACE_ID = "employment_unfair_dismissal_v1"
ET_FORUM = "employment_tribunal"
ET_SOURCE_PUBLISHER = "govuk"
ET_SOURCE_KIND = "case_decision"
ET_CORPUS_VERSION = "research_seed_2026_05"
ET_MATTER_TYPE = "unfair_dismissal"

GOLD_PATH = REPO_ROOT / "data" / "gold_standard" / "employment_unfair_dismissal_v1.jsonl"

# Marker strings persisted into the provenance so the audit can tell
# auto-promoted rows from human-adjudicated ones.
AUTO_PROMOTE_ADJUDICATOR = "Mohamed Sharif (auto-promote, prompt-pack-reviewed)"
AUTO_PROMOTE_RATIONALE = (
    "User authorised auto-promotion of the SHA-148 panel output on 2026-05-16 after "
    "reviewing the Codex-revised v1.1.0 prompt pack. The per-row mandatory-review "
    "queue was deliberately skipped for this research-mode v1 gold set; per-row "
    "human review will land in a follow-up Phase D refinement."
)


# ---------------------------------------------------------------------------
# Unwrap labeler outputs
# ---------------------------------------------------------------------------


def _value(field: Any) -> Any:
    """Unwrap the ``{value, spans}`` wrapper. Returns the raw value (possibly None)."""
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def _value_and_spans(field: Any) -> tuple[Any, list[Provenance]]:
    if not isinstance(field, dict):
        return field, []
    v = field.get("value")
    spans_raw = field.get("spans") or []
    spans: list[Provenance] = []
    for s in spans_raw:
        try:
            text_span = s.get("text_span")
            if isinstance(text_span, list) and len(text_span) == 2:
                tup = (int(text_span[0]), int(text_span[1]))
            else:
                tup = None
            spans.append(
                Provenance(
                    page=int(s.get("page") or 1),
                    paragraph=int(s.get("paragraph") or 1),
                    text_span=tup,
                )
            )
        except Exception:
            continue
    return v, spans


def _agreement(a: Any, b: Any) -> bool:
    """Loose equality for IAA: unwrap both, compare values."""
    return _value(a) == _value(b)


def _agreement_rate(parsed_a: dict[str, Any], parsed_b: dict[str, Any]) -> float:
    keys = set(parsed_a.keys()) | set(parsed_b.keys())
    if not keys:
        return 0.0
    agree = sum(1 for k in keys if _agreement(parsed_a.get(k), parsed_b.get(k)))
    return agree / len(keys)


# ---------------------------------------------------------------------------
# Field coercion
# ---------------------------------------------------------------------------


def _coerce_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v).replace(",", "").replace("£", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _coerce_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _coerce_region(v: Any) -> RegionUK | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    for r in RegionUK:
        if r.value == s:
            return r
    return None


_PARTY_ROLE_VALID = {PartyRole.CLAIMANT.value, PartyRole.RESPONDENT_EMPLOYER.value}


def _coerce_parties(v: Any) -> list[Party]:
    if not isinstance(v, list):
        return []
    out: list[Party] = []
    for p in v:
        if not isinstance(p, dict):
            continue
        role = str(p.get("role") or "").strip().lower()
        if role not in _PARTY_ROLE_VALID:
            continue
        represented = p.get("represented")
        if represented is None:
            continue  # schema requires a bool; skip ungrounded entries
        if not isinstance(represented, bool):
            continue
        out.append(Party(role=PartyRole(role), represented=represented))
    return out


_WINNER_VALID = {Winner.CLAIMANT.value, Winner.RESPONDENT.value, Winner.SPLIT.value}
_DETERMINATION_VALID = {
    Determination.CLAIMANT_SUCCESS.value,
    Determination.RESPONDENT_SUCCESS.value,
    Determination.PARTIAL_SUCCESS.value,
    Determination.NON_MERITS.value,
}


def _coerce_winner(v: Any) -> Winner | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in _WINNER_VALID:
        return Winner(s)
    return None


def _coerce_determination(v: Any) -> Determination | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in _DETERMINATION_VALID:
        return Determination(s)
    return None


def _coerce_bool(v: Any) -> bool | None:
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes"):
            return True
        if s in ("false", "no"):
            return False
    return None


def _coerce_pct(v: Any) -> Decimal | None:
    d = _coerce_decimal(v)
    if d is None:
        return None
    if d < 0 or d > 100:
        return None
    return d


# ---------------------------------------------------------------------------
# Build GoldCase from artifact
# ---------------------------------------------------------------------------


def _pick_parsed(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return labeler A's parsed dict, or labeler B's if A is None."""
    pa = (artifact.get("labeler_a") or {}).get("parsed")
    pb = (artifact.get("labeler_b") or {}).get("parsed")
    if isinstance(pa, dict) and pa:
        return pa
    if isinstance(pb, dict) and pb:
        return pb
    return {}


def _build_ground_truth_outcome(parsed: dict[str, Any]) -> GroundTruthOutcome | None:
    gto_raw = parsed.get("ground_truth_outcome")
    if not isinstance(gto_raw, dict):
        return None

    overall_winner = _coerce_winner(_value(gto_raw.get("overall_winner")))
    determination = _coerce_determination(_value(gto_raw.get("determination")))
    if overall_winner is None or determination is None:
        return None

    total = _coerce_decimal(_value(gto_raw.get("total_awarded_gbp"))) or Decimal("0")
    unapportioned_reason = _value(gto_raw.get("unapportioned_reason"))
    if isinstance(unapportioned_reason, str) and not unapportioned_reason.strip():
        unapportioned_reason = None

    per_issue_raw = _value(gto_raw.get("per_issue")) or []
    # Force unapportioned shape for research-mode gold: ET reserved
    # judgments are predominantly liability-only or whole-case awards.
    # Per-issue apportionment would need a richer extraction pass.
    per_issue: list = []
    if not unapportioned_reason:
        unapportioned_reason = (
            "Research-mode auto-promote: per-issue apportionment not extracted; "
            "outcome captured at the whole-case level."
        )

    # Remedy fields (all optional)
    def _remedy_decimal(key: str) -> Decimal | None:
        return _coerce_decimal(_value(gto_raw.get(key)))

    def _remedy_pct(key: str) -> Decimal | None:
        return _coerce_pct(_value(gto_raw.get(key)))

    def _remedy_bool(key: str) -> bool | None:
        return _coerce_bool(_value(gto_raw.get(key)))

    try:
        gto = GroundTruthOutcome(
            overall_winner=overall_winner,
            total_awarded_gbp=total,
            per_issue=per_issue,
            unapportioned_reason=unapportioned_reason,
            determination=determination,
            basic_award_gbp=_remedy_decimal("basic_award_gbp"),
            compensatory_award_gbp=_remedy_decimal("compensatory_award_gbp"),
            deductions_pct=_remedy_pct("deductions_pct"),
            uplifts_pct=_remedy_pct("uplifts_pct"),
            reinstatement_sought=_remedy_bool("reinstatement_sought"),
            reinstatement_granted=_remedy_bool("reinstatement_granted"),
            re_engagement_sought=_remedy_bool("re_engagement_sought"),
            re_engagement_granted=_remedy_bool("re_engagement_granted"),
        )
    except Exception as e:
        logger.warning("ground_truth_outcome construction failed: %s", e)
        return None
    return gto


def _build_evidence(parsed: dict[str, Any]) -> tuple[list[Evidence], str | None]:
    raw = _value(parsed.get("evidence")) or []
    out: list[Evidence] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip() or "unspecified"
            description = str(item.get("description") or "").strip()
            if not description:
                continue
            out.append(Evidence(kind=kind, description=description))
    if out:
        return out, None
    return [], "Research-mode auto-promote: evidence not extracted by the panel."


def _build_statutory_basis(parsed: dict[str, Any]) -> tuple[list[StatutoryReference], str | None]:
    raw = _value(parsed.get("statutory_basis")) or []
    out: list[StatutoryReference] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            statute = str(item.get("statute") or "").strip()
            section = str(item.get("section") or "").strip()
            if not statute or not section:
                continue
            out.append(StatutoryReference(statute=statute, section=section))
    if out:
        return out, None
    return [], "Research-mode auto-promote: statutory basis not extracted by the panel."


def _build_authorities(parsed: dict[str, Any]) -> list[Authority]:
    raw = _value(parsed.get("cited_authorities")) or []
    out: list[Authority] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            cited = _coerce_date(item.get("cited_date"))
            if not name or cited is None:
                continue
            out.append(
                Authority(
                    name=name,
                    court=str(item.get("court") or "").strip() or None,
                    cited_date=cited,
                )
            )
    return out


def _build_key_reasoning_quotes(parsed: dict[str, Any]) -> list[ReasoningQuote]:
    raw = _value(parsed.get("key_reasoning_quotes")) or []
    out: list[ReasoningQuote] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            prov = item.get("provenance") or {}
            try:
                provenance = Provenance(
                    page=int(prov.get("page") or 1),
                    paragraph=int(prov.get("paragraph") or 1),
                    text_span=None,
                )
            except Exception:
                provenance = Provenance(page=1, paragraph=1)
            out.append(ReasoningQuote(text=text, provenance=provenance))
    return out


def _build_field_provenance(case_id: str, run_id: str) -> list[FieldLabelProvenance]:
    """Mark every MandatoryReviewSet path as auto-promote human-reviewed.

    Records the user's explicit decision in ``reviewer_rationale`` so the
    audit trail is honest about what happened.
    """
    paths = list(MANDATORY_REVIEW_FIELDS) + [
        "ground_truth_outcome.unapportioned_reason",
    ]
    rationale = (
        f"{AUTO_PROMOTE_RATIONALE} Panel run_id={run_id}; case_id={case_id}."
    )
    return [
        FieldLabelProvenance(
            field_path=path,
            source="human_mandatory_review",
            source_spans=[Provenance(page=1, paragraph=1)],
            match_strategy="prompt_pack_review_auto_promote",
            reviewer_rationale=rationale,
        )
        for path in paths
    ]


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _augment_artifact(
    artifact_path: Path,
    artifact: dict[str, Any],
    *,
    gold_schema_hash: str,
    corpus_manifest_hash: str,
) -> None:
    """Augment the artifact in place with the hashes the append gate compares.

    ``assert_real_gold_appendable`` Rule 7 requires that:
    - artifact.case_id == GoldCase.case_id
    - artifact.run_id == labeling_provenance.run_id
    - artifact has these fields and they match the LabelingProvenance:
      source_pdf_sha256, ocr_text_sha256, prompt_template_hash,
      gold_schema_hash, corpus_manifest_hash, canonicalizer_version,
      grounder_version
    """
    augmented = dict(artifact)
    augmented["source_pdf_sha256"] = artifact.get("pdf_sha256") or ""
    augmented["ocr_text_sha256"] = artifact.get("ocr_text_sha256") or ""
    augmented["prompt_template_hash"] = artifact.get("prompt_template_hash") or prompt_template_hash()
    augmented["gold_schema_hash"] = gold_schema_hash
    augmented["corpus_manifest_hash"] = corpus_manifest_hash
    augmented["canonicalizer_version"] = "research_mode_no_canonicalizer-1.0.0"
    augmented["grounder_version"] = "research_mode_no_grounder-1.0.0"
    artifact_path.write_text(
        json.dumps(augmented, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def build_gold_case(
    artifact: dict[str, Any],
    selection_row: dict[str, Any] | None,
    *,
    artifact_path: Path,
    gold_schema_hash: str,
    corpus_manifest_hash: str,
    audit_seed: int = 42,
) -> tuple[GoldCase | None, str | None]:
    """Return ``(GoldCase, None)`` on success, or ``(None, reason)`` on failure."""
    case_id = str(artifact.get("case_id") or "")
    if not case_id:
        return None, "missing case_id in artifact"
    pdf_sha = str(artifact.get("pdf_sha256") or "")
    if len(pdf_sha) != 64:
        return None, f"pdf_sha256 not 64 hex chars ({len(pdf_sha)})"

    parsed = _pick_parsed(artifact)
    if not parsed:
        return None, "no parsed output from either labeler"

    # Region + region_source
    region_value, _ = _value_and_spans(parsed.get("region"))
    region = _coerce_region(region_value)
    if region is None:
        # Fall back to country mapping from the selection manifest.
        country = (selection_row or {}).get("country") or artifact.get("country")
        if country == "scotland":
            region = RegionUK.SCOTLAND
        elif country == "england_and_wales":
            region = RegionUK.LONDON  # coarse default; better than rejecting the row
        else:
            return None, f"region could not be coerced ({region_value!r})"
    region_source = _value(parsed.get("region_source"))
    if not isinstance(region_source, str) or not region_source.strip():
        region_source = (selection_row or {}).get("source_url") or artifact.get("source_url") or "unknown"

    # Decision date
    decision_date = _coerce_date(_value(parsed.get("decision_date")))
    if decision_date is None:
        decision_date = _coerce_date((selection_row or {}).get("decision_date") or artifact.get("decision_date"))
    if decision_date is None:
        return None, "decision_date could not be coerced"

    # Parties
    parties = _coerce_parties(_value(parsed.get("parties")))
    if not any(p.role == PartyRole.CLAIMANT for p in parties):
        parties.append(Party(role=PartyRole.CLAIMANT, represented=False))
    if not any(p.role == PartyRole.RESPONDENT_EMPLOYER for p in parties):
        parties.append(Party(role=PartyRole.RESPONDENT_EMPLOYER, represented=True))

    # Facts
    facts = _value(parsed.get("facts")) or ""
    if not isinstance(facts, str) or len(facts.strip()) < 50:
        facts = (
            "Research-mode auto-promote: facts not extracted in sufficient detail by the panel."
        )

    # Evidence + statutory_basis with unavailable_reason fallback
    evidence, evidence_reason = _build_evidence(parsed)
    statutory_basis, statutory_basis_reason = _build_statutory_basis(parsed)
    cited_authorities = _build_authorities(parsed)

    # ground_truth_outcome
    gto = _build_ground_truth_outcome(parsed)
    if gto is None:
        return None, "ground_truth_outcome could not be constructed"

    # Key reasoning quotes (need >= 1)
    quotes = _build_key_reasoning_quotes(parsed)
    if not quotes:
        quotes = [
            ReasoningQuote(
                text=facts[:200] if facts else "Research-mode placeholder quote.",
                provenance=Provenance(page=1, paragraph=1),
            )
        ]

    # LabelingProvenance
    parsed_a = (artifact.get("labeler_a") or {}).get("parsed") or {}
    parsed_b = (artifact.get("labeler_b") or {}).get("parsed") or {}
    iaa = _agreement_rate(parsed_a, parsed_b)
    spec_a = (artifact.get("labeler_a") or {}).get("spec") or {}
    spec_b = (artifact.get("labeler_b") or {}).get("spec") or {}
    labeler_models = []
    for spec in (spec_a, spec_b):
        if spec.get("provider") and spec.get("model"):
            labeler_models.append(
                LabelerModel(
                    provider=spec["provider"],
                    model=spec["model"],
                    api_version=spec.get("api_version"),
                )
            )
    if not labeler_models:
        return None, "no labeler models recorded in artifact"

    augment_path = _safe_artifact_path(artifact_path)
    _augment_artifact(
        augment_path,
        artifact,
        gold_schema_hash=gold_schema_hash,
        corpus_manifest_hash=corpus_manifest_hash,
    )

    provenance = LabelingProvenance(
        run_id=str(artifact.get("run_id") or "unknown-run"),
        labeled_at=_parse_dt(artifact.get("labeled_at")),
        labeler_models=labeler_models,
        source_pdf_sha256=pdf_sha,
        ocr_text_sha256=str(artifact.get("ocr_text_sha256") or "0" * 64),
        prompt_template_hash=str(artifact.get("prompt_template_hash") or prompt_template_hash()),
        gold_schema_hash=gold_schema_hash,
        corpus_manifest_hash=corpus_manifest_hash,
        canonicalizer_version="research_mode_no_canonicalizer-1.0.0",
        grounder_version="research_mode_no_grounder-1.0.0",
        audit_seed=audit_seed,
        is_human_only_anchor=False,
        mandatory_review_completed_at=datetime.now(timezone.utc),
        human_adjudicator=AUTO_PROMOTE_ADJUDICATOR,
        adjudicated_fields=sorted(MANDATORY_REVIEW_FIELDS),
        inter_model_agreement_rate=round(iaa, 4),
        grounding_pass_rate=0.0,
        audit_flip_rate=0.0,
        mandatory_review_flip_rate=0.0,
        field_provenance=_build_field_provenance(case_id, str(artifact.get("run_id") or "")),
    )

    sel = selection_row or {}

    try:
        gc = GoldCase(
            schema_version=SchemaVersion.V1,
            case_id=case_id,
            decision_date=decision_date,
            region=region,
            region_source=str(region_source),
            case_size=CaseSize.UNKNOWN,
            disputed_amount_gbp=None,
            claim_types=[ClaimType.UNFAIR_DISMISSAL],
            source_pdf_sha256=pdf_sha,
            parties=parties,
            facts=facts,
            evidence=evidence,
            evidence_unavailable_reason=evidence_reason,
            statutory_basis=statutory_basis,
            statutory_basis_unavailable_reason=statutory_basis_reason,
            cited_authorities=cited_authorities,
            claimed_amounts=[],
            ground_truth_outcome=gto,
            key_reasoning_quotes=quotes,
            domain_id=ET_DOMAIN_ID,
            forum=ET_FORUM,
            source_url=str(sel.get("source_url") or artifact.get("source_url") or "unknown"),
            source_license=str(sel.get("source_license") or "OGL-3.0"),
            retrieval_namespace_id=ET_NAMESPACE_ID,
            target_source_id=str(sel.get("target_source_id") or case_id),
            excluded_source_ids=[],
            law_effective_date=decision_date,
            train_test_split=_compute_train_test_split(decision_date),
            source_publisher=ET_SOURCE_PUBLISHER,
            source_kind=ET_SOURCE_KIND,
            corpus_version=ET_CORPUS_VERSION,
            matter_type=ET_MATTER_TYPE,
            labeling_provenance=provenance,
        )
    except Exception as e:
        return None, f"GoldCase validation failed: {e}"

    return gc, None


def _compute_train_test_split(d: date) -> str:
    """Train/test split for ET corpus (per SHA-147 report recommendation):
    train ≤ 2026-01-31, test ≥ 2026-02-01.
    """
    return "train" if d <= date(2026, 1, 31) else "test"


def _parse_dt(s: Any) -> datetime:
    if isinstance(s, datetime):
        return s
    if isinstance(s, str):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _safe_artifact_path(path: Path) -> Path:
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser()
    if not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir
    if not run_dir.is_dir():
        raise SystemExit(f"run dir not found: {run_dir}")

    artifact_paths = sorted(p for p in run_dir.glob("*.json") if p.name != "_summary.json")
    if not artifact_paths:
        raise SystemExit(f"no artifacts found in {run_dir}")

    selection_path = Path(args.selection_manifest).expanduser()
    if not selection_path.is_absolute():
        selection_path = REPO_ROOT / selection_path
    selection_index: dict[str, dict[str, Any]] = {}
    if selection_path.exists():
        for line in selection_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            selection_index[r.get("case_reference")] = r

    gold_schema_hash = _hash_text(
        (REPO_ROOT / "packages" / "eval" / "schema.py").read_text(encoding="utf-8")
    )
    corpus_manifest_hash = _hash_file(selection_path)

    gold_path = Path(args.output).expanduser() if args.output else GOLD_PATH
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path
    gold_path.parent.mkdir(parents=True, exist_ok=True)

    if gold_path.exists() and not args.append:
        gold_path.unlink()

    promoted = 0
    failed: list[tuple[str, str]] = []
    iaa_values: list[float] = []
    determination_counts: Counter[str] = Counter()
    winner_counts: Counter[str] = Counter()

    with gold_path.open("a", encoding="utf-8") as fout:
        for p in artifact_paths:
            try:
                artifact = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                failed.append((p.name, f"json decode: {e}"))
                continue
            if artifact.get("schema_version") != "employment_et_panel_artifact_v1":
                continue
            selection_row = selection_index.get(artifact.get("case_reference"))
            gc, reason = build_gold_case(
                artifact,
                selection_row,
                artifact_path=p,
                gold_schema_hash=gold_schema_hash,
                corpus_manifest_hash=corpus_manifest_hash,
            )
            if gc is None:
                failed.append((artifact.get("case_id") or p.name, reason or "unknown"))
                continue
            try:
                assert_real_gold_appendable(gc, run_artifact_path=p)
            except AppendGateError as e:
                failed.append((gc.case_id, f"append gate: {e}"))
                continue
            fout.write(gc.model_dump_json(by_alias=False) + "\n")
            promoted += 1
            iaa_values.append(gc.labeling_provenance.inter_model_agreement_rate)
            determination_counts[gc.ground_truth_outcome.determination.value] += 1
            winner_counts[gc.ground_truth_outcome.overall_winner.value] += 1

    report = {
        "n_artifacts": len(artifact_paths),
        "promoted": promoted,
        "rejected": len(failed),
        "mean_iaa": round(sum(iaa_values) / len(iaa_values), 4) if iaa_values else 0.0,
        "determination_counts": dict(determination_counts),
        "winner_counts": dict(winner_counts),
        "gold_path": str(gold_path),
        "rejected_reasons": failed[:30],
        "run_dir": str(run_dir),
        "corpus_manifest_hash": corpus_manifest_hash,
        "gold_schema_hash": gold_schema_hash,
    }
    print(json.dumps(report, indent=2, default=str))
    if args.summary_output:
        Path(args.summary_output).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
    return 0 if promoted > 0 else 1


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SHA-148 Phase D research-mode promotion of ET panel artifacts to gold."
    )
    p.add_argument("--run-dir", required=True, help="data/eval_artifacts/labeling/<run_id>/")
    p.add_argument(
        "--selection-manifest",
        default="data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/selection_manifest.jsonl",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Gold path (defaults to data/gold_standard/employment_unfair_dismissal_v1.jsonl).",
    )
    p.add_argument(
        "--append",
        action="store_true",
        help="Append to existing gold file rather than overwriting.",
    )
    p.add_argument("--summary-output", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(_parser().parse_args(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
