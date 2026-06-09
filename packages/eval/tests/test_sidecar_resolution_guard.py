"""Guard: KG-bearing eval modes must not silently run with a missing factor sidecar."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "eval"))
from predict_all import _require_sidecar_exists  # noqa: E402


def test_missing_sidecar_with_kg_mode_raises(tmp_path):
    missing = tmp_path / "nope.factor_assertions.json"
    with pytest.raises(SystemExit, match="factor sidecar not found"):
        _require_sidecar_exists(missing, modes=["hybrid", "kg_only"])


def test_missing_sidecar_without_kg_mode_is_allowed(tmp_path):
    missing = tmp_path / "nope.factor_assertions.json"
    _require_sidecar_exists(missing, modes=["llm_only", "rag_only"])  # no raise


def test_existing_sidecar_is_allowed(tmp_path):
    p = tmp_path / "ok.factor_assertions.json"
    p.write_text("{}")
    _require_sidecar_exists(p, modes=["hybrid"])  # no raise
