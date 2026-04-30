import json
from pathlib import Path

from scripts.migrations.audit_json_stores import audit


def test_audit_counts_files_per_dir(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_a.json").write_text("{}")
    (tmp_path / "sessions" / "session_b.json").write_text("{}")
    (tmp_path / "disputes").mkdir()
    (tmp_path / "disputes" / "dispute_x.json").write_text("{}")

    report = audit(tmp_path)

    assert report["counts"]["sessions"] == 2
    assert report["counts"]["disputes"] == 1
    assert report["counts"].get("predictions", 0) == 0


def test_audit_reports_pydantic_validation_errors(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_bad.json").write_text(
        '{"session_id": "x"}'  # missing required fields
    )

    report = audit(tmp_path)

    assert any(
        e["dir"] == "sessions" and e["file"].endswith("session_bad.json")
        for e in report["validation_errors"]
    )


def test_audit_detects_dispute_session_ref_orphans(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "disputes").mkdir()
    (tmp_path / "disputes" / "dispute_x.json").write_text(json.dumps({
        "dispute_id": "DISP-X",
        "invite_code": "ABC123",
        "status": "waiting_for_landlord",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by_role": "tenant",
        "tenant_session_id": "missing-session",
        "landlord_session_id": None,
        "property_address": None,
        "property_postcode": None,
        "deposit_amount": None,
    }))

    report = audit(tmp_path)
    orphans = report["orphans"]

    assert any(
        o["kind"] == "dispute_tenant_session_missing"
        and o["dispute_id"] == "DISP-X"
        for o in orphans
    )


def test_audit_detects_dispute_prediction_mapping_orphans(tmp_path: Path) -> None:
    (tmp_path / "predictions").mkdir()
    (tmp_path / "dispute_predictions").mkdir()
    (tmp_path / "dispute_predictions" / "DISP-Y.json").write_text(json.dumps({
        "dispute_id": "DISP-Y", "prediction_id": "missing-pred",
    }))

    report = audit(tmp_path)
    assert any(
        o["kind"] == "dispute_prediction_missing" and o["prediction_id"] == "missing-pred"
        for o in report["orphans"]
    )


def test_audit_flags_kg_edges_with_missing_nodes(tmp_path: Path) -> None:
    (tmp_path / "knowledge_graphs").mkdir()
    (tmp_path / "knowledge_graphs" / "kg_case1.json").write_text(json.dumps({
        "graph_id": "g1", "case_id": "case1",
        "created_at": "2026-01-01T00:00:00",
        "nodes": [
            {"node_id": "n1", "node_type": "party", "_node_class": "PartyNode",
             "confidence": 1.0, "source": "user_input", "role": "tenant"}
        ],
        "edges": [
            {"edge_id": "e1", "edge_type": "party_owns",
             "source_node_id": "n1", "target_node_id": "MISSING",
             "confidence": 1.0, "source": "user_input", "description": "x"}
        ],
    }))

    report = audit(tmp_path)
    assert any(
        o["kind"] == "kg_edge_missing_target" and o["case_id"] == "case1"
        for o in report["orphans"]
    )


def test_audit_flags_synthetic_merged_case_ids(tmp_path: Path) -> None:
    (tmp_path / "predictions").mkdir()
    (tmp_path / "predictions" / "prediction_x.json").write_text(json.dumps({
        "case_id": "merged-AAA-BBB",
        "prediction_id": "p1",
    }))

    report = audit(tmp_path)
    assert any(
        n["case_id"] == "merged-AAA-BBB" for n in report["synthetic_case_ids"]
    )
