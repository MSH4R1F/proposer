import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_db_session_can_query(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT COUNT(*) FROM intake_sessions"))
    assert result.scalar_one() == 0
