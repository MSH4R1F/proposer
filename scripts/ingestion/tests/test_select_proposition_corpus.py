"""Tests for the proposition corpus selector CLI.

CI-safe: no real BAILII data. Generates a synthetic ``data/raw/bailii``
layout in ``tmp_path`` using plain ``.txt`` decision files (the loader
supports ``.txt`` with ``extraction_method == "fixture_text"``).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the selector CLI as a subprocess.

    Always uses ``sys.executable`` not literal ``python`` — Python 3.9 systems
    may not have a ``python`` binary. PYTHONPATH is set to ``packages/`` so the
    CLI can import ``kg_builder.propositions.text_loader``.
    """
    base_env = {**os.environ}
    pkg_path = str(REPO_ROOT / "packages")
    existing = base_env.get("PYTHONPATH")
    base_env["PYTHONPATH"] = (
        f"{pkg_path}{os.pathsep}{existing}" if existing else pkg_path
    )
    if env:
        base_env.update(env)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ingestion.select_proposition_corpus",
            *args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=base_env,
    )


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# A blob of legible English text long enough (>100 chars after normalization)
# to satisfy text_loader._ensure_useful, and well above min_chars=1000 by
# default when repeated. One repetition is ~100 chars.
_TEXT_UNIT = (
    "The tribunal heard evidence that the deposit was held by an authorised "
    "scheme and the prescribed information was given to the tenant in time. "
)


def _decision_text(target_chars: int) -> str:
    n = max(1, target_chars // len(_TEXT_UNIT) + 1)
    return _TEXT_UNIT * n


def _make_case(
    bailii_root: Path,
    case_reference: str,
    year: int,
    *,
    category: str = "adjacent",
    case_type_code: str | None = "HMF",
    region_code: str | None = "LON",
    text_chars: int = 2000,
    extension: str = ".txt",
    write_metadata: bool = True,
) -> dict:
    """Create a fake case directory with a decision file + metadata.json."""
    if category == "adjacent":
        cat_dir = "adjacent-cases"
    elif category == "deposit":
        cat_dir = "deposit-cases"
    else:
        cat_dir = "other-cases"

    case_dir = bailii_root / cat_dir / str(year) / case_reference
    case_dir.mkdir(parents=True, exist_ok=True)

    decision_file = case_dir / f"decision{extension}"
    decision_file.write_text(_decision_text(text_chars), encoding="utf-8")

    # Use absolute path strings — selector should accept either, but absolute
    # is the simplest fixture.
    rec = {
        "case_reference": case_reference,
        "year": year,
        "category": category,
        "case_type_code": case_type_code,
        "region_code": region_code,
        "decision_date": None,
    }
    if extension == ".pdf":
        rec["pdf_path"] = str(decision_file)
        rec["html_path"] = None
    elif extension in (".html", ".htm"):
        rec["html_path"] = str(decision_file)
        rec["pdf_path"] = None
    else:
        # Treat .txt fixtures as the "pdf_path" slot — selector tries pdf
        # first; that path being a .txt extension exercises the fixture
        # loader and exercises extraction_method="fixture_text".
        rec["pdf_path"] = str(decision_file)
        rec["html_path"] = None

    if write_metadata:
        (case_dir / "metadata.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )

    return rec


def _write_master_index(bailii_root: Path, cases: list[dict]) -> None:
    payload = {
        "exported_at": "2026-05-01T00:00:00Z",
        "total_cases": len(cases),
        "cases": cases,
    }
    (bailii_root / "master_index.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_selector_fails_when_bailii_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    out = tmp_path / "manifest.json"
    r = _run(["--bailii-root", str(missing), "--output", str(out)])
    assert r.returncode == 2, r.stderr
    assert str(missing) in r.stderr
    assert "bailii_scraper" in r.stderr  # mentions scraper command


def test_selector_fails_when_no_cases_found(tmp_path: Path) -> None:
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    out = tmp_path / "manifest.json"
    r = _run(["--bailii-root", str(bailii_root), "--output", str(out)])
    assert r.returncode == 2, r.stderr
    assert "bailii_scraper" in r.stderr


def test_selector_loads_from_master_index_when_present(tmp_path: Path) -> None:
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    cases = []
    for i in range(5):
        cases.append(
            _make_case(
                bailii_root,
                f"LON_00BG_HMF_2022_{i:04d}",
                2022 + (i % 2),
                case_type_code=("HMF", "HNA", "HAS")[i % 3],
                text_chars=2000,
                # Don't write per-case metadata since master_index is the
                # source of truth. Selector should NOT need both.
                write_metadata=False,
            )
        )
    _write_master_index(bailii_root, cases)

    out = tmp_path / "manifest.json"
    r = _run(
        [
            "--bailii-root",
            str(bailii_root),
            "--output",
            str(out),
            "--n",
            "5",
        ]
    )
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    manifest = json.loads(out.read_text())
    assert len(manifest["cases"]) == 5
    refs = {c["case_reference"] for c in manifest["cases"]}
    assert refs == {c["case_reference"] for c in cases}


def test_selector_falls_back_to_metadata_scan(tmp_path: Path) -> None:
    """No master_index.json → scan adjacent-cases/<year>/<ref>/metadata.json."""
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    for i in range(3):
        _make_case(
            bailii_root,
            f"LON_00BG_HMF_2022_{i:04d}",
            2022,
            text_chars=2000,
            write_metadata=True,
        )
    out = tmp_path / "manifest.json"
    r = _run(
        ["--bailii-root", str(bailii_root), "--output", str(out), "--n", "3"]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    assert len(manifest["cases"]) == 3


def test_selector_filters_below_min_chars(tmp_path: Path) -> None:
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    # First case is 50-char (well below min_chars=1000); second is healthy.
    _make_case(
        bailii_root,
        "LON_TINY_HMF_2022_0001",
        2022,
        text_chars=50,
        write_metadata=True,
    )
    _make_case(
        bailii_root,
        "LON_OK_HMF_2022_0002",
        2022,
        text_chars=2000,
        write_metadata=True,
    )
    out = tmp_path / "manifest.json"
    r = _run(
        [
            "--bailii-root",
            str(bailii_root),
            "--output",
            str(out),
            "--n",
            "5",
            "--min-chars",
            "1000",
        ]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    refs = [c["case_reference"] for c in manifest["cases"]]
    assert "LON_TINY_HMF_2022_0001" not in refs
    assert "LON_OK_HMF_2022_0002" in refs


def test_selector_filters_above_max_chars(tmp_path: Path) -> None:
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    _make_case(
        bailii_root,
        "LON_BIG_HMF_2022_0001",
        2022,
        text_chars=50000,
        write_metadata=True,
    )
    _make_case(
        bailii_root,
        "LON_OK_HMF_2022_0002",
        2022,
        text_chars=2000,
        write_metadata=True,
    )
    out = tmp_path / "manifest.json"
    r = _run(
        [
            "--bailii-root",
            str(bailii_root),
            "--output",
            str(out),
            "--n",
            "5",
            "--max-chars",
            "30000",
        ]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    refs = [c["case_reference"] for c in manifest["cases"]]
    assert "LON_BIG_HMF_2022_0001" not in refs
    assert "LON_OK_HMF_2022_0002" in refs


def test_selector_skips_cases_with_extraction_errors(tmp_path: Path) -> None:
    """Unsupported extension (.docx) → skip, do not include in manifest."""
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    _make_case(
        bailii_root,
        "LON_DOC_HMF_2022_0001",
        2022,
        text_chars=2000,
        extension=".docx",
        write_metadata=True,
    )
    _make_case(
        bailii_root,
        "LON_OK_HMF_2022_0002",
        2022,
        text_chars=2000,
        write_metadata=True,
    )
    out = tmp_path / "manifest.json"
    r = _run(
        ["--bailii-root", str(bailii_root), "--output", str(out), "--n", "5"]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    refs = [c["case_reference"] for c in manifest["cases"]]
    assert "LON_DOC_HMF_2022_0001" not in refs
    assert "LON_OK_HMF_2022_0002" in refs


def test_selector_picks_n_cases(tmp_path: Path) -> None:
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    for i in range(10):
        _make_case(
            bailii_root,
            f"LON_OK_HMF_{2022 + i % 3}_{i:04d}",
            2022 + i % 3,
            case_type_code=("HMF", "HNA", "HAS")[i % 3],
            text_chars=2000,
            write_metadata=True,
        )
    out = tmp_path / "manifest.json"
    r = _run(
        ["--bailii-root", str(bailii_root), "--output", str(out), "--n", "5"]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    assert len(manifest["cases"]) == 5


def test_selector_diversity_prefers_multiple_years(tmp_path: Path) -> None:
    """4×2022 + 2×2023 with n=4 → result should include both years."""
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    for i in range(4):
        _make_case(
            bailii_root,
            f"LON_A_HMF_2022_{i:04d}",
            2022,
            text_chars=2000,
            write_metadata=True,
        )
    for i in range(2):
        _make_case(
            bailii_root,
            f"LON_B_HMF_2023_{i:04d}",
            2023,
            text_chars=2000,
            write_metadata=True,
        )
    out = tmp_path / "manifest.json"
    r = _run(
        ["--bailii-root", str(bailii_root), "--output", str(out), "--n", "4"]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    years = {c["year"] for c in manifest["cases"]}
    assert 2022 in years and 2023 in years, (
        f"diversity failed: years selected = {years}"
    )


def test_selector_writes_correct_manifest_shape(tmp_path: Path) -> None:
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    for i in range(3):
        _make_case(
            bailii_root,
            f"LON_OK_HMF_2022_{i:04d}",
            2022,
            text_chars=2000,
            write_metadata=True,
        )
    out = tmp_path / "manifest.json"
    r = _run(
        ["--bailii-root", str(bailii_root), "--output", str(out), "--n", "3"]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())

    # Top-level keys
    for key in ("manifest_version", "selected_at", "bailii_root", "criteria", "cases"):
        assert key in manifest, f"missing top-level key: {key}"
    assert manifest["manifest_version"] == "v1"
    assert isinstance(manifest["cases"], list)
    assert manifest["criteria"] == {"n": 3, "min_chars": 1000, "max_chars": 30000}

    # Insertion order: selected_at should come before cases
    keys = list(manifest.keys())
    assert keys.index("selected_at") < keys.index("cases")

    # Per-case shape
    expected_keys = {
        "case_reference",
        "year",
        "category",
        "case_type_code",
        "region_code",
        "decision_date",
        "pdf_path",
        "html_path",
        "char_count",
        "extraction_method",
    }
    for case in manifest["cases"]:
        assert expected_keys <= set(case.keys()), (
            f"missing keys: {expected_keys - set(case.keys())}"
        )


def test_selector_extraction_method_reflects_file_type(tmp_path: Path) -> None:
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    _make_case(
        bailii_root,
        "LON_OK_HMF_2022_0001",
        2022,
        text_chars=2000,
        extension=".txt",
        write_metadata=True,
    )
    out = tmp_path / "manifest.json"
    r = _run(
        ["--bailii-root", str(bailii_root), "--output", str(out), "--n", "1"]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    assert len(manifest["cases"]) == 1
    assert manifest["cases"][0]["extraction_method"] == "fixture_text"


def test_selector_emits_warning_when_diversity_target_unreachable(
    tmp_path: Path,
) -> None:
    """Single-year corpus → still selects but warns to stderr."""
    bailii_root = tmp_path / "bailii"
    bailii_root.mkdir()
    for i in range(3):
        _make_case(
            bailii_root,
            f"LON_OK_HMF_2022_{i:04d}",
            2022,
            case_type_code="HMF",
            text_chars=2000,
            write_metadata=True,
        )
    out = tmp_path / "manifest.json"
    r = _run(
        ["--bailii-root", str(bailii_root), "--output", str(out), "--n", "3"]
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads(out.read_text())
    assert len(manifest["cases"]) == 3
    # Some kind of diversity warning on stderr
    assert "diversity" in r.stderr.lower() or "warn" in r.stderr.lower()
