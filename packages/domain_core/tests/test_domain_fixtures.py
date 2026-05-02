"""Per-domain fixture invariants + frozen deposit golden-output parity hook.

The parity assertion is currently a ``pytest.skip`` because we cannot
synthesize a realistic engine snapshot from this leaf package. The fixture
files under ``data/regression/domain_parity/housing_deposit_v1/`` are
stub placeholders; see the README there for re-enablement instructions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain_core.registry import load_domain_specs
from domain_core.spec import DomainSpec, Forum, LaunchStage

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def specs() -> dict:
    return load_domain_specs()


def test_all_four_specs_present(specs: dict):
    assert set(specs.keys()) == {
        "housing.deposit.v1",
        "housing.repairs_social.v1",
        "housing.property_chamber.rro.v1",
        "employment.unfair_dismissal.v1",
    }


def test_housing_deposit_v1_audit_invariants(specs: dict):
    spec: DomainSpec = specs["housing.deposit.v1"]
    # Audit D1: legacy retrieval namespace must be preserved verbatim.
    assert len(spec.retrieval_namespaces) == 1
    ns = spec.retrieval_namespaces[0]
    assert ns.vector_collection == "tribunal_cases"
    assert ns.bm25_index_path == "data/embeddings/bm25_index.pkl"
    assert ns.corpus_root == "data/raw/bailii"
    assert [p.value for p in ns.source_publishers] == ["bailii"]
    # Audit D3: matter_types split must be present.
    assert set(spec.matter_types) == {"deposit_deduction", "deposit_non_protection"}
    # Audit D2: stage stays conservative until gold set is restored.
    assert spec.stage in {LaunchStage.RESEARCH, LaunchStage.DISABLED}
    # Audit forums.
    assert {f.value for f in spec.forums} == {
        "deposit_scheme_adjudication",
        "county_court",
    }


def test_housing_repairs_social_v1_invariants(specs: dict):
    spec: DomainSpec = specs["housing.repairs_social.v1"]
    assert spec.stage == LaunchStage.RESEARCH
    assert [f.value for f in spec.forums] == ["housing_ombudsman"]
    profile = spec.forum_profiles[0]
    # Must NOT use court damages framing.
    assert any("ombudsman" in p.lower() for p in [profile.output_framing])
    assert any(
        "tribunal" in phrase.lower() or "court" in phrase.lower()
        for phrase in profile.prohibited_phrases
    )


def test_housing_property_chamber_rro_v1_invariants(specs: dict):
    spec: DomainSpec = specs["housing.property_chamber.rro.v1"]
    # Audit D4: RRO only.
    assert spec.matter_types == ["rent_repayment_order"]
    assert [f.value for f in spec.forums] == ["first_tier_property_chamber"]
    forbidden = {"leasehold", "tenant_fees", "rents", "park_homes", "building_safety"}
    assert not (forbidden & set(spec.matter_types))


def test_employment_unfair_dismissal_v1_invariants(specs: dict):
    spec: DomainSpec = specs["employment.unfair_dismissal.v1"]
    # Audit D5: unfair dismissal only.
    assert spec.matter_types == ["unfair_dismissal"]
    forbidden = {"wage_disputes", "discrimination", "whistleblowing"}
    assert not (forbidden & set(spec.matter_types))
    assert [f.value for f in spec.forums] == ["employment_tribunal"]


def test_each_spec_has_aligned_forum_profiles(specs: dict):
    """Every forum has exactly one matching ForumProfile (model-validator level)."""
    for spec in specs.values():
        forum_set = sorted(f.value for f in spec.forums)
        profile_set = sorted(p.forum.value for p in spec.forum_profiles)
        assert forum_set == profile_set, (
            f"{spec.id}: forums {forum_set} != profiles {profile_set}"
        )


def test_frozen_deposit_parity_skipped_until_engine_snapshot():
    """Phase 1 task 1.6 is intentionally a stub.

    Synthesizing a realistic ``expected_prediction.json`` requires running
    the orchestrator, which would re-introduce a forbidden import. The
    plan explicitly allows leaving these as stubs with a TODO until the
    parity workflow is wired in (see Phase 1 acceptance criteria and
    README under ``data/regression/domain_parity/housing_deposit_v1/``).
    """
    parity_dir = REPO_ROOT / "data" / "regression" / "domain_parity" / "housing_deposit_v1"
    if not parity_dir.is_dir():
        pytest.skip(f"parity fixtures not present at {parity_dir}")
    expected = parity_dir / "expected_prediction.json"
    if not expected.exists():
        pytest.skip("expected_prediction.json missing - parity not yet captured")
    payload = json.loads(expected.read_text(encoding="utf-8"))
    if payload.get("status") == "stub":
        pytest.skip(
            "frozen-deposit parity fixture pending engine snapshot - "
            "see README in housing_deposit_v1/ parity dir"
        )
    # If a real expected_prediction.json was added, run actual parity here.
    assert "winner" in payload
