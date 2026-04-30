"""Audit JSON storage directories before migration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Add repo root and packages directory so direct script execution works.
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_project_root / "packages") not in sys.path:
    sys.path.insert(0, str(_project_root / "packages"))

from packages.llm_orchestrator.models.conversation import ConversationState
from packages.llm_orchestrator.models.dispute import DisputeCase
from packages.llm_orchestrator.models.evidence import EvidenceMetadata
from packages.llm_orchestrator.models.mediation import MediationSession
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult
from packages.kg_builder.storage.graph_serialization import (
    deserialize_knowledge_graph,
    serialize_knowledge_graph,
)

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
    "evidence_metadata": EvidenceMetadata,
}


def _validate_kg_payload(data: dict[str, Any]) -> None:
    kg = deserialize_knowledge_graph(data)
    serialized = serialize_knowledge_graph(kg)
    if len(serialized.get("nodes", [])) != len(data.get("nodes", [])):
        raise ValueError("KG node count changed during polymorphic round-trip")
    if len(serialized.get("edges", [])) != len(data.get("edges", [])):
        raise ValueError("KG edge count changed during polymorphic round-trip")


def _safe_error(exc: Exception) -> str:
    return type(exc).__name__


def _prepare_evidence_payload(raw: dict[str, Any], path: Path) -> dict[str, Any]:
    data = dict(raw)
    path_case_id = path.parent.name
    path_evidence_id = path.stem
    if "case_id" not in data:
        data["case_id"] = path_case_id
    elif data["case_id"] != path_case_id:
        raise ValueError("evidence case_id does not match path")
    if "evidence_id" not in data:
        data["evidence_id"] = path_evidence_id
    elif data["evidence_id"] != path_evidence_id:
        raise ValueError("evidence evidence_id does not match path")
    return data


def audit(data_dir: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    validation_errors: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    synthetic_case_ids: list[dict[str, Any]] = []
    duplicate_keys: list[dict[str, Any]] = []

    session_ids: set[str] = set()
    prediction_ids: set[str] = set()
    raw_disputes: list[dict[str, Any]] = []
    seen: dict[str, dict[str, str]] = {}

    def _track_unique(kind: str, key: Any, file: Path) -> None:
        if key in (None, ""):
            return
        key_str = str(key)
        bucket = seen.setdefault(kind, {})
        if key_str in bucket:
            duplicate_keys.append({
                "kind": kind,
                "key": key_str,
                "first_file": bucket[key_str],
                "second_file": str(file),
            })
        else:
            bucket[key_str] = str(file)

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
                _track_unique("session_id", data.get("session_id"), f)
                case_id = (data.get("case_file") or {}).get("case_id")
                _track_unique("session_case_id", case_id, f)

    predictions_dir = data_dir / "predictions"
    if predictions_dir.is_dir():
        for f in predictions_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            if "prediction_id" in data:
                prediction_ids.add(data["prediction_id"])
                _track_unique("prediction_id", data.get("prediction_id"), f)
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
            _track_unique("dispute_id", data.get("dispute_id"), f)
            _track_unique("invite_code", data.get("invite_code"), f)
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
            _track_unique("dispute_prediction_dispute_id", data.get("dispute_id"), f)
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
            _track_unique("knowledge_graph_case_id", data.get("case_id"), f)
            _track_unique("knowledge_graph_graph_id", data.get("graph_id"), f)
            cid = data.get("case_id", "")
            if isinstance(cid, str) and cid.startswith("merged-"):
                synthetic_case_ids.append({"file": str(f), "case_id": cid})
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
                elif d == "evidence_metadata":
                    data = _prepare_evidence_payload(data, f)
                    model.model_validate(data)
                    _track_unique("evidence_metadata_key", f"{data['case_id']}/{data['evidence_id']}", f)
                else:
                    model.model_validate(data)
            except Exception as exc:
                validation_errors.append({"dir": d, "file": str(f), "error": _safe_error(exc)})

    return {
        "counts": counts,
        "validation_errors": validation_errors,
        "orphans": orphans,
        "duplicate_keys": duplicate_keys,
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
    if report["validation_errors"] or report["orphans"] or report["duplicate_keys"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
