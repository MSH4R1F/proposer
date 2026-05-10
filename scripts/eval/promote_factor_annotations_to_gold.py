#!/usr/bin/env python3
"""Promote double-pass factor annotations into the case-side sidecar.

The companion to ``factor_gold_annotation.py``: takes the IAA-style JSONL
output of two annotators, picks a canonical value per ``(case_id, factor_id)``
via the tie-break rule below, and writes a
:func:`eval.factor_assertion_sidecar`-shaped JSON file. The eval runner
reads that sidecar at engine-input time so the FactorRetriever's
``asserted_factors`` input is non-empty (Stream C case-side backfill).

Tie-break rule per ``(case_id, factor_id)``::

    - If both annotators agree on .value (with is_null treated as a value):
        use it.
    - If they disagree:
        prefer the higher-confidence annotator's value AND set
        requires_human_review=True.
    - If both are equally confident on disagreement:
        default to the annotator whose annotator_id sorts first
        alphabetically AND set requires_human_review=True.
    - If the chosen value's confidence < --min-confidence (default 0.5):
        set requires_human_review=True regardless.

The script is **idempotent**: running it twice on the same input produces
byte-identical output (sort_keys=True + atomic write). The
``factor_assertion_id`` is a deterministic UUID5 of
``(case_id, factor_id, "promoted")`` so re-runs don't churn IDs.

Usage::

    scripts/eval/promote_factor_annotations_to_gold.py \\
        --annotations data/eval_artifacts/gold_annotation/<input>.jsonl \\
        --gold-corpus data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \\
        --domain housing.repairs_social.v1 \\
        --execute
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))
sys.path.insert(0, str(_HERE.parent))


# Deterministic namespace for promoted factor_assertion_ids. Stable for the
# whole project — do NOT regenerate; ID stability across runs is the entire
# point of this constant.
_PROMOTER_UUID5_NAMESPACE = uuid.UUID("4d2c7c47-3a8f-5b9b-9b1d-25e4d4d7f1a1")


def _stable_factor_assertion_id(case_id: str, factor_id: str) -> str:
    """Deterministic UUID5 → ``fa_promoted_<hex>``."""
    seed = f"{case_id}::{factor_id}::promoted"
    return f"fa_promoted_{uuid.uuid5(_PROMOTER_UUID5_NAMESPACE, seed).hex}"


def _stable_evidence_span_id(case_id: str, factor_id: str, ord_: int = 0) -> str:
    """Deterministic synthetic EvidenceSpan id.

    The IAA annotator JSON carries ``source_span: Optional[str]``, not a
    structured EvidenceSpan. To satisfy ``FactorAssertion.supported_by``
    (which requires at least one span ref for non-deterministic
    extractions), we fabricate a stable id that downstream tooling can
    later resolve to a real span if/when one is produced.
    """
    seed = f"{case_id}::{factor_id}::evidence::{ord_}"
    return f"es_promoted_{uuid.uuid5(_PROMOTER_UUID5_NAMESPACE, seed).hex}"


def _normalise_source_span(value: Any) -> Optional[str]:
    """Return non-empty annotator quote text, if present."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _value_signature(annotation: Dict[str, Any]) -> Tuple[Any, ...]:
    """Hashable signature of an Annotation's value for equality checks.

    Two annotations agree iff their signatures compare equal. Captures
    both the typed payload and the ``is_null`` flag (so explicit
    "no value" by both annotators counts as agreement).
    """
    val = annotation.get("value") or {}
    return (
        bool(val.get("is_null", False)),
        val.get("boolean"),
        val.get("enum"),
        val.get("number"),
        val.get("duration_days"),
    )


def _read_annotations_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _load_factors_yaml(domain_id: str) -> Dict[str, Dict[str, Any]]:
    """Return a ``factor_id -> factor_dict`` map from the domain pack."""
    try:
        # Reuse the existing loader — it handles dotted-id → directory
        # mapping and version stripping.
        from factor_catalog_review import load_domain_pack  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Could not import factor_catalog_review.load_domain_pack; the "
            "promoter must be invoked with scripts/eval/ on sys.path"
        ) from exc

    pack = load_domain_pack(domain_id, repo_root=_REPO_ROOT)
    return {f["id"]: f for f in pack["factors"]}


def _factor_value_type(catalog_value_type: str) -> str:
    """Map factor catalog value_type → FactorValue/FactorAssertion value_type.

    The catalog uses ``boolean``, ``enum``, ``number``, ``duration``. The
    FactorValueType enum in legal_core matches exactly (lower-case).
    """
    return catalog_value_type


def _build_factor_value(
    annotation_value: Dict[str, Any],
    catalog_value_type: str,
) -> Optional[Dict[str, Any]]:
    """Translate an Annotation.value (from IAA JSONL) → a FactorValue dict.

    Returns ``None`` when the canonical annotation is ``is_null=True`` —
    callers must skip emitting an assertion in that case (a null value
    carries no signal for retrieval).
    """
    if annotation_value.get("is_null"):
        return None

    if catalog_value_type == "boolean":
        b = annotation_value.get("boolean")
        if b is None:
            return None
        return {"value_type": "boolean", "boolean": bool(b)}

    if catalog_value_type == "enum":
        e = annotation_value.get("enum")
        if e is None:
            return None
        return {"value_type": "enum", "enum": str(e)}

    if catalog_value_type == "number":
        n = annotation_value.get("number")
        if n is None:
            return None
        return {"value_type": "number", "number": float(n)}

    if catalog_value_type == "duration":
        d = annotation_value.get("duration_days")
        if d is None:
            return None
        return {"value_type": "duration", "duration_days": int(d)}

    raise ValueError(f"unsupported catalog value_type: {catalog_value_type!r}")


def _polarity_from_catalog(factor: Dict[str, Any]) -> str:
    p = factor.get("polarity")
    if p is None:
        return "neutral"
    return str(p)


# ---------------------------------------------------------------------------
# Tie-break + canonicalisation
# ---------------------------------------------------------------------------


def select_canonical_annotation(
    annotations_for_pair: List[Dict[str, Any]],
    *,
    min_confidence: float,
) -> Tuple[Dict[str, Any], bool]:
    """Pick the canonical Annotation row for one ``(case_id, factor_id)`` pair.

    Returns ``(canonical_annotation, requires_human_review_flag)``.

    See module docstring for the tie-break rule. ``annotations_for_pair``
    must be non-empty.
    """
    if not annotations_for_pair:
        raise ValueError("annotations_for_pair must be non-empty")

    if len(annotations_for_pair) == 1:
        ann = annotations_for_pair[0]
        flag = bool(
            ann.get("requires_human_review")
            or float(ann.get("confidence", 0.0)) < min_confidence
        )
        return ann, flag

    # Two (or more) annotators. Group by value signature.
    by_sig: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for ann in annotations_for_pair:
        by_sig[_value_signature(ann)].append(ann)

    if len(by_sig) == 1:
        # All annotators agree. Pick the highest-confidence row (stable
        # tiebreak by annotator_id) so attributes like source_span and
        # reasoning come from the most-confident annotator.
        candidates = annotations_for_pair
        canonical = max(
            candidates,
            key=lambda a: (
                float(a.get("confidence", 0.0)),
                # alphabetically-first annotator wins ties
                -_alpha_rank(a.get("annotator_id", "")),
            ),
        )
        flag = bool(
            canonical.get("requires_human_review")
            or float(canonical.get("confidence", 0.0)) < min_confidence
        )
        return canonical, flag

    # Disagreement. Tie-break by max confidence; alpha annotator_id.
    canonical = max(
        annotations_for_pair,
        key=lambda a: (
            float(a.get("confidence", 0.0)),
            -_alpha_rank(a.get("annotator_id", "")),
        ),
    )
    return canonical, True


def _alpha_rank(annotator_id: str) -> int:
    """Stable integer rank from annotator_id string for tie-breaking.

    ``-_alpha_rank(...)`` in a max() key inverts the order so the
    alphabetically-FIRST id wins.
    """
    # Use a hashable, comparable value. Python's tuple-of-codepoints
    # already orders strings lexicographically; we just turn that into a
    # pseudo-int via repr.
    return sum((ord(c) << (8 * i)) for i, c in enumerate(annotator_id[:8]))


# ---------------------------------------------------------------------------
# Promoter — turn canonical annotations into FactorAssertion dicts
# ---------------------------------------------------------------------------


def promote_annotations(
    annotation_rows: Iterable[Dict[str, Any]],
    *,
    domain_id: str,
    extractor_version: str,
    min_confidence: float,
    claim_head_id_for_case: Optional[Dict[str, str]] = None,
    evidence_spans_by_case_id: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Group → tie-break → translate. Returns ``case_id -> [FactorAssertion dicts]``.

    *claim_head_id_for_case*: optional map ``case_id -> claim_head_id``.
    When omitted, ``claim_head_id`` defaults to the case's primary
    matter_type / a hard-coded ``"repairs_damp_mould"`` for housing
    repairs (the only domain in scope today). The map lets the eval
    runner pass real per-case heads when one is available.
    """
    factors_by_id = _load_factors_yaml(domain_id)

    # Group by (case_id, factor_id)
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in annotation_rows:
        case_id = str(row.get("case_id"))
        factor_id = str(row.get("factor_id"))
        grouped[(case_id, factor_id)].append(row)

    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for (case_id, factor_id), rows in sorted(grouped.items()):
        if factor_id not in factors_by_id:
            # Unknown factor — skip with a warning. Don't fail the run.
            print(
                f"warning: skipping unknown factor_id={factor_id!r} for "
                f"case_id={case_id!r}",
                file=sys.stderr,
            )
            continue

        factor = factors_by_id[factor_id]
        catalog_value_type = factor.get("value_type", "boolean")

        canonical, review_flag = select_canonical_annotation(
            rows, min_confidence=min_confidence,
        )

        # is_null canonical → no assertion to emit (skip).
        canon_value = canonical.get("value") or {}
        if canon_value.get("is_null"):
            continue

        factor_value = _build_factor_value(canon_value, catalog_value_type)
        if factor_value is None:
            # Annotators wanted to populate this factor but the typed
            # payload is missing. Skip — we cannot construct a valid
            # FactorAssertion without a typed value.
            continue

        confidence = float(canonical.get("confidence", 0.0))
        if confidence < min_confidence:
            review_flag = True

        # Build supporting evidence span ids. The annotators carry a
        # free-text source_span; we emit one synthetic span id so the
        # FactorAssertion validator's "must have at least one span" rule
        # for non-deterministic extractions is satisfied.
        span_id = _stable_evidence_span_id(case_id, factor_id)
        source_span = _normalise_source_span(canonical.get("source_span"))
        if source_span and evidence_spans_by_case_id is not None:
            evidence_spans_by_case_id.setdefault(case_id, []).append(
                {
                    "evidence_span_id": span_id,
                    "source_kind": "ombudsman_determination",
                    "source_reference": case_id,
                    "quote_text": source_span,
                    "paragraph_range": None,
                }
            )
        annotator_ids = sorted(
            {str(r.get("annotator_id", "")) for r in rows if r.get("annotator_id")}
        )
        annotator_summary = "+".join(annotator_ids) if annotator_ids else "unknown"

        claim_head_id = (
            (claim_head_id_for_case or {}).get(case_id) or "repairs_damp_mould"
        )

        fa: Dict[str, Any] = {
            "factor_assertion_id": _stable_factor_assertion_id(case_id, factor_id),
            "factor_id": factor_id,
            "domain_id": domain_id,
            "claim_head_id": claim_head_id,
            "value": factor_value,
            "value_type": _factor_value_type(catalog_value_type),
            "confidence": confidence,
            "polarity": _polarity_from_catalog(factor),
            "expected_effects": [],
            # Surface catalog outcome mappings so the FactorRetriever's
            # counterexample pass has signal even with case-side-only data.
            "maps_to_outcomes": list(factor.get("maps_to_outcomes") or []),
            "maps_to_remedies": [],
            "supported_by": [span_id],
            "refuted_by": [],
            "linked_events": [],
            "linked_issues": [],
            "source_span_refs": [span_id],
            "extraction_method": "llm_extracted",
            "extractor_version": (
                f"promoted/{extractor_version}/annotators={annotator_summary}"
            ),
            "verifier_version": None,
            "requires_human_review": bool(review_flag),
        }
        out[case_id].append(fa)

    # Stable per-case ordering by factor_id (idempotency)
    return {
        cid: sorted(rows, key=lambda r: r["factor_id"])
        for cid, rows in sorted(out.items())
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _summarise(factor_assertions_by_case_id: Dict[str, List[Dict[str, Any]]]) -> str:
    n_cases = len(factor_assertions_by_case_id)
    n_fa = sum(len(v) for v in factor_assertions_by_case_id.values())
    n_review = sum(
        1
        for rows in factor_assertions_by_case_id.values()
        for r in rows
        if r.get("requires_human_review")
    )
    return (
        f"cases={n_cases} factor_assertions={n_fa} "
        f"requires_human_review={n_review}"
    )


def _validate_against_pydantic(
    factor_assertions_by_case_id: Dict[str, List[Dict[str, Any]]],
    evidence_spans_by_case_id: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> None:
    """Round-trip every promoted dict through the FactorAssertion model.

    Catches validation errors before we write — any failure is a logic
    bug in the promoter, not a user input problem.
    """
    from legal_core.graph.factor_assertion import FactorAssertion  # noqa: PLC0415
    from legal_core.graph.evidence_span import EvidenceSpan  # noqa: PLC0415

    for case_id, rows in factor_assertions_by_case_id.items():
        for r in rows:
            try:
                FactorAssertion.model_validate(r)
            except Exception as exc:
                raise RuntimeError(
                    f"promoter produced invalid FactorAssertion for case_id="
                    f"{case_id!r} factor_id={r.get('factor_id')!r}: {exc}"
                ) from exc

    for case_id, rows in (evidence_spans_by_case_id or {}).items():
        for r in rows:
            try:
                EvidenceSpan.model_validate(r)
            except Exception as exc:
                raise RuntimeError(
                    f"promoter produced invalid EvidenceSpan for case_id="
                    f"{case_id!r} evidence_span_id={r.get('evidence_span_id')!r}: {exc}"
                ) from exc


def _cli_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote double-pass factor annotations into the eval "
            "factor-assertion sidecar."
        ),
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        required=True,
        help="Path to the IAA JSONL produced by factor_gold_annotation.py",
    )
    parser.add_argument(
        "--domain",
        default="housing.repairs_social.v1",
        help="Domain id for the factor catalog (default housing.repairs_social.v1)",
    )
    parser.add_argument(
        "--gold-corpus",
        type=Path,
        default=None,
        help=(
            "Path to the gold-standard JSONL whose case_ids should be the "
            "set written into the sidecar. When omitted, the sidecar carries "
            "all case_ids appearing in the annotations input."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Sidecar output path. When omitted, defaults to "
            "data/eval_artifacts/factor_assertions/<gold-stem>.factor_assertions.json "
            "(requires --gold-corpus)."
        ),
    )
    parser.add_argument(
        "--extractor-version",
        default="2026-05-08",
        help=(
            "String stamped onto each FactorAssertion's extractor_version "
            "(prefixed with 'promoted/'). Use to reflect the annotator "
            "models + date so two refresh runs are distinguishable."
        ),
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Below this threshold, requires_human_review=True (default 0.5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary; do not write the sidecar.",
    )
    args = parser.parse_args(argv)

    if not args.annotations.exists():
        print(f"Error: annotations path {args.annotations} not found", file=sys.stderr)
        return 1

    rows = _read_annotations_jsonl(args.annotations)
    if not rows:
        print(f"Error: annotations JSONL at {args.annotations} is empty", file=sys.stderr)
        return 1

    evidence_spans_by_case_id: Dict[str, List[Dict[str, Any]]] = {}
    factor_assertions_by_case_id = promote_annotations(
        rows,
        domain_id=args.domain,
        extractor_version=args.extractor_version,
        min_confidence=args.min_confidence,
        evidence_spans_by_case_id=evidence_spans_by_case_id,
    )

    # Optionally restrict to gold-corpus case_ids
    if args.gold_corpus is not None:
        if not args.gold_corpus.exists():
            print(
                f"Error: gold corpus {args.gold_corpus} not found", file=sys.stderr,
            )
            return 1
        gold_case_ids: set[str] = set()
        with args.gold_corpus.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                gold_case_ids.add(json.loads(line).get("case_id"))
        kept = {
            cid: rows
            for cid, rows in factor_assertions_by_case_id.items()
            if cid in gold_case_ids
        }
        dropped = sorted(set(factor_assertions_by_case_id) - set(kept))
        if dropped:
            print(
                f"Note: dropping {len(dropped)} case_id(s) not present in "
                f"gold corpus: {dropped[:5]}{'...' if len(dropped) > 5 else ''}"
            )
        factor_assertions_by_case_id = kept
        evidence_spans_by_case_id = {
            cid: rows
            for cid, rows in evidence_spans_by_case_id.items()
            if cid in gold_case_ids
        }

    print(f"Promotion summary: {_summarise(factor_assertions_by_case_id)}")

    # Sanity: every emitted dict must round-trip through Pydantic
    _validate_against_pydantic(
        factor_assertions_by_case_id,
        evidence_spans_by_case_id=evidence_spans_by_case_id,
    )

    if args.dry_run:
        print("--dry-run set; sidecar NOT written.")
        return 0

    # Resolve output path
    output_path = args.output
    if output_path is None:
        if args.gold_corpus is None:
            print(
                "Error: --output OR --gold-corpus must be set so the sidecar "
                "destination can be resolved",
                file=sys.stderr,
            )
            return 1
        from eval.factor_assertion_sidecar import default_sidecar_path  # noqa: PLC0415

        output_path = default_sidecar_path(_REPO_ROOT, args.gold_corpus.name)

    from eval.factor_assertion_sidecar import write_sidecar  # noqa: PLC0415

    write_sidecar(
        output_path,
        domain_id=args.domain,
        extractor_version=args.extractor_version,
        factor_assertions_by_case_id=factor_assertions_by_case_id,
        evidence_spans_by_case_id=evidence_spans_by_case_id,
    )
    print(f"Wrote sidecar to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
