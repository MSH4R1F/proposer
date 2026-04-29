"""
Pytest configuration for migration scripts tests.

Adds the monorepo `packages/` directory to sys.path so that
`import llm_orchestrator` (without the `packages.` prefix) resolves
correctly — required because issue_predictor.py uses
importlib.import_module("llm_orchestrator.prompts.prediction_v2").
"""

import sys
from pathlib import Path

# Repo root is three levels up from this file.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES_DIR = _REPO_ROOT / "packages"

if str(_PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_DIR))
