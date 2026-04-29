"""Pytest config for eval package tests: ensure `packages/` is on sys.path.

Mirrors `packages/rag_engine/tests/conftest.py` so `from eval.schema import ...`
resolves the same way `from rag_engine.config import ...` does there.

Also exposes test-only factories `gold_case_dict()` and `write_jsonl()` for use
by `test_dataset.py`. These are deliberately ordinary module-level helpers (not
pytest fixtures) so tests can `from eval.tests.conftest import ...` directly,
which keeps the call sites readable. If the import path ever breaks, switch to
fixtures and refactor the call sites — neither is a deep change.
"""
import json as _json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_minimal_dict() -> dict:
    return _json.loads((_FIXTURES_DIR / "gold_case_minimal.json").read_text())


def gold_case_dict(**overrides: Any) -> dict:
    """Return a fresh, valid GoldCase dict with optional shallow overrides.

    Tests use this to build corpora in-memory or in `tmp_path` JSONL files.
    Example:
        gold_case_dict(case_id="X", decision_date="2020-05-01")
    """
    base = _load_minimal_dict()
    base.update(overrides)
    return base


def write_jsonl(path: Path, dicts: list) -> Path:
    """Write a list of dicts to JSONL at `path`. Returns `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for d in dicts:
            f.write(_json.dumps(d))
            f.write("\n")
    return path
