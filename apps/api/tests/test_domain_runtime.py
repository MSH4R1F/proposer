"""SHA-20 Phase 3 + 8: tests for the API-layer domain runtime resolver.

Covers:

- default deposit happy path (strict gates off — local-dev carve-out)
- unknown domain id → DomainNotFoundError
- domain absent from ENABLED_DOMAINS → gate_status = disabled
- research-stage domain w/ allowlist enforcement
- comma-separated env parsing (whitespace, blanks, dedupe, unknown rejection)
- prediction cache key changes when domain_spec_hash changes
- prediction cache key changes when ANY of the four artifact hashes change
- LangFuseTraceLogger / no-op tags include the Phase 8 trace-tag set
- strict-eval-gates fail-closed even for the default deposit baseline
- production-mode request against research-stage domain → DISABLED
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
    """Reload ``apps.api.src.config`` so each test sees a fresh APIConfig.

    By default the fixture turns ``DOMAIN_STRICT_EVAL_GATES`` off so that
    the legacy deposit-baseline carve-out is exercised. Tests that want
    to assert fail-closed behaviour pass ``DOMAIN_STRICT_EVAL_GATES=true``
    explicitly via the ``env`` dict.
    """

    def _reload(env: dict) -> None:
        # Default strict-gates off; tests can override.
        env_with_defaults = {"DOMAIN_STRICT_EVAL_GATES": "false", **env}
        for k, v in env_with_defaults.items():
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
    monkeypatch.delenv("DOMAIN_STRICT_EVAL_GATES", raising=False)
    monkeypatch.delenv("DOMAIN_GATE_ARTIFACT_DIR", raising=False)
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
        "employment.unfair_dismissal.v1",
        user_id="some-other-user",
        requested_mode="research",
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
        "employment.unfair_dismissal.v1",
        user_id="user-allowed",
        requested_mode="research",
    )
    assert ctx.gate_status == DomainGateStatus.ENABLED
    assert ctx.allowlist_status == DomainAllowlistStatus.ALLOWLISTED
    assert ctx.is_usable is True


def test_research_stage_rejects_production_mode(reload_config):
    """A research-stage domain cannot run with ``requested_mode=production``."""
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1,employment.unfair_dismissal.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
            "DOMAIN_EMPLOYMENT_BETA_ALLOWLIST_USER_IDS": "user-allowed",
        }
    )
    ctx = dr.resolve_domain_runtime(
        "employment.unfair_dismissal.v1",
        user_id="user-allowed",
        requested_mode="production",
    )
    assert ctx.gate_status == DomainGateStatus.DISABLED
    assert ctx.is_usable is False


def test_strict_gates_fail_closed_for_default_deposit(reload_config, tmp_path):
    """Audit D2: default deposit baseline fails closed with strict gates on.

    The deposit YAML stage is ``research`` (audit D1/D2): with strict
    gates ON and no artifact, BOTH the stage-mode policy (production not
    allowed for research-stage) AND the gate-check step would refuse
    the request. We assert the request is unusable; the precise status
    is whichever check fires first (currently DISABLED via stage policy).
    """
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
            "DOMAIN_STRICT_EVAL_GATES": "true",
            "DOMAIN_GATE_ARTIFACT_DIR": str(tmp_path / "no-gates-here"),
        }
    )
    # research mode does not require an artifact even with strict gates
    # on, so the gate status should be ENABLED for research.
    ctx = dr.resolve_domain_runtime(
        "housing.deposit.v1", requested_mode="research"
    )
    assert ctx.gate_status == DomainGateStatus.ENABLED

    # production mode under strict gates: REFUSED. The deposit YAML stage
    # is research, so stage policy refuses first. Audit D2: result is
    # unusable regardless of the precise reason.
    ctx_prod = dr.resolve_domain_runtime(
        "housing.deposit.v1", requested_mode="production"
    )
    assert ctx_prod.gate_status in {
        DomainGateStatus.DISABLED,
        DomainGateStatus.GATE_MISSING,
        DomainGateStatus.GATE_STALE,
    }
    assert ctx_prod.is_usable is False


def test_strict_gates_fail_closed_when_artifact_missing_for_production_stage(
    reload_config, tmp_path
):
    """If a domain were production-stage AND strict gates on AND no
    artifact, gate check returns GATE_MISSING."""
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
            "DOMAIN_STRICT_EVAL_GATES": "true",
            "DOMAIN_GATE_ARTIFACT_DIR": str(tmp_path / "no-gates"),
        }
    )
    # Build a synthetic spec at production stage to exercise the
    # gate-check branch directly via DomainGateChecker.
    from apps.api.src.domain_runtime import DomainGateChecker
    from domain_core import get_domain_spec

    spec = get_domain_spec("housing.deposit.v1")
    checker = DomainGateChecker(gate_dir=tmp_path / "no-gates")
    result = checker.check(spec, requested_mode="production")
    assert result.status == DomainGateStatus.GATE_MISSING


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


def test_domain_tags_include_phase8_keys(reload_config):
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    ctx = dr.resolve_domain_runtime("housing.deposit.v1")
    tags = ctx.domain_tags()
    # Core Phase-3 tags.
    assert tags["domain.id"] == "housing.deposit.v1"
    assert tags["domain.family"] == "housing"
    assert tags["domain.domain_version"] == "v1"
    assert tags["domain.stage"] == "research"
    assert tags["prediction_mode"] == "production"
    assert tags["cross_domain_retrieval"] == "false"
    # Phase-8 tag superset present.
    assert tags["forum"] == "deposit_scheme_adjudication"
    assert tags["retrieval.namespace"] == "housing_deposit_v1_legacy"
    assert tags["prompt_pack.id"] == "housing.deposit.v1"
    assert tags["ontology.id"] == "housing.deposit.v1"
    assert tags["eval_suite.id"] == "housing.deposit.v1"
    # Per-citation / runtime-only tags are dropped when None.
    assert "source.publisher" not in tags
    assert "source.kind" not in tags
    assert "llm.role" not in tags
    assert "llm.provider" not in tags


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


def test_prediction_cache_segment_uses_real_hashes(reload_config):
    """Phase 8: the cache segment carries the real prompt-pack / ontology
    / namespace / corpus values, not the legacy sentinels."""
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    from apps.api.src.services.prediction_service import (
        _build_domain_cache_segment,
        _resolve_domain_artifact_hashes,
    )
    from llm_orchestrator.models.prediction_v2 import PredictionMode

    ctx = dr.resolve_domain_runtime("housing.deposit.v1")
    seg = _build_domain_cache_segment(
        ctx, mode=PredictionMode.HYBRID, cross_domain=False
    )
    # Real prompt-pack hash is 64 hex chars (sha256), not the sentinel.
    hashes = _resolve_domain_artifact_hashes(ctx)
    assert hashes["prompt_pack_hash"] != "legacy_deposit_v1"
    assert len(hashes["prompt_pack_hash"]) == 64
    assert hashes["ontology_hash"] != "legacy_deposit_v1"
    assert len(hashes["ontology_hash"]) == 64
    assert hashes["corpus_version"] == "legacy_2025_pre_sha20"
    assert hashes["namespace_id"] == "housing_deposit_v1_legacy"
    # Segment incorporates them all.
    assert f"|pp={hashes['prompt_pack_hash']}" in seg
    assert f"|on={hashes['ontology_hash']}" in seg
    assert f"|cv={hashes['corpus_version']}" in seg
    assert f"|ns={hashes['namespace_id']}" in seg


def test_prediction_cache_segment_changes_when_pack_content_changes(
    reload_config, monkeypatch
):
    """Mutating the prompt pack file content must change the cache segment."""
    dr = reload_config(
        {
            "ENABLED_DOMAINS": "housing.deposit.v1",
            "DEFAULT_DOMAIN": "housing.deposit.v1",
        }
    )
    from apps.api.src.services import prediction_service as ps_module
    from llm_orchestrator.models.prediction_v2 import PredictionMode
    from llm_orchestrator.prompts.packs import (
        BasePromptPack,
        get_prompt_pack,
        hash_prompt_pack,
    )

    ctx = dr.resolve_domain_runtime("housing.deposit.v1")

    seg_before = ps_module._build_domain_cache_segment(
        ctx, mode=PredictionMode.HYBRID, cross_domain=False
    )

    # Patch the prompt-pack lookup to return a mutated pack so we can
    # observe that the cache segment changes when the pack changes.
    pack = get_prompt_pack("housing.deposit.v1")
    mutated = BasePromptPack(
        id=pack.id,
        schema_version=pack.schema_version,
        forum_profile_id=pack.forum_profile_id,
        intake_system=pack.intake_system,
        prediction_system=pack.prediction_system + "\n# mutated for test",
        mediator_system=pack.mediator_system,
        output_contract=pack.output_contract,
        expected_llm_roles=list(pack.expected_llm_roles),
        safety_version=pack.safety_version,
        cite_or_abstain_version=pack.cite_or_abstain_version,
        output_contract_version=pack.output_contract_version,
        forum_policy_version=pack.forum_policy_version,
    )
    new_hash = hash_prompt_pack(mutated)
    assert new_hash != hash_prompt_pack(pack)

    import llm_orchestrator.prompts.packs as packs_module

    monkeypatch.setattr(
        packs_module, "get_prompt_pack", lambda _domain: mutated
    )

    seg_after = ps_module._build_domain_cache_segment(
        ctx, mode=PredictionMode.HYBRID, cross_domain=False
    )
    assert seg_before != seg_after
    assert f"|pp={new_hash}" in seg_after


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
