"""Stable spec hashing: must be invariant to YAML key order and whitespace."""

from __future__ import annotations

from pathlib import Path

import yaml

from domain_core.hashing import hash_domain_spec
from domain_core.registry import load_domain_specs
from domain_core.spec import DomainSpec


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _reorder_dict_keys(d: dict) -> dict:
    """Return a new dict with reversed key order. Lists are NOT reordered."""
    return {k: d[k] for k in reversed(list(d.keys()))}


def test_hash_is_stable_across_key_reordering(tmp_path: Path):
    """YAML key order must not change the hash."""
    canonical_path = (
        Path(__file__).resolve().parents[1]
        / "domains"
        / "housing_deposit_v1.yaml"
    )
    raw = _load_yaml(canonical_path)
    spec_a = DomainSpec.model_validate(raw)

    # Reorder top-level keys, plus reorder eval_gate's sub-dict.
    raw_reordered = _reorder_dict_keys(raw)
    if isinstance(raw_reordered.get("eval_gate"), dict):
        raw_reordered["eval_gate"] = _reorder_dict_keys(raw_reordered["eval_gate"])
    spec_b = DomainSpec.model_validate(raw_reordered)

    assert hash_domain_spec(spec_a) == hash_domain_spec(spec_b)


def test_hash_is_stable_across_yaml_whitespace_and_comments(tmp_path: Path):
    """A re-emitted YAML (no comments, different style) yields the same hash."""
    canonical_path = (
        Path(__file__).resolve().parents[1]
        / "domains"
        / "housing_deposit_v1.yaml"
    )
    raw = _load_yaml(canonical_path)

    # Re-emit YAML with default_flow_style=True (very different formatting).
    flow_yaml = yaml.safe_dump(raw, default_flow_style=True, sort_keys=False)
    block_yaml = yaml.safe_dump(raw, default_flow_style=False, sort_keys=True)

    spec_a = DomainSpec.model_validate(yaml.safe_load(flow_yaml))
    spec_b = DomainSpec.model_validate(yaml.safe_load(block_yaml))
    spec_c = DomainSpec.model_validate(raw)

    h = hash_domain_spec(spec_c)
    assert hash_domain_spec(spec_a) == h
    assert hash_domain_spec(spec_b) == h


def test_hash_changes_when_a_field_changes():
    """Sanity: meaningful change to the spec MUST change the hash."""
    canonical_path = (
        Path(__file__).resolve().parents[1]
        / "domains"
        / "housing_deposit_v1.yaml"
    )
    raw = _load_yaml(canonical_path)
    spec_a = DomainSpec.model_validate(raw)

    raw_modified = dict(raw)
    raw_modified["display_name"] = "Housing - Deposit Disputes (v1) [MUTATED]"
    spec_b = DomainSpec.model_validate(raw_modified)

    assert hash_domain_spec(spec_a) != hash_domain_spec(spec_b)


def test_hash_is_deterministic_across_repeated_calls():
    specs = load_domain_specs()
    deposit = specs["housing.deposit.v1"]
    h1 = hash_domain_spec(deposit)
    h2 = hash_domain_spec(deposit)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    assert all(c in "0123456789abcdef" for c in h1)


def test_hash_changes_when_list_order_changes():
    """List order is semantically meaningful - reordering MUST change the hash."""
    canonical_path = (
        Path(__file__).resolve().parents[1]
        / "domains"
        / "housing_deposit_v1.yaml"
    )
    raw = _load_yaml(canonical_path)
    spec_a = DomainSpec.model_validate(raw)

    raw_reordered = dict(raw)
    raw_reordered["forums"] = list(reversed(raw["forums"]))
    raw_reordered["forum_profiles"] = list(reversed(raw["forum_profiles"]))
    spec_b = DomainSpec.model_validate(raw_reordered)

    assert hash_domain_spec(spec_a) != hash_domain_spec(spec_b)
