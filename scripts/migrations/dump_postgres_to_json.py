"""Dump Postgres state back to the JSON-on-disk shape.

Used for rollback insurance: if the migration goes wrong, you can dump the
DB back to the directory layout the previous JSONStore code understood.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root so packages/ resolves when run directly.
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.db.models import DisputeRow, PredictionRow, MediationSessionRow, EvidenceMetadataRow
from apps.api.src.db.repositories import (
    DisputesRepo,
    EvidenceRepo,
    KnowledgeGraphRepo,
    MediationsRepo,
    PredictionsRepo,
    SessionsRepo,
)
from packages.kg_builder.storage.graph_serialization import serialize_knowledge_graph
from packages.llm_orchestrator.models.conversation import ConversationState
from packages.llm_orchestrator.models.dispute import DisputeCase
from packages.llm_orchestrator.models.evidence import EvidenceMetadata
from packages.llm_orchestrator.models.mediation import MediationSession
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult


async def dump(
    sessionmaker: async_sessionmaker[AsyncSession],
    out_dir: Path,
) -> dict[str, int]:
    """Dump every entity from Postgres to JSON files under out_dir.

    Output directory shape matches what backfill_json_to_postgres expects as
    input, so this can be used as a round-trip rollback tool.
    """
    counts: dict[str, int] = {k: 0 for k in (
        "sessions",
        "predictions",
        "disputes",
        "dispute_predictions",
        "knowledge_graphs",
        "mediations",
        "evidence_metadata",
    )}

    async with sessionmaker() as session:
        sessions_repo = SessionsRepo(session)
        disputes_repo = DisputesRepo(session)
        kg_repo = KnowledgeGraphRepo(session)

        # 1) sessions
        sessions_dir = out_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        for state in await sessions_repo.list_all():
            (sessions_dir / f"{state.session_id}.json").write_text(
                json.dumps(state.model_dump(mode="json"), indent=2, default=str)
            )
            counts["sessions"] += 1

        # 2) predictions — no list_all on PredictionsRepo; use raw select
        predictions_dir = out_dir / "predictions"
        predictions_dir.mkdir(parents=True, exist_ok=True)
        result = await session.execute(select(PredictionRow))
        for row in result.scalars():
            p = PredictionResult.model_validate(row.payload)
            (predictions_dir / f"{p.prediction_id}.json").write_text(
                json.dumps(p.model_dump(mode="json"), indent=2, default=str)
            )
            counts["predictions"] += 1

        # 3) disputes + dispute_predictions (derived from cached_prediction_id)
        disputes_dir = out_dir / "disputes"
        dispute_predictions_dir = out_dir / "dispute_predictions"
        disputes_dir.mkdir(parents=True, exist_ok=True)
        dispute_predictions_dir.mkdir(parents=True, exist_ok=True)
        for d in await disputes_repo.list_all():
            (disputes_dir / f"{d.dispute_id}.json").write_text(
                json.dumps(d.model_dump(mode="json"), indent=2, default=str)
            )
            counts["disputes"] += 1
            # dispute_predictions mapping lives on the DB row, not the Pydantic model
            row = await session.get(DisputeRow, d.dispute_id)
            if row and row.cached_prediction_id:
                mapping: dict[str, str] = {
                    "dispute_id": d.dispute_id,
                    "prediction_id": row.cached_prediction_id,
                }
                if row.prediction_cache_key:
                    mapping["cache_key"] = row.prediction_cache_key
                (dispute_predictions_dir / f"{d.dispute_id}.json").write_text(
                    json.dumps(mapping, indent=2)
                )
                counts["dispute_predictions"] += 1

        # 4) knowledge_graphs — use serialize_knowledge_graph so _node_class
        #    and subclass fields survive the round-trip.
        kg_dir = out_dir / "knowledge_graphs"
        kg_dir.mkdir(parents=True, exist_ok=True)
        for case_id in await kg_repo.list_case_ids():
            kg = await kg_repo.get(case_id)
            if kg is None:
                continue
            data = serialize_knowledge_graph(kg)
            (kg_dir / f"kg_{case_id}.json").write_text(
                json.dumps(data, indent=2, default=str)
            )
            counts["knowledge_graphs"] += 1

        # 5) mediations — no list_all on MediationsRepo; use raw select
        mediations_dir = out_dir / "mediations"
        mediations_dir.mkdir(parents=True, exist_ok=True)
        result = await session.execute(select(MediationSessionRow))
        for row in result.scalars():
            m = MediationSession.model_validate(row.payload)
            (mediations_dir / f"{m.mediation_id}.json").write_text(
                json.dumps(m.model_dump(mode="json"), indent=2, default=str)
            )
            counts["mediations"] += 1

        # 6) evidence_metadata (nested per case_id directory)
        evidence_dir = out_dir / "evidence_metadata"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        result = await session.execute(select(EvidenceMetadataRow))
        for row in result.scalars():
            em = EvidenceMetadata.model_validate(row.payload)
            sub = evidence_dir / em.case_id
            sub.mkdir(parents=True, exist_ok=True)
            (sub / f"{em.evidence_id}.json").write_text(
                json.dumps(em.model_dump(mode="json"), indent=2, default=str)
            )
            counts["evidence_metadata"] += 1

    return counts


def main() -> None:
    import os

    p = argparse.ArgumentParser(
        description="Dump Postgres state back to the JSON-on-disk shape (rollback insurance)."
    )
    p.add_argument("--out", type=Path, required=True, help="output directory")
    p.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="override DATABASE_URL env var",
    )
    args = p.parse_args()

    url = args.database_url or os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("dump requires DATABASE_URL or --database-url")

    from apps.api.src.db.engine import create_engine_from_url

    engine = create_engine_from_url(url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        counts = asyncio.run(dump(sm, args.out))
        print(json.dumps({"dumped": counts}, indent=2))
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
