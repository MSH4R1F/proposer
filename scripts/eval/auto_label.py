#!/usr/bin/env python
"""Phase 10 — pre-adjudication labeling CLI.

Usage::

    python -m scripts.eval.auto_label \\
        --case-id FTT-2023-0001 \\
        --pdf data/raw/bailii/FTT-2023-0001.txt \\
        --domain-id housing.deposit.v1 \\
        --run-id run-2026-05-03-001 \\
        --labeler-a anthropic:claude-sonnet-4-20250514 \\
        --labeler-b openai:gpt-5.5

The CLI:

1. Loads the post-OCR text plus its page/paragraph/section-tag triples
   (``--pdf`` may either be a JSON file with ``{pages, sections, triples,
   text}`` keys, OR a plain text file in which case a single-page,
   single-section, no-grounding skeleton is built — the latter is
   primarily for test fixtures).
2. Builds two ``BaseLLMClient`` instances via
   ``llm_orchestrator.clients.labeler_factory.build_labeler_client``
   (overridden by an injected factory in tests).
3. Runs ``packages.eval.auto_label.runner.run_one_case`` to dispatch
   both labelers in parallel, ground each output, and write a per-case
   artifact under ``data/eval_artifacts/labeling/<run_id>/``.
4. Refuses to touch ``data/gold_standard/*.jsonl`` directly. Promotion to
   the gold corpus happens only via ``scripts/eval/adjudicate.py``.

The CLI is offline by default for fixture-driven tests: pass
``--offline`` plus ``--canned-a`` / ``--canned-b`` JSON paths and the
runner will use a stub client that returns those JSON files verbatim
instead of calling a real provider.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# Path bootstrap so this script runs as a top-level executable (mirrors
# scripts/eval/annotate.py).
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval.auto_label.grounder import GroundingDeps  # noqa: E402
from eval.auto_label.lookups.authorities import InMemoryAuthorityLookup  # noqa: E402
from eval.auto_label.lookups.statutes import InMemoryStatuteLookup  # noqa: E402
from eval.auto_label.runner import (  # noqa: E402
    LabelingRun,
    run_one_case,
    write_artifact,
)
from llm_orchestrator.clients.base import BaseLLMClient  # noqa: E402
from llm_orchestrator.clients.labeler_factory import (  # noqa: E402
    LabelerModelSpec,
    build_labeler_client,
)


# Hard refuse: this CLI never writes to the gold corpus.
_GOLD_DIR_NAME = "gold_standard"


# ---------------------------------------------------------------------------
# Source-text loading
# ---------------------------------------------------------------------------


@dataclass
class SourceBundle:
    """Everything the runner needs about one PDF/text source."""

    pdf_triples: list[Mapping[str, Any]]
    page_text: dict[int, str]
    page_sections: dict[tuple[int, int], str]
    source_pdf_sha256: str
    ocr_text_sha256: str


def _load_source(path: Path) -> SourceBundle:
    """Load a source PDF/text file into a ``SourceBundle``.

    Two accepted layouts:

    1. JSON with keys ``triples``, ``page_text``, ``page_sections``,
       ``source_pdf_sha256``, ``ocr_text_sha256``. Used when an OCR /
       unitization stage has already produced structured spans.
    2. Plain text file. Treated as one page, one paragraph, one
       ``pre_decision_record`` section. SHA-256 of the bytes becomes the
       PDF hash; SHA-256 of the canonicalised text becomes the OCR hash.
       Useful for tests and for ad-hoc dry-runs.
    """
    raw_bytes = path.read_bytes()
    pdf_sha = hashlib.sha256(raw_bytes).hexdigest()

    if path.suffix.lower() == ".json":
        body = json.loads(raw_bytes.decode("utf-8"))
        # ``page_sections`` JSON keys are "page,paragraph"; convert to tuples.
        sections_raw = body.get("page_sections", {})
        sections: dict[tuple[int, int], str] = {}
        for k, v in sections_raw.items():
            if isinstance(k, str) and "," in k:
                p_str, par_str = k.split(",", 1)
                sections[(int(p_str), int(par_str))] = v
        page_text_raw = body.get("page_text", {})
        page_text = {int(k): v for k, v in page_text_raw.items()}
        return SourceBundle(
            pdf_triples=list(body.get("triples", [])),
            page_text=page_text,
            page_sections=sections,
            source_pdf_sha256=body.get("source_pdf_sha256") or pdf_sha,
            ocr_text_sha256=body.get("ocr_text_sha256")
            or hashlib.sha256(json.dumps(page_text, sort_keys=True).encode()).hexdigest(),
        )

    text = raw_bytes.decode("utf-8")
    triples = [
        {
            "page": 1,
            "paragraph": 1,
            "section_tag": "pre_decision_record",
            "char_start": 0,
            "char_end": len(text),
            "text": text,
        }
    ]
    return SourceBundle(
        pdf_triples=triples,
        page_text={1: text},
        page_sections={(1, 1): "pre_decision_record"},
        source_pdf_sha256=pdf_sha,
        ocr_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def _parse_spec(s: str) -> LabelerModelSpec:
    if ":" not in s:
        raise SystemExit(
            f"--labeler-* must be of the form provider:model (got {s!r})"
        )
    provider, model = s.split(":", 1)
    return LabelerModelSpec(provider=provider, model=model)


# ---------------------------------------------------------------------------
# Stub client for offline / test runs
# ---------------------------------------------------------------------------


class _OfflineStubClient(BaseLLMClient):
    """Minimal BaseLLMClient that returns a canned JSON string."""

    def __init__(self, canned: dict[str, Any]):
        self._canned = canned

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        return json.dumps(self._canned)

    async def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("offline stub does not support generate_structured")

    def get_stats(self) -> dict[str, Any]:
        return {"offline": True}

    def reset_stats(self) -> None:
        return None


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


ClientFactory = Any  # callable: (LabelerModelSpec) -> BaseLLMClient


def _default_factory() -> ClientFactory:
    api_keys = {
        provider: key
        for provider, key in (
            ("anthropic", os.environ.get("ANTHROPIC_API_KEY")),
            ("openai", os.environ.get("OPENAI_API_KEY")),
        )
        if key
    }

    def _build(spec: LabelerModelSpec) -> BaseLLMClient:
        return build_labeler_client(spec, api_keys=api_keys)

    return _build


def _spec_key(spec: LabelerModelSpec) -> str:
    return f"{spec.provider}:{spec.model}"


def _build_offline_factory(
    *,
    spec_a: LabelerModelSpec,
    canned_a_path: Path,
    spec_b: LabelerModelSpec,
    canned_b_path: Path,
) -> ClientFactory:
    canned_a = json.loads(canned_a_path.read_text())
    canned_b = json.loads(canned_b_path.read_text())
    canned_by_spec = {
        _spec_key(spec_a): canned_a,
        _spec_key(spec_b): canned_b,
    }

    def _build(spec: LabelerModelSpec) -> BaseLLMClient:
        return _OfflineStubClient(canned_by_spec[_spec_key(spec)])

    return _build


def _refuse_gold_path(path: Path) -> None:
    if any(part == _GOLD_DIR_NAME for part in path.resolve().parts):
        raise SystemExit(
            f"Refusing to use {path}: auto_label.py never writes to "
            f"data/gold_standard/. Promotion happens via scripts/eval/adjudicate.py."
        )


def _run(args: argparse.Namespace, *, client_factory: Optional[ClientFactory] = None) -> int:
    pdf_path = Path(args.pdf).resolve()
    artifacts_root = Path(args.artifacts_root).resolve()
    _refuse_gold_path(artifacts_root)

    source = _load_source(pdf_path)

    spec_a = _parse_spec(args.labeler_a)
    spec_b = _parse_spec(args.labeler_b)
    if spec_a.provider == spec_b.provider:
        raise SystemExit(
            f"Refusing run: --labeler-a and --labeler-b must use different "
            f"providers (got both {spec_a.provider!r}). Provider independence "
            f"is enforced by Codex finding [4]."
        )

    factory = client_factory or (
        _build_offline_factory(
            spec_a=spec_a,
            canned_a_path=Path(args.canned_a),
            spec_b=spec_b,
            canned_b_path=Path(args.canned_b),
        )
        if args.offline
        else _default_factory()
    )

    run = LabelingRun(
        run_id=args.run_id,
        labeler_a_spec=spec_a,
        labeler_b_spec=spec_b,
        artifacts_root=artifacts_root,
        gold_schema_hash=args.gold_schema_hash,
        corpus_manifest_hash=args.corpus_manifest_hash,
        domain_id=args.domain_id,
    )

    clients = {
        _spec_key(spec_a): factory(spec_a),
        _spec_key(spec_b): factory(spec_b),
    }

    deps = GroundingDeps(
        authority_lookup=InMemoryAuthorityLookup(),
        statute_lookup=InMemoryStatuteLookup(),
        run_artifact_path=artifacts_root / args.run_id / f"{args.case_id}.json",
    )

    case_pass = asyncio.run(
        run_one_case(
            case_id=args.case_id,
            pdf_triples=list(source.pdf_triples),
            page_text=source.page_text,
            page_sections=source.page_sections,
            source_pdf_sha256=source.source_pdf_sha256,
            ocr_text_sha256=source.ocr_text_sha256,
            run=run,
            clients_by_spec=clients,
            lookups=deps,
        )
    )
    artifact = write_artifact(case_pass, run=run)
    print(f"Wrote {artifact}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto_label.py",
        description="Pre-adjudication LLM labeling for one case (Phase 10).",
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--pdf", required=True, help="Path to source text or .json bundle")
    parser.add_argument(
        "--domain-id",
        required=True,
        help="Routing domain id (recorded in the artifact for downstream gates)",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--labeler-a", required=True, help="provider:model")
    parser.add_argument("--labeler-b", required=True, help="provider:model")
    parser.add_argument(
        "--artifacts-root",
        default="data/eval_artifacts/labeling",
        help="Where per-case artifacts are written. NEVER points at data/gold_standard/.",
    )
    parser.add_argument("--gold-schema-hash", default="UNSET")
    parser.add_argument("--corpus-manifest-hash", default="UNSET")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use canned labeler outputs instead of calling real providers.",
    )
    parser.add_argument("--canned-a", default=None, help="JSON file for offline labeler A.")
    parser.add_argument("--canned-b", default=None, help="JSON file for offline labeler B.")
    return parser


def _cli_main(
    argv: Optional[Sequence[str]] = None,
    *,
    client_factory: Optional[ClientFactory] = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.offline and (args.canned_a is None or args.canned_b is None):
        parser.error("--offline requires --canned-a AND --canned-b paths")
    return _run(args, client_factory=client_factory)


if __name__ == "__main__":
    raise SystemExit(_cli_main())
