"""SHA-35: fail-fast validator tests.

Three+ tests per validator method covering:
- happy path (no violation)
- soft warning (data-quality, doesn't raise)
- hard error (impossibility, raises KGValidationError when raise_on_error=True)
"""

from datetime import date
from typing import Optional

import pytest

from kg_builder.builders.validators import (
    KGValidationError,
    KGValidator,
    check_temporal_consistency,
)
from kg_builder.models.edges import Edge, EdgeType
from kg_builder.models.graph import KnowledgeGraph
from kg_builder.models.nodes import (
    ClaimedAmountNode,
    EventNode,
    EvidenceNode,
    IssueNode,
    LeaseNode,
    PartyNode,
    PropertyNode,
)


def _kg_with_lease(start: date, end: Optional[date] = None, **lease_kwargs) -> KnowledgeGraph:
    kg = KnowledgeGraph(case_id="test")
    kg.add_node(LeaseNode(node_id="lease_main", start_date=start, end_date=end, **lease_kwargs))
    return kg


# ────────────────────────────── _validate_temporal_logic ──────────────────────────────


def test_temporal_logic_happy_path_no_errors():
    kg = _kg_with_lease(date(2023, 1, 1), date(2024, 1, 1))
    KGValidator(raise_on_error=True).validate(kg)
    assert kg.validation_errors == []


def test_temporal_logic_end_before_start_raises():
    kg = _kg_with_lease(date(2024, 1, 1), date(2023, 1, 1))
    with pytest.raises(KGValidationError) as exc:
        KGValidator(raise_on_error=True).validate(kg)
    assert any("end date is before start" in e.lower() for e in exc.value.errors)


def test_temporal_logic_event_before_tenancy_start_raises():
    kg = _kg_with_lease(date(2023, 6, 1), date(2024, 6, 1))
    kg.add_node(
        EventNode(
            node_id="ev_damage",
            event_type="damage_discovered",
            event_date=date(2023, 1, 1),  # 5 months before tenancy started
            description="Damage found",
        )
    )
    with pytest.raises(KGValidationError) as exc:
        KGValidator(raise_on_error=True).validate(kg)
    assert any(
        "before tenancy started" in e.lower() and "damage_discovered" in e.lower()
        for e in exc.value.errors
    )


def test_temporal_logic_tenancy_start_event_exempt():
    """tenancy_start events may legitimately predate lease.start_date
    (e.g. lease signed with deferred move-in)."""
    kg = _kg_with_lease(date(2023, 6, 1))
    kg.add_node(
        EventNode(
            node_id="ev_ts",
            event_type="tenancy_start",
            event_date=date(2023, 5, 28),
            description="Move-in",
        )
    )
    KGValidator(raise_on_error=True).validate(kg)  # must not raise
    assert kg.validation_errors == []


def test_temporal_logic_protection_before_start_raises():
    """Deposit protected before tenancy started is chronologically impossible."""
    kg = _kg_with_lease(
        date(2023, 6, 1),
        protection_date=date(2023, 1, 1),  # before start
        deposit_protected=True,
    )
    with pytest.raises(KGValidationError) as exc:
        KGValidator(raise_on_error=True).validate(kg)
    assert any("protected before tenancy start" in e.lower() for e in exc.value.errors)


def test_temporal_logic_late_protection_is_warning_not_error():
    """Late protection (> 30 days) is non-compliance, not impossibility — stays as warning."""
    kg = _kg_with_lease(
        date(2023, 1, 1),
        protection_date=date(2023, 4, 1),  # 90 days late but possible
        deposit_protected=True,
    )
    KGValidator(raise_on_error=True).validate(kg)  # must not raise
    assert kg.validation_errors == []
    assert any("> 30 day limit" in w for w in kg.validation_warnings)


def test_temporal_logic_prescribed_info_before_start_raises():
    kg = _kg_with_lease(
        date(2023, 6, 1),
        prescribed_info_date=date(2023, 1, 1),
        prescribed_info_provided=True,
    )
    with pytest.raises(KGValidationError) as exc:
        KGValidator(raise_on_error=True).validate(kg)
    assert any(
        "prescribed information date is before tenancy start" in e.lower()
        for e in exc.value.errors
    )


# ────────────────────────────── _validate_deposit_protection (soft) ──────────────────────────────


def test_deposit_protection_warning_when_issue_claimed_but_protected_on_time():
    """Soft inconsistency: user says protection issue but KG shows on-time protection.
    Stays as warning — possible the user is confused, not impossible."""
    kg = _kg_with_lease(
        date(2023, 1, 1),
        protection_date=date(2023, 1, 14),
        deposit_protected=True,
    )
    kg.add_node(
        IssueNode(
            node_id="issue_dp",
            issue_type="deposit_protection",
            description="Claims late protection",
        )
    )
    KGValidator(raise_on_error=True).validate(kg)  # must not raise
    assert any("protected within 30 days" in w for w in kg.validation_warnings)


def test_deposit_protection_no_warning_when_no_issue_claimed():
    kg = _kg_with_lease(
        date(2023, 1, 1),
        protection_date=date(2023, 1, 14),
        deposit_protected=True,
    )
    KGValidator(raise_on_error=True).validate(kg)
    assert not any("protected within 30 days" in w for w in kg.validation_warnings)


def test_deposit_protection_no_warning_when_no_lease():
    kg = KnowledgeGraph(case_id="empty")
    KGValidator(raise_on_error=True).validate(kg)
    assert kg.validation_errors == []


# ────────────────────────────── _validate_evidence_coverage ──────────────────────────────


def test_evidence_coverage_warning_when_issue_unsupported():
    kg = KnowledgeGraph(case_id="ev_test")
    kg.add_node(IssueNode(node_id="issue_clean", issue_type="cleaning", description="x"))
    KGValidator(raise_on_error=True).validate(kg)
    assert any("without linked evidence" in w for w in kg.validation_warnings)
    assert kg.validation_errors == []  # warning only


def test_evidence_coverage_no_warning_when_evidence_linked():
    kg = KnowledgeGraph(case_id="ev_test")
    kg.add_node(IssueNode(node_id="issue_clean", issue_type="cleaning", description="x"))
    kg.add_node(EvidenceNode(node_id="ev_1", evidence_type="receipts", description="y"))
    kg.add_edge(
        Edge.create(EdgeType.EVIDENCE_RELATES_TO, "ev_1", "issue_clean")
    )
    KGValidator(raise_on_error=True).validate(kg)
    assert not any("without linked evidence" in w for w in kg.validation_warnings)


def test_evidence_coverage_no_warning_when_no_issues():
    kg = KnowledgeGraph(case_id="empty")
    KGValidator(raise_on_error=True).validate(kg)
    assert not any("without linked evidence" in w for w in kg.validation_warnings)


# ────────────────────────────── _validate_claim_support ──────────────────────────────


def test_claim_support_warning_when_orphaned():
    kg = KnowledgeGraph(case_id="claim_test")
    kg.add_node(
        ClaimedAmountNode(
            node_id="claim_1", claimant="landlord", amount=500.0,
            issue_type="cleaning", description="cleaning charges",
        )
    )
    KGValidator(raise_on_error=True).validate(kg)
    assert any("no supporting evidence or issue link" in w for w in kg.validation_warnings)


def test_claim_support_no_warning_when_linked_to_issue():
    kg = KnowledgeGraph(case_id="claim_test")
    kg.add_node(
        ClaimedAmountNode(
            node_id="claim_1", claimant="landlord", amount=500.0,
            issue_type="cleaning", description="cleaning",
        )
    )
    kg.add_node(IssueNode(node_id="issue_clean", issue_type="cleaning", description="x"))
    kg.add_edge(Edge.create(EdgeType.CLAIM_RELATES_TO, "claim_1", "issue_clean"))
    KGValidator(raise_on_error=True).validate(kg)
    assert not any("no supporting evidence or issue link" in w for w in kg.validation_warnings)


def test_claim_support_no_warning_when_evidence_supports():
    kg = KnowledgeGraph(case_id="claim_test")
    kg.add_node(
        ClaimedAmountNode(
            node_id="claim_1", claimant="tenant", amount=200.0,
            issue_type="damage", description="d",
        )
    )
    kg.add_node(EvidenceNode(node_id="ev_1", evidence_type="receipts", description="y"))
    kg.add_edge(Edge.create(EdgeType.EVIDENCE_SUPPORTS, "ev_1", "claim_1"))
    KGValidator(raise_on_error=True).validate(kg)
    assert not any("no supporting evidence or issue link" in w for w in kg.validation_warnings)


# ────────────────────────────── _validate_required_nodes ──────────────────────────────


def test_required_nodes_info_when_only_one_party():
    kg = KnowledgeGraph(case_id="req_test")
    kg.add_node(PartyNode(node_id="p1", role="tenant"))
    KGValidator(raise_on_error=True).validate(kg)
    assert any("Only one party" in i for i in kg.validation_info)


def test_required_nodes_warning_when_no_issues():
    kg = KnowledgeGraph(case_id="req_test")
    KGValidator(raise_on_error=True).validate(kg)
    assert any("No dispute issues" in w for w in kg.validation_warnings)


def test_required_nodes_no_complaint_when_present():
    kg = KnowledgeGraph(case_id="req_test")
    kg.add_node(PartyNode(node_id="p1", role="tenant"))
    kg.add_node(PartyNode(node_id="p2", role="landlord"))
    kg.add_node(PropertyNode(node_id="prop", address="x"))
    kg.add_node(IssueNode(node_id="issue_clean", issue_type="cleaning", description="x"))
    KGValidator(raise_on_error=True).validate(kg)
    assert not any("Only one party" in i for i in kg.validation_info)
    assert not any("No dispute issues" in w for w in kg.validation_warnings)


# ────────────────────────────── KGValidationError mechanics ──────────────────────────────


def test_validation_error_carries_case_id_and_errors():
    kg = _kg_with_lease(date(2024, 1, 1), date(2023, 1, 1))
    kg.case_id = "case_xyz"
    with pytest.raises(KGValidationError) as exc:
        KGValidator(raise_on_error=True).validate(kg)
    assert exc.value.case_id == "case_xyz"
    assert len(exc.value.errors) >= 1
    assert "case_xyz" in str(exc.value)


def test_raise_on_error_false_collects_but_does_not_raise():
    """Admin-dashboard / read-only mode: surface violations without raising."""
    kg = _kg_with_lease(date(2024, 1, 1), date(2023, 1, 1))
    validator = KGValidator(raise_on_error=False)
    result = validator.validate(kg)
    assert result is kg
    assert kg.validation_errors  # populated, not raised
    assert not kg.is_consistent


def test_validate_collects_multiple_errors_into_one_exception():
    """All errors are surfaced in a single exception, not first-failing."""
    kg = _kg_with_lease(
        date(2024, 1, 1),
        date(2023, 1, 1),  # end < start
        protection_date=date(2023, 6, 1),  # before start (will trigger second error)
        deposit_protected=True,
    )
    with pytest.raises(KGValidationError) as exc:
        KGValidator(raise_on_error=True).validate(kg)
    assert len(exc.value.errors) >= 2


# ────────────────────────────── check_temporal_consistency helper ──────────────────────────────


def test_check_temporal_consistency_helper_unchanged():
    """Public helper preserves its existing return-list-of-strings interface."""
    issues = check_temporal_consistency(
        start_date=date(2023, 1, 1),
        end_date=date(2022, 1, 1),  # invalid
        events=[],
    )
    assert any("End date before start date" in i for i in issues)
