"""Phase 10.4: hard regression guard — production paths must never write
to data/<entity>/ JSON state directories. The DB is the source of truth.

This wraps Path.write_text / write_bytes / open(..., write-mode) and
records any call whose path is under one of the guarded directories.
We then exercise representative API endpoints (the ones most likely to
regress on persistence) and assert no guarded write happened.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any, List

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from apps.api.src.config import APIConfig
from apps.api.src.dependencies import (
    get_dispute_service,
    get_intake_service,
    get_storage_service,
)
from apps.api.src.main import create_app


GUARDED_DIRS = (
    "data/sessions",
    "data/disputes",
    "data/predictions",
    "data/dispute_predictions",
    "data/knowledge_graphs",
    "data/mediations",
    "data/evidence_metadata",
)


def _is_guarded(path_str: str) -> bool:
    for d in GUARDED_DIRS:
        if d in str(path_str):
            return True
    return False


@pytest_asyncio.fixture
async def write_guard(monkeypatch):
    """Record any write attempt whose target path is under a guarded data/<entity>/ dir."""
    blocked: List[str] = []

    real_write_text = Path.write_text
    real_write_bytes = Path.write_bytes
    real_open = builtins.open

    def _patched_write_text(self: Path, *a, **kw):
        if _is_guarded(str(self)):
            blocked.append(f"write_text:{self}")
        return real_write_text(self, *a, **kw)

    def _patched_write_bytes(self: Path, *a, **kw):
        if _is_guarded(str(self)):
            blocked.append(f"write_bytes:{self}")
        return real_write_bytes(self, *a, **kw)

    def _patched_open(file, mode="r", *args, **kwargs):
        # Only flag write-mode opens
        is_write = any(c in str(mode) for c in ("w", "a", "x", "+"))
        if is_write and _is_guarded(str(file)):
            blocked.append(f"open({mode}):{file}")
        return real_open(file, mode, *args, **kwargs)

    real_path_open = Path.open

    def _patched_path_open(self, mode="r", *args, **kwargs):
        is_write = any(c in str(mode) for c in ("w", "a", "x", "+"))
        if is_write and _is_guarded(str(self)):
            blocked.append(f"path_open({mode}):{self}")
        return real_path_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _patched_write_text)
    monkeypatch.setattr(Path, "write_bytes", _patched_write_bytes)
    monkeypatch.setattr(builtins, "open", _patched_open)
    monkeypatch.setattr(Path, "open", _patched_path_open)

    yield blocked


@pytest_asyncio.fixture
async def app_client(db_sessionmaker, tmp_path):
    """Test client with service deps overridden to use the test sessionmaker."""
    from unittest.mock import AsyncMock

    from apps.api.src.services.dispute_service import DisputeService
    from apps.api.src.services.intake_service import IntakeService
    from apps.api.src.services.storage_service import StorageService
    from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole
    from packages.llm_orchestrator.models.conversation import (
        ConversationState,
        IntakeStage,
    )

    bind_url = str(db_sessionmaker.kw["bind"].url)
    cfg = APIConfig(database_url=bind_url)
    app = create_app(cfg)

    # Mock the LLM agent so /chat/start doesn't hit Anthropic
    mock_intake_agent = AsyncMock()
    state = ConversationState(
        session_id="guard-sess-1",
        case_file=CaseFile(case_id="guard-case-1", user_role=PartyRole.TENANT),
        messages=[],
        current_stage=IntakeStage.GREETING,
        started_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        stages_completed=[],
        current_stage_attempts=0,
        last_extraction_successful=True,
        extraction_errors=[],
        role_explicitly_set=False,
    )
    mock_intake_agent.start_conversation.return_value = ("hello", state)

    app.dependency_overrides[get_intake_service] = lambda: IntakeService(
        sessionmaker=db_sessionmaker,
        agent=mock_intake_agent,
    )
    app.dependency_overrides[get_dispute_service] = lambda: DisputeService(
        sessionmaker=db_sessionmaker,
    )
    app.dependency_overrides[get_storage_service] = lambda: _make_storage_service(
        db_sessionmaker, tmp_path
    )

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


def _make_storage_service(db_sessionmaker, tmp_path):
    from apps.api.src.services.storage_service import StorageService

    svc = StorageService(sessionmaker=db_sessionmaker)
    svc.use_supabase = False
    if hasattr(svc, "local_storage_dir"):
        svc.local_storage_dir = tmp_path
    return svc


@pytest.mark.asyncio
async def test_chat_start_does_not_write_json(app_client, write_guard):
    """POST /chat/start with role + create_dispute writes session+dispute to DB only."""
    resp = await app_client.post(
        "/chat/start",
        json={"role": "tenant", "create_dispute": True},
    )
    assert resp.status_code == 200, resp.text
    assert write_guard == [], f"unexpected JSON writes: {write_guard}"


@pytest.mark.asyncio
async def test_evidence_upload_does_not_write_metadata_json(app_client, write_guard):
    """POST /evidence/upload writes blob (allowed) but not metadata JSON."""
    files = {"file": ("a.pdf", b"x", "application/pdf")}
    data = {"evidence_type": "receipts", "description": "x"}
    resp = await app_client.post(
        "/evidence/upload/guard-case-evidence",
        files=files,
        data=data,
    )
    assert resp.status_code == 200, resp.text
    assert write_guard == [], f"unexpected JSON writes: {write_guard}"


@pytest.mark.asyncio
async def test_disputes_create_does_not_write_json(app_client, write_guard):
    """POST /disputes/create writes to DB only."""
    # Set up a session first (DisputeService.create_dispute requires session_id)
    start_resp = await app_client.post(
        "/chat/start",
        json={"role": "tenant", "create_dispute": False},
    )
    assert start_resp.status_code == 200, start_resp.text
    session_id = start_resp.json()["session_id"]

    # Reset write_guard so we only check the dispute create call
    write_guard.clear()

    resp = await app_client.post(
        "/disputes/create",
        json={"session_id": session_id, "role": "tenant"},
    )
    assert resp.status_code == 200, resp.text
    assert write_guard == [], f"unexpected JSON writes: {write_guard}"
