"""Resolve BAILII / internal source URLs for tribunal citations.

Order:
1. Authoritative URL from ingested corpus (data/raw/bailii/**/metadata.json).
2. Deterministic BAILII fallback (https://www.bailii.org/uk/cases/UKFTT/PC/{year}/{ref}.html).
3. None when case_reference is empty/unknown or year is missing.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

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
