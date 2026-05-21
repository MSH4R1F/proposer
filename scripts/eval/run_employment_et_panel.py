#!/usr/bin/env python3
"""SHA-148 Phase C live run — dual-LLM extraction panel for the ET gold set.

Standalone, research-mode runner. Intentionally does NOT depend on
``packages/eval/auto_label/runner.py`` (which hardcodes the housing
prompt pack); instead it:

1. Reads the SHA-148 Phase A selection manifest.
2. For each of the 50 cases, loads the redacted PDF text and applies a
   heuristic section-tag chunker (PyMuPDF flattens most ET PDFs into a
   single paragraph block, so the runner accepts that and tags chunks
   coarsely as case_header / tribunal_reasoning / judgment).
3. Renders the ET prompt pack v1.1.0 with that chunked input.
4. Sends the same rendered prompt to two cross-provider LLM clients
   (one Anthropic + one OpenAI per the labeler-factory's
   provider-independence guard).
5. Parses each labeler's JSON response and writes a per-case artifact
   under ``data/eval_artifacts/labeling/<run_id>/<case_id>.json``
   containing raw responses, parsed partial-GoldCase dicts, prompt
   template hash, and per-labeler stats. Grounding is deliberately
   skipped because the section-tag chunking is heuristic.

The artifacts are the input to ``promote_employment_et_gold.py``.

This runner is honest about its limits:

- "research-mode" provenance label persisted on every artifact.
- No grounder pass.
- Section tags are coarse, not span-accurate.

Cost: 50 cases × 2 LLMs ≈ £2-5 depending on token counts.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from eval.auto_label.prompts.extraction_employment_et_unfair_dismissal import (  # noqa: E402
    EXTRACTION_ALLOWED_FIELDS,
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_PACK_VERSION,
    prompt_template_hash,
    render_extraction_prompt,
)
from llm_orchestrator.clients.base import BaseLLMClient  # noqa: E402
from llm_orchestrator.clients.labeler_factory import (  # noqa: E402
    LabelerModelSpec,
    build_labeler_client,
)

logger = logging.getLogger("sha148.panel")

# Default labeler pair — cross-provider per the factory's invariant.
DEFAULT_LABELER_A = "anthropic:claude-sonnet-4-6"
DEFAULT_LABELER_B = "openai:gpt-5.5"

DECISIONS_ROOT = REPO_ROOT / "data" / "raw" / "employment" / "decisions"


# ---------------------------------------------------------------------------
# Section-tag heuristic
# ---------------------------------------------------------------------------


# Heuristic chunk size in characters. PyMuPDF often returns one huge
# paragraph block per PDF; this chops it into windows that the prompt's
# (page, paragraph, char_start, char_end, text) tuple shape can carry.
CHUNK_CHARS = 1500


def _section_tag_for(idx: int, total: int) -> str:
    """Coarse section-tag heuristic.

    Real ET reserved judgments follow roughly:
    [header / parties] -> [facts] -> [issues] -> [evidence] ->
    [submissions] -> [tribunal_reasoning] -> [judgment / order].

    Without a real PDF segmenter the runner can't pick boundaries by
    heading text, so this maps chunk index by fraction of document:

    - chunk[0] (first chunk)         : "case_header"
    - chunks in first third          : "facts"
    - chunks in middle third         : "tribunal_reasoning"
    - chunks in last third           : "judgment"

    The prompt allows ``key_reasoning_quotes`` and outcome fields to be
    grounded in any of those sections, so this coarse labelling is
    sufficient for the v1 panel run. Phase D human review can correct
    individual rows.
    """
    if total == 0:
        return "case_header"
    if idx == 0:
        return "case_header"
    frac = idx / total
    if frac < 0.33:
        return "facts"
    if frac < 0.67:
        return "tribunal_reasoning"
    return "judgment"


def _chunk_text(text: str) -> list[dict[str, Any]]:
    """Convert a flat PDF text blob into pseudo-triples.

    Each triple is one chunk of ~CHUNK_CHARS characters. Page is fixed at
    1 (PyMuPDF doesn't preserve page breaks reliably across landing-
    page + PDF documents). Paragraph index increments per chunk.
    """
    text = text or ""
    if not text.strip():
        return []
    chunks: list[dict[str, Any]] = []
    cursor = 0
    paragraph = 0
    while cursor < len(text):
        # Prefer breaking on a paragraph or sentence boundary if one is
        # within ~200 chars of the chunk-size target.
        end = min(cursor + CHUNK_CHARS, len(text))
        if end < len(text):
            for sep in ("\n\n", "\n", ". "):
                cut = text.rfind(sep, cursor + CHUNK_CHARS - 200, end)
                if cut > cursor:
                    end = cut + len(sep)
                    break
        slice_text = text[cursor:end].strip()
        if slice_text:
            chunks.append(
                {
                    "page": 1,
                    "paragraph": paragraph + 1,
                    "section_tag": "",  # filled below once we know total
                    "char_start": cursor,
                    "char_end": end,
                    "text": slice_text,
                }
            )
            paragraph += 1
        cursor = end
    total = len(chunks)
    for i, ch in enumerate(chunks):
        ch["section_tag"] = _section_tag_for(i, total)
    return chunks


# ---------------------------------------------------------------------------
# Run sheet + per-case execution
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    case_id: str
    case_reference: str
    n_chunks: int
    labeler_a_ok: bool
    labeler_b_ok: bool
    labeler_a_raw_chars: int = 0
    labeler_b_raw_chars: int = 0
    labeler_a_error: str | None = None
    labeler_b_error: str | None = None


def _new_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}-emp-et"


def _content_sha256(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _read_redacted_text(case_ref: str) -> tuple[str, str]:
    """Return ``(redacted_text, pdf_sha256)`` for a case_ref.

    case_ref maps to ``data/raw/employment/decisions/<case_ref>/`` where
    ``pdf_text_redacted.txt`` is the model-facing text and
    ``pdf_metadata.json`` carries the SHA-256 of the source PDF.
    """
    safe = case_ref.replace("/", "_").replace(" ", "_")
    case_dir = DECISIONS_ROOT / safe
    text_path = case_dir / "pdf_text_redacted.txt"
    meta_path = case_dir / "pdf_metadata.json"
    if not text_path.exists():
        raise FileNotFoundError(f"redacted text not found for {case_ref}: {text_path}")
    text = text_path.read_text(encoding="utf-8")
    pdf_sha = ""
    if meta_path.exists():
        try:
            pdf_sha = json.loads(meta_path.read_text(encoding="utf-8")).get("pdf_sha256", "")
        except Exception:
            pdf_sha = ""
    return text, pdf_sha


async def _call_labeler(
    client: BaseLLMClient,
    spec: LabelerModelSpec,
    rendered_prompt: str,
) -> tuple[str, dict[str, Any] | None]:
    """Send the rendered prompt to one labeler. Returns ``(raw_text, parsed_or_None)``.

    Parsing tolerates markdown fences a model might emit even when told
    not to (per ``_safe_json_loads`` in the housing runner).
    """
    raw = await client.generate(
        messages=[{"role": "user", "content": rendered_prompt}],
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        max_tokens=8192,
        temperature=0.0,
    )
    parsed = _safe_json_loads(raw)
    return raw, parsed


def _safe_json_loads(raw: str) -> dict[str, Any] | None:
    """Parse a labeler's response; tolerate markdown fences."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


async def _process_case(
    row: dict[str, Any],
    client_a: BaseLLMClient,
    spec_a: LabelerModelSpec,
    client_b: BaseLLMClient,
    spec_b: LabelerModelSpec,
    run_dir: Path,
    run_id: str,
) -> CaseResult:
    case_ref = row["case_reference"]
    case_id = case_ref  # one-to-one for the ET corpus

    try:
        redacted_text, pdf_sha = _read_redacted_text(case_ref)
    except FileNotFoundError as e:
        return CaseResult(
            case_id=case_id,
            case_reference=case_ref,
            n_chunks=0,
            labeler_a_ok=False,
            labeler_b_ok=False,
            labeler_a_error=str(e),
            labeler_b_error=str(e),
        )

    triples = _chunk_text(redacted_text)
    if not triples:
        return CaseResult(
            case_id=case_id,
            case_reference=case_ref,
            n_chunks=0,
            labeler_a_ok=False,
            labeler_b_ok=False,
            labeler_a_error="empty PDF text",
            labeler_b_error="empty PDF text",
        )

    rendered = render_extraction_prompt(
        case_id=case_id,
        allowed_fields=EXTRACTION_ALLOWED_FIELDS,
        pdf_triples=triples,
    )

    # Dispatch both labelers in parallel.
    results = await asyncio.gather(
        _call_labeler(client_a, spec_a, rendered),
        _call_labeler(client_b, spec_b, rendered),
        return_exceptions=True,
    )

    def _unpack(r) -> tuple[str, dict[str, Any] | None, str | None]:
        if isinstance(r, Exception):
            return "", None, repr(r)
        raw, parsed = r
        return raw, parsed, None

    raw_a, parsed_a, err_a = _unpack(results[0])
    raw_b, parsed_b, err_b = _unpack(results[1])

    # Persist per-case artifact.
    artifact = {
        "schema_version": "employment_et_panel_artifact_v1",
        "run_id": run_id,
        "case_id": case_id,
        "case_reference": case_ref,
        "domain_id": row.get("domain_id"),
        "compat_domain_id": row.get("compat_domain_id"),
        "decision_date": row.get("decision_date"),
        "country": row.get("country"),
        "case_numbers": row.get("case_numbers"),
        "jurisdiction_codes": row.get("jurisdiction_codes"),
        "source_url": row.get("source_url"),
        "first_attachment": row.get("first_attachment"),
        "pdf_sha256": pdf_sha,
        "ocr_text_sha256": _content_sha256(redacted_text),
        "prompt_pack_version": PROMPT_PACK_VERSION,
        "prompt_template_hash": prompt_template_hash(),
        "rendered_prompt": rendered,
        "n_chunks": len(triples),
        "section_tag_counts": _section_tag_distribution(triples),
        "labeler_a": {
            "spec": spec_a.model_dump(mode="json"),
            "raw_response": raw_a,
            "parsed": parsed_a,
            "error": err_a,
        },
        "labeler_b": {
            "spec": spec_b.model_dump(mode="json"),
            "raw_response": raw_b,
            "parsed": parsed_b,
            "error": err_b,
        },
        "labeled_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact_path = run_dir / f"{_safe_case_id(case_id)}.json"
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    return CaseResult(
        case_id=case_id,
        case_reference=case_ref,
        n_chunks=len(triples),
        labeler_a_ok=err_a is None and parsed_a is not None,
        labeler_b_ok=err_b is None and parsed_b is not None,
        labeler_a_raw_chars=len(raw_a or ""),
        labeler_b_raw_chars=len(raw_b or ""),
        labeler_a_error=err_a,
        labeler_b_error=err_b,
    )


def _section_tag_distribution(triples: list[dict[str, Any]]) -> dict[str, int]:
    from collections import Counter

    return dict(Counter(t["section_tag"] for t in triples))


def _safe_case_id(case_id: str) -> str:
    return case_id.replace("/", "_").replace(" ", "_")[:120]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> int:
    manifest_path = Path(args.selection_manifest).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path
    if not manifest_path.exists():
        raise SystemExit(f"selection manifest not found: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if args.limit > 0:
        rows = rows[: args.limit]

    spec_a = _parse_labeler(args.labeler_a)
    spec_b = _parse_labeler(args.labeler_b)
    if spec_a.provider == spec_b.provider and not args.allow_same_provider:
        raise SystemExit(
            "Provider-independence guard: labeler_a and labeler_b must use different providers. "
            "Pass --allow-same-provider to bypass for research-mode runs (e.g. credits exhausted "
            "for the other provider). The IAA signal is correspondingly weaker."
        )
    if spec_a.provider == spec_b.provider:
        logger.warning(
            "Running with same-provider labelers (%s + %s); IAA signal is correlated and "
            "weaker than a cross-provider run. Provenance records this as research-mode.",
            f"{spec_a.provider}:{spec_a.model}",
            f"{spec_b.provider}:{spec_b.model}",
        )

    api_keys = {
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "openai": os.getenv("OPENAI_API_KEY", ""),
    }
    for needed in (spec_a.provider, spec_b.provider):
        if not api_keys.get(needed):
            raise SystemExit(
                f"missing API key env var for provider {needed!r}"
            )

    client_a = build_labeler_client(spec_a, api_keys=api_keys)
    client_b = build_labeler_client(spec_b, api_keys=api_keys)

    run_id = args.run_id or _new_run_id()
    run_dir = (REPO_ROOT / "data" / "eval_artifacts" / "labeling" / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc)
    logger.info(
        "run_start n_cases=%d run_id=%s labeler_a=%s labeler_b=%s",
        len(rows),
        run_id,
        f"{spec_a.provider}:{spec_a.model}",
        f"{spec_b.provider}:{spec_b.model}",
    )

    # Concurrency: 4 cases in flight at once (per-provider rate limits
    # are usually generous enough). Keeping it modest reduces noisy
    # neighbour effects on the eval harness.
    sem = asyncio.Semaphore(args.concurrency)
    results: list[CaseResult] = []

    async def _wrapped(row: dict[str, Any]) -> CaseResult:
        async with sem:
            r = await _process_case(row, client_a, spec_a, client_b, spec_b, run_dir, run_id)
            status = "OK" if r.labeler_a_ok and r.labeler_b_ok else "PARTIAL"
            logger.info(
                "case %s -> %s a_chars=%d b_chars=%d chunks=%d errs=%s/%s",
                r.case_reference[:60],
                status,
                r.labeler_a_raw_chars,
                r.labeler_b_raw_chars,
                r.n_chunks,
                r.labeler_a_error,
                r.labeler_b_error,
            )
            return r

    results = await asyncio.gather(*[_wrapped(row) for row in rows])
    finished = datetime.now(timezone.utc)

    # Summary
    summary = {
        "run_id": run_id,
        "selection_manifest": str(manifest_path),
        "run_dir": str(run_dir),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "labeler_a": spec_a.model_dump(mode="json"),
        "labeler_b": spec_b.model_dump(mode="json"),
        "prompt_pack_version": PROMPT_PACK_VERSION,
        "prompt_template_hash": prompt_template_hash(),
        "n_cases": len(results),
        "n_both_ok": sum(1 for r in results if r.labeler_a_ok and r.labeler_b_ok),
        "n_partial": sum(1 for r in results if (r.labeler_a_ok or r.labeler_b_ok) and not (r.labeler_a_ok and r.labeler_b_ok)),
        "n_both_failed": sum(1 for r in results if not r.labeler_a_ok and not r.labeler_b_ok),
        "stats_a": client_a.get_stats() if hasattr(client_a, "get_stats") else {},
        "stats_b": client_b.get_stats() if hasattr(client_b, "get_stats") else {},
    }
    summary_path = run_dir / "_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _parse_labeler(s: str) -> LabelerModelSpec:
    if ":" not in s:
        raise SystemExit(f"--labeler-* must be 'provider:model', got {s!r}")
    provider, model = s.split(":", 1)
    return LabelerModelSpec(provider=provider, model=model)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SHA-148 Phase C live runner: dual-LLM panel over ET PDFs."
    )
    p.add_argument(
        "--selection-manifest",
        default="data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/selection_manifest.jsonl",
    )
    p.add_argument("--labeler-a", default=DEFAULT_LABELER_A)
    p.add_argument("--labeler-b", default=DEFAULT_LABELER_B)
    p.add_argument("--run-id", default=None, help="Run ID; auto-generated if omitted.")
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="If > 0, only process the first N rows (smoke testing).",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="In-flight cases at once.",
    )
    p.add_argument(
        "--allow-same-provider",
        action="store_true",
        help=(
            "Bypass the cross-provider invariant. Use only when one provider's "
            "credits are exhausted; the resulting IAA signal is correlated and "
            "should be flagged in downstream reports."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(run(_parser().parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
