"""Shared fixtures for the GOV.UK ET scraper tests.

All fixtures are in-memory or filesystem-backed by ``fixtures/``. No tests
in this module make HTTP calls; the scraper's network seam is exercised
only through ``run_dry`` in ``test_orchestrator.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/scrapers/employment_tribunal/tests/conftest.py -> repo root is parents[4].
# Same pattern as scripts/scrapers/housing_ombudsman/tests/conftest.py — adds
# the repo root and packages/ to sys.path so internal imports resolve without
# a top-level pyproject.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PACKAGES = _REPO_ROOT / "packages"
for _p in (_REPO_ROOT, _PACKAGES):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def listing_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "listing.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def detail_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "detail"


def _read_detail(fixtures_dir: Path, name: str) -> tuple[str, str]:
    """Each detail fixture has the canonical URL as line 1, body from line 2."""
    raw = (fixtures_dir / "detail" / name).read_text(encoding="utf-8")
    lines = raw.splitlines()
    url = lines[0].strip()
    body = "\n".join(lines[1:])
    return url, body


@pytest.fixture(scope="session")
def detail_unfair_misconduct(fixtures_dir: Path) -> tuple[str, str]:
    return _read_detail(fixtures_dir, "unfair_misconduct.html")


@pytest.fixture(scope="session")
def detail_unfair_capability_partial(fixtures_dir: Path) -> tuple[str, str]:
    return _read_detail(fixtures_dir, "unfair_capability_partial.html")


@pytest.fixture(scope="session")
def detail_preliminary(fixtures_dir: Path) -> tuple[str, str]:
    return _read_detail(fixtures_dir, "preliminary.html")


@pytest.fixture(scope="session")
def detail_discrimination_led(fixtures_dir: Path) -> tuple[str, str]:
    return _read_detail(fixtures_dir, "discrimination_led.html")
