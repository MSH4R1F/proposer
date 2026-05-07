"""Unit tests for ReasoningPath."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from legal_core.graph.reasoning_path import ReasoningPath


def test_minimum_valid_path():
    rp = ReasoningPath(
        reasoning_path_id="rp_1",
        outcome_component_id="oc_1",
        node_chain=["span_1", "fa_1"],
        confidence=0.8,
    )
    assert rp.reasoning_path_id == "rp_1"
    assert rp.outcome_component_id == "oc_1"
    assert rp.node_chain == ["span_1", "fa_1"]
    assert rp.edges_used == []
    assert rp.confidence == 0.8


def test_chain_too_short_rejected():
    with pytest.raises(ValidationError):
        ReasoningPath(
            reasoning_path_id="rp_1",
            outcome_component_id="oc_1",
            node_chain=["only_one"],
            confidence=0.5,
        )


def test_chain_empty_rejected():
    with pytest.raises(ValidationError):
        ReasoningPath(
            reasoning_path_id="rp_1",
            outcome_component_id="oc_1",
            node_chain=[],
            confidence=0.5,
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        ReasoningPath(
            reasoning_path_id="rp_1",
            outcome_component_id="oc_1",
            node_chain=["a", "b"],
            confidence=0.5,
            unexpected="x",
        )


def test_frozen_after_construction():
    rp = ReasoningPath(
        reasoning_path_id="rp_1",
        outcome_component_id="oc_1",
        node_chain=["a", "b"],
        confidence=0.5,
    )
    with pytest.raises(ValidationError):
        rp.confidence = 0.9


def test_confidence_lower_bound():
    with pytest.raises(ValidationError):
        ReasoningPath(
            reasoning_path_id="rp_1",
            outcome_component_id="oc_1",
            node_chain=["a", "b"],
            confidence=-0.1,
        )


def test_confidence_upper_bound():
    with pytest.raises(ValidationError):
        ReasoningPath(
            reasoning_path_id="rp_1",
            outcome_component_id="oc_1",
            node_chain=["a", "b"],
            confidence=1.1,
        )


def test_node_chain_round_trip_via_json():
    rp = ReasoningPath(
        reasoning_path_id="rp_1",
        outcome_component_id="oc_1",
        node_chain=["span_1", "fa_1", "prop_1"],
        edges_used=["e_1", "e_2"],
        confidence=0.75,
    )
    json_str = rp.model_dump_json()
    restored = ReasoningPath.model_validate_json(json_str)
    assert restored == rp
    # Chain order preserved.
    assert restored.node_chain == ["span_1", "fa_1", "prop_1"]
    assert restored.node_chain[0] == "span_1"
    assert restored.node_chain[-1] == "prop_1"


def test_edges_used_default_empty():
    rp = ReasoningPath(
        reasoning_path_id="rp_1",
        outcome_component_id="oc_1",
        node_chain=["a", "b"],
        confidence=0.5,
    )
    assert rp.edges_used == []
    json_str = rp.model_dump_json()
    restored = ReasoningPath.model_validate_json(json_str)
    assert restored.edges_used == []
    assert restored == rp


def test_full_chain_round_trip():
    rp = ReasoningPath(
        reasoning_path_id="rp_full",
        outcome_component_id="oc_1",
        node_chain=["span_1", "fa_1", "prop_1", "oc_1"],
        edges_used=["edge_span_to_fa", "edge_fa_to_prop", "edge_prop_to_oc"],
        confidence=0.9,
    )
    dumped = rp.model_dump()
    assert dumped["node_chain"] == ["span_1", "fa_1", "prop_1", "oc_1"]
    assert dumped["edges_used"] == [
        "edge_span_to_fa",
        "edge_fa_to_prop",
        "edge_prop_to_oc",
    ]
    restored = ReasoningPath.model_validate(dumped)
    assert restored == rp
    assert restored.node_chain == ["span_1", "fa_1", "prop_1", "oc_1"]
