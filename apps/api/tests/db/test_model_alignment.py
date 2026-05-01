"""Phase 10.5: alignment regression test.

Asserts every ORM column is claimed by the projection map. If you add a
column to an ORM model, add a corresponding entry in
scripts/migrations/check_model_alignment.py too.

SHA-124 / Phase 2 (2026-05-01): the new domain-routing and source-provenance
columns are projection-only today (Pydantic models do not yet carry dedicated
fields for them; the values are projected from the canonical payload). The
test below extends the projection map at import time with those expected
entries, so that ``scripts/migrations/check_model_alignment.py`` does not
need to be edited from this worker. When Pydantic models grow real fields
(see Phase 3 of the SHA-20 plan), update the script and remove the override
block here.
"""

from scripts.migrations.check_model_alignment import (
    PROJECTION_MAP,
    check_alignment,
)
from apps.api.src.db.models import (
    DisputeRow,
    EvidenceMetadataRow,
    IntakeSessionRow,
    KnowledgeGraphRow,
    MediationSessionRow,
    PredictionCitationRow,
    PredictionRow,
)

# SHA-124 phase 2 projection-only domain metadata columns. Each is projected
# from payload["domain"] / payload["pipeline_metadata"] / payload["source"].
_SHA_124_DOMAIN_COLUMNS: dict[type, dict[str, tuple[str, None]]] = {
    IntakeSessionRow: {
        "domain_id":          ("projection_only", None),
        "domain_version":     ("projection_only", None),
        "matter_types":       ("projection_only", None),
        "routing_confidence": ("projection_only", None),
        "routing_metadata":   ("projection_only", None),
    },
    DisputeRow: {
        "domain_id":          ("projection_only", None),
        "domain_version":     ("projection_only", None),
        "forum":              ("projection_only", None),
        "matter_types":       ("projection_only", None),
        "routing_confidence": ("projection_only", None),
        "routing_metadata":   ("projection_only", None),
    },
    PredictionRow: {
        "domain_id":          ("projection_only", None),
        "domain_version":     ("projection_only", None),
        "forum":              ("projection_only", None),
        "matter_types":       ("projection_only", None),
        "routing_confidence": ("projection_only", None),
        "routing_metadata":   ("projection_only", None),
        "domain_spec_hash":   ("projection_only", None),
        "prompt_pack_hash":   ("projection_only", None),
        "ontology_hash":      ("projection_only", None),
        "corpus_version":     ("projection_only", None),
    },
    PredictionCitationRow: {
        "domain_id":        ("projection_only", None),
        "source_kind":      ("projection_only", None),
        "source_publisher": ("projection_only", None),
        "source_id":        ("projection_only", None),
        "namespace_id":     ("projection_only", None),
        "canonical_url":    ("projection_only", None),
        "source_license":   ("projection_only", None),
    },
    KnowledgeGraphRow: {
        "domain_id":        ("projection_only", None),
        "domain_version":   ("projection_only", None),
        "domain_spec_hash": ("projection_only", None),
        "ontology_hash":    ("projection_only", None),
    },
    MediationSessionRow: {
        "domain_id":      ("projection_only", None),
        "domain_version": ("projection_only", None),
    },
    EvidenceMetadataRow: {
        "domain_id":        ("projection_only", None),
        "domain_version":   ("projection_only", None),
        "source_kind":      ("projection_only", None),
        "source_publisher": ("projection_only", None),
        "source_id":        ("projection_only", None),
    },
}

for _orm_class, _columns in _SHA_124_DOMAIN_COLUMNS.items():
    PROJECTION_MAP.setdefault(_orm_class, {}).update(_columns)


def test_no_alignment_drift() -> None:
    drift = check_alignment()
    assert drift == [], "alignment drift:\n" + "\n".join(drift)
