"""Unit tests for DomainPack registry."""

from __future__ import annotations

import pytest

from domain_packs.registry import (
    DomainPack,
    DomainPackNotFoundError,
    get_domain_pack,
)


def test_get_domain_pack_returns_pack_for_known_id():
    pack = get_domain_pack("housing.repairs_social.v1")
    assert pack.domain_id == "housing.repairs_social.v1"
    assert len(pack.factors.factors) == 15  # per Stream B catalog
    assert pack.outcomes.domain_id == "housing.repairs_social.v1"


def test_get_domain_pack_unknown_id_raises():
    with pytest.raises(DomainPackNotFoundError):
        get_domain_pack("nonexistent.domain.v99")


def test_get_domain_pack_loads_deposit_pack():
    """housing.deposit.v1 was scaffolded in Task 4.2 (PR 4). The pack must now
    load with its 3-factor catalog."""
    pack = get_domain_pack("housing.deposit.v1")
    assert pack.domain_id == "housing.deposit.v1"
    assert len(pack.factors.factors) == 3  # per Stream C PR 4 catalog
    assert pack.outcomes.domain_id == "housing.deposit.v1"


def test_get_domain_pack_missing_dir_branch_raises(monkeypatch, tmp_path):
    """The 'directory missing' branch must still raise distinctly from 'unknown
    id' for any registered-but-missing pack. Previously verified by deposit;
    now verified by injecting a stub registration that points to a missing dir."""
    from domain_packs import registry

    fake_dir = tmp_path / "does_not_exist"
    fake_id = "test.missingdir.v1"
    monkeypatch.setitem(registry._KNOWN_PACK_DIRS, fake_id, fake_dir)
    # Cache is keyed per domain_id, so this lookup is fresh.
    with pytest.raises(DomainPackNotFoundError, match="directory missing"):
        get_domain_pack(fake_id)


def test_domain_pack_is_frozen():
    pack = get_domain_pack("housing.repairs_social.v1")
    with pytest.raises((AttributeError, ValueError)):
        pack.domain_id = "modified"


def test_domain_pack_has_all_required_attrs():
    pack = get_domain_pack("housing.repairs_social.v1")
    for attr in (
        "domain_id", "spec", "factors", "outcomes", "remedies",
        "retrieval_profile", "graph_quality_gate", "extractor_strategy",
        "annotation_rubric",
    ):
        assert hasattr(pack, attr), f"missing attr: {attr}"


def test_render_factor_card_method_exists():
    pack = get_domain_pack("housing.repairs_social.v1")
    assert callable(pack.render_factor_card)


def test_is_kg_usable_method_exists():
    pack = get_domain_pack("housing.repairs_social.v1")
    assert callable(pack.is_kg_usable)


def test_loading_caches_per_domain_id():
    """Repeated lookup returns the same instance."""
    p1 = get_domain_pack("housing.repairs_social.v1")
    p2 = get_domain_pack("housing.repairs_social.v1")
    assert p1 is p2
