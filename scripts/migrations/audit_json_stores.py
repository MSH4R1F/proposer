"""Audit JSON storage directories before migration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.llm_orchestrator.models.conversation import ConversationState
from packages.llm_orchestrator.models.dispute import DisputeCase
from packages.llm_orchestrator.models.mediation import MediationSession
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult
from packages.kg_builder.storage.json_store import JSONGraphStore

DIRS: tuple[str, ...] = (
    "sessions",
    "disputes",
    "predictions",
    "dispute_predictions",
    "knowledge_graphs",
    "mediations",
    "evidence_metadata",
)

MODEL_FOR_DIR = {
    "sessions": ConversationState,
    "disputes": DisputeCase,
    "predictions": PredictionResult,
    "mediations": MediationSession,
}

# Module-level singleton; storage_dir unused because we only call _serialize_graph
# / _deserialize_graph on already-loaded data, never read from / write to disk.
_KG_STORE_FOR_AUDIT = JSONGraphStore(storage_dir=Path("/tmp/audit-kg-unused"))


def _validate_kg_payload(data: dict[str, Any]) -> None:
    kg = _KG_STORE_FOR_AUDIT._deserialize_graph(data)  # noqa: SLF001
    serialized = _KG_STORE_FOR_AUDIT._serialize_graph(kg)  # noqa: SLF001
    if len(serialized.get("nodes", [])) != len(data.get("nodes", [])):
        raise ValueError("KG node count changed during polymorphic round-trip")


def audit(data_dir: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    validation_errors: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    synthetic_case_ids: list[dict[str, Any]] = []

    session_ids: set[str] = set()
    prediction_ids: set[str] = set()
    raw_disputes: list[dict[str, Any]] = []

    def _read_json(p: Path) -> dict[str, Any] | None:
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    def _json_files(dirname: str) -> list[Path]:
        sub = data_dir / dirname
        if not sub.is_dir():
            return []
        if dirname == "evidence_metadata":
            return sorted(sub.rglob("*.json"))
        return sorted(sub.glob("*.json"))

    for d in DIRS:
        counts[d] = len(_json_files(d))

    sessions_dir = data_dir / "sessions"
    if sessions_dir.is_dir():
        for f in sessions_dir.glob("*.json"):
            data = _read_json(f)
            if data and "session_id" in data:
                session_ids.add(data["session_id"])

    predictions_dir = data_dir / "predictions"
    if predictions_dir.is_dir():
        for f in predictions_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            if "prediction_id" in data:
                prediction_ids.add(data["prediction_id"])
            cid = data.get("case_id", "")
            if isinstance(cid, str) and cid.startswith("merged-"):
                synthetic_case_ids.append({"file": str(f), "case_id": cid})

    disputes_dir = data_dir / "disputes"
    if disputes_dir.is_dir():
        for f in disputes_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            raw_disputes.append({"file": str(f), "data": data})
            ts = data.get("tenant_session_id")
            ls = data.get("landlord_session_id")
            if ts and ts not in session_ids:
                orphans.append({
                    "kind": "dispute_tenant_session_missing",
                    "dispute_id": data.get("dispute_id"),
                    "tenant_session_id": ts,
                })
            if ls and ls not in session_ids:
                orphans.append({
                    "kind": "dispute_landlord_session_missing",
                    "dispute_id": data.get("dispute_id"),
                    "landlord_session_id": ls,
                })

    dp_dir = data_dir / "dispute_predictions"
    if dp_dir.is_dir():
        dispute_ids = {d["data"].get("dispute_id") for d in raw_disputes}
        for f in dp_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            did = data.get("dispute_id")
            pid = data.get("prediction_id")
            if did not in dispute_ids:
                orphans.append({"kind": "dispute_prediction_dispute_missing",
                                "file": str(f), "dispute_id": did})
            if pid not in prediction_ids:
                orphans.append({"kind": "dispute_prediction_missing",
                                "file": str(f), "prediction_id": pid})

    kg_dir = data_dir / "knowledge_graphs"
    if kg_dir.is_dir():
        for f in kg_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            node_ids = {n.get("node_id") for n in data.get("nodes", [])}
            for e in data.get("edges", []):
                if e.get("source_node_id") not in node_ids:
                    orphans.append({
                        "kind": "kg_edge_missing_source",
                        "case_id": data.get("case_id"), "edge_id": e.get("edge_id"),
                        "missing": e.get("source_node_id"),
                    })
                if e.get("target_node_id") not in node_ids:
                    orphans.append({
                        "kind": "kg_edge_missing_target",
                        "case_id": data.get("case_id"), "edge_id": e.get("edge_id"),
                        "missing": e.get("target_node_id"),
                    })

    for d in DIRS:
        sub = data_dir / d
        if not sub.is_dir():
            continue
        model = MODEL_FOR_DIR.get(d)
        if model is None and d != "knowledge_graphs":
            continue
        for f in _json_files(d):
            data = _read_json(f)
            if data is None:
                validation_errors.append({"dir": d, "file": str(f), "error": "unreadable"})
                continue
            try:
                if d == "knowledge_graphs":
                    _validate_kg_payload(data)
                else:
                    model.model_validate(data)
            except Exception as exc:
                validation_errors.append({"dir": d, "file": str(f), "error": repr(exc)[:500]})

    return {
        "counts": counts,
        "validation_errors": validation_errors,
        "orphans": orphans,
        "synthetic_case_ids": synthetic_case_ids,
    }


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    report = audit(args.data_dir)
    out = args.out or (args.data_dir / "_migration_audit_report.json")
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
