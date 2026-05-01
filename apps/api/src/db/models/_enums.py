"""All Postgres enums used by ORM models. One file so migrations stay clean."""

from sqlalchemy.dialects.postgresql import ENUM

# Names match the Python enum string values from packages/llm_orchestrator/models
# and packages/kg_builder/models. Keep these in sync with the Pydantic enums.

user_role_enum = ENUM("tenant", "landlord", name="user_role", create_type=False)
intake_stage_enum = ENUM(
    "greeting", "role_identification", "basic_details", "tenancy_details",
    "deposit_details", "issue_identification", "evidence_collection",
    "claim_amounts", "narrative", "confirmation", "complete",
    name="intake_stage", create_type=False,
)
dispute_status_enum = ENUM(
    "waiting_for_tenant", "waiting_for_landlord",
    "tenant_in_progress", "landlord_in_progress", "both_in_progress",
    "tenant_complete", "landlord_complete", "both_complete",
    "ready_for_mediation", "in_mediation", "settled", "closed",
    name="dispute_status", create_type=False,
)
party_role_enum = ENUM("tenant", "landlord", name="party_role", create_type=False)
outcome_type_enum = ENUM(
    "tenant_win", "landlord_win", "split", "uncertain",
    name="outcome_type", create_type=False,
)
issue_outcome_enum = ENUM(
    "tenant_wins", "landlord_wins", "split", "uncertain",
    name="issue_outcome", create_type=False,
)
issue_type_enum = ENUM(
    "cleaning", "damage", "rent_arrears", "deposit_protection", "inventory",
    "garden", "redecoration", "keys", "fair_wear_and_tear", "missing_items",
    "utilities", "other",
    name="issue_type", create_type=False,
)
evidence_strength_enum = ENUM(
    "strong", "moderate", "weak", "insufficient",
    name="evidence_strength", create_type=False,
)
evidence_type_enum = ENUM(
    "inventory_checkin", "inventory_checkout", "photos_before", "photos_after",
    "receipts", "invoices", "correspondence", "tenancy_agreement",
    "deposit_certificate", "witness_statement", "other",
    name="evidence_type", create_type=False,
)
mediation_status_enum = ENUM(
    "expectation_adjustment", "active_negotiation", "settled", "escalated",
    name="mediation_status", create_type=False,
)
message_type_enum = ENUM(
    "text", "offer", "system", "ai_mediator",
    name="message_type", create_type=False,
)
offer_status_enum = ENUM(
    "pending", "accepted", "rejected", "countered", "expired",
    name="offer_status", create_type=False,
)
node_type_enum = ENUM(
    "party", "property", "lease", "evidence", "event", "issue", "claimed_amount",
    name="node_type", create_type=False,
)
edge_type_enum = ENUM(
    "evidence_supports", "evidence_refutes", "evidence_relates_to",
    "event_before", "event_after", "event_during",
    "party_owns", "party_rents", "party_manages", "party_claims",
    "claim_relates_to", "issue_involves", "issue_caused_by",
    "lease_for", "deposit_protected_by",
    name="edge_type", create_type=False,
)
citation_source_enum = ENUM(
    "reasoning", "issue_supporting_case", "verified", "removed",
    name="citation_source", create_type=False,
)
proposition_type_enum = ENUM(
    "fact", "rule", "outcome", "authority",
    name="proposition_type", create_type=False,
)
proposition_edge_type_enum = ENUM(
    "supports", "contradicts", "cites", "temporal_before", "applies_rule_to_fact",
    name="proposition_edge_type", create_type=False,
)
proposition_run_status_enum = ENUM(
    "started", "succeeded", "failed", "skipped",
    name="proposition_run_status", create_type=False,
)

ALL_ENUMS = (
    user_role_enum, intake_stage_enum, dispute_status_enum, party_role_enum,
    outcome_type_enum, issue_outcome_enum, issue_type_enum,
    evidence_strength_enum, evidence_type_enum,
    mediation_status_enum, message_type_enum, offer_status_enum,
    node_type_enum, edge_type_enum, citation_source_enum,
    proposition_type_enum, proposition_edge_type_enum, proposition_run_status_enum,
)
