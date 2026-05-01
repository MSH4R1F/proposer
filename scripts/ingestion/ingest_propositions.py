"""Proposition KG ingestion CLI (SHA-36 Task 9).

Walks a corpus manifest produced by ``scripts.ingestion.select_proposition_corpus``
and runs the full extraction pipeline for each case:

  load text -> extract propositions -> extract edges -> validate graph
  -> persist (document, run, propositions, edges) in Postgres.

Two modes:

* ``--dry-run`` exercises the LLM extractors but does NOT touch the database.
* ``--commit`` runs the full pipeline and writes rows.

See the SHA-36 plan and ``scripts/ingestion/tests/test_ingest_propositions.py``
for the contract.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional, Tuple


# ---------------------------------------------------------------------------
# Path setup so this module works under ``python -m`` from the repo root.
# Mirrors scripts/ingestion/select_proposition_corpus.py.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "packages"))

# These imports MUST come after sys.path manipulation above.
from kg_builder.propositions import (  # noqa: E402
    DecisionDocument,
    ExtractionRunStatus,
    PropositionExtractionRun,
    deterministic_document_id,
    sha256_hex,
)
from kg_builder.propositions.text_loader import (  # noqa: E402
    DecisionTextExtractionError,
    LoadedDecisionText,
    load_decision_text,
)
from kg_builder.propositions.extractor import (  # noqa: E402
    LLMPropositionExtractor,
    PropositionExtractionResponse,
)
from kg_builder.propositions.edge_extractor import (  # noqa: E402
    EdgeExtractionResponse,
    LLMPropositionEdgeExtractor,
)
from kg_builder.propositions.graph_validator import validate_graph  # noqa: E402
from kg_builder.propositions.prompts import (  # noqa: E402
    EDGE_EXTRACTION_PROMPT_VERSION,
    EDGE_EXTRACTION_SYSTEM_PROMPT,
    PROPOSITION_EXTRACTION_PROMPT_VERSION,
    PROPOSITION_EXTRACTION_SYSTEM_PROMPT,
)


log = logging.getLogger("ingest_propositions")


_DEFAULT_MODEL = "claude-haiku-4-5"  # matches ClaudeClient default
_EXTRACTOR_VERSION = (
    f"prop-{PROPOSITION_EXTRACTION_PROMPT_VERSION}"
    f"+edge-{EDGE_EXTRACTION_PROMPT_VERSION}"
)


# ---------------------------------------------------------------------------
# Mock LLM (for --mock-response)
# ---------------------------------------------------------------------------


class _MockLLM:
    """In-process LLM stub.

    Returns the ``propositions_response`` payload for every
    ``PropositionExtractionResponse`` call and the ``edges_response``
    payload for every ``EdgeExtractionResponse`` call.

    Mirrors ``ClaudeClient.generate_structured`` enough that the
    extractors don't notice. Also exposes a ``_stats`` dict so the
    ingestion driver can read tokens (always zero for the mock).
    """

    def __init__(self, fixture: dict) -> None:
        if "propositions_response" not in fixture:
            raise ValueError("mock fixture missing 'propositions_response'")
        if "edges_response" not in fixture:
            raise ValueError("mock fixture missing 'edges_response'")
        self.fixture = fixture
        self.call_count = 0
        self._stats = {"tokens_in": 0, "tokens_out": 0}

    async def generate_structured(
        self,
        *,
        messages,  # noqa: ANN001 — duck-typed
        system_prompt,  # noqa: ANN001
        response_model,  # noqa: ANN001
        max_tokens,  # noqa: ANN001
    ):
        self.call_count += 1
        if response_model is PropositionExtractionResponse:
            return PropositionExtractionResponse(
                **self.fixture["propositions_response"]
            )
        if response_model is EdgeExtractionResponse:
            return EdgeExtractionResponse(**self.fixture["edges_response"])
        raise ValueError(f"Mock has no response for {response_model!r}")


def _load_mock_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_llm(args: argparse.Namespace):
    """Build the LLM client based on CLI args.

    --mock-response → in-process stub.
    Otherwise → real ClaudeClient (requires ANTHROPIC_API_KEY).
    """
    if args.mock_response is not None:
        fixture = _load_mock_fixture(Path(args.mock_response))
        return _MockLLM(fixture)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is required (or use --mock-response with --dry-run)"
        )
    # Imported lazily so --dry-run --mock-response doesn't pull in
    # `anthropic` (and isn't blocked by an unset key during import).
    from llm_orchestrator.clients.claude_client import ClaudeClient

    model = args.model or _DEFAULT_MODEL
    return ClaudeClient(api_key=api_key, model=model)


# ---------------------------------------------------------------------------
# Manifest + document construction
# ---------------------------------------------------------------------------


def _select_source_path(case: dict) -> Optional[Path]:
    """Pick the file to load: prefer pdf_path, fall back to html_path.

    Both fields may be absolute or repo-relative — resolve repo-relative
    against the worktree root.
    """
    for slot in ("pdf_path", "html_path"):
        raw = case.get(slot)
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = (_REPO_ROOT / p).resolve()
        if p.exists():
            return p
    return None


def _build_doc(
    case: dict,
    source_path: Path,
    loaded: LoadedDecisionText,
) -> DecisionDocument:
    """Construct a DecisionDocument domain object from a manifest entry +
    loaded text.

    content_sha256 hashes the raw file bytes; text_sha256 hashes the
    extracted full_text. The document_id is deterministic over
    (source_key, content_sha256) so re-ingestions of the same bytes from
    the same path produce the same id.
    """
    raw_bytes = source_path.read_bytes()
    content_sha = hashlib.sha256(raw_bytes).hexdigest()
    text_sha = sha256_hex(loaded.full_text)
    source_key = case.get("source_url") or str(source_path)
    document_id = deterministic_document_id(source_key, content_sha)

    decision_date = case.get("decision_date")
    # Pydantic accepts ISO date strings — but only if non-empty
    if decision_date == "" or decision_date is None:
        decision_date = None

    return DecisionDocument(
        document_id=document_id,
        case_reference=case["case_reference"],
        source_url=case.get("source_url"),
        local_path=str(source_path),
        year=case.get("year"),
        category=case.get("category"),
        case_type_code=case.get("case_type_code"),
        region_code=case.get("region_code"),
        decision_date=decision_date,
        content_sha256=content_sha,
        text_sha256=text_sha,
        char_count=len(loaded.full_text),
        page_count=loaded.page_count,
        extraction_method=loaded.extraction_method,
        metadata={k: v for k, v in (loaded.metadata or {}).items()},
    )


def _compute_prompt_sha(min_confidence: float) -> str:
    """SHA-256 of (prop prompt + edge prompt + str(min_confidence)).

    Any change to either prompt or to the threshold invalidates --resume,
    forcing a fresh extraction. This is intentional: the threshold
    affects which propositions get accepted, so a different threshold is
    a different pipeline.
    """
    blob = (
        PROPOSITION_EXTRACTION_SYSTEM_PROMPT
        + EDGE_EXTRACTION_SYSTEM_PROMPT
        + str(min_confidence)
    )
    return sha256_hex(blob)


# ---------------------------------------------------------------------------
# JSONL report
# ---------------------------------------------------------------------------


def _emit_jsonl(report_path: Optional[Path], record: dict) -> None:
    """Append one JSON line to the report file. No-op if path is None."""
    if report_path is None:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def _token_totals(llm) -> tuple[int, int]:  # noqa: ANN001 - duck-typed client
    """Return cumulative token totals exposed by the LLM client, if any."""
    stats = getattr(llm, "_stats", None)
    if not isinstance(stats, dict):
        return 0, 0
    return int(stats.get("tokens_in", 0) or 0), int(
        stats.get("tokens_out", 0) or 0
    )


# ---------------------------------------------------------------------------
# Per-document driver
# ---------------------------------------------------------------------------


async def _run_one_document(
    *,
    case: dict,
    args: argparse.Namespace,
    sessionmaker,  # async_sessionmaker | None (None for --dry-run)
    llm,
    prompt_sha: str,
    model: str,
) -> Tuple[str, dict]:
    """Process a single case end-to-end.

    Returns a tuple ``(status, metrics)`` where status is one of
    ``"succeeded" | "failed" | "skipped"`` and metrics is the JSONL
    record for the report.

    Never raises (unless ``--fail-fast`` is set, in which case the
    caller re-raises). All failures are caught and recorded.
    """
    case_ref = case.get("case_reference", "<unknown>")
    started = time.monotonic()

    metrics: dict = {
        "case_reference": case_ref,
        "document_id": None,
        "status": "failed",
        "proposition_count": 0,
        "proposition_rejected_count": 0,
        "edge_count": 0,
        "edge_rejected_count": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "error_message": None,
        "duration_seconds": 0.0,
    }

    # 1) Resolve and load source text. Failure here -> skip + continue.
    source_path = _select_source_path(case)
    if source_path is None:
        metrics["error_message"] = "no extractable file (pdf/html missing)"
        log.error("skip case=%s: %s", case_ref, metrics["error_message"])
        metrics["duration_seconds"] = round(time.monotonic() - started, 3)
        return "failed", metrics

    try:
        loaded = load_decision_text(source_path)
    except DecisionTextExtractionError as exc:
        metrics["error_message"] = f"DecisionTextExtractionError: {exc}"
        log.error("skip case=%s: %s", case_ref, exc)
        metrics["duration_seconds"] = round(time.monotonic() - started, 3)
        return "failed", metrics

    # 2) Build the domain DecisionDocument.
    try:
        doc = _build_doc(case, source_path, loaded)
    except Exception as exc:  # validation error
        metrics["error_message"] = f"document_build_error: {type(exc).__name__}"
        log.error("skip case=%s: doc build failed: %s", case_ref, exc)
        metrics["duration_seconds"] = round(time.monotonic() - started, 3)
        return "failed", metrics

    metrics["document_id"] = str(doc.document_id)
    log.info(
        "loaded case=%s doc_id=%s chars=%d method=%s",
        case_ref,
        doc.document_id,
        doc.char_count,
        doc.extraction_method,
    )

    # 3) Persist document (commit mode only). Then handle --resume.
    if args.commit:
        # Step (a): upsert document in its own committed UoW.
        from apps.api.src.db.uow import UnitOfWork

        async with UnitOfWork(sessionmaker) as uow:
            await uow.propositions.upsert_document(doc)

        # --resume: bail before creating a new run row when one already exists.
        if args.resume and not args.force:
            async with UnitOfWork(sessionmaker) as uow:
                existing = await uow.propositions.find_succeeded_run(
                    document_id=doc.document_id,
                    extractor_version=_EXTRACTOR_VERSION,
                    prompt_sha256=prompt_sha,
                    model=model,
                )
            if existing is not None:
                log.info(
                    "resume case=%s: succeeded run %s already exists; skipping",
                    case_ref,
                    existing,
                )
                metrics["status"] = "skipped"
                metrics["error_message"] = None
                metrics["duration_seconds"] = round(
                    time.monotonic() - started, 3
                )
                return "skipped", metrics

    # 4) Build the run row (commit only). Step (c) per the plan:
    #    its own UoW so the row survives even if extraction fails later.
    run = PropositionExtractionRun(
        document_id=doc.document_id,
        extractor_version=_EXTRACTOR_VERSION,
        prompt_version=PROPOSITION_EXTRACTION_PROMPT_VERSION,
        prompt_sha256=prompt_sha,
        model=model,
        status=ExtractionRunStatus.started,
        input_chars=doc.char_count,
        chunk_count=0,
        proposition_count=0,
        edge_count=0,
        rejected_count=0,
    )
    if args.commit:
        from apps.api.src.db.uow import UnitOfWork

        async with UnitOfWork(sessionmaker) as uow:
            await uow.propositions.create_run(run)

    # 5) Extract propositions + edges + validate.
    extractor = LLMPropositionExtractor(
        llm,
        max_chars_per_chunk=args.max_chars_per_chunk,
        min_confidence=args.min_confidence,
    )
    edge_extractor = LLMPropositionEdgeExtractor(
        llm,
        min_confidence=args.min_confidence,
    )
    tokens_in_before, tokens_out_before = _token_totals(llm)

    try:
        prop_result = await extractor.extract(
            document_id=doc.document_id,
            case_reference=doc.case_reference,
            loaded=loaded,
            run_id=run.run_id,
        )
        # Stamp run_id onto edges via the validator/edge_extractor —
        # edge extractor uses document_id, not run_id, so edges don't
        # carry run_id directly. That matches the schema (edges link to
        # propositions, propositions link to runs).
        edge_result = await edge_extractor.extract_edges(
            doc.document_id, prop_result.propositions
        )
        accepted_edges, graph_rejections = validate_graph(
            edge_result.edges,
            prop_result.propositions,
            expected_document_id=doc.document_id,
        )
    except Exception as exc:
        log.exception("extraction failed for case=%s", case_ref)
        metrics["error_message"] = f"extraction_error: {type(exc).__name__}: {exc}"
        tokens_in_after, tokens_out_after = _token_totals(llm)
        metrics["tokens_in"] = max(0, tokens_in_after - tokens_in_before)
        metrics["tokens_out"] = max(0, tokens_out_after - tokens_out_before)
        if args.commit:
            # Mark the run as failed in a fresh UoW (Option A).
            from apps.api.src.db.uow import UnitOfWork

            try:
                async with UnitOfWork(sessionmaker) as uow:
                    await uow.propositions.finish_run(
                        run.run_id,
                        status=ExtractionRunStatus.failed,
                        counts={
                            "tokens_in": metrics["tokens_in"],
                            "tokens_out": metrics["tokens_out"],
                        },
                        error_message=str(exc)[:1900],
                    )
            except Exception:
                log.exception(
                    "could not record failed status for run %s", run.run_id
                )
        metrics["duration_seconds"] = round(time.monotonic() - started, 3)
        return "failed", metrics

    prop_count = len(prop_result.propositions)
    prop_rejected = len(prop_result.rejections)
    edge_count = len(accepted_edges)
    edge_rejected = len(edge_result.rejections) + len(graph_rejections)

    # Token usage from the LLM client is cumulative; store/report the
    # per-document delta so run rows are usable for cost-per-document analysis.
    tokens_in_after, tokens_out_after = _token_totals(llm)
    tokens_in = max(0, tokens_in_after - tokens_in_before)
    tokens_out = max(0, tokens_out_after - tokens_out_before)

    metrics.update(
        {
            "status": "succeeded",
            "proposition_count": prop_count,
            "proposition_rejected_count": prop_rejected,
            "edge_count": edge_count,
            "edge_rejected_count": edge_rejected,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
    )

    log.info(
        "extracted case=%s propositions=%d edges=%d rejected=%d/%d",
        case_ref,
        prop_count,
        edge_count,
        prop_rejected,
        edge_rejected,
    )

    # 6) Persist propositions + edges + finish_run (commit only).
    if args.commit:
        from apps.api.src.db.uow import UnitOfWork

        try:
            async with UnitOfWork(sessionmaker) as uow:
                inserted_props = await uow.propositions.bulk_upsert_propositions(
                    prop_result.propositions
                )
                inserted_edges = await uow.propositions.bulk_upsert_edges(
                    accepted_edges
                )
        except Exception as exc:
            log.exception(
                "persistence failed for case=%s after successful extraction",
                case_ref,
            )
            metrics["status"] = "failed"
            metrics["error_message"] = (
                f"persistence_error: {type(exc).__name__}: {exc}"
            )
            try:
                async with UnitOfWork(sessionmaker) as uow:
                    await uow.propositions.finish_run(
                        run.run_id,
                        status=ExtractionRunStatus.failed,
                        counts={},
                        error_message=str(exc)[:1900],
                    )
            except Exception:
                log.exception(
                    "could not record failed status for run %s", run.run_id
                )
            metrics["duration_seconds"] = round(time.monotonic() - started, 3)
            return "failed", metrics

        # Counts above are the row-insert counts; they may be < total when
        # idempotent re-runs hit ON CONFLICT DO NOTHING. We persist the
        # *attempted* counts (proposition_count / edge_count) so the run
        # record reflects what extraction produced, not what survived
        # dedup.
        async with UnitOfWork(sessionmaker) as uow:
            await uow.propositions.finish_run(
                run.run_id,
                status=ExtractionRunStatus.succeeded,
                counts={
                    "input_chars": doc.char_count,
                    "chunk_count": prop_result.chunks_called,
                    "proposition_count": prop_count,
                    "edge_count": edge_count,
                    "rejected_count": prop_rejected + edge_rejected,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                },
            )
        log.info(
            "persisted case=%s inserted_props=%d inserted_edges=%d",
            case_ref,
            inserted_props,
            inserted_edges,
        )

    metrics["duration_seconds"] = round(time.monotonic() - started, 3)
    return "succeeded", metrics


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------


async def _run_async(args: argparse.Namespace) -> int:
    """Async entry point. Returns the desired process exit code."""
    # 1) Validate manifest.
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(
            f"error: manifest unreadable: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    cases = manifest.get("cases", []) if isinstance(manifest, dict) else []
    if args.decisions is not None:
        cases = cases[: args.decisions]

    # 2) Build the sessionmaker for commit mode FIRST — DATABASE_URL must
    # be validated before we attempt any LLM setup so a missing DB env
    # gives a clean exit-2 even when ANTHROPIC_API_KEY is also unset.
    sessionmaker = None
    engine = None
    if args.commit:
        from apps.api.src.db.engine import (
            create_engine_from_url,
            make_sessionmaker,
        )

        url = os.environ.get("DATABASE_URL")
        if not url:
            print(
                "error: --commit requires DATABASE_URL in the environment",
                file=sys.stderr,
            )
            return 2
        engine = create_engine_from_url(url)
        sessionmaker = make_sessionmaker(engine)

    # 3) Build the LLM client (or mock) and resolve the model name we'll record.
    try:
        llm = _make_llm(args)
    except SystemExit as exc:
        # _make_llm raises SystemExit with a message string; exit code 2
        # because this is a CLI-arg / environment configuration problem.
        if engine is not None:
            await engine.dispose()
        msg = str(exc)
        if msg:
            print(f"error: {msg}", file=sys.stderr)
        return 2
    if isinstance(llm, _MockLLM):
        model = args.model or "mock"
    else:
        model = getattr(llm, "model", args.model or _DEFAULT_MODEL)

    # 4) Compute prompt sha once.
    prompt_sha = _compute_prompt_sha(args.min_confidence)

    report_path = (
        Path(args.jsonl_report) if args.jsonl_report else None
    )

    # 5) Walk cases.
    failures = 0
    successes = 0
    skipped = 0
    try:
        for case in cases:
            case_ref = case.get("case_reference", "<unknown>")
            try:
                status, metrics = await _run_one_document(
                    case=case,
                    args=args,
                    sessionmaker=sessionmaker,
                    llm=llm,
                    prompt_sha=prompt_sha,
                    model=model,
                )
            except Exception as exc:
                # Defensive: _run_one_document is supposed to swallow its own
                # errors, but if something surprising leaks out we surface
                # it here.
                log.exception("unexpected error processing case=%s", case_ref)
                if args.fail_fast:
                    raise
                failures += 1
                _emit_jsonl(
                    report_path,
                    {
                        "case_reference": case_ref,
                        "status": "failed",
                        "error_message": (
                            f"unexpected: {type(exc).__name__}: {exc}"
                        ),
                    },
                )
                continue

            _emit_jsonl(report_path, metrics)
            if status == "failed":
                failures += 1
                if args.fail_fast:
                    print(
                        f"--fail-fast: stopping after failure on {case_ref}",
                        file=sys.stderr,
                    )
                    break
            elif status == "skipped":
                skipped += 1
            else:
                successes += 1

            # Per-document summary (counts only — never log text bodies).
            print(
                json.dumps(
                    {
                        "case_reference": case_ref,
                        "status": status,
                        "proposition_count": metrics["proposition_count"],
                        "edge_count": metrics["edge_count"],
                    },
                    sort_keys=True,
                )
            )
    finally:
        if engine is not None:
            await engine.dispose()

    log.info(
        "done: succeeded=%d failed=%d skipped=%d total=%d",
        successes,
        failures,
        skipped,
        len(cases),
    )

    return 0 if failures == 0 else 1


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ingest_propositions",
        description=(
            "Run the proposition KG extraction pipeline over a corpus "
            "manifest. Writes to Postgres in --commit mode."
        ),
    )
    p.add_argument("--manifest", required=True, type=str,
                   help="Path to a corpus manifest JSON (Task 8 output).")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="Load + extract only. No DB writes.")
    mode.add_argument("--commit", action="store_true",
                      help="Full pipeline. Writes to Postgres.")
    p.add_argument("--decisions", type=int, default=None,
                   help="Process only the first N cases.")
    p.add_argument("--resume", action="store_true",
                   help="Skip cases with an existing succeeded run.")
    p.add_argument("--force", action="store_true",
                   help="Opposite of --resume: always create a new run.")
    p.add_argument("--model", type=str, default=None,
                   help="Override Claude model (default: ClaudeClient default).")
    p.add_argument("--min-confidence", type=float, default=0.5,
                   help="Confidence threshold for propositions + edges.")
    p.add_argument("--max-chars-per-chunk", type=int, default=12000,
                   help="Max chars per LLM extraction chunk.")
    p.add_argument("--jsonl-report", type=str, default=None,
                   help="Append per-document JSON metrics to this path.")
    p.add_argument("--mock-response", type=str, default=None,
                   help=(
                       "Path to a mock LLM fixture. Forces --dry-run; "
                       "incompatible with --commit."
                   ))
    p.add_argument("--fail-fast", action="store_true",
                   help="Exit on first document failure.")
    return p


def _validate_args_returning_exit_code(args: argparse.Namespace) -> Optional[int]:
    """Return None if args are OK, otherwise the exit code to return.

    Split from ``main`` so async tests can re-use the same checks.
    """
    if args.commit and args.mock_response is not None:
        print(
            "error: --commit refuses --mock-response (mock data must not "
            "be persisted to the database)",
            file=sys.stderr,
        )
        return 2
    if args.resume and args.force:
        print("error: --resume and --force are mutually exclusive",
              file=sys.stderr)
        return 2
    return None


async def main_async(argv: Optional[list] = None) -> int:
    """Async entry point. Tests use this directly to avoid nested
    ``asyncio.run`` calls inside an already-running event loop.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

    rc = _validate_args_returning_exit_code(args)
    if rc is not None:
        return rc

    return await _run_async(args)


def main(argv: Optional[list] = None) -> int:
    """Sync entry point used by ``python -m`` and shell invocations."""
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
