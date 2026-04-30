import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.evidence_repo import EvidenceRepo
from packages.llm_orchestrator.models.evidence import EvidenceMetadata


def _make_evidence(
    case_id: str = "case-1",
    evidence_id: str = "ev-1",
    evidence_type: str = "receipts",
    file_url: str = "https://example.com/foo",
    file_name: str = "foo.pdf",
    file_type: str = "application/pdf",
    description: str = "A receipt",
    extracted_text=None,
    image_description=None,
    **overrides,
):
    return EvidenceMetadata(
        case_id=case_id,
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        file_url=file_url,
        file_name=file_name,
        file_type=file_type,
        description=description,
        extracted_text=extracted_text,
        image_description=image_description,
        **overrides,
    )


@pytest.mark.asyncio
async def test_evidence_roundtrip(db_session: AsyncSession) -> None:
    repo = EvidenceRepo(db_session)
    e = _make_evidence()
    await repo.save(e)
    await db_session.commit()
    loaded = await repo.get(e.case_id, e.evidence_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == e.model_dump(mode="json")


@pytest.mark.asyncio
async def test_get_by_case_id_filters_correctly(db_session: AsyncSession) -> None:
    repo = EvidenceRepo(db_session)
    a = _make_evidence(case_id="case-A", evidence_id="ev-1")
    b = _make_evidence(case_id="case-A", evidence_id="ev-2")
    c = _make_evidence(case_id="case-B", evidence_id="ev-1")
    await repo.save(a)
    await repo.save(b)
    await repo.save(c)
    await db_session.commit()
    listed = await repo.get_by_case_id("case-A")
    assert {e.evidence_id for e in listed} == {"ev-1", "ev-2"}


@pytest.mark.asyncio
async def test_duplicate_evidence_id_across_cases(db_session: AsyncSession) -> None:
    """Composite (case_id, evidence_id) lets duplicate evidence_ids coexist across cases."""
    repo = EvidenceRepo(db_session)
    a = _make_evidence(case_id="case-A", evidence_id="ev-1", description="A")
    b = _make_evidence(case_id="case-B", evidence_id="ev-1", description="B")
    await repo.save(a)
    await repo.save(b)
    await db_session.commit()
    la = await repo.get("case-A", "ev-1")
    lb = await repo.get("case-B", "ev-1")
    assert la is not None and lb is not None
    assert la.description == "A"
    assert lb.description == "B"


@pytest.mark.asyncio
async def test_delete_removes_only_matching(db_session: AsyncSession) -> None:
    repo = EvidenceRepo(db_session)
    a = _make_evidence(case_id="case-A", evidence_id="ev-1")
    b = _make_evidence(case_id="case-A", evidence_id="ev-2")
    await repo.save(a)
    await repo.save(b)
    await db_session.commit()

    await repo.delete("case-A", "ev-1")
    await db_session.commit()

    assert await repo.get("case-A", "ev-1") is None
    assert await repo.get("case-A", "ev-2") is not None
