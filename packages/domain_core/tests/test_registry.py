"""Registry tests: load behaviour, error paths, invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain_core.errors import DomainConfigError, DomainNotFoundError
from domain_core.ids import DomainId
from domain_core.registry import (
    get_domain_spec,
    list_domain_specs,
    load_domain_specs,
    reset_cache,
)
from domain_core.spec import DomainSpec, Forum, LaunchStage


def test_load_domain_specs_loads_all_five_fixtures():
    specs = load_domain_specs()
    assert set(specs.keys()) == {
        "housing.deposit.v1",
        "housing.repairs_social.v1",
        "housing.property_chamber.rro.v1",
        "housing.rent_determination.v1",
        "employment.unfair_dismissal.v1",
    }
    for spec in specs.values():
        assert isinstance(spec, DomainSpec)


def test_housing_deposit_v1_compatibility_baseline():
    """Audit D1 invariants on the deposit baseline."""
    specs = load_domain_specs()
    deposit = specs["housing.deposit.v1"]
    assert str(deposit.id) == "housing.deposit.v1"
    assert deposit.domain_version == "v1"
    assert deposit.schema_version == 1
    assert {f.value for f in deposit.forums} == {
        "deposit_scheme_adjudication",
        "county_court",
    }
    assert set(deposit.matter_types) == {
        "deposit_deduction",
        "deposit_non_protection",
    }
    # Legacy-namespace preservation - must NOT change without a migration.
    assert len(deposit.retrieval_namespaces) == 1
    ns = deposit.retrieval_namespaces[0]
    assert ns.vector_collection == "tribunal_cases"
    assert ns.bm25_index_path == "data/embeddings/bm25_index.pkl"
    assert ns.corpus_root == "data/raw/bailii"
    assert [p.value for p in ns.source_publishers] == ["bailii"]


def test_get_domain_spec_returns_known_id():
    reset_cache()
    spec = get_domain_spec("housing.deposit.v1")
    assert isinstance(spec, DomainSpec)
    assert str(spec.id) == "housing.deposit.v1"


def test_get_domain_spec_unknown_id_raises():
    reset_cache()
    with pytest.raises(DomainNotFoundError):
        get_domain_spec("housing.nonexistent.v99")


def test_list_domain_specs_filters_by_stage():
    reset_cache()
    research = list_domain_specs(stage="research")
    assert len(research) >= 5
    for spec in research:
        assert spec.stage == LaunchStage.RESEARCH

    production = list_domain_specs(stage="production")
    # No production-stage specs yet; gate is fail-closed (audit D2).
    assert all(s.stage == LaunchStage.PRODUCTION for s in production)


def test_id_domain_version_mismatch_rejected(tmp_path: Path):
    """An id whose final segment != domain_version must fail validation."""
    bad = tmp_path / "housing_deposit_v1.yaml"
    bad.write_text(
        # final id segment is v1 but we set domain_version: v2 -> mismatch
        "id: housing.deposit.v1\n"
        "family: housing\n"
        "domain_version: v2\n"
        "schema_version: 1\n"
        "display_name: x\n"
        "user_facing_name: x\n"
        "stage: research\n"
        "jurisdiction: [GB-ENG]\n"
        "forums: []\n"
        "forum_profiles: []\n"
        "party_roles: []\n"
        "matter_types: []\n"
        "remedies: []\n"
        "intake_schema_ref: ref://intake_schema/housing.deposit.v1\n"
        "case_file_adapter_ref: ref://case_file_adapter/housing.deposit.v1\n"
        "ontology_ref: ref://ontology/housing.deposit.v1\n"
        "prompt_pack_ref: ref://prompt_pack/housing.deposit.v1\n"
        "retrieval_namespaces: []\n"
        "eval_gate:\n"
        "  gold_set_path: data/gold.jsonl\n"
        "  min_cases: 0\n"
        "safety_notes: []\n"
        "temporal_law_markers: []\n"
    )
    with pytest.raises(DomainConfigError):
        load_domain_specs(domains_dir=tmp_path)


def test_filename_id_mismatch_rejected(tmp_path: Path):
    bad = tmp_path / "housing_deposit_v1.yaml"
    bad.write_text(
        "id: employment.unfair_dismissal.v1\n"
        "family: employment\n"
        "domain_version: v1\n"
        "schema_version: 1\n"
        "display_name: x\n"
        "user_facing_name: x\n"
        "stage: research\n"
        "jurisdiction: [GB-ENG]\n"
        "forums: [employment_tribunal]\n"
        "forum_profiles:\n"
        "  - forum: employment_tribunal\n"
        "    source_publishers: [bailii]\n"
        "    source_kinds: [case_decision]\n"
        "    citation_kinds: [retrieved_legal_source]\n"
        "    matter_types: [unfair_dismissal]\n"
        "    remedies: [basic_award]\n"
        "    output_framing: x\n"
        "    citation_label: x\n"
        "party_roles: []\n"
        "matter_types: [unfair_dismissal]\n"
        "remedies: [basic_award]\n"
        "intake_schema_ref: ref://intake_schema/employment.unfair_dismissal.v1\n"
        "case_file_adapter_ref: ref://case_file_adapter/employment.unfair_dismissal.v1\n"
        "ontology_ref: ref://ontology/employment.unfair_dismissal.v1\n"
        "prompt_pack_ref: ref://prompt_pack/employment.unfair_dismissal.v1\n"
        "retrieval_namespaces: []\n"
        "eval_gate:\n"
        "  gold_set_path: data/gold.jsonl\n"
        "  min_cases: 0\n"
    )
    with pytest.raises(DomainConfigError):
        load_domain_specs(domains_dir=tmp_path)


def test_duplicate_id_rejected(tmp_path: Path):
    body = (
        "id: housing.deposit.v1\n"
        "family: housing\n"
        "domain_version: v1\n"
        "schema_version: 1\n"
        "display_name: x\n"
        "user_facing_name: x\n"
        "stage: research\n"
        "jurisdiction: [GB-ENG]\n"
        "forums: []\n"
        "forum_profiles: []\n"
        "party_roles: []\n"
        "matter_types: []\n"
        "remedies: []\n"
        "intake_schema_ref: ref://intake_schema/housing.deposit.v1\n"
        "case_file_adapter_ref: ref://case_file_adapter/housing.deposit.v1\n"
        "ontology_ref: ref://ontology/housing.deposit.v1\n"
        "prompt_pack_ref: ref://prompt_pack/housing.deposit.v1\n"
        "retrieval_namespaces: []\n"
        "eval_gate:\n"
        "  gold_set_path: data/gold.jsonl\n"
        "  min_cases: 0\n"
    )
    (tmp_path / "housing_deposit_v1.yaml").write_text(body)
    # Same id, different filename stem -> filename consistency catches this
    # before duplicate detection. To test duplicate-id specifically we'd
    # need two files with the same correct stem, which the OS prevents.
    # So we instead verify filename consistency catches it.
    (tmp_path / "housing_deposit_v1_copy.yaml").write_text(body)
    with pytest.raises(DomainConfigError):
        load_domain_specs(domains_dir=tmp_path)


def test_ref_uri_syntax_rejected(tmp_path: Path):
    bad = tmp_path / "housing_deposit_v1.yaml"
    bad.write_text(
        "id: housing.deposit.v1\n"
        "family: housing\n"
        "domain_version: v1\n"
        "schema_version: 1\n"
        "display_name: x\n"
        "user_facing_name: x\n"
        "stage: research\n"
        "jurisdiction: [GB-ENG]\n"
        "forums: []\n"
        "forum_profiles: []\n"
        "party_roles: []\n"
        "matter_types: []\n"
        "remedies: []\n"
        # wrong scheme
        "intake_schema_ref: not_a_ref_uri\n"
        "case_file_adapter_ref: ref://case_file_adapter/housing.deposit.v1\n"
        "ontology_ref: ref://ontology/housing.deposit.v1\n"
        "prompt_pack_ref: ref://prompt_pack/housing.deposit.v1\n"
        "retrieval_namespaces: []\n"
        "eval_gate:\n"
        "  gold_set_path: data/gold.jsonl\n"
        "  min_cases: 0\n"
    )
    with pytest.raises(DomainConfigError):
        load_domain_specs(domains_dir=tmp_path)


def test_forum_profile_must_match_forums(tmp_path: Path):
    bad = tmp_path / "housing_deposit_v1.yaml"
    bad.write_text(
        "id: housing.deposit.v1\n"
        "family: housing\n"
        "domain_version: v1\n"
        "schema_version: 1\n"
        "display_name: x\n"
        "user_facing_name: x\n"
        "stage: research\n"
        "jurisdiction: [GB-ENG]\n"
        "forums: [deposit_scheme_adjudication]\n"
        # Profile defines a different forum from `forums` list.
        "forum_profiles:\n"
        "  - forum: county_court\n"
        "    source_publishers: [bailii]\n"
        "    source_kinds: [case_decision]\n"
        "    citation_kinds: [retrieved_legal_source]\n"
        "    matter_types: []\n"
        "    remedies: []\n"
        "    output_framing: x\n"
        "    citation_label: x\n"
        "party_roles: []\n"
        "matter_types: []\n"
        "remedies: []\n"
        "intake_schema_ref: ref://intake_schema/housing.deposit.v1\n"
        "case_file_adapter_ref: ref://case_file_adapter/housing.deposit.v1\n"
        "ontology_ref: ref://ontology/housing.deposit.v1\n"
        "prompt_pack_ref: ref://prompt_pack/housing.deposit.v1\n"
        "retrieval_namespaces: []\n"
        "eval_gate:\n"
        "  gold_set_path: data/gold.jsonl\n"
        "  min_cases: 0\n"
    )
    with pytest.raises(DomainConfigError):
        load_domain_specs(domains_dir=tmp_path)


def test_domain_id_constructor_rejects_bad_input():
    with pytest.raises(ValueError):
        DomainId("Housing.Deposit.V1")  # uppercase
    with pytest.raises(ValueError):
        DomainId("housing.deposit")  # missing version
    with pytest.raises(ValueError):
        DomainId("housing.deposit.x1")  # bad version tag


def test_domain_id_properties():
    did = DomainId("housing.deposit.v1")
    assert did.family == "housing"
    assert did.version == "v1"
