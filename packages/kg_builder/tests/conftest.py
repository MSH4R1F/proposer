"""Pytest config for kg_builder tests.

Ensures that both ``kg_builder.x`` and ``packages.kg_builder.x`` import
spellings resolve. The legacy tests (e.g. ``test_validators_fail_fast``)
use the bare ``kg_builder`` form via ``PYTHONPATH=packages``; some of
the production modules under ``packages/kg_builder`` use the
``packages.kg_builder.*`` form because they're shared with apps/api,
which adds the project root to sys.path. This conftest reconciles both
by adding the project root to sys.path when the tests run.
"""

from __future__ import annotations

import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES_DIR = _PROJECT_ROOT / "packages"

for _p in (_PROJECT_ROOT, _PACKAGES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
