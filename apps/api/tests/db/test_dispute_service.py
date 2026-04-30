"""
Integration tests for the UoW-backed DisputeService (Phase 6.2).

These tests exercise the full persistence path against a real (migrated)
Postgres database spun up by pytest-postgresql.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from apps.api.src.services.dispute_service import DisputeService
from packages.llm_orchestrator.models.case_file import PartyRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def dispute_service(db_sessionmaker):
    return DisputeService(sessionmaker=db_sessionmaker)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dispute_persists_row(dispute_service: DisputeService) -> None:
    """create_dispute must write a row that is retrievable by ID."""
    d = await dispute_service.create_dispute(role=PartyRole.TENANT.value)
    assert d.dispute_id
    assert d.invite_code

    loaded = await dispute_service.get_dispute(d.dispute_id)
    assert loaded is not None
    assert loaded.invite_code == d.invite_code
    assert loaded.dispute_id == d.dispute_id


@pytest.mark.asyncio
async def test_get_dispute_by_invite_code_normalizes(dispute_service: DisputeService) -> None:
    """get_dispute_by_invite_code must match regardless of case."""
    d = await dispute_service.create_dispute(role=PartyRole.TENANT.value)

    loaded = await dispute_service.get_dispute_by_invite_code(d.invite_code.lower())
    assert loaded is not None
    assert loaded.dispute_id == d.dispute_id


@pytest.mark.asyncio
async def test_invite_code_unique_constraint(db_sessionmaker, monkeypatch) -> None:
    """Duplicate invite codes trigger retry; service lands on first unique code."""
    import apps.api.src.services.dispute_service as svc_mod

    codes = iter(["DUPCODE", "DUPCODE", "FRESH01"])
    monkeypatch.setattr(svc_mod, "generate_invite_code", lambda: next(codes))

    svc = DisputeService(sessionmaker=db_sessionmaker)
    a = await svc.create_dispute(role=PartyRole.TENANT.value)
    b = await svc.create_dispute(role=PartyRole.TENANT.value)

    assert a.invite_code == "DUPCODE"
    assert b.invite_code == "FRESH01"  # service regenerated past the duplicate


@pytest.mark.asyncio
async def test_delete_dispute(dispute_service: DisputeService) -> None:
    """delete_dispute returns True for existing disputes, False for unknown IDs."""
    d = await dispute_service.create_dispute(role=PartyRole.TENANT.value)

    assert await dispute_service.delete_dispute(d.dispute_id) is True
    assert await dispute_service.get_dispute(d.dispute_id) is None
    assert await dispute_service.delete_dispute("does-not-exist") is False


@pytest.mark.asyncio
async def test_list_disputes_returns_all(dispute_service: DisputeService) -> None:
    """list_disputes returns all created disputes."""
    d1 = await dispute_service.create_dispute(role=PartyRole.TENANT.value)
    d2 = await dispute_service.create_dispute(role=PartyRole.LANDLORD.value)

    listed = await dispute_service.list_disputes()
    ids = {d.dispute_id for d in listed}

    assert d1.dispute_id in ids
    assert d2.dispute_id in ids
