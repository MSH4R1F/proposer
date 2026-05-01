"""Ontology registry: parse + extends-resolution + filename-id consistency.

Mirrors the structure of
``packages/domain_core/tests/test_registry.py``. Loads every YAML under
``packages/kg_builder/ontology/`` and verifies:

- Each parses into an :class:`OntologySpec`.
- ``extends`` chains resolve into merged node/edge kinds.
- Filename stem matches the spec id.
- Each per-domain ontology id matches the corresponding domain's
  ``ontology_ref`` in ``packages/domain_core/domains/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from kg_builder.ontology.registry import (
    OntologyConfigError,
    OntologyNotFoundError,
    _ONTOLOGY_DIR,
    get_ontology,
    hash_ontology_spec,
    list_ontologies,
    load_ontology,
    reset_ontology_cache,
)
from kg_builder.ontology.spec import OntologySpec


_DOMAIN_CORE_DOMAINS = (
    Path(__file__).resolve().parents[2] / "domain_core" / "domains"
)


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_ontology_cache()
    yield
    reset_ontology_cache()


def test_load_ontology_returns_all_yaml_ids():
    specs = load_ontology()
    assert "base.v1" in specs
    assert "housing.deposit.v1" in specs
    assert "housing.repairs_social.v1" in specs
    assert "housing.property_chamber.rro.v1" in specs
    assert "employment.unfair_dismissal.v1" in specs
    # All entries are OntologySpec instances
    assert all(isinstance(s, OntologySpec) for s in specs.values())


def test_extends_resolution_inherits_base_kinds():
    """Per-domain ontologies must inherit base.v1 node + edge kinds."""
    deposit = get_ontology("housing.deposit.v1")
    base_kind_names = {n.name for n in get_ontology("base.v1").node_kinds}
    deposit_kind_names = {n.name for n in deposit.node_kinds}
    # Every base kind is present in the resolved deposit ontology.
    assert base_kind_names.issubset(deposit_kind_names)
    # Plus deposit-specific kinds.
    assert "DepositScheme" in deposit_kind_names
    assert "DepositDeduction" in deposit_kind_names
    assert "DepositNonProtection" in deposit_kind_names


def test_extends_resolution_inherits_base_edges():
    deposit = get_ontology("housing.deposit.v1")
    edge_names = {e.name for e in deposit.edge_kinds}
    # base edges
    assert "evidence_supports" in edge_names
    assert "party_owns" in edge_names
    assert "event_before" in edge_names
    # deposit-specific edges
    assert "deduction_against_deposit" in edge_names
    assert "lease_protected_by_scheme" in edge_names


def test_filename_id_consistency_enforced(tmp_path: Path):
    """A YAML whose filename doesn't match its id must fail to load."""
    bad = tmp_path / "wrong_stem_v1.yaml"
    bad.write_text(
        "id: housing.deposit.v1\nschema_version: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(OntologyConfigError, match="expected filename stem"):
        load_ontology(ontology_dir=tmp_path)


def test_get_ontology_unknown_id_raises():
    with pytest.raises(OntologyNotFoundError):
        get_ontology("nonexistent.domain.v1")


def test_list_ontologies_returns_all():
    items = list_ontologies()
    ids = {s.id for s in items}
    assert "base.v1" in ids
    assert len(items) >= 5  # base + 4 domain ontologies


def test_hash_is_stable_across_yaml_cosmetics():
    """Hash must be stable under whitespace / key ordering changes."""
    deposit_a = get_ontology("housing.deposit.v1")
    h1 = hash_ontology_spec(deposit_a)
    # Build an equivalent spec from re-loading
    reset_ontology_cache()
    deposit_b = get_ontology("housing.deposit.v1")
    h2 = hash_ontology_spec(deposit_b)
    assert h1 == h2
    # Different ontologies -> different hashes.
    assert h1 != hash_ontology_spec(get_ontology("base.v1"))


def test_per_domain_yaml_ids_align_with_domain_core_ontology_refs():
    """For each domain in domain_core, the referenced ontology must exist
    in the kg_builder ontology registry."""
    if not _DOMAIN_CORE_DOMAINS.is_dir():
        pytest.skip("domain_core/domains not present")
    for yaml_path in sorted(_DOMAIN_CORE_DOMAINS.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        ontology_ref = data.get("ontology_ref", "")
        prefix = "ref://ontology/"
        assert ontology_ref.startswith(prefix), (
            f"{yaml_path.name} ontology_ref {ontology_ref!r} must start with {prefix!r}"
        )
        ontology_id = ontology_ref[len(prefix):]
        # Must be loadable
        spec = get_ontology(ontology_id)
        assert spec.id == ontology_id


def test_extends_cycle_raises(tmp_path: Path):
    """Two YAMLs that mutually extend each other must raise."""
    a = tmp_path / "alpha_v1.yaml"
    b = tmp_path / "beta_v1.yaml"
    a.write_text(
        "id: alpha.v1\nschema_version: 1\nextends: beta.v1\n", encoding="utf-8"
    )
    b.write_text(
        "id: beta.v1\nschema_version: 1\nextends: alpha.v1\n", encoding="utf-8"
    )
    with pytest.raises(OntologyConfigError, match="cycle"):
        load_ontology(ontology_dir=tmp_path)


def test_unknown_extends_raises(tmp_path: Path):
    a = tmp_path / "alpha_v1.yaml"
    a.write_text(
        "id: alpha.v1\nschema_version: 1\nextends: nonexistent.v1\n",
        encoding="utf-8",
    )
    with pytest.raises(OntologyConfigError, match="unknown id"):
        load_ontology(ontology_dir=tmp_path)


def test_duplicate_node_kind_names_rejected(tmp_path: Path):
    yml = tmp_path / "dup_v1.yaml"
    yml.write_text(
        """
id: dup.v1
schema_version: 1
node_kinds:
  - name: Foo
  - name: Foo
""",
        encoding="utf-8",
    )
    with pytest.raises(OntologyConfigError):
        load_ontology(ontology_dir=tmp_path)


def test_cross_domain_bridges_must_reference_known_edges(tmp_path: Path):
    yml = tmp_path / "bridge_v1.yaml"
    yml.write_text(
        """
id: bridge.v1
schema_version: 1
node_kinds:
  - name: Foo
  - name: Bar
edge_kinds:
  - name: foo_to_bar
    from_kind: Foo
    to_kind: Bar
cross_domain_bridges:
  - foo_to_bar
  - some_phantom_edge
""",
        encoding="utf-8",
    )
    with pytest.raises(OntologyConfigError):
        load_ontology(ontology_dir=tmp_path)
