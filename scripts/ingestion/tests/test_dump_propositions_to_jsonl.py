"""Tests for ``scripts.ingestion.dump_propositions_to_jsonl``.

Verifies the eval-corpus -> proposition-corpus manifest translation +
the wrapper around ``ingest_propositions`` in ``--dry-run`` mode.

We use the existing ``--mock-response`` LLM fixture pattern from
``test_ingest_propositions.py`` to drive the extractor without paying
for real LLM calls, so this test runs hermetically.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages"))

from scripts.ingestion.dump_propositions_to_jsonl import (  # noqa: E402
    _read_eval_corpus,
    build_manifest,
    main_async,
)


# ---------------------------------------------------------------------------
# Fixture builders mirrored from test_ingest_propositions.py
# ---------------------------------------------------------------------------

_PASSAGE = "The deposit was £1500 and was protected with the DPS scheme."
_DECISION_TEXT = (
    "Paragraph 1.\n"
    f"{_PASSAGE}\n"
    "Paragraph 2.\n"
    "The tenant moved out on 30 June 2022 leaving the property clean.\n"
    "Paragraph 3.\n"
    "The tribunal awarded the deposit return in full to the tenant.\n"
)


def _write_decision_txt(tmp_path: Path, name: str = "case_a.txt") -> Path:
    p = tmp_path / name
    p.write_text(_DECISION_TEXT, encoding="utf-8")
    return p


def _write_eval_corpus(
    tmp_path: Path,
    rows: list,
    name: str = "eval_corpus.jsonl",
) -> Path:
    p = tmp_path / name
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return p


def _make_eval_row(case_id: str, txt_path: Path, *, decision_date="2024-01-15") -> dict:
    return {
        "case_id": case_id,
        "raw_text_path": str(txt_path),
        "decision_date": decision_date,
        "domain_id": "housing.repairs_social.v1",
        "primary_matter_type": "repairs_damp_mould",
        "source_url": "https://example.test/case/x",
    }


def _two_props_mock(tmp_path: Path) -> Path:
    payload = {
        "propositions_response": {
            "propositions": [
                {
                    "text": "Deposit was £1500.",
                    "source_passage": _PASSAGE,
                    "paragraph_ref": "1",
                    "proposition_type": "fact",
                    "confidence": 0.92,
                    "entities": ["deposit"],
                    "issue_tags": ["deposit_amount"],
                },
                {
                    "text": "Tenant moved out on 30 June 2022.",
                    "source_passage": (
                        "The tenant moved out on 30 June 2022 leaving the "
                        "property clean."
                    ),
                    "paragraph_ref": "2",
                    "proposition_type": "fact",
                    "confidence": 0.88,
                    "entities": ["tenant"],
                    "issue_tags": ["timeline"],
                },
            ]
        },
        "edges_response": {"edges": []},
    }
    p = tmp_path / "mock.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Pure-translation tests (no LLM, no extractor)
# ---------------------------------------------------------------------------


def test_read_eval_corpus_round_trip(tmp_path):
    txt = _write_decision_txt(tmp_path)
    rows = [_make_eval_row("housing-x-1", txt)]
    path = _write_eval_corpus(tmp_path, rows)
    out = _read_eval_corpus(path)
    assert len(out) == 1
    assert out[0]["case_id"] == "housing-x-1"


def test_read_eval_corpus_skips_blank_lines(tmp_path):
    txt = _write_decision_txt(tmp_path)
    rows = [_make_eval_row("a", txt), _make_eval_row("b", txt)]
    path = tmp_path / "c.jsonl"
    body = "\n" + json.dumps(rows[0]) + "\n  \n" + json.dumps(rows[1]) + "\n"
    path.write_text(body, encoding="utf-8")
    out = _read_eval_corpus(path)
    assert len(out) == 2


def test_read_eval_corpus_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _read_eval_corpus(tmp_path / "no.jsonl")


def test_build_manifest_translates_eval_rows(tmp_path):
    txt = _write_decision_txt(tmp_path)
    rows = [
        _make_eval_row("housing-x-1", txt, decision_date="2025-10-23"),
        _make_eval_row("housing-x-2", txt, decision_date="2024-04-01"),
    ]
    manifest = build_manifest(rows, data_root=tmp_path)
    assert manifest["manifest_version"] == "v1"
    assert len(manifest["cases"]) == 2
    refs = {c["case_reference"] for c in manifest["cases"]}
    assert refs == {"housing-x-1", "housing-x-2"}
    case0 = manifest["cases"][0]
    assert case0["pdf_path"] == str(txt)
    assert case0["html_path"] is None
    assert case0["year"] == 2025
    assert case0["category"] == "housing.repairs_social.v1"
    assert case0["case_type_code"] == "repairs_damp_mould"


def test_build_manifest_filters_by_case_ids(tmp_path):
    txt = _write_decision_txt(tmp_path)
    rows = [
        _make_eval_row("housing-x-1", txt),
        _make_eval_row("housing-x-2", txt),
        _make_eval_row("housing-x-3", txt),
    ]
    manifest = build_manifest(
        rows, data_root=tmp_path, case_ids=["housing-x-2"]
    )
    refs = [c["case_reference"] for c in manifest["cases"]]
    assert refs == ["housing-x-2"]


def test_build_manifest_drops_rows_with_missing_text_path(tmp_path):
    txt = _write_decision_txt(tmp_path)
    rows = [
        _make_eval_row("good", txt),
        {
            "case_id": "missing-text",
            "raw_text_path": str(tmp_path / "does_not_exist.txt"),
            "decision_date": "2024-01-01",
            "domain_id": "x",
        },
        {
            "case_id": "no-text-field",
            "decision_date": "2024-01-01",
        },
    ]
    manifest = build_manifest(rows, data_root=tmp_path)
    refs = [c["case_reference"] for c in manifest["cases"]]
    assert refs == ["good"]


# ---------------------------------------------------------------------------
# Print-manifest-only smoke (no LLM, no extractor)
# ---------------------------------------------------------------------------


def test_print_manifest_only_does_not_invoke_extractor(tmp_path, capsys):
    txt = _write_decision_txt(tmp_path)
    eval_path = _write_eval_corpus(
        tmp_path, [_make_eval_row("housing-x-1", txt)]
    )
    out_path = tmp_path / "props.jsonl"
    rc = asyncio.run(
        main_async(
            [
                "--eval-corpus",
                str(eval_path),
                "--output",
                str(out_path),
                "--data-root",
                str(tmp_path),
                "--print-manifest-only",
            ]
        )
    )
    assert rc == 0
    captured = capsys.readouterr().out
    parsed = json.loads(captured)
    assert parsed["manifest_version"] == "v1"
    assert parsed["cases"][0]["case_reference"] == "housing-x-1"
    # Critical: the output JSONL must NOT have been created — print-only
    # short-circuits before any extractor work.
    assert not out_path.exists()


def test_main_async_errors_when_no_eligible_cases(tmp_path, capsys):
    eval_path = _write_eval_corpus(tmp_path, [])
    out_path = tmp_path / "props.jsonl"
    rc = asyncio.run(
        main_async(
            [
                "--eval-corpus",
                str(eval_path),
                "--output",
                str(out_path),
                "--data-root",
                str(tmp_path),
            ]
        )
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "no eligible cases" in err


def test_main_async_errors_when_eval_corpus_missing(tmp_path, capsys):
    rc = asyncio.run(
        main_async(
            [
                "--eval-corpus",
                str(tmp_path / "ghost.jsonl"),
                "--output",
                str(tmp_path / "out.jsonl"),
            ]
        )
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "not found" in err


# ---------------------------------------------------------------------------
# End-to-end with a mocked LLM — verify Proposition JSONL output
# ---------------------------------------------------------------------------


def test_dry_run_with_mock_response_writes_proposition_jsonl(tmp_path):
    """The wrapper must invoke the extractor in --dry-run mode and
    capture every successfully-extracted Proposition to the output JSONL.
    Uses the same mock LLM fixture pattern as test_ingest_propositions.
    """
    txt = _write_decision_txt(tmp_path)
    eval_path = _write_eval_corpus(
        tmp_path, [_make_eval_row("housing-x-1", txt)]
    )
    mock = _two_props_mock(tmp_path)
    out_path = tmp_path / "props.jsonl"

    rc = asyncio.run(
        main_async(
            [
                "--eval-corpus",
                str(eval_path),
                "--output",
                str(out_path),
                "--data-root",
                str(tmp_path),
                "--mock-response",
                str(mock),
            ]
        )
    )
    assert rc == 0, "extractor wrapper must succeed with mock LLM"
    assert out_path.exists(), "output JSONL must be created"

    # Each line must round-trip through the Proposition Pydantic model
    from kg_builder.propositions.models import Proposition

    lines = [
        ln for ln in out_path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(lines) == 2  # mock yields exactly two propositions
    parsed = [Proposition.model_validate_json(ln) for ln in lines]
    texts = {p.text for p in parsed}
    assert texts == {"Deposit was £1500.", "Tenant moved out on 30 June 2022."}


def test_dry_run_overwrites_output_unless_append(tmp_path):
    """Without --append, a stale output file must be replaced — otherwise
    re-runs append duplicate rows."""
    txt = _write_decision_txt(tmp_path)
    eval_path = _write_eval_corpus(
        tmp_path, [_make_eval_row("housing-x-1", txt)]
    )
    mock = _two_props_mock(tmp_path)
    out_path = tmp_path / "props.jsonl"
    out_path.write_text("STALE\n", encoding="utf-8")

    rc = asyncio.run(
        main_async(
            [
                "--eval-corpus",
                str(eval_path),
                "--output",
                str(out_path),
                "--data-root",
                str(tmp_path),
                "--mock-response",
                str(mock),
            ]
        )
    )
    assert rc == 0
    contents = out_path.read_text(encoding="utf-8")
    assert "STALE" not in contents
    # Only the two mock propositions
    assert sum(1 for ln in contents.splitlines() if ln.strip()) == 2
