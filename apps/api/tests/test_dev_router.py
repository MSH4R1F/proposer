"""Tests for the debug agent-smoke router.

Covers:
- route is mounted only when debug=True
- returns 404 when debug=False
- forwards prompt into AgentLoop and returns the final_text + trace
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.src.config import APIConfig
from apps.api.src.main import create_app
from llm_orchestrator.agent_loop.loop import AgentTurnResponse


def _debug_config(**overrides) -> APIConfig:
    return APIConfig(
        debug=True,
        anthropic_api_key="test-key",
        openai_api_key="",
        supabase_url="",
        supabase_key="",
        **overrides,
    )


def _prod_config(**overrides) -> APIConfig:
    return APIConfig(
        debug=False,
        anthropic_api_key="test-key",
        openai_api_key="",
        supabase_url="",
        supabase_key="",
        **overrides,
    )


@pytest.mark.asyncio
async def test_agent_smoke_absent_when_debug_false() -> None:
    app = create_app(_prod_config())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/dev/agent-smoke", json={"prompt": "hi"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_smoke_runs_end_to_end_when_debug_true() -> None:
    app = create_app(_debug_config())

    # Override the cached client dependency so no real API call is made.
    from apps.api.src.dependencies import get_agent_loop_client

    fake_client = AsyncMock()
    # Scripted two-turn response: tool_use(add) -> end_turn("42")
    fake_client.run_agent_turn = AsyncMock(side_effect=[
        AgentTurnResponse(
            content_blocks=[
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "add",
                    "input": {"a": 17, "b": 25},
                }
            ],
            stop_reason="tool_use",
            tokens_in=10,
            tokens_out=5,
            model_used="claude-test",
        ),
        AgentTurnResponse(
            content_blocks=[{"type": "text", "text": "42"}],
            stop_reason="end_turn",
            tokens_in=12,
            tokens_out=3,
            model_used="claude-test",
        ),
    ])
    app.dependency_overrides[get_agent_loop_client] = lambda: fake_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/dev/agent-smoke",
            json={"prompt": "add 17 and 25"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["final_text"] == "42"
    assert body["termination"] == "end_turn"
    assert "trace_summary" in body
    assert len(body["trace_summary"]["steps"]) >= 3  # at least 2 model_turns + termination


@pytest.mark.asyncio
async def test_agent_smoke_rejects_empty_prompt() -> None:
    app = create_app(_debug_config())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/dev/agent-smoke", json={"prompt": ""})
    # Pydantic min_length validation -> 422.
    assert resp.status_code == 422
