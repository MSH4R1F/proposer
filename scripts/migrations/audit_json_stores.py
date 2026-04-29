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

    for d in DIRS:
        sub = data_dir / d
        if not sub.exists() or not sub.is_dir():
            counts[d] = 0
            continue
        files = sorted(sub.rglob("*.json") if d == "evidence_metadata" else sub.glob("*.json"))
        counts[d] = len(files)

        model = MODEL_FOR_DIR.get(d)
        if model is None and d != "knowledge_graphs":
            continue
        for f in files:
            try:
                data = json.loads(f.read_text())
                if d == "knowledge_graphs":
                    _validate_kg_payload(data)
                else:
                    model.model_validate(data)
            except Exception as exc:
                validation_errors.append(
                    {"dir": d, "file": str(f), "error": repr(exc)[:500]}
                )
    return {"counts": counts, "validation_errors": validation_errors}


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
