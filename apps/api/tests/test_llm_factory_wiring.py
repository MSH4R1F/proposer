"""Smoke tests for role-aware LLM dependency wiring."""

from __future__ import annotations

from apps.api.src import dependencies
from llm_orchestrator.clients.openai_client import OpenAIClient
from llm_orchestrator.clients.types import LLMProvider


class _FakeAsyncOpenAI:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key
        self.responses = object()


def test_prediction_debug_dependency_uses_openai_when_role_env_set(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PREDICTION_PROVIDER", "openai")
    monkeypatch.setenv("LLM_PREDICTION_PRIMARY_MODEL", "gpt-5.4-mini")
    monkeypatch.setattr(
        "llm_orchestrator.clients.openai_client.AsyncOpenAI",
        _FakeAsyncOpenAI,
    )
    dependencies._cached_agent_loop_client.cache_clear()
    dependencies._cached_agent_loop_provider.cache_clear()

    try:
        client = dependencies.get_agent_loop_client()
        provider = dependencies.get_agent_loop_provider()
    finally:
        dependencies._cached_agent_loop_client.cache_clear()
        dependencies._cached_agent_loop_provider.cache_clear()

    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-5.4-mini"
    assert provider is LLMProvider.OPENAI
