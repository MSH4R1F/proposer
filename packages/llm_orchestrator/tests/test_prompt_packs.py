"""Tests for SHA-20 prompt packs (SHA-62, SHA-119).

These tests assert structural properties (the contract) and provider/role
neutrality. Behavioural tests for forum policy live in
``test_forum_policy.py``.
"""

from __future__ import annotations

import json

import pytest

from domain_core.registry import load_domain_specs

from llm_orchestrator.prompts.packs import (
    REGISTRY,
    BasePromptPack,
    PromptPack,
    get_prompt_pack,
    hash_prompt_pack,
)


ALL_PACK_IDS = [
    "housing.deposit.v1",
    "housing.repairs_social.v1",
    "housing.property_chamber.rro.v1",
    "employment.unfair_dismissal.v1",
]


# ---------------------------------------------------------------------------
# Registry / contract
# ---------------------------------------------------------------------------


def test_registry_contains_all_four_domains() -> None:
    assert sorted(REGISTRY) == sorted(ALL_PACK_IDS)


@pytest.mark.parametrize("pack_id", ALL_PACK_IDS)
def test_pack_satisfies_protocol(pack_id: str) -> None:
    pack = get_prompt_pack(pack_id)
    assert isinstance(pack, BasePromptPack)
    assert isinstance(pack, PromptPack)


@pytest.mark.parametrize("pack_id", ALL_PACK_IDS)
def test_pack_id_matches_domain_spec(pack_id: str) -> None:
    pack = get_prompt_pack(pack_id)
    assert pack.id == pack_id


def test_unknown_pack_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_prompt_pack("housing.unknown.v1")


@pytest.mark.parametrize("pack_id", ALL_PACK_IDS)
def test_pack_forum_profile_id_is_in_domain_spec(pack_id: str) -> None:
    """Each pack's forum_profile_id must reference a forum in its domain spec."""
    specs = load_domain_specs()
    spec = specs[pack_id]
    pack = get_prompt_pack(pack_id)
    forum_values = {p.forum.value for p in spec.forum_profiles}
    assert pack.forum_profile_id in forum_values


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pack_id", ALL_PACK_IDS)
def test_hash_is_stable_and_hex(pack_id: str) -> None:
    pack = get_prompt_pack(pack_id)
    h1 = hash_prompt_pack(pack)
    h2 = hash_prompt_pack(pack)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    int(h1, 16)


def test_hashes_differ_across_packs() -> None:
    seen = {pack_id: hash_prompt_pack(get_prompt_pack(pack_id)) for pack_id in ALL_PACK_IDS}
    assert len(set(seen.values())) == len(ALL_PACK_IDS)


def test_hash_changes_when_pack_changes() -> None:
    """Hash regression: changing the prediction system text must change the hash.

    This is the contract Phase 3's cache key relies on. The legacy sentinel
    prompt-pack hash (``legacy_deposit_v1``) is intentionally NOT equal to
    any real pack hash, so once the apps prediction service swaps in a real
    hash, cached entries with the sentinel will be invalidated.
    """
    pack = get_prompt_pack("housing.deposit.v1")
    h1 = hash_prompt_pack(pack)
    mutated = BasePromptPack(
        id=pack.id,
        schema_version=pack.schema_version,
        forum_profile_id=pack.forum_profile_id,
        intake_system=pack.intake_system,
        prediction_system=pack.prediction_system + "\n# mutated",
        mediator_system=pack.mediator_system,
        output_contract=pack.output_contract,
        expected_llm_roles=list(pack.expected_llm_roles),
        safety_version=pack.safety_version,
        cite_or_abstain_version=pack.cite_or_abstain_version,
        output_contract_version=pack.output_contract_version,
        forum_policy_version=pack.forum_policy_version,
    )
    h2 = hash_prompt_pack(mutated)
    assert h1 != h2


def test_real_hash_differs_from_legacy_sentinel() -> None:
    """The Phase-3 cache-key sentinel differs from any real pack hash."""
    sentinel = "legacy_deposit_v1"
    for pack_id in ALL_PACK_IDS:
        assert hash_prompt_pack(get_prompt_pack(pack_id)) != sentinel


# ---------------------------------------------------------------------------
# Role neutrality (no provider/model leakage)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pack_id", ALL_PACK_IDS)
def test_pack_does_not_pin_any_provider_or_model(pack_id: str) -> None:
    """Packs declare expected ROLES, never concrete provider/model names.

    Provider/model selection is owned by SHA-113/114 (LLMRole + provider
    factories). Packs that pin a provider would couple the prompt layer to a
    runtime concern and break swappability.
    """
    pack = get_prompt_pack(pack_id)
    forbidden_tokens = (
        "claude-3",
        "claude-4",
        "claude-3-5",
        "gpt-4",
        "gpt-4o",
        "gpt-3.5",
        "gemini",
        "anthropic.com/v1",
        "api.openai.com",
        "model:",
        '"model":',
    )
    haystack = (
        pack.intake_system
        + "\n"
        + pack.prediction_system
        + "\n"
        + pack.mediator_system
        + "\n"
        + json.dumps(pack.output_contract, sort_keys=True)
    ).lower()
    for token in forbidden_tokens:
        assert token.lower() not in haystack, (
            f"Pack {pack_id} leaks provider/model token {token!r}"
        )
    # Roles must be a subset of the canonical set.
    assert set(pack.expected_llm_roles) <= {"intake", "predict", "mediate"}


# ---------------------------------------------------------------------------
# Output contract: schema-compatible deposit baseline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pack_id", ALL_PACK_IDS)
def test_output_contract_carries_required_envelope_fields(pack_id: str) -> None:
    pack = get_prompt_pack(pack_id)
    contract = pack.output_contract
    assert contract["type"] == "object"
    required = set(contract["required"])
    assert {"issue_type", "outcome", "raw_confidence", "reasoning",
            "supporting_cases", "evidence_strength", "matter_type",
            "forum"} <= required


def test_deposit_pack_prediction_system_remains_schema_compatible() -> None:
    """The deposit pack must not lose any field the legacy IRAC prompt declared.

    We can't take a live snapshot of model output without calling an LLM, so
    instead we assert that the pack's prediction_system text still carries
    the IRAC headers (Issue/Rule/Application/Conclusion), the legacy JSON
    schema marker, and references the unchanged output keys.
    """
    pack = get_prompt_pack("housing.deposit.v1")
    text = pack.prediction_system
    for marker in ("**Issue**", "**Rule**", "**Application**", "**Conclusion**"):
        assert marker in text
    # Legacy output schema fields must still be present in the system prompt.
    for key in ("issue_type", "outcome", "raw_confidence", "predicted_amount",
                "supporting_cases", "evidence_strength"):
        assert key in text
    # Legal-information disclaimer must still be enforced.
    assert "legal information" in text.lower()
    assert "not legal advice" in text.lower()


# ---------------------------------------------------------------------------
# Domain-content guardrails
# ---------------------------------------------------------------------------


def test_rro_pack_has_explicit_scope_fence_in_prediction_prompt() -> None:
    pack = get_prompt_pack("housing.property_chamber.rro.v1")
    text = pack.prediction_system.lower()
    # The pack must call out the scope fence so the model sees it pre-generation.
    for term in ("leasehold", "tenant fees act", "park homes", "building safety"):
        assert term in text


def test_employment_pack_routes_unsupported_matters_to_uncertain() -> None:
    pack = get_prompt_pack("employment.unfair_dismissal.v1")
    text = pack.prediction_system.lower()
    assert "wage" in text
    assert "discrimination" in text
    assert "whistleblowing" in text
    assert "unsupported" in text or "uncertain" in text
    # 2026 weekly-cap value (£751) must appear in the pack.
    assert "751" in pack.prediction_system


def test_ombudsman_pack_uses_complaint_outcome_framing_not_court_damages() -> None:
    pack = get_prompt_pack("housing.repairs_social.v1")
    text = pack.prediction_system.lower()
    assert "complaint outcome" in text
    # Awaab's Law and statutory backdrops must be referenced.
    assert "awaab" in text
    assert "homes (fitness for human habitation)" in text
    assert "comparator-award ledger" in text
    assert "predicted_amount only from cited comparator awards" in text
    assert "amount_band" in text
