"""Backfill JSON state directories into Postgres."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add packages directory to path for when this is run as a module
_project_root = Path(__file__).parent.parent.parent
if str(_project_root / "packages") not in sys.path:
    sys.path.insert(0, str(_project_root / "packages"))

from packages.llm_orchestrator.models.conversation import ConversationState
from packages.llm_orchestrator.models.dispute import DisputeCase
from packages.llm_orchestrator.models.mediation import MediationSession
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult
from packages.kg_builder.storage.graph_serialization import (
    deserialize_knowledge_graph,
    serialize_knowledge_graph,
)

VALIDATORS: dict[str, Any] = {
    "sessions": ConversationState,
    "disputes": DisputeCase,
    "predictions": PredictionResult,
    "mediations": MediationSession,
}


def _validate_kg_payload(data: dict[str, Any]) -> None:
    kg = deserialize_knowledge_graph(data)
    serialized = serialize_knowledge_graph(kg)
    if len(serialized.get("nodes", [])) != len(data.get("nodes", [])):
        raise ValueError("KG node count changed during polymorphic round-trip")


def dry_run(data_dir: Path) -> dict[str, Any]:
    planned: dict[str, int] = {}
    invalid: list[dict[str, Any]] = []

    def _json_files(dirname: str) -> list[Path]:
        sub = data_dir / dirname
        if not sub.is_dir():
            return []
        if dirname == "evidence_metadata":
            return sorted(sub.rglob("*.json"))
        return sorted(sub.glob("*.json"))

    for d, model in VALIDATORS.items():
        files = _json_files(d)
        planned[d] = 0
        for f in files:
            try:
                model.model_validate(json.loads(f.read_text()))
                planned[d] += 1
            except Exception as exc:
                invalid.append({"dir": d, "file": str(f), "error": repr(exc)[:300]})

    planned["knowledge_graphs"] = 0
    for f in _json_files("knowledge_graphs"):
        try:
            _validate_kg_payload(json.loads(f.read_text()))
            planned["knowledge_graphs"] += 1
        except Exception as exc:
            invalid.append({"dir": "knowledge_graphs", "file": str(f), "error": repr(exc)[:300]})

    planned["dispute_predictions"] = len(_json_files("dispute_predictions"))
    planned["evidence_metadata"] = len(_json_files("evidence_metadata"))

    return {"planned": planned, "invalid": invalid}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--archive-json", action="store_true")
    args = p.parse_args()

    if args.dry_run:
        report = dry_run(args.data_dir)
        print(json.dumps(report, indent=2))
        return
    raise NotImplementedError("--commit / --verify / --archive-json land in 4.2/4.3/4.4/11.4")


if __name__ == "__main__":
    main()
