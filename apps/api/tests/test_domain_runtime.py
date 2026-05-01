"""SHA-20 Phase 3: tests for the API-layer domain runtime resolver.

Covers the resolution rules listed in the Phase 3 plan:

- default deposit happy path
- unknown domain id → DomainNotFoundError
- domain absent from ENABLED_DOMAINS → gate_status = disabled
- research-stage domain w/ allowlist enforcement
- comma-separated env parsing (whitespace, blanks, dedupe, unknown rejection)
- prediction cache key changes when domain_spec_hash changes
- LangFuseTraceLogger / no-op tags include domain.* tags
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

from apps.api.src import config as config_module
from apps.api.src.domain_runtime import (
    DomainAllowlistStatus,
    DomainGateStatus,
    DomainNotFoundError,
    resolve_domain_runtime,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reload_config(monkeypatch):
    """Reload ``apps.api.src.config`` so each test sees a fresh APIConfig."""

    def _reload(env: dict) -> None:
        for k, v in env.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
        importlib.reload(config_module)
        # The domain_runtime module captured `config` at import time, so we
        # must reload it as well to bind to the new module-level instance.
        from apps.api.src import domain_runtime as dr_module

        importlib.reload(dr_module)
        return dr_module

    yield _reload

    # Restore canonical config for any later imports. Reset env first so
    # validation succeeds.
    monkeypatch.delenv("ENABLED_DOMAINS", raising=False)
    monkeypatch.delenv("DEFAULT_DOMAIN", raising=False)
    monkeypatch.delenv("DOMAIN_BETA_ALLOWLIST_USER_IDS", raising=False)
    monkeypatch.delenv("DOMAIN_EMPLOYMENT_BETA_ALLOWLIST_USER_IDS", raising=False)
    importlib.reload(config_module)


# ---------------------------------------------------------------------------
# Resolution rules
# ---------------------------------------------------------------------------


def test_resolve_default_deposit_happy_path(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    ctx = dr.resolve_domain_runtime(None)
    assert ctx.domain_id == "housing.deposit.v1"
    assert ctx.gate_status == DomainGateStatus.ENABLED
    # Compatibility carve-out: default deposit is unrestricted even though
    # its YAML stage is ``research`` (deposit baseline must keep working
    # for anonymous traffic until the launch gate is signed in Phase 8).
    assert ctx.allowlist_status == DomainAllowlistStatus.UNRESTRICTED
    assert ctx.is_usable is True


def test_resolve_unknown_domain_raises(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    with pytest.raises(DomainNotFoundError):
        dr.resolve_domain_runtime("housing.deposit.v999")


def test_resolve_disabled_domain_returns_disabled(reload_config):
    dr = reload_config(
        {
            # Only deposit is enabled; employment is registered but disabled.
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
            "DOMAIN_EMPLOYMENT_BETA_ALLOWLIST_USER_IDS": "user-x",
        }
    )
    ctx = dr.resolve_domain_runtime("employment.unfair_dismissal.v1", user_id="user-x")
    assert ctx.gate_status == DomainGateStatus.DISABLED
    # Allowlist still resolves so callers can distinguish "gate blocks"
    # from "user blocks". With the user on the allowlist, status is allowlisted.
    assert ctx.allowlist_status == DomainAllowlistStatus.ALLOWLISTED
    assert ctx.is_usable is False


def test_research_domain_blocks_non_allowlisted_user(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1,employment.unfair_dismissal.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
            "DOMAIN_EMPLOYMENT_BETA_ALLOWLIST_USER_IDS": "user-allowed",
        }
    )
    ctx = dr.resolve_domain_runtime(
        "employment.unfair_dismissal.v1", user_id="some-other-user"
    )
    assert ctx.gate_status == DomainGateStatus.ENABLED
    assert ctx.allowlist_status == DomainAllowlistStatus.BLOCKED
    assert ctx.is_usable is False


def test_research_domain_allows_allowlisted_user(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1,employment.unfair_dismissal.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
            "DOMAIN_EMPLOYMENT_BETA_ALLOWLIST_USER_IDS": "user-allowed",
        }
    )
    ctx = dr.resolve_domain_runtime(
        "employment.unfair_dismissal.v1", user_id="user-allowed"
    )
    assert ctx.gate_status == DomainGateStatus.ENABLED
    assert ctx.allowlist_status == DomainAllowlistStatus.ALLOWLISTED
    assert ctx.is_usable is True


# ---------------------------------------------------------------------------
# CSV env parsing
# ---------------------------------------------------------------------------


def test_csv_env_parser_handles_whitespace_blanks_and_dedupe():
    from apps.api.src.config import _parse_csv_env

    parsed = _parse_csv_env(" a , , b,a, c ,, ")
    assert parsed == ["a", "b", "c"]


def test_config_rejects_unknown_domain_at_startup(reload_config):
    with pytest.raises(ValueError, match="unknown domain"):
        reload_config(
            {
                "ENABLED_DOMAINS": "housing.deposit.v1,housing.unknown.v9",
                "DEFAULT_DOMAIN": "housing.deposit.v1",
            }
        )


def test_config_rejects_default_outside_enabled(reload_config):
    with pytest.raises(ValueError, match="ENABLED_DOMAINS"):
        reload_config(
            {
                "ENABLED_DOMAINS": "housing.deposit.v1",
                "DEFAULT_DOMAIN": "employment.unfair_dismissal.v1",
            }
        )


# ---------------------------------------------------------------------------
# Domain tags + cache key
# ---------------------------------------------------------------------------


def test_domain_tags_include_phase3_keys(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    ctx = dr.resolve_domain_runtime("housing.deposit.v1")
    tags = ctx.domain_tags()
    assert tags["domain.id"] == "housing.deposit.v1"
    assert tags["domain.family"] == "housing"
    assert tags["domain.domain_version"] == "v1"
    assert tags["domain.stage"] == "research"
    assert tags["prediction_mode"] == "production"
    assert tags["cross_domain_retrieval"] == "false"


def test_prediction_cache_segment_changes_with_spec_hash(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    from apps.api.src.services.prediction_service import _build_domain_cache_segment
    from llm_orchestrator.models.prediction_v2 import PredictionMode

    ctx = dr.resolve_domain_runtime("housing.deposit.v1")
    seg_a = _build_domain_cache_segment(
        ctx, mode=PredictionMode.HYBRID, cross_domain=False
    )

    # Mutate the captured spec hash by wrapping the runtime in a clone
    # whose ``domain_spec_hash`` differs.
    ctx_b = ctx.__class__(
        domain_spec=ctx.domain_spec,
        gate_status=ctx.gate_status,
        allowlist_status=ctx.allowlist_status,
        routing_metadata=dict(ctx.routing_metadata),
        core=ctx.core,
        prediction_mode=ctx.prediction_mode,
        cross_domain_retrieval=ctx.cross_domain_retrieval,
    )
    # Patch the property at the class level just for this call.
    fake = MagicMock()
    fake.domain_spec_hash = "different_hash"
    fake.domain_id = ctx_b.domain_id
    fake.domain_spec = ctx_b.domain_spec
    seg_b = _build_domain_cache_segment(
        fake, mode=PredictionMode.HYBRID, cross_domain=False
    )
    assert seg_a != seg_b
    assert "different_hash" in seg_b


def test_prediction_cache_segment_changes_with_mode(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    from apps.api.src.services.prediction_service import _build_domain_cache_segment
    from llm_orchestrator.models.prediction_v2 import PredictionMode

    ctx = dr.resolve_domain_runtime("housing.deposit.v1")
    seg_hybrid = _build_domain_cache_segment(
        ctx, mode=PredictionMode.HYBRID, cross_domain=False
    )
    seg_rag = _build_domain_cache_segment(
        ctx, mode=PredictionMode.RAG_ONLY, cross_domain=False
    )
    seg_cross = _build_domain_cache_segment(
        ctx, mode=PredictionMode.HYBRID, cross_domain=True
    )
    assert seg_hybrid != seg_rag
    assert seg_hybrid != seg_cross


def test_trace_summary_carries_domain_metadata(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    from llm_orchestrator.agent_loop.trace import TraceLogger, TraceTerminationReason

    ctx = dr.resolve_domain_runtime("housing.deposit.v1")
    logger = TraceLogger()
    logger.start_trace(trace_id="t-1", tags=ctx.domain_tags())
    summary = logger.end_trace(termination=TraceTerminationReason.END_TURN)
    assert summary.metadata.get("domain.id") == "housing.deposit.v1"
    assert summary.metadata.get("domain.family") == "housing"
