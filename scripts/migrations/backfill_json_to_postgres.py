"""Backfill JSON state directories into Postgres."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Add packages directory to path for when this is run as a module
_project_root = Path(__file__).parent.parent.parent
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

log = logging.getLogger(__name__)

VALIDATORS: dict[str, Any] = {
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
                raw = json.loads(f.read_text())
                # Derive missing fields for evidence_metadata before validation
                if d == "evidence_metadata":
                    if "case_id" not in raw:
                        raw["case_id"] = f.parent.name
                    if "evidence_id" not in raw:
                        raw["evidence_id"] = f.stem
                model.model_validate(raw)
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

    return {"planned": planned, "invalid": invalid}


class BackfillError(RuntimeError):
    pass


def _read_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text())


def _log_event(report_path: Path, **kwargs: Any) -> None:
    """Append a single JSON line to the backfill report."""
    line = {"timestamp": datetime.now(timezone.utc).isoformat(), **kwargs}
    with open(report_path, "a") as f:
        f.write(json.dumps(line) + "\n")


async def commit(
    data_dir: Path,
    sessionmaker: Any,
    *,
    report_path: Optional[Path] = None,
) -> dict[str, int]:
    """Load all JSON entities into Postgres in FK-correct order.

    Uses one AsyncSession transaction: all inserts are committed atomically.
    On any exception the session rolls back automatically (context manager).
    Idempotent: underlying repos use pg_insert + on_conflict_do_update.
    """
    # 1. Preflight via dry_run
    pre = dry_run(data_dir)
    if pre["invalid"]:
        raise BackfillError(
            f"Preflight found {len(pre['invalid'])} invalid files; refusing to commit"
        )

    report_path = report_path or (data_dir / "_backfill_report.jsonl")
    counts: dict[str, int] = {k: 0 for k in (
        "sessions", "predictions", "disputes", "dispute_predictions",
        "knowledge_graphs", "mediations", "evidence_metadata",
    )}

    # Import repos inside the function so the module can be imported without
    # the full apps package being on sys.path (e.g. during dry_run-only use).
    from apps.api.src.db.repositories import (
        DisputesRepo,
        EvidenceRepo,
        KnowledgeGraphRepo,
        MediationsRepo,
        PredictionsRepo,
        SessionsRepo,
    )

    def _glob(dirname: str) -> list[Path]:
        sub = data_dir / dirname
        return sorted(sub.glob("*.json")) if sub.is_dir() else []

    async with sessionmaker() as session:
        sessions_repo = SessionsRepo(session)
        predictions_repo = PredictionsRepo(session)
        disputes_repo = DisputesRepo(session)
        kg_repo = KnowledgeGraphRepo(session)
        mediations_repo = MediationsRepo(session)
        evidence_repo = EvidenceRepo(session)

        # 1) intake_sessions
        for f in _glob("sessions"):
            state = ConversationState.model_validate(_read_json(f))
            await sessions_repo.save(state)
            counts["sessions"] += 1
            _log_event(
                report_path,
                dir="sessions",
                file=f.name,
                status="saved",
                id=state.session_id,
            )
            log.debug("session saved: %s", state.session_id)

        # 2) predictions (with children)
        for f in _glob("predictions"):
            p = PredictionResult.model_validate(_read_json(f))
            await predictions_repo.save(p)
            counts["predictions"] += 1
            _log_event(
                report_path,
                dir="predictions",
                file=f.name,
                status="saved",
                id=p.prediction_id,
            )
            log.debug("prediction saved: %s", p.prediction_id)

        # 3) disputes (without cached_prediction_id — FK safe)
        for f in _glob("disputes"):
            d = DisputeCase.model_validate(_read_json(f))
            await disputes_repo.save(d)
            counts["disputes"] += 1
            _log_event(
                report_path,
                dir="disputes",
                file=f.name,
                status="saved",
                id=d.dispute_id,
            )
            log.debug("dispute saved: %s", d.dispute_id)

        # 4) dispute_predictions mappings
        for f in _glob("dispute_predictions"):
            mapping = _read_json(f)
            did = mapping["dispute_id"]
            pid = mapping.get("prediction_id")
            cache_key = mapping.get("cache_key")
            await disputes_repo.set_cached_prediction_id(did, pid, cache_key=cache_key)
            counts["dispute_predictions"] += 1
            _log_event(
                report_path,
                dir="dispute_predictions",
                file=f.name,
                status="mapped",
                dispute_id=did,
                prediction_id=pid,
            )
            log.debug("dispute_prediction mapped: %s -> %s", did, pid)

        # 5) knowledge_graphs
        for f in _glob("knowledge_graphs"):
            data = _read_json(f)
            kg = deserialize_knowledge_graph(data)
            await kg_repo.save(kg)
            counts["knowledge_graphs"] += 1
            _log_event(
                report_path,
                dir="knowledge_graphs",
                file=f.name,
                status="saved",
                case_id=kg.case_id,
            )
            log.debug("knowledge_graph saved: %s", kg.case_id)

        # 6) mediations
        for f in _glob("mediations"):
            m = MediationSession.model_validate(_read_json(f))
            await mediations_repo.save(m)
            counts["mediations"] += 1
            _log_event(
                report_path,
                dir="mediations",
                file=f.name,
                status="saved",
                id=m.mediation_id,
            )
            log.debug("mediation saved: %s", m.mediation_id)

        # 7) evidence_metadata (nested per case_id)
        ev_dir = data_dir / "evidence_metadata"
        if ev_dir.is_dir():
            for f in sorted(ev_dir.rglob("*.json")):
                data = _read_json(f)
                # Derive case_id from parent dir name if absent in the JSON
                if "case_id" not in data:
                    data["case_id"] = f.parent.name
                # Derive evidence_id from filename stem if absent
                if "evidence_id" not in data:
                    data["evidence_id"] = f.stem
                em = EvidenceMetadata.model_validate(data)
                await evidence_repo.save(em)
                counts["evidence_metadata"] += 1
                _log_event(
                    report_path,
                    dir="evidence_metadata",
                    file=str(f.relative_to(data_dir)),
                    status="saved",
                    case_id=em.case_id,
                    evidence_id=em.evidence_id,
                )
                log.debug("evidence saved: %s/%s", em.case_id, em.evidence_id)

        await session.commit()

    return counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--archive-json", action="store_true")
    p.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="override DATABASE_URL env var",
    )
    args = p.parse_args()

    if args.dry_run:
        report = dry_run(args.data_dir)
        print(json.dumps(report, indent=2))
        return

    if args.commit:
        import os

        from sqlalchemy.ext.asyncio import async_sessionmaker
        from apps.api.src.db.engine import create_engine_from_url

        url = args.database_url or os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("--commit requires DATABASE_URL or --database-url")
        engine = create_engine_from_url(url)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            counts = asyncio.run(commit(args.data_dir, sm))
            print(json.dumps({"committed": counts}, indent=2))
        finally:
            asyncio.run(engine.dispose())
        return

    raise NotImplementedError("--verify / --archive-json land in 4.3 / 11.3")


if __name__ == "__main__":
    main()
