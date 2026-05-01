"""Pydantic <-> SQLAlchemy alignment check.

Run as a CI step (Phase 11.1). Catches indexed-query drift that payload-only
round-trip tests miss: a new column added to the ORM but not surfaced in the
Pydantic model, or vice versa.

Each ORM column must be classified into one of:
- "field": projects directly to a Pydantic field (must have compatible type)
- "tuple_field_lo" / "tuple_field_hi": projects from a tuple-typed Pydantic field
- "payload": canonical JSONB blob holding the full Pydantic dump
- "metadata": metadata JSONB column (mapped from metadata_ Python attr)
- "ordinal": child-row ordinal column with no Pydantic counterpart
- "projection_only": DB-only state (e.g. cached_prediction_id, prediction_cache_key, version)
- "audit": created_at/updated_at timestamps when not in the Pydantic model
- "derived": projection from a Pydantic computed property (e.g. id from autoincrement)
"""

from __future__ import annotations

import sys
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))


from apps.api.src.db.models import (
    DisputeRow,
    EvidenceMetadataRow,
    IntakeSessionRow,
    KGEdgeRow,
    KGNodeRow,
    KnowledgeGraphRow,
    MediationMessageRow,
    MediationSessionRow,
    PredictionCitationRow,
    PredictionIssueRow,
    PredictionReasoningStepRow,
    PredictionRow,
    StructuredOfferRow,
)


# Each value is (kind, pydantic_field_path_or_none).
# Every column present in an ORM table __must__ appear as a key here.
# Allowed kinds:
#   "field"            - 1-to-1 projection to a named Pydantic field
#   "tuple_field_lo"   - lower bound of a tuple/range Pydantic field
#   "tuple_field_hi"   - upper bound of a tuple/range Pydantic field
#   "payload"          - canonical JSONB dump of the full Pydantic model
#   "metadata"         - metadata JSONB column (Python attr: metadata_)
#   "ordinal"          - child-row position integer, no Pydantic counterpart
#   "projection_only"  - DB-only state with no Pydantic field
#   "audit"            - audit timestamps absent from the Pydantic model
#   "derived"          - derived from autoincrement PK or parent FK
PROJECTION_MAP: dict[type, dict[str, tuple[str, str | None]]] = {
    IntakeSessionRow: {
        "session_id":          ("field", "ConversationState.session_id"),
        "case_id":             ("field", "ConversationState.case_file.case_id"),
        "user_role":           ("field", "ConversationState.case_file.user_role"),
        "current_stage":       ("field", "ConversationState.current_stage"),
        "started_at":          ("field", "ConversationState.started_at"),
        "updated_at":          ("field", "ConversationState.updated_at"),
        "intake_complete":     ("field", "ConversationState.case_file.intake_complete"),
        "completeness_score":  ("field", "ConversationState.case_file.completeness_score"),
        "role_explicitly_set": ("field", "ConversationState.role_explicitly_set"),
        "version":             ("projection_only", None),
        # SHA-20 Phase 3: domain routing fields are real Pydantic fields on
        # ConversationState (mirrored on case_file).
        "domain_id":          ("field", "ConversationState.domain_id"),
        "domain_version":     ("field", "ConversationState.domain_version"),
        "matter_types":       ("field", "ConversationState.matter_types"),
        "routing_confidence": ("field", "ConversationState.routing_confidence"),
        "routing_metadata":   ("field", "ConversationState.routing_metadata"),
        "payload":             ("payload", None),
    },
    DisputeRow: {
        "dispute_id":           ("field", "DisputeCase.dispute_id"),
        "invite_code":          ("field", "DisputeCase.invite_code"),
        "status":               ("field", "DisputeCase.status"),
        "created_at":           ("field", "DisputeCase.created_at"),
        "updated_at":           ("field", "DisputeCase.updated_at"),
        "created_by_role":      ("field", "DisputeCase.created_by_role"),
        "tenant_session_id":    ("field", "DisputeCase.tenant_session_id"),
        "landlord_session_id":  ("field", "DisputeCase.landlord_session_id"),
        "property_address":     ("field", "DisputeCase.property_address"),
        "property_postcode":    ("field", "DisputeCase.property_postcode"),
        "deposit_amount":       ("field", "DisputeCase.deposit_amount"),
        "cached_prediction_id": ("projection_only", None),
        "prediction_cache_key": ("projection_only", None),
        "version":              ("projection_only", None),
        # SHA-20 Phase 3: domain routing fields are real Pydantic fields.
        "domain_id":          ("field", "DisputeCase.domain_id"),
        "domain_version":     ("field", "DisputeCase.domain_version"),
        "forum":              ("field", "DisputeCase.forum"),
        "matter_types":       ("field", "DisputeCase.matter_types"),
        "routing_confidence": ("field", "DisputeCase.routing_confidence"),
        "routing_metadata":   ("field", "DisputeCase.routing_metadata"),
        "payload":              ("payload", None),
    },
    PredictionRow: {
        "prediction_id":       ("field", "PredictionResult.prediction_id"),
        "case_id":             ("field", "PredictionResult.case_id"),
        "created_at":          ("field", "PredictionResult.timestamp"),
        "overall_outcome":     ("field", "PredictionResult.overall_outcome"),
        "overall_confidence":  ("field", "PredictionResult.overall_confidence"),
        "range_lo":            ("tuple_field_lo", "PredictionResult.predicted_settlement_range"),
        "range_hi":            ("tuple_field_hi", "PredictionResult.predicted_settlement_range"),
        "pipeline_version":    ("field", "PredictionResult.pipeline_version"),
        "model_version":       ("field", "PredictionResult.model_version"),
        "retrieval_quality":   ("field", "PredictionResult.retrieval_quality"),
        "rag_confidence":      ("field", "PredictionResult.rag_confidence"),
        "pipeline_metadata":   ("field", "PredictionResult.pipeline_metadata"),
        "citation_verification": ("field", "PredictionResult.citation_verification"),
        "metadata":            ("metadata", None),
        # SHA-20 Phase 3: domain routing + reproducibility hashes are real
        # Pydantic fields on PredictionResult.
        "domain_id":          ("field", "PredictionResult.domain_id"),
        "domain_version":     ("field", "PredictionResult.domain_version"),
        "forum":              ("field", "PredictionResult.forum"),
        "matter_types":       ("field", "PredictionResult.matter_types"),
        "routing_confidence": ("field", "PredictionResult.routing_confidence"),
        "routing_metadata":   ("field", "PredictionResult.routing_metadata"),
        "domain_spec_hash":   ("field", "PredictionResult.domain_spec_hash"),
        "prompt_pack_hash":   ("field", "PredictionResult.prompt_pack_hash"),
        "ontology_hash":      ("field", "PredictionResult.ontology_hash"),
        "corpus_version":     ("field", "PredictionResult.corpus_version"),
        "payload":             ("payload", None),
    },
    PredictionIssueRow: {
        "id":                        ("derived", None),
        "prediction_id":             ("derived", None),
        "ordinal":                   ("ordinal", None),
        "issue_type":                ("field", "IssuePrediction.issue_type"),
        "issue_description":         ("field", "IssuePrediction.issue_description"),
        "outcome":                   ("field", "IssuePrediction.outcome"),
        "raw_confidence":            ("field", "IssuePrediction.raw_confidence"),
        "calibrated_confidence":     ("field", "IssuePrediction.calibrated_confidence"),
        "predicted_amount":          ("field", "IssuePrediction.predicted_amount"),
        "amount_range_lo":           ("tuple_field_lo", "IssuePrediction.amount_range"),
        "amount_range_hi":           ("tuple_field_hi", "IssuePrediction.amount_range"),
        "reasoning":                 ("field", "IssuePrediction.reasoning"),
        "key_factors":               ("field", "IssuePrediction.key_factors"),
        "supporting_cases":          ("field", "IssuePrediction.supporting_cases"),
        "counterfactuals":           ("field", "IssuePrediction.counterfactuals"),
        "evidence_strength":         ("field", "IssuePrediction.evidence_strength"),
        "data_completeness_impact":  ("field", "IssuePrediction.data_completeness_impact"),
        "payload":                   ("payload", None),
    },
    PredictionReasoningStepRow: {
        "id":            ("derived", None),
        "prediction_id": ("derived", None),
        "ordinal":       ("ordinal", None),
        "step_number":   ("field", "ReasoningStep.step_number"),
        "category":      ("field", "ReasoningStep.category"),
        "title":         ("field", "ReasoningStep.title"),
        "content":       ("field", "ReasoningStep.content"),
        "confidence":    ("field", "ReasoningStep.confidence"),
        "payload":       ("payload", None),
    },
    PredictionCitationRow: {
        "id":               ("derived", None),
        "prediction_id":    ("derived", None),
        "reasoning_step_id": ("derived", None),
        # issue_ordinal is a DB-internal link back to the parent issue row; no
        # direct Pydantic counterpart on Citation (the parent IssuePrediction
        # owns the ordinal).
        "issue_ordinal":    ("projection_only", None),
        "citation_source":  ("field", "Citation.source"),
        "ordinal":          ("ordinal", None),
        "case_reference":   ("field", "Citation.case_reference"),
        "year":             ("field", "Citation.year"),
        "region":           ("field", "Citation.region"),
        "paragraph":        ("field", "Citation.paragraph"),
        "quote":            ("field", "Citation.quote"),
        "relevance":        ("field", "Citation.relevance"),
        "similarity_score": ("field", "Citation.similarity_score"),
        "verified":         ("field", "Citation.verified"),
        # SHA-20 Phase 3: PredictionCitationRow inherits domain + source
        # provenance from its parent PredictionResult; the Citation Pydantic
        # model itself does not carry these fields, so they remain
        # projection-only at the citation row level.
        "domain_id":        ("projection_only", None),
        "source_kind":      ("projection_only", None),
        "source_publisher": ("projection_only", None),
        "source_id":        ("projection_only", None),
        "namespace_id":     ("projection_only", None),
        "canonical_url":    ("projection_only", None),
        "source_license":   ("projection_only", None),
        "payload":          ("payload", None),
    },
    KnowledgeGraphRow: {
        "case_id":              ("field", "KnowledgeGraph.case_id"),
        "graph_id":             ("field", "KnowledgeGraph.graph_id"),
        "created_at":           ("field", "KnowledgeGraph.created_at"),
        "updated_at":           ("field", "KnowledgeGraph.updated_at"),
        "validation_errors":    ("field", "KnowledgeGraph.validation_errors"),
        "validation_warnings":  ("field", "KnowledgeGraph.validation_warnings"),
        "validation_info":      ("field", "KnowledgeGraph.validation_info"),
        "is_consistent":        ("field", "KnowledgeGraph.is_consistent"),
        "data_quality_tier":    ("field", "KnowledgeGraph.data_quality_tier"),
        # SHA-20 Phase 3: domain routing + ontology hash are real fields on
        # KnowledgeGraph; spec hash is also surfaced at top level.
        "domain_id":        ("field", "KnowledgeGraph.domain_id"),
        "domain_version":   ("field", "KnowledgeGraph.domain_version"),
        "domain_spec_hash": ("field", "KnowledgeGraph.domain_spec_hash"),
        "ontology_hash":    ("field", "KnowledgeGraph.ontology_hash"),
        "metadata":             ("metadata", None),
        "payload":              ("payload", None),
    },
    KGNodeRow: {
        "case_id":      ("derived", None),
        "node_id":      ("field", "BaseNode.node_id"),
        # ordinal tracks insertion order in the DB; no Pydantic counterpart
        "ordinal":      ("ordinal", None),
        "node_type":    ("field", "BaseNode.node_type"),
        "confidence":   ("field", "BaseNode.confidence"),
        "source":       ("field", "BaseNode.source"),
        "source_text":  ("field", "BaseNode.source_text"),
        "created_at":   ("field", "BaseNode.created_at"),
        # event_date and amount are subclass-specific projected columns
        "event_date":   ("field", "EventNode.event_date"),
        "amount":       ("field", "ClaimedAmountNode.amount"),
        "node_data":    ("payload", None),
        "metadata":     ("metadata", None),
        # NOTE: KGNodeRow has no "payload" column — node_data serves that role.
    },
    KGEdgeRow: {
        "case_id":        ("derived", None),
        "edge_id":        ("field", "Edge.edge_id"),
        # ordinal tracks insertion order in the DB; no Pydantic counterpart
        "ordinal":        ("ordinal", None),
        "edge_type":      ("field", "Edge.edge_type"),
        "source_node_id": ("field", "Edge.source_node_id"),
        "target_node_id": ("field", "Edge.target_node_id"),
        "confidence":     ("field", "Edge.confidence"),
        "source":         ("field", "Edge.source"),
        "description":    ("field", "Edge.description"),
        "metadata":       ("metadata", None),
        "payload":        ("payload", None),
    },
    MediationSessionRow: {
        "mediation_id":      ("field", "MediationSession.mediation_id"),
        "dispute_id":        ("field", "MediationSession.dispute_id"),
        "status":            ("field", "MediationSession.status"),
        "started_at":        ("field", "MediationSession.started_at"),
        "updated_at":        ("field", "MediationSession.updated_at"),
        "settled_at":        ("field", "MediationSession.settled_at"),
        "settlement_amount": ("field", "MediationSession.settlement_amount"),
        "escalated_at":      ("field", "MediationSession.escalated_at"),
        "version":           ("projection_only", None),
        # SHA-20 Phase 3: minimal domain routing (id + version) is a real
        # field on MediationSession.
        "domain_id":      ("field", "MediationSession.domain_id"),
        "domain_version": ("field", "MediationSession.domain_version"),
        "payload":           ("payload", None),
    },
    MediationMessageRow: {
        "id":           ("derived", None),
        "mediation_id": ("derived", None),
        "message_id":   ("field", "MediationMessage.id"),
        "ordinal":      ("ordinal", None),
        "sender_role":  ("field", "MediationMessage.sender_role"),
        "content":      ("field", "MediationMessage.content"),
        "message_type": ("field", "MediationMessage.message_type"),
        "timestamp":    ("field", "MediationMessage.timestamp"),
        "offer_id":     ("field", "MediationMessage.offer_id"),
        "metadata":     ("metadata", None),
        "payload":      ("payload", None),
    },
    StructuredOfferRow: {
        "id":               ("derived", None),
        "mediation_id":     ("derived", None),
        "offer_id":         ("field", "StructuredOffer.id"),
        "ordinal":          ("ordinal", None),
        "amount":           ("field", "StructuredOffer.amount"),
        "proposed_by_role": ("field", "StructuredOffer.proposed_by_role"),
        "status":           ("field", "StructuredOffer.status"),
        "proposed_at":      ("field", "StructuredOffer.proposed_at"),
        "responded_at":     ("field", "StructuredOffer.responded_at"),
        "counter_amount":   ("field", "StructuredOffer.counter_amount"),
        "payload":          ("payload", None),
    },
    EvidenceMetadataRow: {
        "case_id":           ("field", "EvidenceMetadata.case_id"),
        "evidence_id":       ("field", "EvidenceMetadata.evidence_id"),
        "evidence_type":     ("field", "EvidenceMetadata.evidence_type"),
        "file_url":          ("field", "EvidenceMetadata.file_url"),
        # storage_path is a DB-internal column (object-store path); the
        # Pydantic model surfaces only the public file_url.
        "storage_path":      ("projection_only", None),
        "file_name":         ("field", "EvidenceMetadata.file_name"),
        "file_type":         ("field", "EvidenceMetadata.file_type"),
        "description":       ("field", "EvidenceMetadata.description"),
        "extracted_text":    ("field", "EvidenceMetadata.extracted_text"),
        "image_description": ("field", "EvidenceMetadata.image_description"),
        # SHA-20 Phase 3: domain routing + source provenance are real fields.
        "domain_id":        ("field", "EvidenceMetadata.domain_id"),
        "domain_version":   ("field", "EvidenceMetadata.domain_version"),
        "source_kind":      ("field", "EvidenceMetadata.source_kind"),
        "source_publisher": ("field", "EvidenceMetadata.source_publisher"),
        "source_id":        ("field", "EvidenceMetadata.source_id"),
        "payload":           ("payload", None),
    },
}

_VALID_KINDS = frozenset({
    "field",
    "tuple_field_lo",
    "tuple_field_hi",
    "payload",
    "metadata",
    "ordinal",
    "projection_only",
    "audit",
    "derived",
})


def check_alignment() -> list[str]:
    """Return a list of drift-violation messages. Empty list means aligned."""
    import inspect
    from apps.api.src.db import models as models_pkg

    drift: list[str] = []

    # Table-level coverage: every ORM class with __tablename__ must be in PROJECTION_MAP.
    expected_tables = set(PROJECTION_MAP.keys())
    declared_orm_classes = set()
    for _, cls in inspect.getmembers(models_pkg, inspect.isclass):
        if hasattr(cls, "__tablename__") and cls.__module__.startswith("apps.api.src.db.models"):
            declared_orm_classes.add(cls)
    missing_tables = declared_orm_classes - expected_tables
    for cls in sorted(missing_tables, key=lambda c: c.__name__):
        drift.append(
            f"{cls.__name__} has __tablename__={cls.__tablename__!r} but is not in PROJECTION_MAP. "
            f"Add an entry to track its column projections."
        )

    for orm_class, mapping in PROJECTION_MAP.items():
        actual_columns = {c.name for c in orm_class.__table__.columns}
        mapped_columns = set(mapping.keys())

        # Columns present in the ORM table but absent from the projection map.
        for col in sorted(actual_columns - mapped_columns):
            drift.append(
                f"{orm_class.__name__}.{col}: exists in ORM but not in the projection map. "
                f"Add it as ('field', 'PydanticClass.field') or one of "
                f"('payload'|'projection_only'|'audit'|'metadata'|'ordinal'|'derived', None)."
            )

        # Entries in the projection map that no longer exist in the ORM table.
        for col in sorted(mapped_columns - actual_columns):
            drift.append(
                f"{orm_class.__name__}.{col}: is in the projection map but no longer "
                f"exists in the ORM table. Remove the stale entry."
            )

        # Entries with unrecognised kind tags.
        for col, (kind, _) in sorted(mapping.items()):
            if kind not in _VALID_KINDS:
                drift.append(
                    f"{orm_class.__name__}.{col}: unknown kind tag '{kind}'. "
                    f"Allowed: {sorted(_VALID_KINDS)}."
                )

    return drift


def main() -> int:
    drift = check_alignment()
    if drift:
        print("ALIGNMENT DRIFT DETECTED:")
        for msg in drift:
            print(f"  - {msg}")
        return 1

    total = sum(len(m) for m in PROJECTION_MAP.values())
    print(f"OK — every ORM column is claimed by the projection map ({total} entries across {len(PROJECTION_MAP)} tables).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
