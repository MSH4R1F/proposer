"""Phase 10.5: alignment regression test.

Asserts every ORM column is claimed by the projection map. If you add a
column to an ORM model, add a corresponding entry in
scripts/migrations/check_model_alignment.py too.
"""

from scripts.migrations.check_model_alignment import check_alignment


def test_no_alignment_drift() -> None:
    drift = check_alignment()
    assert drift == [], "alignment drift:\n" + "\n".join(drift)
