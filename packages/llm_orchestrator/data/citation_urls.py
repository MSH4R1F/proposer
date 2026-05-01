"""Resolve source URLs for legal citations.

Order (legacy / deposit pipeline path):
1. Authoritative URL from ingested corpus (data/raw/bailii/**/metadata.json).
2. Deterministic BAILII fallback (https://www.bailii.org/uk/cases/UKFTT/PC/{year}/{ref}.html).
3. None when case_reference is empty/unknown or year is missing.

SHA-20 Phase 4 (multi-domain): for non-BAILII publishers (GOV.UK,
Housing Ombudsman, legislation.gov.uk, ACAS, internal), call
:func:`resolve_citation_url` which keys off
``(source_publisher, source_kind, source_id)``. The deposit pipeline's
caller is unchanged — it still calls :func:`resolve_source_url`, which
now also accepts an explicit ``source_publisher`` keyword for forward
compatibility but defaults to BAILII.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from domain_core.spec import SourceKind, SourcePublisher

logger = logging.getLogger(__name__)

BAILII_BASE = "https://www.bailii.org/uk/cases/UKFTT/PC"


def _project_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


@lru_cache(maxsize=1)
def _corpus_index() -> dict[str, str]:
    bailii_dir = _project_root() / "data" / "raw" / "bailii"
    index: dict[str, str] = {}
    if not bailii_dir.exists():
        return index
    for meta_path in bailii_dir.rglob("metadata.json"):
        try:
            with meta_path.open() as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        ref = meta.get("case_reference")
        url = meta.get("html_url")
        if isinstance(ref, str) and isinstance(url, str):
            index[ref] = url
    return index


def reset_corpus_index_cache() -> None:
    _corpus_index.cache_clear()


def resolve_source_url(
    case_reference: Optional[str], year: Optional[int] = None
) -> Optional[str]:
    if not case_reference or case_reference.strip().lower() in {"", "unknown"}:
        return None

    indexed = _corpus_index().get(case_reference)
    if indexed:
        return indexed

    if year is None:
        logger.info(
            "citation_url.fallback_skipped case_reference=%s reason=missing_year",
            case_reference,
        )
        return None

    return f"{BAILII_BASE}/{year}/{case_reference}.html"


def resolve_citation_url(
    *,
    source_publisher: "SourcePublisher",
    source_kind: "SourceKind",
    source_id: str,
    year: Optional[int] = None,
    as_of: Optional[date] = None,
) -> Optional[str]:
    """SHA-20 Phase 4: publisher/kind-aware citation URL resolver.

    Delegates to :mod:`rag_engine.citation_mapping`, which has the
    per-publisher URL builders. Kept here as a thin re-export so call
    sites in ``llm_orchestrator`` don't need to import the rag package
    directly.
    """
    # Local import keeps ``llm_orchestrator -> rag_engine`` from being
    # an unconditional dependency at module load.
    from rag_engine.citation_mapping import map_citation_to_url

    return map_citation_to_url(
        source_publisher=source_publisher,
        source_kind=source_kind,
        source_id=source_id,
        year=year,
        as_of=as_of,
    )
