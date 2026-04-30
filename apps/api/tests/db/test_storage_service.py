"""Phase 8.1 integration tests: StorageService routes metadata through EvidenceRepo with blob compensation."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from apps.api.src.services.storage_service import StorageService


# ---------------------------------------------------------------------------
# Helpers — build a minimal FastAPI UploadFile-like object that upload_evidence
# accepts without a running ASGI app.
# ---------------------------------------------------------------------------

def _make_upload_file(
    filename: str = "test.pdf",
    content_type: str = "application/pdf",
    content: bytes = b"fake pdf bytes",
):
    """Return a minimal UploadFile compatible with storage_service.upload_evidence.

    FastAPI >= 0.103 changed UploadFile.__init__ to accept ``file`` positionally
    and derive content_type from the ``headers`` mapping.  We build a minimal
    Headers object so that ``file.content_type`` resolves correctly.
    """
    from fastapi import UploadFile
    from starlette.datastructures import Headers

    headers = Headers(headers={"content-type": content_type})
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def storage_service(db_sessionmaker, tmp_path):
    """A StorageService configured for local-blob mode (no Supabase)."""
    svc = StorageService(sessionmaker=db_sessionmaker)
    # Force local mode regardless of env vars
    svc.use_supabase = False
    if not hasattr(svc, "local_storage_dir"):
        svc.local_storage_dir = tmp_path
    else:
        svc.local_storage_dir = tmp_path
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_evidence_persists_metadata(storage_service, db_sessionmaker):
    """upload_evidence writes a DB row readable back via EvidenceRepo."""
    file = _make_upload_file("receipt.pdf", "application/pdf", b"fake pdf bytes")
    result = await storage_service.upload_evidence(
        case_id="case-X",
        file=file,
        evidence_type="receipts",
        description="A receipt",
    )
    assert "evidence_id" in result
    evidence_id = result["evidence_id"]

    # Read back via repo directly
    from apps.api.src.db.repositories.evidence_repo import EvidenceRepo
    async with db_sessionmaker() as session:
        repo = EvidenceRepo(session)
        loaded = await repo.get("case-X", evidence_id)

    assert loaded is not None
    assert loaded.evidence_type.value == "receipts"
    assert loaded.file_name == "receipt.pdf"
    assert loaded.file_type == "application/pdf"


@pytest.mark.asyncio
async def test_upload_evidence_compensates_on_db_failure(
    storage_service, db_sessionmaker, monkeypatch,
):
    """If the metadata save fails, the blob is deleted (compensation) and the error re-raised."""
    from apps.api.src.db.repositories import evidence_repo as ev_mod

    async def boom(self, metadata):
        raise RuntimeError("simulated metadata save failure")

    monkeypatch.setattr(ev_mod.EvidenceRepo, "save", boom)

    delete_calls = []

    async def track_delete(self, file_url, storage_path=None):
        delete_calls.append(file_url)

    monkeypatch.setattr(StorageService, "_delete_blob", track_delete)

    file = _make_upload_file("r.pdf", "application/pdf", b"x")

    with pytest.raises(RuntimeError, match="simulated metadata save failure"):
        await storage_service.upload_evidence(
            case_id="case-X",
            file=file,
            evidence_type="receipts",
            description="",
        )

    # Compensation called: blob delete attempted exactly once
    assert len(delete_calls) == 1


@pytest.mark.asyncio
async def test_list_evidence_returns_all_for_case(storage_service):
    """list_evidence returns all evidence rows for a given case."""
    file_a = _make_upload_file("a.pdf", "application/pdf", b"a")
    file_b = _make_upload_file("b.pdf", "application/pdf", b"b")

    await storage_service.upload_evidence(
        case_id="case-L", file=file_a, evidence_type="receipts",
    )
    await storage_service.upload_evidence(
        case_id="case-L", file=file_b, evidence_type="invoices",
    )

    listed = await storage_service.list_evidence("case-L")
    names = {e["file_name"] for e in listed}
    assert names == {"a.pdf", "b.pdf"}

    types = {e["evidence_type"] for e in listed}
    assert "receipts" in types
    assert "invoices" in types


@pytest.mark.asyncio
async def test_delete_evidence_removes_row_and_blob(storage_service, monkeypatch):
    """delete_evidence removes the DB row and calls _delete_blob."""
    file = _make_upload_file("x.pdf", "application/pdf", b"x")
    result = await storage_service.upload_evidence(
        case_id="case-D", file=file, evidence_type="receipts",
    )
    evidence_id = result["evidence_id"]

    delete_calls = []

    async def track_delete(self, file_url, storage_path=None):
        delete_calls.append(file_url)

    monkeypatch.setattr(StorageService, "_delete_blob", track_delete)

    ok = await storage_service.delete_evidence("case-D", evidence_id)
    assert ok is True
    assert len(delete_calls) == 1

    # Row is gone
    listed = await storage_service.list_evidence("case-D")
    assert listed == []


@pytest.mark.asyncio
async def test_delete_evidence_returns_false_for_missing(storage_service):
    """delete_evidence returns False when the evidence_id does not exist."""
    ok = await storage_service.delete_evidence("case-Z", "nonexistent-id")
    assert ok is False


@pytest.mark.asyncio
async def test_list_evidence_returns_empty_for_unknown_case(storage_service):
    """list_evidence returns an empty list for a case with no evidence."""
    result = await storage_service.list_evidence("case-never-uploaded")
    assert result == []
