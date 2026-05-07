"""Snapshot tests for both pack renderer outputs.

Catches silent drift in deposit and repairs factor card rendering.
Run with `UPDATE_SNAPSHOTS=1` to regenerate snapshots after intentional
changes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from domain_packs.registry import get_domain_pack
from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType
from llm_orchestrator.pipeline.kg_facts import KGFacts


_SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"


def _read_or_update_snapshot(name: str, actual: str) -> str:
    """Read snapshot file. If UPDATE_SNAPSHOTS=1, write `actual` to it first."""
    snap_path = _SNAPSHOTS_DIR / name
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(actual, encoding="utf-8")
    return snap_path.read_text(encoding="utf-8")


def test_deposit_factor_card_snapshot():
    """Deterministic deposit fixture should produce stable card output."""
    pack = get_domain_pack("housing.deposit.v1")
    facts = KGFacts(
        deposit_protection_status="protected_late",
        deposit_scheme="MyDeposits",
        deposit_late_by_days=14,
        prescribed_information_status="provided_late",
        prescribed_late_by_days=30,
        check_in_inventory_baseline="present",
    )
    actual = pack.render_factor_card(facts)
    expected = _read_or_update_snapshot("factor_card_deposit_full.txt", actual)
    assert actual == expected, (
        f"Deposit factor card drifted from snapshot. "
        f"Run with UPDATE_SNAPSHOTS=1 to regenerate."
    )


def _make_fa(
    factor_id: str,
    value: FactorValue,
    *,
    polarity: FactorPolarity = FactorPolarity.PRO_CLAIMANT,
    confidence: float = 0.92,
    requires_human_review: bool = False,
    supported_by: list[str] | None = None,
) -> FactorAssertion:
    return FactorAssertion(
        factor_assertion_id=f"fa_{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        value=value,
        value_type=value.value_type,
        confidence=confidence,
        polarity=polarity,
        supported_by=supported_by or ["span_1"],
        requires_human_review=requires_human_review,
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="snapshot_v1",
        verifier_version="snapshot_v1",
    )


class _FakeKG:
    def __init__(self, factor_assertions: list[FactorAssertion]):
        self.factor_assertions = factor_assertions


def test_repairs_factor_card_snapshot():
    """Deterministic 8-factor repairs fixture should produce stable card output."""
    pack = get_domain_pack("housing.repairs_social.v1")
    fas = [
        # 5 boolean factors + 3 duration factors covering all main shapes
        _make_fa(
            "repair_responsibility_established",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
            polarity=FactorPolarity.PRO_CLAIMANT,
            confidence=0.95,
            supported_by=["span_1"],
        ),
        _make_fa(
            "hazard_or_disrepair_reported",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
            polarity=FactorPolarity.PRO_CLAIMANT,
            confidence=0.93,
            supported_by=["span_2"],
        ),
        _make_fa(
            "landlord_notice_established",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
            polarity=FactorPolarity.PRO_CLAIMANT,
            confidence=0.90,
            supported_by=["span_3"],
        ),
        _make_fa(
            "inspection_offered",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=False),
            polarity=FactorPolarity.PRO_RESPONDENT,
            confidence=0.85,
            supported_by=["span_4"],
        ),
        _make_fa(
            "repair_attempted",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=False),
            polarity=FactorPolarity.PRO_RESPONDENT,
            confidence=0.88,
            supported_by=["span_5"],
        ),
        _make_fa(
            "inspection_delay_days",
            FactorValue(value_type=FactorValueType.DURATION, duration_days=45),
            polarity=FactorPolarity.PRO_CLAIMANT,
            confidence=0.97,
            supported_by=["span_6", "span_7"],
        ),
        _make_fa(
            "repair_delay_days",
            FactorValue(value_type=FactorValueType.DURATION, duration_days=120),
            polarity=FactorPolarity.PRO_CLAIMANT,
            confidence=0.96,
            supported_by=["span_8"],
        ),
        _make_fa(
            "communication_gap_days",
            FactorValue(value_type=FactorValueType.DURATION, duration_days=21),
            polarity=FactorPolarity.PRO_CLAIMANT,
            confidence=0.80,
            requires_human_review=True,
            supported_by=["span_9"],
        ),
    ]
    kg = _FakeKG(factor_assertions=fas)
    actual = pack.render_factor_card(kg)
    expected = _read_or_update_snapshot("factor_card_repairs_full.txt", actual)
    assert actual == expected, (
        f"Repairs factor card drifted from snapshot. "
        f"Run with UPDATE_SNAPSHOTS=1 to regenerate."
    )
