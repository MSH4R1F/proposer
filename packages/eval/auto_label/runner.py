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
    return parsed if isinstance(parsed, dict) else {}


async def _run_labeler(
    *,
    client: BaseLLMClient,
    spec: LabelerModelSpec,
    rendered_prompt: str,
) -> LabelerOutput:
    raw = await client.generate(
        messages=[{"role": "user", "content": rendered_prompt}],
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        max_tokens=4096,
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
    "CasePass",
    "LabelerOutput",
    "LabelingRun",
    "_EXTRACTION_ALLOWED_FIELDS",
    "run_one_case",
    "sha256_hex",
    "write_artifact",
]
