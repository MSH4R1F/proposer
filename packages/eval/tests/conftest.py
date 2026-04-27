"""Pytest config for eval package tests: ensure `packages/` is on sys.path.

Mirrors `packages/rag_engine/tests/conftest.py` so `from eval.schema import ...`
resolves the same way `from rag_engine.config import ...` does there.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
