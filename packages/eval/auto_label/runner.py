"""Phase 9 — labeler runner + per-case run artifact writer.

Orchestrates one case through the dual-LLM extraction + auto-grounder
pipeline:

1. Two ``LabelerModelSpec`` configs (one Anthropic, one OpenAI by
   convention) run in parallel via ``asyncio.gather``. Each consumes the
   same allowed-field list and the same source text triples; their
   outputs are partial-``GoldCase``-shaped dicts.
2. The grounder runs once per labeler output, producing a
   ``GroundingResult`` with field-path verdicts and a pass rate.
3. A per-case JSON artifact is written under
   ``data/eval_artifacts/labeling/<run_id>/<case_id>.json`` containing
   raw labeler outputs, the rendered prompts (after template
   substitution), the grounding decisions, and every reproducibility
   hash. The corpus row only carries a ``LabelingProvenance`` summary —
   raw outputs stay in the artifact so the JSONL stays diffable.

The runner does NOT append to ``housing_v1.jsonl``. Adjudication and the
real-gold append gate live in ``scripts/eval/adjudicate.py`` (Phase 11).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from eval.auto_label.canonicalize import CANONICALIZER_VERSION
from eval.auto_label.grounder import GROUNDER_VERSION, GroundingDeps, GroundingResult, ground
from eval.auto_label.prompts.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_PACK_VERSION,
    prompt_template_hash,
    render_extraction_prompt,
)
from llm_orchestrator.clients.base import BaseLLMClient
from llm_orchestrator.clients.labeler_factory import LabelerModelSpec


RUNNER_VERSION = "1.0.0"
LABELER_MAX_TOKENS = 12000


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LabelerOutput:
    """One labeler's pass over a single case."""

    spec: LabelerModelSpec
    rendered_prompt: str
    raw_response: str
    partial_case: dict[str, Any]


@dataclass
class LabelingRun:
    """Per-run configuration shared across cases."""

    run_id: str
    labeler_a_spec: LabelerModelSpec
    labeler_b_spec: LabelerModelSpec
    artifacts_root: Path
    gold_schema_hash: str
    corpus_manifest_hash: str
    domain_id: str = ""

    @property
    def run_dir(self) -> Path:
        return self.artifacts_root / self.run_id


@dataclass
class CasePass:
    """Complete record of one case's pass through the pipeline."""

    case_id: str
    run_id: str
    labeler_a: LabelerOutput
    labeler_b: LabelerOutput
    grounding_a: GroundingResult
    grounding_b: GroundingResult
    source_pdf_sha256: str
    ocr_text_sha256: str
    prompt_template_hash: str
    artifact_path: Optional[Path] = None
    ran_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_EXTRACTION_ALLOWED_FIELDS: tuple[str, ...] = (
    "decision_date",
    "region",
    "region_source",
    "parties",
    "facts",
    "evidence",
    "statutory_basis",
    "cited_authorities",
    "claimed_amounts",
    "disputed_amount_gbp",
    "claim_types",
    "matter_type",
    "ground_truth_outcome",
    "key_reasoning_quotes",
)


def _safe_json_loads(raw: str) -> dict[str, Any]:
    """Parse a labeler's response into a dict; tolerate empty / malformed."""
    text = raw.strip()
    if not text:
        return {}
    # Strip markdown fences a model might emit even when told not to.
    if text.startswith("```"):
        # Drop the first line and an optional trailing fence.
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return _normalise_extraction_shape(parsed)


def _is_extraction_cell(value: Any) -> bool:
    return isinstance(value, Mapping) and any(
        key in value for key in ("value", "spans", "unavailable_reason")
    )


def _coerce_span(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    try:
        page = int(value["page"])
        paragraph = int(value["paragraph"])
    except (KeyError, TypeError, ValueError):
        return None
    out: dict[str, Any] = {"page": page, "paragraph": paragraph}
    text_span = value.get("text_span")
    if (
        isinstance(text_span, (list, tuple))
        and len(text_span) == 2
        and all(isinstance(v, int) for v in text_span)
    ):
        if int(text_span[0]) >= int(text_span[1]):
            return None
        out["text_span"] = [int(text_span[0]), int(text_span[1])]
    return out


def _normalise_quotes(value: Any, spans: list[dict[str, Any]]) -> Any:
    if not isinstance(value, list):
        return value
    out: list[Any] = []
    for idx, item in enumerate(value):
        if isinstance(item, Mapping):
            out.append(dict(item))
            continue
        if isinstance(item, str):
            quote: dict[str, Any] = {"text": item}
            if spans:
                quote["provenance"] = spans[min(idx, len(spans) - 1)]
            out.append(quote)
            continue
        out.append(item)
    return out


def _normalise_facts(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("value") or item.get("description")
                if text is not None:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return " ".join(part for part in parts if part).strip()
    if isinstance(value, Mapping):
        text = value.get("text") or value.get("value") or value.get("summary")
        if text is not None:
            return str(text)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _normalise_extraction_shape(parsed: dict[str, Any]) -> dict[str, Any]:
    """Convert prompt-contract cells into the partial-case shape.

    The live labelers are instructed to emit ``{"value": ..., "spans": ...}``
    cells, while older offline fixtures used direct GoldCase-like values.
    The grounder consumes the latter shape plus ``_field_provenance``. Keep
    direct fixture rows unchanged, but unwrap live extraction cells before
    grounding so real provider output does not crash on nested dict values.
    """
    normalised: dict[str, Any] = {}
    field_provenance: dict[str, list[dict[str, Any]]] = {}
    unavailable_reasons: dict[str, str] = {}

    for field, cell in parsed.items():
        if not _is_extraction_cell(cell):
            normalised[field] = cell
            continue

        assert isinstance(cell, Mapping)
        spans = [
            span
            for span in (_coerce_span(raw_span) for raw_span in cell.get("spans", []) or [])
            if span is not None
        ]
        if spans:
            field_provenance[field] = spans

        if cell.get("unavailable_reason"):
            unavailable_reasons[field] = str(cell["unavailable_reason"])

        value = cell.get("value")
        if value is None:
            continue
        if field == "facts":
            value = _normalise_facts(value)
        if field == "key_reasoning_quotes":
            value = _normalise_quotes(value, spans)
        normalised[field] = value

    if field_provenance:
        existing = normalised.get("_field_provenance", {})
        if isinstance(existing, Mapping):
            merged = {**existing, **field_provenance}
        else:
            merged = field_provenance
        normalised["_field_provenance"] = merged
    if unavailable_reasons:
        normalised["_unavailable_reasons"] = unavailable_reasons
    return normalised


async def _run_labeler(
    *,
    client: BaseLLMClient,
    spec: LabelerModelSpec,
    rendered_prompt: str,
) -> LabelerOutput:
    raw = await client.generate(
        messages=[{"role": "user", "content": rendered_prompt}],
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        max_tokens=LABELER_MAX_TOKENS,
        temperature=0.0,
    )
    partial = _safe_json_loads(raw)
    return LabelerOutput(
        spec=spec,
        rendered_prompt=rendered_prompt,
        raw_response=raw,
        partial_case=partial,
    )


# ---------------------------------------------------------------------------
# run_one_case
# ---------------------------------------------------------------------------


async def run_one_case(
    *,
    case_id: str,
    pdf_triples: list[Mapping[str, Any]],
    page_text: dict[int, str],
    page_sections: dict[tuple[int, int], str],
    source_pdf_sha256: str,
    ocr_text_sha256: str,
    run: LabelingRun,
    clients_by_spec: Mapping[str, BaseLLMClient],
    lookups: GroundingDeps,
) -> CasePass:
    """Dispatch both labelers in parallel, ground each output, return ``CasePass``.

    ``clients_by_spec`` keys MUST be ``f"{spec.provider}:{spec.model}"``
    for both A and B. Distinct providers + distinct keys is what enforces
    A/B independence at runtime — the labeler factory builds these
    upstream.
    """
    rendered = render_extraction_prompt(
        case_id=case_id,
        allowed_fields=_EXTRACTION_ALLOWED_FIELDS,
        pdf_triples=pdf_triples,
    )

    def _key(spec: LabelerModelSpec) -> str:
        return f"{spec.provider}:{spec.model}"

    client_a = clients_by_spec[_key(run.labeler_a_spec)]
    client_b = clients_by_spec[_key(run.labeler_b_spec)]

    output_a, output_b = await asyncio.gather(
        _run_labeler(client=client_a, spec=run.labeler_a_spec, rendered_prompt=rendered),
        _run_labeler(client=client_b, spec=run.labeler_b_spec, rendered_prompt=rendered),
    )

    grounding_a = ground(
        output_a.partial_case,
        page_text=page_text,
        page_sections=page_sections,
        spans=[],
        lookups=lookups,
    )
    grounding_b = ground(
        output_b.partial_case,
        page_text=page_text,
        page_sections=page_sections,
        spans=[],
        lookups=lookups,
    )

    return CasePass(
        case_id=case_id,
        run_id=run.run_id,
        labeler_a=output_a,
        labeler_b=output_b,
        grounding_a=grounding_a,
        grounding_b=grounding_b,
        source_pdf_sha256=source_pdf_sha256,
        ocr_text_sha256=ocr_text_sha256,
        prompt_template_hash=prompt_template_hash(),
    )


# ---------------------------------------------------------------------------
# Artifact writer
# ---------------------------------------------------------------------------


def _spec_to_dict(spec: LabelerModelSpec) -> dict[str, Any]:
    return spec.model_dump(mode="json")


def _grounding_to_dict(g: GroundingResult) -> dict[str, Any]:
    return {
        "field_path": dict(g.field_path),
        "reasons": dict(g.reasons),
        "match_strategy": dict(getattr(g, "match_strategy", {}) or {}),
        "grounding_pass_rate": g.grounding_pass_rate,
    }


def _output_to_dict(o: LabelerOutput) -> dict[str, Any]:
    return {
        "spec": _spec_to_dict(o.spec),
        "rendered_prompt": o.rendered_prompt,
        "raw_response": o.raw_response,
        "partial_case": o.partial_case,
    }


def write_artifact(case_pass: CasePass, *, run: LabelingRun) -> Path:
    """Write the per-case JSON artifact and return its path.

    Mirrors the ``data/eval_artifacts/labeling/<run_id>/<case_id>.json``
    layout from sparring §7. The artifact is the source of truth for
    replay; the JSONL row only carries a summary in
    ``LabelingProvenance``.
    """
    run.run_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = run.run_dir / f"{case_pass.case_id}.json"

    payload: dict[str, Any] = {
        "case_id": case_pass.case_id,
        "run_id": case_pass.run_id,
        "ran_at": case_pass.ran_at.isoformat(),
        "source_pdf_sha256": case_pass.source_pdf_sha256,
        "ocr_text_sha256": case_pass.ocr_text_sha256,
        "domain_id": run.domain_id,
        "prompt_template_hash": case_pass.prompt_template_hash,
        "prompt_pack_version": PROMPT_PACK_VERSION,
        "canonicalizer_version": CANONICALIZER_VERSION,
        "grounder_version": GROUNDER_VERSION,
        "runner_version": RUNNER_VERSION,
        "gold_schema_hash": run.gold_schema_hash,
        "corpus_manifest_hash": run.corpus_manifest_hash,
        "labeler_a": _output_to_dict(case_pass.labeler_a),
        "labeler_b": _output_to_dict(case_pass.labeler_b),
        "grounding_a": _grounding_to_dict(case_pass.grounding_a),
        "grounding_b": _grounding_to_dict(case_pass.grounding_b),
    }
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    case_pass.artifact_path = artifact_path
    return artifact_path


# ---------------------------------------------------------------------------
# Hash helpers (used by CLI to compute source hashes)
# ---------------------------------------------------------------------------


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "RUNNER_VERSION",
    "LABELER_MAX_TOKENS",
    "CasePass",
    "LabelerOutput",
    "LabelingRun",
    "_EXTRACTION_ALLOWED_FIELDS",
    "run_one_case",
    "sha256_hex",
    "write_artifact",
]
