"""Tests for the proposition ingestion CLI (SHA-36 Task 9).

CI-safe: argv-handling tests use ``subprocess`` with a synthetic txt
fixture; commit-mode tests call ``main([...])`` in-process and use the
``db_sessionmaker`` fixture from ``apps/api/tests/db/conftest.py``-style
machinery (replicated here so ``scripts/ingestion/tests/`` tests don't
have to live under ``apps/``).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# DB fixtures: replicate apps/api/tests/db/conftest.py for this directory.
# ---------------------------------------------------------------------------


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


from pytest_postgresql import factories  # noqa: E402

postgresql_proc = factories.postgresql_proc(
    port=_unused_tcp_port(), unixsocketdir="/tmp"
)


def _admin_url(proc) -> str:
    return f"postgresql://{proc.user}:@{proc.host}:{proc.port}/postgres"


def _async_url(proc, db_name: str) -> str:
    return (
        f"postgresql+asyncpg://{proc.user}:@"
        f"{proc.host}:{proc.port}/{db_name}"
    )


@pytest.fixture(scope="session")
def _migrated_template(postgresql_proc):
    import psycopg

    template_name = f"proposer_template_{uuid.uuid4().hex[:8]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {template_name}")
        conn.execute(f"CREATE DATABASE {template_name}")
    template_url = _async_url(postgresql_proc, template_name)
    env = {**os.environ, "DATABASE_URL": template_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    yield template_name
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {template_name} WITH (FORCE)")


@pytest_asyncio.fixture
async def db_sessionmaker(postgresql_proc, _migrated_template):
    import psycopg
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    db_name = f"proposer_test_{uuid.uuid4().hex[:12]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {db_name} TEMPLATE {_migrated_template}")
    url = _async_url(postgresql_proc, db_name)
    engine = create_async_engine(url, poolclass=NullPool, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield sm, url
    await engine.dispose()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Minimum normalized length the loader requires (100). Build a long passage
# so the same source text can be quoted back as a proposition's
# source_passage and still be a substring of the chunk.
_PASSAGE = (
    "The deposit of one thousand five hundred pounds was held throughout "
    "the tenancy in compliance with the relevant scheme requirements."
)
_DECISION_TEXT = (
    "Tribunal Decision\n\n"
    "Paragraph 1.\n"
    f"{_PASSAGE}\n\n"
    "Paragraph 2.\n"
    "The tenant moved out on 30 June 2022 leaving the property clean.\n\n"
    "Paragraph 3.\n"
    "The tribunal awarded the deposit return in full to the tenant.\n"
)


def _write_decision_txt(
    tmp_path: Path,
    name: str = "case_a.txt",
    *,
    suffix: str = "",
) -> Path:
    """Write a fixture decision file. Optional ``suffix`` is appended so
    callers can produce content-distinct files (decision_documents has a
    UNIQUE on content_sha256).
    """
    p = tmp_path / name
    body = _DECISION_TEXT + suffix
    p.write_text(body, encoding="utf-8")
    return p


def _write_manifest(tmp_path: Path, cases: list, name: str = "manifest.json") -> Path:
    payload = {"manifest_version": "v1", "cases": cases}
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _make_case(case_ref: str, txt_path: Path, *, year: int = 2022) -> dict:
    return {
        "case_reference": case_ref,
        "year": year,
        "category": "deposit",
        "case_type_code": "PRP",
        "region_code": "LON",
        "decision_date": None,
        "pdf_path": str(txt_path),  # txt loader handles .txt fixtures
        "html_path": None,
        "char_count": len(_DECISION_TEXT),
        "extraction_method": "fixture_text",
    }


def _make_mock_fixture(tmp_path: Path, *, propositions: list, edges: list,
                       name: str = "mock.json") -> Path:
    payload = {
        "propositions_response": {"propositions": propositions},
        "edges_response": {"edges": edges},
    }
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _two_props_fixture(tmp_path: Path) -> Path:
    """Two valid propositions whose source_passage substring is in the chunk."""
    return _make_mock_fixture(
        tmp_path,
        propositions=[
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
                    "The tenant moved out on 30 June 2022 leaving the property clean."
                ),
                "paragraph_ref": "2",
                "proposition_type": "fact",
                "confidence": 0.88,
                "entities": ["tenant"],
                "issue_tags": ["timeline"],
            },
        ],
        edges=[],
    )


def _run_subprocess(args: list, env: dict = None) -> subprocess.CompletedProcess:
    base_env = {**os.environ}
    pkg_path = str(REPO_ROOT / "packages")
    existing = base_env.get("PYTHONPATH")
    base_env["PYTHONPATH"] = (
        f"{pkg_path}{os.pathsep}{existing}" if existing else pkg_path
    )
    if env is not None:
        base_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "scripts.ingestion.ingest_propositions", *args],
        cwd=str(REPO_ROOT),
        env=base_env,
        capture_output=True,
        text=True,
    )


def _import_main():
    """Import scripts.ingestion.ingest_propositions.main_async once sys.path is set."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(REPO_ROOT / "packages") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "packages"))
    from scripts.ingestion.ingest_propositions import main_async  # type: ignore
    return main_async


# ---------------------------------------------------------------------------
# 1. Argv / env-handling tests (subprocess)
# ---------------------------------------------------------------------------


def test_dry_run_does_not_require_database_url(tmp_path):
    """--dry-run with --mock-response runs without DATABASE_URL or API key."""
    txt = _write_decision_txt(tmp_path)
    case = _make_case("LON_TEST_2022_0001", txt)
    manifest = _write_manifest(tmp_path, [case])
    fixture = _two_props_fixture(tmp_path)

    # Strip DATABASE_URL + ANTHROPIC_API_KEY so we prove they're not needed.
    env = {**os.environ}
    env.pop("DATABASE_URL", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env["DATABASE_URL"] = ""

    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ingestion.ingest_propositions",
         "--manifest", str(manifest), "--dry-run",
         "--mock-response", str(fixture)],
        cwd=str(REPO_ROOT),
        env={**env, "PYTHONPATH": str(REPO_ROOT / "packages")},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "LON_TEST_2022_0001" in proc.stdout


def test_dry_run_with_mock_response_does_not_require_anthropic_key(tmp_path):
    txt = _write_decision_txt(tmp_path)
    case = _make_case("LON_TEST_2022_0002", txt)
    manifest = _write_manifest(tmp_path, [case])
    fixture = _two_props_fixture(tmp_path)

    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = _run_subprocess(
        ["--manifest", str(manifest), "--dry-run",
         "--mock-response", str(fixture)],
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "LON_TEST_2022_0002" in proc.stdout


def test_commit_requires_database_url(tmp_path):
    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(tmp_path, [_make_case("X", txt)])
    env = {**os.environ}
    env.pop("DATABASE_URL", None)
    env["DATABASE_URL"] = ""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ingestion.ingest_propositions",
         "--manifest", str(manifest), "--commit"],
        cwd=str(REPO_ROOT),
        env={**env, "PYTHONPATH": str(REPO_ROOT / "packages")},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "DATABASE_URL" in proc.stderr


def test_commit_refuses_mock_response(tmp_path):
    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(tmp_path, [_make_case("X", txt)])
    fixture = _two_props_fixture(tmp_path)
    proc = _run_subprocess(
        ["--manifest", str(manifest), "--commit",
         "--mock-response", str(fixture)]
    )
    assert proc.returncode == 2
    assert "mock-response" in proc.stderr.lower() or "mock_response" in proc.stderr.lower()


# ---------------------------------------------------------------------------
# 2. In-process commit-mode behavior tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_persists_document_run_and_propositions(
    db_sessionmaker, tmp_path,
) -> None:
    sm, url = db_sessionmaker

    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(
        tmp_path, [_make_case("LON_PERSIST_2022_0001", txt)]
    )
    fixture = _two_props_fixture(tmp_path)

    main_async = _import_main()
    # We can't pass a sessionmaker to main() — it builds one from
    # DATABASE_URL. So we set DATABASE_URL to the per-test DB URL.
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        # We also need the mock-response path; but --commit refuses it.
        # Trick: we patch _make_llm in the module to return a mock so
        # we don't need an API key.
        from scripts.ingestion import ingest_propositions as mod
        from scripts.ingestion.ingest_propositions import _MockLLM, _load_mock_fixture
        original_make = mod._make_llm
        mod._make_llm = lambda args: _MockLLM(_load_mock_fixture(fixture))
        try:
            rc = await main_async([
                "--manifest", str(manifest), "--commit",
            ])
        finally:
            mod._make_llm = original_make
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    assert rc == 0

    # Verify rows persisted.
    from sqlalchemy import select
    from apps.api.src.db.models import (
        DecisionDocumentRow,
        PropositionExtractionRunRow,
        PropositionRow,
    )
    async with sm() as session:
        docs = (await session.execute(select(DecisionDocumentRow))).scalars().all()
        assert len(docs) == 1
        runs = (await session.execute(select(PropositionExtractionRunRow))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "succeeded"
        props = (await session.execute(select(PropositionRow))).scalars().all()
        assert len(props) == 2
        assert all(p.run_id == runs[0].run_id for p in props)


@pytest.mark.asyncio
async def test_commit_persists_edges(db_sessionmaker, tmp_path) -> None:
    sm, url = db_sessionmaker
    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(
        tmp_path, [_make_case("LON_EDGE_2022_0001", txt)]
    )

    # Build a fixture with 2 props and 1 supports edge between them.
    # We need to know the deterministic proposition_ids in advance.
    from kg_builder.propositions import (
        deterministic_document_id,
        deterministic_proposition_id,
        sha256_hex,
        PropositionType,
    )
    txt_bytes = txt.read_bytes()
    content_sha = __import__("hashlib").sha256(txt_bytes).hexdigest()
    doc_id = deterministic_document_id(str(txt), content_sha)

    p1_id = deterministic_proposition_id(
        doc_id, "1", _PASSAGE, PropositionType.fact, "Deposit was £1500.",
    )
    p2_passage = (
        "The tenant moved out on 30 June 2022 leaving the property clean."
    )
    p2_id = deterministic_proposition_id(
        doc_id, "2", p2_passage, PropositionType.fact,
        "Tenant moved out on 30 June 2022.",
    )

    fixture = _make_mock_fixture(
        tmp_path,
        propositions=[
            {
                "text": "Deposit was £1500.",
                "source_passage": _PASSAGE,
                "paragraph_ref": "1",
                "proposition_type": "fact",
                "confidence": 0.9,
                "entities": [],
                "issue_tags": [],
            },
            {
                "text": "Tenant moved out on 30 June 2022.",
                "source_passage": p2_passage,
                "paragraph_ref": "2",
                "proposition_type": "fact",
                "confidence": 0.9,
                "entities": [],
                "issue_tags": [],
            },
        ],
        edges=[
            {
                "from_proposition_id": str(p1_id),
                "to_proposition_id": str(p2_id),
                "edge_type": "supports",
                "confidence": 0.85,
                "rationale": "Both describe the same tenancy.",
            }
        ],
    )

    main_async = _import_main()
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from scripts.ingestion import ingest_propositions as mod
        from scripts.ingestion.ingest_propositions import _MockLLM, _load_mock_fixture
        mod._make_llm = lambda args: _MockLLM(_load_mock_fixture(fixture))
        rc = await main_async(["--manifest", str(manifest), "--commit"])
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    assert rc == 0
    from sqlalchemy import select
    from apps.api.src.db.models import PropositionRow, PropositionEdgeRow
    async with sm() as session:
        props = (await session.execute(select(PropositionRow))).scalars().all()
        edges = (await session.execute(select(PropositionEdgeRow))).scalars().all()
        assert len(props) == 2
        assert len(edges) == 1
        assert edges[0].from_proposition_id == p1_id
        assert edges[0].to_proposition_id == p2_id


@pytest.mark.asyncio
async def test_commit_with_validation_failure_skips_invalid_edges(
    db_sessionmaker, tmp_path,
) -> None:
    """An applies_rule_to_fact edge between two facts must be rejected by
    the graph validator. Run still succeeds; just no edge stored."""
    sm, url = db_sessionmaker
    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(
        tmp_path, [_make_case("LON_VALID_2022_0001", txt)]
    )

    from kg_builder.propositions import (
        deterministic_document_id,
        deterministic_proposition_id,
        PropositionType,
    )
    import hashlib as _hashlib
    content_sha = _hashlib.sha256(txt.read_bytes()).hexdigest()
    doc_id = deterministic_document_id(str(txt), content_sha)
    p1_id = deterministic_proposition_id(
        doc_id, "1", _PASSAGE, PropositionType.fact, "Deposit was £1500.",
    )
    p2_passage = (
        "The tenant moved out on 30 June 2022 leaving the property clean."
    )
    p2_id = deterministic_proposition_id(
        doc_id, "2", p2_passage, PropositionType.fact,
        "Tenant moved out on 30 June 2022.",
    )

    fixture = _make_mock_fixture(
        tmp_path,
        propositions=[
            {
                "text": "Deposit was £1500.", "source_passage": _PASSAGE,
                "paragraph_ref": "1", "proposition_type": "fact",
                "confidence": 0.9, "entities": [], "issue_tags": [],
            },
            {
                "text": "Tenant moved out on 30 June 2022.",
                "source_passage": p2_passage, "paragraph_ref": "2",
                "proposition_type": "fact",
                "confidence": 0.9, "entities": [], "issue_tags": [],
            },
        ],
        edges=[
            {
                "from_proposition_id": str(p1_id),
                "to_proposition_id": str(p2_id),
                # Invalid: applies_rule_to_fact requires from=rule, to=fact.
                "edge_type": "applies_rule_to_fact",
                "confidence": 0.85,
            }
        ],
    )

    main_async = _import_main()
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from scripts.ingestion import ingest_propositions as mod
        from scripts.ingestion.ingest_propositions import _MockLLM, _load_mock_fixture
        mod._make_llm = lambda args: _MockLLM(_load_mock_fixture(fixture))
        rc = await main_async(["--manifest", str(manifest), "--commit"])
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    assert rc == 0
    from sqlalchemy import select
    from apps.api.src.db.models import (
        PropositionRow, PropositionEdgeRow, PropositionExtractionRunRow,
    )
    async with sm() as session:
        props = (await session.execute(select(PropositionRow))).scalars().all()
        edges = (await session.execute(select(PropositionEdgeRow))).scalars().all()
        runs = (await session.execute(select(PropositionExtractionRunRow))).scalars().all()
        assert len(props) == 2
        assert len(edges) == 0
        # The run still succeeded — extraction worked, just one edge was filtered.
        assert len(runs) == 1
        assert runs[0].status == "succeeded"


@pytest.mark.asyncio
async def test_resume_skips_already_succeeded_run(db_sessionmaker, tmp_path) -> None:
    sm, url = db_sessionmaker
    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(
        tmp_path, [_make_case("LON_RESUME_2022_0001", txt)]
    )
    fixture = _two_props_fixture(tmp_path)

    main_async = _import_main()
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from scripts.ingestion import ingest_propositions as mod
        from scripts.ingestion.ingest_propositions import _MockLLM, _load_mock_fixture
        mod._make_llm = lambda args: _MockLLM(_load_mock_fixture(fixture))
        rc1 = await main_async(["--manifest", str(manifest), "--commit"])
        assert rc1 == 0

        # Re-run with --resume: should not create another run row.
        rc2 = await main_async(["--manifest", str(manifest), "--commit", "--resume"])
        assert rc2 == 0
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    from sqlalchemy import select
    from apps.api.src.db.models import PropositionExtractionRunRow
    async with sm() as session:
        runs = (await session.execute(select(PropositionExtractionRunRow))).scalars().all()
        assert len(runs) == 1, (
            "--resume must not create a second run row when one already succeeded"
        )


@pytest.mark.asyncio
async def test_force_creates_new_run_even_after_succeeded(
    db_sessionmaker, tmp_path,
) -> None:
    sm, url = db_sessionmaker
    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(
        tmp_path, [_make_case("LON_FORCE_2022_0001", txt)]
    )
    fixture = _two_props_fixture(tmp_path)

    main_async = _import_main()
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from scripts.ingestion import ingest_propositions as mod
        from scripts.ingestion.ingest_propositions import _MockLLM, _load_mock_fixture
        mod._make_llm = lambda args: _MockLLM(_load_mock_fixture(fixture))
        rc1 = await main_async(["--manifest", str(manifest), "--commit"])
        rc2 = await main_async(["--manifest", str(manifest), "--commit", "--force"])
        assert rc1 == 0
        assert rc2 == 0
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    from sqlalchemy import select
    from apps.api.src.db.models import PropositionExtractionRunRow
    async with sm() as session:
        runs = (await session.execute(select(PropositionExtractionRunRow))).scalars().all()
        # First run created during default commit (no --resume); second
        # run created by --force. Both should be present and succeeded.
        assert len(runs) == 2, f"expected 2 runs after --force, got {len(runs)}"
        assert all(r.status == "succeeded" for r in runs)


@pytest.mark.asyncio
async def test_jsonl_report_writes_one_line_per_document(
    db_sessionmaker, tmp_path,
) -> None:
    sm, url = db_sessionmaker
    txt1 = _write_decision_txt(tmp_path, name="case_a.txt")
    txt2 = _write_decision_txt(
        tmp_path, name="case_b.txt", suffix="\nAdditional unique paragraph for case b.\n",
    )
    manifest = _write_manifest(
        tmp_path,
        [
            _make_case("LON_REPORT_2022_0001", txt1),
            _make_case("LON_REPORT_2022_0002", txt2),
        ],
    )
    fixture = _two_props_fixture(tmp_path)
    report = tmp_path / "report.jsonl"

    main_async = _import_main()
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from scripts.ingestion import ingest_propositions as mod
        from scripts.ingestion.ingest_propositions import _MockLLM, _load_mock_fixture
        mod._make_llm = lambda args: _MockLLM(_load_mock_fixture(fixture))
        rc = await main_async([
            "--manifest", str(manifest), "--commit",
            "--jsonl-report", str(report),
        ])
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    assert rc == 0
    lines = report.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(l) for l in lines]
    case_refs = {p["case_reference"] for p in parsed}
    assert case_refs == {"LON_REPORT_2022_0001", "LON_REPORT_2022_0002"}
    for p in parsed:
        assert "status" in p
        assert "proposition_count" in p
        assert "edge_count" in p
        assert "duration_seconds" in p
        assert "tokens_in" in p
        assert "tokens_out" in p


def test_decisions_flag_limits_processing(tmp_path):
    txts = [
        _write_decision_txt(
            tmp_path, name=f"case_{i}.txt", suffix=f"\nSuffix for case {i}.\n",
        )
        for i in range(3)
    ]
    cases = [
        _make_case(f"LON_DEC_2022_{i:04d}", t) for i, t in enumerate(txts)
    ]
    manifest = _write_manifest(tmp_path, cases)
    fixture = _two_props_fixture(tmp_path)

    proc = _run_subprocess(
        ["--manifest", str(manifest), "--dry-run",
         "--mock-response", str(fixture), "--decisions", "1"]
    )
    assert proc.returncode == 0, proc.stderr
    # Only the first case_reference should appear in stdout.
    assert "LON_DEC_2022_0000" in proc.stdout
    assert "LON_DEC_2022_0001" not in proc.stdout
    assert "LON_DEC_2022_0002" not in proc.stdout


def test_continue_after_failure_unless_fail_fast(tmp_path):
    """A bad path triggers DecisionTextExtractionError. Without --fail-fast,
    the second case still runs; with --fail-fast it does not.
    """
    bad_path = tmp_path / "missing.txt"  # never created
    good_txt = _write_decision_txt(tmp_path, name="good.txt")
    cases = [
        # first case has no readable file, will fail
        {**_make_case("LON_BAD_2022_0001", bad_path), "pdf_path": str(bad_path)},
        _make_case("LON_GOOD_2022_0001", good_txt),
    ]
    manifest = _write_manifest(tmp_path, cases)
    fixture = _two_props_fixture(tmp_path)

    proc = _run_subprocess(
        ["--manifest", str(manifest), "--dry-run",
         "--mock-response", str(fixture)]
    )
    # Without --fail-fast: exit 1 (one failure), second case still processed.
    assert proc.returncode == 1
    assert "LON_GOOD_2022_0001" in proc.stdout

    proc2 = _run_subprocess(
        ["--manifest", str(manifest), "--dry-run",
         "--mock-response", str(fixture), "--fail-fast"]
    )
    # With --fail-fast: exit 1, second case NOT processed.
    assert proc2.returncode == 1
    assert "LON_GOOD_2022_0001" not in proc2.stdout


def test_resume_and_force_are_mutually_exclusive(tmp_path):
    txt = _write_decision_txt(tmp_path)
    manifest = _write_manifest(tmp_path, [_make_case("X", txt)])
    proc = _run_subprocess(
        ["--manifest", str(manifest), "--commit", "--resume", "--force"]
    )
    assert proc.returncode == 2


def test_unreadable_manifest_returns_2(tmp_path):
    bad_manifest = tmp_path / "missing-manifest.json"
    proc = _run_subprocess(
        ["--manifest", str(bad_manifest), "--dry-run"]
    )
    assert proc.returncode == 2
    assert "manifest" in proc.stderr.lower()
