"""Pytest config for the GOV.UK Property Tribunal RRO scraper tests.

Adds the repo root to sys.path so that
``from scripts.scrapers.govuk_property_tribunal.filter import ...`` resolves
without a top-level pyproject. Also adds ``packages/`` so direct
imports of internal libraries (``rag_engine``, ``domain_core``) work.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/scrapers/govuk_property_tribunal/tests/conftest.py
#  -> repo root is parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PACKAGES = _REPO_ROOT / "packages"

for p in (_REPO_ROOT, _PACKAGES):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
