"""Phase 8.2: end-to-end smoke tests for /evidence/* routes against a test DB."""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from apps.api.src.config import APIConfig
from apps.api.src.dependencies import get_storage_service
from apps.api.src.main import create_app
from apps.api.src.services.storage_service import StorageService


@pytest_asyncio.fixture
async def app_client(db_sessionmaker, tmp_path):
    """FastAPI test client wired to the per-test Postgres sessionmaker.

    Strategy:
    - Extract the test DB URL from the sessionmaker's bound engine so that
      create_lifespan produces an engine that points at the test DB.  This
      prevents LifespanManager from creating an orphan engine aimed at the
      real localhost:5432/proposer instance.
    - Override get_storage_service so that every evidence route receives a
      StorageService backed by ``db_sessionmaker``, regardless of what
      ``app.state.db_sessionmaker`` holds after lifespan startup.
    """
    # Extract the test DB URL from the sessionmaker's bound engine.
    test_db_url = str(db_sessionmaker.kw["bind"].url)

    cfg = APIConfig(database_url=test_db_url)
    app = create_app(cfg)

    # Override storage dep so routes reach the test sessionmaker directly.
    def _override_storage():
        svc = StorageService(sessionmaker=db_sessionmaker)
        svc.use_supabase = False
        # StorageService._init_local sets local_storage_dir; redirect to tmp.
        svc.local_storage_dir = tmp_path
        return svc

    app.dependency_overrides[get_storage_service] = _override_storage

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_upload_then_list_evidence(app_client):
    """POST /evidence/upload/{case_id} writes a row; GET /evidence/{case_id} returns it."""
    files = {"file": ("receipt.pdf", b"fake pdf", "application/pdf")}
    data = {
        "evidence_type": "receipts",
        "description": "A receipt",
    }
    upload = await app_client.post(
        "/evidence/upload/case-route-1",
        files=files,
        data=data,
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body.get("evidence_id"), body

    listing = await app_client.get("/evidence/case-route-1")
    assert listing.status_code == 200
    payload = listing.json()
    # Router returns EvidenceListResponse with an "evidence" key.
    items = payload.get("evidence") or payload.get("items") or payload
    assert isinstance(items, list)
    assert any(e.get("evidence_id") == body["evidence_id"] for e in items)


@pytest.mark.asyncio
async def test_delete_evidence(app_client):
    """DELETE /evidence/{case_id}/{evidence_id} removes the row."""
    files = {"file": ("a.pdf", b"a", "application/pdf")}
    data = {"evidence_type": "receipts"}
    upload = await app_client.post(
        "/evidence/upload/case-route-2",
        files=files,
        data=data,
    )
    assert upload.status_code == 200, upload.text
    eid = upload.json()["evidence_id"]

    delete = await app_client.delete(f"/evidence/case-route-2/{eid}")
    assert delete.status_code == 200, delete.text

    listing = await app_client.get("/evidence/case-route-2")
    assert listing.status_code == 200
    items = listing.json().get("evidence") or listing.json().get("items") or []
    assert all(e.get("evidence_id") != eid for e in items)
