"""Tests for LLMKGBuilder transcript → KG enrichment (SHA-34).

Five fixture transcripts cover:
1. Simple late-protection case — happy path event + evidence link
2. Complaint-followed-by-repair-request — multi-event timeline
3. Validator-rejecting transcript (damage event predates tenancy start) — must raise
4. Empty / no-new-info transcript — no-op
5. Malformed LLM JSON — graceful degradation, no nodes added
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from kg_builder.builders.graph_builder import GraphBuilder
from kg_builder.builders.llm_builder import (
    LLMEvent,
    LLMEvidenceClaimLink,
    LLMExtraction,
    LLMKGBuilder,
)
from kg_builder.builders.validators import KGValidationError
from kg_builder.models.edges import EdgeType
from kg_builder.models.graph import KnowledgeGraph
from kg_builder.models.nodes import (
    ClaimedAmountNode,
    EventNode,
    EvidenceNode,
    LeaseNode,
    NodeType,
    PartyNode,
)


def _base_kg(
    case_id: str = "case_test",
    start: date = date(2023, 1, 1),
    end: date = date(2024, 1, 1),
) -> KnowledgeGraph:
    """Reusable base KG with lease + tenant + landlord + one issue + evidence + claim."""
    kg = KnowledgeGraph(case_id=case_id)
    kg.add_node(LeaseNode(node_id="lease_main", start_date=start, end_date=end))
    kg.add_node(PartyNode(node_id="party_tenant", role="tenant"))
    kg.add_node(PartyNode(node_id="party_landlord", role="landlord"))
    kg.add_node(
        EvidenceNode(
            node_id="ev_receipt",
            evidence_type="receipts",
            description="Cleaning company invoice for £200",
        )
    )
    kg.add_node(
        ClaimedAmountNode(
            node_id="claim_landlord_clean",
            claimant="landlord",
            amount=200.0,
            issue_type="cleaning",
            description="Professional cleaning charge",
        )
    )
    return kg


def _llm_returning(payload: dict) -> AsyncMock:
    """Mock LLM client whose generate() returns a JSON-encoded payload."""
    import json

    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=json.dumps(payload))
    return llm


# ────────────────────────────── Fixture transcript 1: simple events + link ──────────────────────────────


@pytest.mark.asyncio
async def test_fixture1_simple_event_and_evidence_link():
    kg = _base_kg()
    transcript = (
        "We moved in on 1st January 2023 and paid the deposit £1500 that day. "
        "The landlord charged us £200 for cleaning at the end "
        "and showed us the cleaning company invoice."
    )
    llm = _llm_returning({
        "events": [
            {
                "event_type": "deposit_paid",
                "date": "2023-01-01",
                "description": "Tenant paid £1500 deposit on move-in",
                "actors": ["tenant", "landlord"],
                "confidence": 0.9,
            },
            {
                "event_type": "tenancy_start",
                "date": "2023-01-01",
                "description": "Move-in day",
                "actors": ["tenant"],
                "confidence": 0.95,
            },
        ],
        "evidence_supports_claims": [
            {
                "evidence_description": "cleaning company invoice",
                "claim_description": "professional cleaning charge",
                "claimant": "landlord",
                "confidence": 0.85,
            }
        ],
        "no_new_info": False,
    })

    builder = LLMKGBuilder(llm_client=llm)
    enriched = await builder.enrich(kg, transcript)

    events = enriched.get_nodes_by_type(NodeType.EVENT)
    assert len(events) == 2
    types = {e.event_type for e in events}
    assert types == {"deposit_paid", "tenancy_start"}

    support_edges = enriched.get_edges_by_type(EdgeType.EVIDENCE_SUPPORTS)
    assert len(support_edges) == 1
    edge = support_edges[0]
    assert edge.source_node_id == "ev_receipt"
    assert edge.target_node_id == "claim_landlord_clean"
    assert edge.source == "llm_extracted"


# ────────────────────────────── Fixture 2: multi-event timeline ──────────────────────────────


@pytest.mark.asyncio
async def test_fixture2_multi_event_timeline_complaint_then_repair():
    kg = _base_kg()
    transcript = (
        "On 5 March 2023 the boiler broke. I emailed the agent the next day. "
        "They sent a contractor on 12 March who said it was beyond repair. "
        "We had no hot water until 28 March."
    )
    llm = _llm_returning({
        "events": [
            {
                "event_type": "damage_discovered",
                "date": "2023-03-05",
                "description": "Boiler broke",
                "actors": ["tenant"],
                "confidence": 0.95,
            },
            {
                "event_type": "complaint_made",
                "date": "2023-03-06",
                "description": "Tenant emailed agent",
                "actors": ["tenant", "agent"],
                "confidence": 0.9,
            },
            {
                "event_type": "inspection",
                "date": "2023-03-12",
                "description": "Contractor inspected boiler",
                "actors": ["agent"],
                "confidence": 0.9,
            },
            {
                "event_type": "repair_requested",
                "date": "2023-03-12",
                "description": "Contractor reported boiler beyond repair",
                "actors": ["agent"],
                "confidence": 0.85,
            },
        ],
        "evidence_supports_claims": [],
        "no_new_info": False,
    })

    enriched = await LLMKGBuilder(llm_client=llm).enrich(kg, transcript)
    events = enriched.get_nodes_by_type(NodeType.EVENT)
    assert len(events) == 4
    sorted_dates = sorted(e.event_date for e in events if e.event_date)
    assert sorted_dates == [
        date(2023, 3, 5),
        date(2023, 3, 6),
        date(2023, 3, 12),
        date(2023, 3, 12),
    ]


# ────────────────────────────── Fixture 3: validator-rejecting transcript ──────────────────────────────


@pytest.mark.asyncio
async def test_fixture3_validator_rejects_event_before_tenancy_start():
    """SHA-35 chain: LLM returns an event predating tenancy → KGValidationError."""
    kg = _base_kg(start=date(2023, 6, 1))
    llm = _llm_returning({
        "events": [
            {
                "event_type": "damage_discovered",
                "date": "2023-01-15",  # 5 months before tenancy started — impossible
                "description": "Tenant claims damage from before move-in",
                "actors": ["tenant"],
                "confidence": 0.9,
            }
        ],
        "evidence_supports_claims": [],
        "no_new_info": False,
    })

    builder = LLMKGBuilder(llm_client=llm, validate=True)

    with pytest.raises(KGValidationError) as exc:
        await builder.enrich(kg, "transcript text")
    assert any("damage_discovered" in e.lower() for e in exc.value.errors)


@pytest.mark.asyncio
async def test_fixture3_validate_false_skips_raise():
    """validate=False mode — caller wants to inspect the dirty KG."""
    kg = _base_kg(start=date(2023, 6, 1))
    llm = _llm_returning({
        "events": [
            {
                "event_type": "damage_discovered",
                "date": "2023-01-15",
                "description": "Damage from earlier",
                "actors": ["tenant"],
                "confidence": 0.9,
            }
        ],
        "evidence_supports_claims": [],
        "no_new_info": False,
    })

    builder = LLMKGBuilder(llm_client=llm, validate=False)
    enriched = await builder.enrich(kg, "transcript")

    # Node was added (no validation), but kg is dirty
    events = enriched.get_nodes_by_type(NodeType.EVENT)
    assert len(events) == 1


# ────────────────────────────── Fixture 4: no-new-info ──────────────────────────────


@pytest.mark.asyncio
async def test_fixture4_no_new_info_payload_is_noop():
    kg = _base_kg()
    initial_event_count = len(kg.get_nodes_by_type(NodeType.EVENT))
    initial_edge_count = len(kg.get_edges_by_type(EdgeType.EVIDENCE_SUPPORTS))

    llm = _llm_returning({
        "events": [],
        "evidence_supports_claims": [],
        "no_new_info": True,
    })

    enriched = await LLMKGBuilder(llm_client=llm).enrich(kg, "I have nothing else to add.")

    assert len(enriched.get_nodes_by_type(NodeType.EVENT)) == initial_event_count
    assert len(enriched.get_edges_by_type(EdgeType.EVIDENCE_SUPPORTS)) == initial_edge_count


@pytest.mark.asyncio
async def test_empty_transcript_short_circuits_without_llm_call():
    kg = _base_kg()
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value='{"events":[],"no_new_info":true}')

    enriched = await LLMKGBuilder(llm_client=llm).enrich(kg, "")

    llm.generate.assert_not_called()  # short-circuit before calling LLM
    assert enriched is kg


# ────────────────────────────── Fixture 5: malformed LLM JSON ──────────────────────────────


@pytest.mark.asyncio
async def test_fixture5_malformed_llm_json_graceful_degradation():
    """LLM returns junk → no nodes added, no exception raised, base KG preserved."""
    kg = _base_kg()
    initial_event_count = len(kg.get_nodes_by_type(NodeType.EVENT))

    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="this is not JSON at all 🤷")

    builder = LLMKGBuilder(llm_client=llm)
    enriched = await builder.enrich(kg, "Some transcript text.")

    assert enriched is kg
    assert len(enriched.get_nodes_by_type(NodeType.EVENT)) == initial_event_count


@pytest.mark.asyncio
async def test_llm_call_exception_returns_kg_unchanged():
    """LLM client exception → graceful degradation."""
    kg = _base_kg()
    initial_count = len(kg.nodes)

    llm = AsyncMock()
    llm.generate = AsyncMock(side_effect=ConnectionError("rate limited"))

    enriched = await LLMKGBuilder(llm_client=llm).enrich(kg, "transcript")
    assert len(enriched.nodes) == initial_count


# ────────────────────────────── Pydantic schema tests ──────────────────────────────


def test_llm_extraction_pydantic_validates_event_dates():
    """Bad date strings fail Pydantic — never reach the KG."""
    from pydantic import ValidationError as PydanticVE

    with pytest.raises(PydanticVE):
        LLMExtraction.model_validate({
            "events": [
                {
                    "event_type": "damage_discovered",
                    "date": "not-a-date",
                    "description": "x",
                    "actors": [],
                    "confidence": 0.5,
                }
            ],
            "evidence_supports_claims": [],
            "no_new_info": False,
        })


def test_llm_extraction_confidence_clamped():
    """Confidence > 1.0 fails Pydantic ge/le constraints."""
    from pydantic import ValidationError as PydanticVE

    with pytest.raises(PydanticVE):
        LLMEvent.model_validate({
            "event_type": "damage_discovered",
            "description": "x",
            "confidence": 1.5,
        })


# ────────────────────────────── Confidence threshold ──────────────────────────────


@pytest.mark.asyncio
async def test_low_confidence_events_dropped():
    kg = _base_kg()
    llm = _llm_returning({
        "events": [
            {
                "event_type": "damage_discovered",
                "date": "2023-06-01",
                "description": "Maybe damage?",
                "actors": [],
                "confidence": 0.3,  # below default threshold 0.5
            },
            {
                "event_type": "complaint_made",
                "date": "2023-06-15",
                "description": "Definitely complained",
                "actors": ["tenant"],
                "confidence": 0.9,
            },
        ],
        "evidence_supports_claims": [],
        "no_new_info": False,
    })

    enriched = await LLMKGBuilder(llm_client=llm, min_confidence=0.5).enrich(kg, "tx")
    events = enriched.get_nodes_by_type(NodeType.EVENT)
    types = [e.event_type for e in events]
    assert "complaint_made" in types
    assert "damage_discovered" not in types


# ────────────────────────────── Unknown event_type silently dropped ──────────────────────────────


@pytest.mark.asyncio
async def test_unknown_event_type_dropped():
    """LLM hallucinates a novel event_type → drop it (logged as warning)."""
    kg = _base_kg()
    llm = _llm_returning({
        "events": [
            {
                "event_type": "alien_invasion",  # not in allowed set
                "date": "2023-06-01",
                "description": "x",
                "actors": [],
                "confidence": 0.95,
            }
        ],
        "evidence_supports_claims": [],
        "no_new_info": False,
    })
    enriched = await LLMKGBuilder(llm_client=llm).enrich(kg, "tx")
    assert len(enriched.get_nodes_by_type(NodeType.EVENT)) == 0


# ────────────────────────────── Best-match: link ignored when no evidence/claim matches ──────────────────────────────


@pytest.mark.asyncio
async def test_evidence_claim_link_ignored_when_no_match():
    """LLM tries to link to a claim/evidence not in the KG → silently ignored."""
    kg = _base_kg()  # has cleaning evidence + cleaning claim
    llm = _llm_returning({
        "events": [],
        "evidence_supports_claims": [
            {
                "evidence_description": "photographs of garden weeds",  # no matching evidence
                "claim_description": "garden maintenance",  # no matching claim
                "claimant": "landlord",
                "confidence": 0.9,
            }
        ],
        "no_new_info": False,
    })

    enriched = await LLMKGBuilder(llm_client=llm).enrich(kg, "tx")
    new_edges = [
        e for e in enriched.get_edges_by_type(EdgeType.EVIDENCE_SUPPORTS)
        if e.source == "llm_extracted"
    ]
    assert new_edges == []


# ────────────────────────────── Markdown-fenced JSON tolerated ──────────────────────────────


@pytest.mark.asyncio
async def test_markdown_fenced_json_parsed():
    """LLM occasionally wraps JSON in ```json fences — parser must handle."""
    import json

    payload = {
        "events": [
            {
                "event_type": "tenancy_end",
                "date": "2024-01-01",
                "description": "Tenancy ended",
                "actors": ["tenant"],
                "confidence": 0.9,
            }
        ],
        "evidence_supports_claims": [],
        "no_new_info": False,
    }
    fenced = f"```json\n{json.dumps(payload)}\n```"

    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=fenced)

    kg = _base_kg()
    enriched = await LLMKGBuilder(llm_client=llm).enrich(kg, "tx")
    events = enriched.get_nodes_by_type(NodeType.EVENT)
    assert any(e.event_type == "tenancy_end" for e in events)
