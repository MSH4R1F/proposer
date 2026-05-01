"""Structural tests for the Proposition KG ORM rows (SHA-36 Task 2).

These are pure metadata-inspection tests — no Postgres connection needed.
They verify column names, key constraints, indexes, and FK cascade semantics.
The actual migration that creates these tables in the live schema is Task 3.
"""

from sqlalchemy import inspect

from apps.api.src.db.models import (
    DecisionDocumentRow,
    PropositionEdgeRow,
    PropositionExtractionRunRow,
    PropositionRow,
)


# ---------------------------------------------------------------------------
# DecisionDocumentRow
# ---------------------------------------------------------------------------


def test_decision_document_columns() -> None:
    cols = {c.name for c in inspect(DecisionDocumentRow).columns}
    expected = {
        "document_id",
        "case_reference",
        "source_url",
        "local_path",
        "year",
        "category",
        "case_type_code",
        "region_code",
        "decision_date",
        "content_sha256",
        "text_sha256",
        "char_count",
        "page_count",
        "extraction_method",
        "metadata",
        "created_at",
    }
    assert cols == expected


def test_decision_document_unique_content_sha256() -> None:
    table = DecisionDocumentRow.__table__
    uniques = [
        c for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"
    ]
    found = any(
        "content_sha256" in {col.name for col in uc.columns} for uc in uniques
    )
    if not found:
        col = table.c.content_sha256
        assert col.unique, "content_sha256 must be unique"


def test_extraction_method_not_null() -> None:
    col = inspect(DecisionDocumentRow).columns["extraction_method"]
    assert col.nullable is False


def test_decision_document_metadata_attribute_renamed() -> None:
    """Python attribute is `metadata_`; DB column name is `metadata`."""
    assert hasattr(DecisionDocumentRow, "metadata_")
    col = DecisionDocumentRow.__table__.c.metadata
    assert col.nullable is False


# ---------------------------------------------------------------------------
# PropositionExtractionRunRow
# ---------------------------------------------------------------------------


def test_proposition_run_columns() -> None:
    cols = {c.name for c in inspect(PropositionExtractionRunRow).columns}
    expected = {
        "run_id",
        "document_id",
        "extractor_version",
        "prompt_version",
        "prompt_sha256",
        "model",
        "status",
        "input_chars",
        "chunk_count",
        "proposition_count",
        "edge_count",
        "rejected_count",
        "tokens_in",
        "tokens_out",
        "error_message",
        "created_at",
    }
    assert cols == expected


def test_proposition_run_no_pipeline_unique_constraint() -> None:
    """Phase 1 Task 9 dropped the (document, extractor, prompt, model) unique
    constraint so deliberate re-runs (--force / measurement) are allowed.
    Application-layer --resume in the ingestion CLI handles dedup.
    """
    table = PropositionExtractionRunRow.__table__
    uniques = [
        c for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"
    ]
    triple_names = [{col.name for col in uc.columns} for uc in uniques]
    assert {
        "document_id",
        "extractor_version",
        "prompt_sha256",
        "model",
    } not in triple_names


def test_proposition_run_check_constraints() -> None:
    table = PropositionExtractionRunRow.__table__
    checks = [c for c in table.constraints if c.__class__.__name__ == "CheckConstraint"]
    # input_chars, chunk_count, proposition_count, edge_count, rejected_count,
    # tokens_in, tokens_out — at minimum 5 non-negative checks.
    assert len(checks) >= 5


def test_proposition_run_document_fk_cascades() -> None:
    col = PropositionExtractionRunRow.__table__.c.document_id
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert fks[0].ondelete == "CASCADE"
    assert fks[0].column.table.name == "decision_documents"


# ---------------------------------------------------------------------------
# PropositionRow
# ---------------------------------------------------------------------------


def test_proposition_columns() -> None:
    cols = {c.name for c in inspect(PropositionRow).columns}
    expected = {
        "proposition_id",
        "document_id",
        "run_id",
        "case_reference",
        "text",
        "source_passage",
        "paragraph_ref",
        "source_start_char",
        "source_end_char",
        "page_start",
        "page_end",
        "proposition_type",
        "issue_tags",
        "entities",
        "confidence",
        "created_at",
    }
    assert cols == expected


def test_proposition_indexes() -> None:
    table = PropositionRow.__table__
    index_names = {ix.name for ix in table.indexes}
    expected = {
        "ix_propositions_case_reference",
        "ix_propositions_document_type",
        "ix_propositions_paragraph_ref",
        "ix_propositions_issue_tags_gin",
        "ix_propositions_entities_gin",
    }
    assert expected.issubset(index_names)


def test_proposition_check_constraints_present() -> None:
    table = PropositionRow.__table__
    checks = [c for c in table.constraints if c.__class__.__name__ == "CheckConstraint"]
    # confidence, source_start_char, source_end_char, page_start, page_end
    assert len(checks) >= 5


def test_proposition_document_fk_cascades() -> None:
    col = PropositionRow.__table__.c.document_id
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert fks[0].ondelete == "CASCADE"


def test_proposition_run_fk_set_null() -> None:
    col = PropositionRow.__table__.c.run_id
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert fks[0].ondelete == "SET NULL"
    assert col.nullable is True


def test_proposition_gin_indexes_use_gin() -> None:
    table = PropositionRow.__table__
    by_name = {ix.name: ix for ix in table.indexes}
    for gin_name in ("ix_propositions_issue_tags_gin", "ix_propositions_entities_gin"):
        ix = by_name[gin_name]
        # postgresql_using is stashed on the dialect kwargs
        assert ix.dialect_kwargs.get("postgresql_using") == "gin"


# ---------------------------------------------------------------------------
# PropositionEdgeRow
# ---------------------------------------------------------------------------


def test_proposition_edge_columns() -> None:
    cols = {c.name for c in inspect(PropositionEdgeRow).columns}
    expected = {
        "edge_id",
        "from_proposition_id",
        "to_proposition_id",
        "document_id",
        "edge_type",
        "rationale",
        "confidence",
        "created_at",
    }
    assert cols == expected


def test_proposition_edge_no_self_loop_check() -> None:
    table = PropositionEdgeRow.__table__
    check_names = {
        c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_proposition_edges_no_self_loop" in check_names


def test_proposition_edge_unique_triple() -> None:
    table = PropositionEdgeRow.__table__
    uniques = [
        c for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"
    ]
    found = any(
        {"from_proposition_id", "to_proposition_id", "edge_type"}
        == {col.name for col in uc.columns}
        for uc in uniques
    )
    assert found, "missing uq_proposition_edges_triple"


def test_proposition_edge_fks_cascade() -> None:
    table = PropositionEdgeRow.__table__
    for col_name in ("from_proposition_id", "to_proposition_id", "document_id"):
        fks = list(table.c[col_name].foreign_keys)
        assert len(fks) == 1, f"{col_name} should have exactly one FK"
        assert fks[0].ondelete == "CASCADE", f"{col_name} FK should cascade"
