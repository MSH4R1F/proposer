"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


ENUMS = {
    "user_role": ("tenant", "landlord"),
    "intake_stage": (
        "greeting", "role_identification", "basic_details", "tenancy_details",
        "deposit_details", "issue_identification", "evidence_collection",
        "claim_amounts", "narrative", "confirmation", "complete",
    ),
    "dispute_status": (
        "waiting_for_tenant", "waiting_for_landlord",
        "tenant_in_progress", "landlord_in_progress", "both_in_progress",
        "tenant_complete", "landlord_complete", "both_complete",
        "ready_for_mediation", "in_mediation", "settled", "closed",
    ),
    "party_role": ("tenant", "landlord"),
    "outcome_type": ("tenant_win", "landlord_win", "split", "uncertain"),
    "issue_outcome": ("tenant_wins", "landlord_wins", "split", "uncertain"),
    "issue_type": (
        "cleaning", "damage", "rent_arrears", "deposit_protection", "inventory",
        "garden", "redecoration", "keys", "fair_wear_and_tear", "missing_items",
        "utilities", "other",
    ),
    "evidence_strength": ("strong", "moderate", "weak", "insufficient"),
    "evidence_type": (
        "inventory_checkin", "inventory_checkout", "photos_before", "photos_after",
        "receipts", "invoices", "correspondence", "tenancy_agreement",
        "deposit_certificate", "witness_statement", "other",
    ),
    "mediation_status": ("expectation_adjustment", "active_negotiation", "settled", "escalated"),
    "message_type": ("text", "offer", "system", "ai_mediator"),
    "offer_status": ("pending", "accepted", "rejected", "countered", "expired"),
    "node_type": ("party", "property", "lease", "evidence", "event", "issue", "claimed_amount"),
    "edge_type": (
        "evidence_supports", "evidence_refutes", "evidence_relates_to",
        "event_before", "event_after", "event_during",
        "party_owns", "party_rents", "party_manages", "party_claims",
        "claim_relates_to", "issue_involves", "issue_caused_by",
        "lease_for", "deposit_protected_by",
    ),
    "citation_source": ("reasoning", "issue_supporting_case", "verified", "removed"),
}


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        sa.Enum(*values, name=name).create(bind, checkfirst=False)

    op.create_table(
        "intake_sessions",
        sa.Column("session_id", sa.String, primary_key=True),
        sa.Column("case_id", sa.String, nullable=False, unique=True),
        sa.Column("user_role", sa.Enum(name="user_role", create_type=False), nullable=True),
        sa.Column("current_stage", sa.Enum(name="intake_stage", create_type=False), nullable=False),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("intake_complete", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("completeness_score", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("role_explicitly_set", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_intake_sessions_user_role", "intake_sessions", ["user_role"])
    op.create_index("ix_intake_sessions_current_stage", "intake_sessions", ["current_stage"])

    op.create_table(
        "predictions",
        sa.Column("prediction_id", sa.String, primary_key=True),
        sa.Column("case_id", sa.String, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("overall_outcome", sa.Enum(name="outcome_type", create_type=False), nullable=False),
        sa.Column("overall_confidence", sa.Numeric, nullable=False),
        sa.Column("range_lo", sa.Numeric, nullable=True),
        sa.Column("range_hi", sa.Numeric, nullable=True),
        sa.Column("pipeline_version", sa.String, nullable=True),
        sa.Column("model_version", sa.String, nullable=True),
        sa.Column("retrieval_quality", sa.String, nullable=True),
        sa.Column("rag_confidence", sa.Numeric, nullable=True),
        sa.Column("pipeline_metadata", JSONB, nullable=True),
        sa.Column("citation_verification", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.CheckConstraint("overall_confidence >= 0 AND overall_confidence <= 1",
                           name="ck_predictions_overall_confidence_range"),
    )
    op.create_index("ix_predictions_case_id", "predictions", ["case_id"])
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])
    op.create_index("ix_predictions_pipeline_version", "predictions", ["pipeline_version"])

    op.create_table(
        "disputes",
        sa.Column("dispute_id", sa.String, primary_key=True),
        sa.Column("invite_code", sa.String, nullable=False, unique=True),
        sa.Column("status", sa.Enum(name="dispute_status", create_type=False), nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("created_by_role", sa.Enum(name="party_role", create_type=False), nullable=True),
        sa.Column("tenant_session_id", sa.String,
                  sa.ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True),
        sa.Column("landlord_session_id", sa.String,
                  sa.ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True),
        sa.Column("property_address", sa.Text, nullable=True),
        sa.Column("property_postcode", sa.String, nullable=True),
        sa.Column("deposit_amount", sa.Numeric, nullable=True),
        sa.Column("cached_prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="SET NULL"), nullable=True),
        sa.Column("prediction_cache_key", sa.String, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=False),
        sa.CheckConstraint("deposit_amount IS NULL OR deposit_amount >= 0",
                           name="ck_disputes_deposit_amount_nonnegative"),
    )
    op.create_index("ix_disputes_tenant_session_id", "disputes", ["tenant_session_id"])
    op.create_index("ix_disputes_landlord_session_id", "disputes", ["landlord_session_id"])
    op.create_index("ix_disputes_cached_prediction_id", "disputes", ["cached_prediction_id"])

    op.create_table(
        "prediction_issues",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("issue_type", sa.Enum(name="issue_type", create_type=False), nullable=False),
        sa.Column("issue_description", sa.Text, nullable=True),
        sa.Column("outcome", sa.Enum(name="issue_outcome", create_type=False), nullable=False),
        sa.Column("raw_confidence", sa.Numeric, nullable=False),
        sa.Column("calibrated_confidence", sa.Numeric, nullable=True),
        sa.Column("predicted_amount", sa.Numeric, nullable=True),
        sa.Column("amount_range_lo", sa.Numeric, nullable=True),
        sa.Column("amount_range_hi", sa.Numeric, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("key_factors", JSONB, nullable=True),
        sa.Column("supporting_cases", JSONB, nullable=True),
        sa.Column("counterfactuals", JSONB, nullable=True),
        sa.Column("evidence_strength", sa.Enum(name="evidence_strength", create_type=False), nullable=True),
        sa.Column("data_completeness_impact", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("prediction_id", "ordinal", name="uq_prediction_issues_pred_ordinal"),
        sa.CheckConstraint("raw_confidence >= 0 AND raw_confidence <= 1",
                           name="ck_prediction_issues_raw_confidence_range"),
    )
    op.create_index("ix_prediction_issues_pred_ordinal", "prediction_issues", ["prediction_id", "ordinal"])
    op.create_index("ix_prediction_issues_issue_type", "prediction_issues", ["issue_type"])

    op.create_table(
        "prediction_reasoning_steps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("step_number", sa.Integer, nullable=True),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("prediction_id", "ordinal", name="uq_prediction_reasoning_pred_ordinal"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                           name="ck_prediction_reasoning_confidence_range"),
    )
    op.create_index("ix_prediction_reasoning_pred_ordinal",
                    "prediction_reasoning_steps", ["prediction_id", "ordinal"])

    op.create_table(
        "prediction_citations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("reasoning_step_id", sa.Integer,
                  sa.ForeignKey("prediction_reasoning_steps.id", ondelete="CASCADE"), nullable=True),
        sa.Column("citation_source", sa.Enum(name="citation_source", create_type=False), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("case_reference", sa.Text, nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("region", sa.String, nullable=True),
        sa.Column("paragraph", sa.Text, nullable=True),
        sa.Column("quote", sa.Text, nullable=True),
        sa.Column("relevance", sa.Text, nullable=True),
        sa.Column("similarity_score", sa.Numeric, nullable=True),
        sa.Column("verified", sa.Boolean, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_prediction_citations_pred", "prediction_citations", ["prediction_id"])
    op.create_index("ix_prediction_citations_step", "prediction_citations", ["reasoning_step_id"])
    op.create_index("ix_prediction_citations_source", "prediction_citations", ["citation_source"])

    op.create_table(
        "knowledge_graphs",
        sa.Column("case_id", sa.String, primary_key=True),
        sa.Column("graph_id", sa.String, nullable=False, unique=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=True),
        sa.Column("validation_errors", JSONB, nullable=True),
        sa.Column("validation_warnings", JSONB, nullable=True),
        sa.Column("validation_info", JSONB, nullable=True),
        sa.Column("is_consistent", sa.Boolean, nullable=True),
        sa.Column("data_quality_tier", sa.String, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
    )

    op.create_table(
        "kg_nodes",
        sa.Column("case_id", sa.String,
                  sa.ForeignKey("knowledge_graphs.case_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("node_id", sa.String, primary_key=True),
        sa.Column("node_type", sa.Enum(name="node_type", create_type=False), nullable=False),
        sa.Column("confidence", sa.Numeric, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("source_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("event_date", sa.Date, nullable=True),
        sa.Column("amount", sa.Numeric, nullable=True),
        sa.Column("node_data", JSONB, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1",
                           name="ck_kg_nodes_confidence_range"),
    )
    op.create_index("ix_kg_nodes_case_type", "kg_nodes", ["case_id", "node_type"])
    op.execute(
        "CREATE INDEX ix_kg_nodes_event_timeline ON kg_nodes(case_id, event_date) "
        "WHERE node_type = 'event'"
    )
    op.execute(
        "CREATE INDEX ix_kg_nodes_claim_amount ON kg_nodes(case_id, amount) "
        "WHERE node_type = 'claimed_amount'"
    )

    op.create_table(
        "kg_edges",
        sa.Column("case_id", sa.String, primary_key=True),
        sa.Column("edge_id", sa.String, primary_key=True),
        sa.Column("edge_type", sa.Enum(name="edge_type", create_type=False), nullable=False),
        sa.Column("source_node_id", sa.String, nullable=False),
        sa.Column("target_node_id", sa.String, nullable=False),
        sa.Column("confidence", sa.Numeric, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id", "source_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "target_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1",
                           name="ck_kg_edges_confidence_range"),
    )
    op.create_index("ix_kg_edges_src", "kg_edges", ["case_id", "source_node_id", "edge_type"])
    op.create_index("ix_kg_edges_tgt", "kg_edges", ["case_id", "target_node_id", "edge_type"])

    op.create_table(
        "mediations",
        sa.Column("mediation_id", sa.String, primary_key=True),
        sa.Column("dispute_id", sa.String,
                  sa.ForeignKey("disputes.dispute_id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("status", sa.Enum(name="mediation_status", create_type=False), nullable=False),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=True),
        sa.Column("settled_at", sa.Text, nullable=True),
        sa.Column("settlement_amount", sa.Numeric, nullable=True),
        sa.Column("escalated_at", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=False),
    )

    op.create_table(
        "mediation_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("mediation_id", sa.String,
                  sa.ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        # May be "tenant", "landlord", or "ai_mediator"; keep as String, not party_role enum.
        sa.Column("sender_role", sa.String, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("message_type", sa.Enum(name="message_type", create_type=False), nullable=False),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("offer_id", sa.String, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("mediation_id", "message_id", name="uq_mediation_messages_message_id"),
        sa.UniqueConstraint("mediation_id", "ordinal", name="uq_mediation_messages_med_ordinal"),
    )
    op.create_index("ix_mediation_messages_med_ordinal", "mediation_messages", ["mediation_id", "ordinal"])
    op.create_index("ix_mediation_messages_med_ts", "mediation_messages", ["mediation_id", "timestamp"])
    op.create_index("ix_mediation_messages_offer", "mediation_messages", ["offer_id"])

    op.create_table(
        "structured_offers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("mediation_id", sa.String,
                  sa.ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_id", sa.String, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("amount", sa.Numeric, nullable=False),
        sa.Column("proposed_by_role", sa.Enum(name="party_role", create_type=False), nullable=False),
        sa.Column("status", sa.Enum(name="offer_status", create_type=False), nullable=False),
        sa.Column("proposed_at", sa.Text, nullable=False),
        sa.Column("responded_at", sa.Text, nullable=True),
        sa.Column("counter_amount", sa.Numeric, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("mediation_id", "offer_id", name="uq_structured_offers_offer_id"),
        sa.UniqueConstraint("mediation_id", "ordinal", name="uq_structured_offers_med_ordinal"),
        sa.CheckConstraint("amount >= 0", name="ck_structured_offers_amount_nonnegative"),
    )
    op.create_index("ix_offers_med_ordinal", "structured_offers", ["mediation_id", "ordinal"])
    op.create_index("ix_offers_med_status", "structured_offers", ["mediation_id", "status"])

    op.create_table(
        "evidence_metadata",
        sa.Column("case_id", sa.String, primary_key=True),
        sa.Column("evidence_id", sa.String, primary_key=True),
        sa.Column("evidence_type", sa.Enum(name="evidence_type", create_type=False), nullable=False),
        sa.Column("file_url", sa.Text, nullable=True),
        sa.Column("file_name", sa.Text, nullable=True),
        sa.Column("file_type", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("image_description", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_evidence_metadata_case_id", "evidence_metadata", ["case_id"])
    op.create_index("ix_evidence_metadata_type", "evidence_metadata", ["evidence_type"])


def downgrade() -> None:
    op.drop_table("evidence_metadata")
    op.drop_table("structured_offers")
    op.drop_table("mediation_messages")
    op.drop_table("mediations")
    op.drop_table("kg_edges")
    op.drop_table("kg_nodes")
    op.drop_table("knowledge_graphs")
    op.drop_table("prediction_citations")
    op.drop_table("prediction_reasoning_steps")
    op.drop_table("prediction_issues")
    op.drop_table("disputes")
    op.drop_table("predictions")
    op.drop_table("intake_sessions")

    bind = op.get_bind()
    for name in reversed(list(ENUMS.keys())):
        sa.Enum(name=name).drop(bind, checkfirst=False)
