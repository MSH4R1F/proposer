"""Phase 10.5: alignment regression test.

Asserts every ORM column is claimed by the projection map. If you add a
column to an ORM model, add a corresponding entry in
scripts/migrations/check_model_alignment.py too.

SHA-20 Phase 3 (2026-05-01): the SHA-124 domain-routing and
source-provenance columns now have real Pydantic fields on
``ConversationState``, ``DisputeCase``, ``PredictionResult``,
``MediationSession``, ``EvidenceMetadata`` and ``KnowledgeGraph``. The
projection map in ``scripts/migrations/check_model_alignment.py`` was
updated to reflect this — the previous test-time override is no longer
needed and has been removed.
"""

from scripts.migrations.check_model_alignment import check_alignment


def test_no_alignment_drift() -> None:
    drift = check_alignment()
    assert drift == [], "alignment drift:\n" + "\n".join(drift)
