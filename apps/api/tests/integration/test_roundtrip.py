"""Phase 10.1: round-trip identity for every JSON file in data/.

The production data lives in the main repo, not in the worktree.  We derive
the main-repo path from the worktree's .git pointer so this test works on any
machine without hard-coding a path.

FK seeding strategy
-------------------
* sessions        — no inbound FK dependencies; saved as-is.
* disputes        — FK to intake_sessions (tenant/landlord session_id) and
                    predictions (cached_prediction_id).  The repo always sets
                    cached_prediction_id=None on save.  We null out the session
                    FK refs before saving so we don't need to pre-load sessions.
                    The round-trip identity assertion covers the DisputeCase
                    payload; session linkage is tested elsewhere.
* predictions     — FK to disputes (case_id string, no hard constraint in schema).
                    Saved as-is; no seeding needed.
* knowledge_graphs— standalone; saved as-is.
* mediations      — FK to disputes.dispute_id (NOT NULL).  We pre-create a
                    minimal stub dispute with the matching dispute_id before
                    saving the mediation.
* evidence_metadata — no data files exist (0 files); parametrized case skips.

TODO: if future test data includes sessions with real FK deps, re-enable the
FK-linked dispute/mediation seeding instead of nulling refs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from packages.kg_builder.storage.graph_serialization import deserialize_knowledge_graph
from packages.llm_orchestrator.models.conversation import ConversationState
from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus  # noqa: F401
from packages.llm_orchestrator.models.evidence import EvidenceMetadata
from packages.llm_orchestrator.models.mediation import MediationSession
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult
from apps.api.src.db.uow import UnitOfWork


# ---------------------------------------------------------------------------
# Locate data directory
# ---------------------------------------------------------------------------

_WORKTREE_ROOT = Path(__file__).resolve().parents[4]

def _find_data_dir() -> Path:
    """Locate the data/ directory. Prefers worktree-local; falls back to main repo."""
    worktree_data = _WORKTREE_ROOT / "data"
    # If the worktree's own data/ has files, prefer it
    if worktree_data.is_dir() and any(worktree_data.iterdir()):
        return worktree_data

    # Worktree case: .git is a file pointing to the main repo's .git/worktrees/<name>
    git_path = _WORKTREE_ROOT / ".git"
    if git_path.is_file():
        try:
            git_file = git_path.read_text().strip()
            gitdir = Path(git_file.split(": ", 1)[1])
            main_repo = gitdir.parents[1].parent
            main_data = main_repo / "data"
            if main_data.is_dir():
                return main_data
        except (OSError, IndexError):
            pass

    # Standard checkout: .git is a directory; use the worktree's own data/
    return worktree_data


DATA_DIR = _find_data_dir()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _data_files(kind: str) -> list[Path]:
    """Return sorted list of JSON files for a given entity kind."""
    sub = DATA_DIR / kind
    if not sub.is_dir():
        return []
    if kind == "evidence_metadata":
        return sorted(sub.rglob("*.json"))
    return sorted(sub.glob("*.json"))


async def _seed_stub_dispute(uow: UnitOfWork, dispute_id: str) -> None:
    """Insert a minimal dispute row so mediation FK is satisfied."""
    stub = DisputeCase(
        dispute_id=dispute_id,
        status=DisputeStatus.WAITING_FOR_TENANT,
        tenant_session_id=None,
        landlord_session_id=None,
    )
    await uow.disputes.save(stub)


# ---------------------------------------------------------------------------
# Parametrized round-trip test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", [
    "sessions",
    "disputes",
    "predictions",
    "knowledge_graphs",
    "mediations",
    "evidence_metadata",
])
@pytest.mark.asyncio
async def test_roundtrip_every_data_file(kind: str, db_sessionmaker) -> None:
    """Load every JSON file, save through the repo, reload, and assert identity."""
    files = _data_files(kind)
    if not files:
        pytest.skip(f"no data/{kind} files found (DATA_DIR={DATA_DIR})")

    for f in files:
        raw = json.loads(f.read_text())

        # --- Deserialize ---
        if kind == "knowledge_graphs":
            original = deserialize_knowledge_graph(raw)
        elif kind == "sessions":
            original = ConversationState.model_validate(raw)
        elif kind == "disputes":
            original = DisputeCase.model_validate(raw)
        elif kind == "predictions":
            original = PredictionResult.model_validate(raw)
        elif kind == "mediations":
            original = MediationSession.model_validate(raw)
        else:  # evidence_metadata
            data = dict(raw)
            data.setdefault("case_id", f.parent.name)
            data.setdefault("evidence_id", f.stem)
            original = EvidenceMetadata.model_validate(data)

        # --- Apply FK workarounds before save ---
        if kind == "disputes":
            # Null out session FKs to avoid needing pre-seeded sessions.
            # The payload round-trip assertion is about the DisputeCase fields;
            # FK linkage is verified separately.
            original = original.model_copy(
                update={
                    "tenant_session_id": None,
                    "landlord_session_id": None,
                }
            )

        # --- Save ---
        async with UnitOfWork(db_sessionmaker) as uow:
            if kind == "mediations":
                # Mediation has NOT NULL FK to disputes; seed a stub dispute first.
                await _seed_stub_dispute(uow, original.dispute_id)
                await uow.mediations.save(original)
            elif kind == "sessions":
                await uow.sessions.save(original)
            elif kind == "disputes":
                await uow.disputes.save(original)
            elif kind == "predictions":
                await uow.predictions.save(original)
            elif kind == "knowledge_graphs":
                await uow.knowledge_graphs.save(original)
            else:  # evidence_metadata
                await uow.evidence.save(original)

        # --- Reload ---
        async with UnitOfWork(db_sessionmaker) as uow:
            if kind == "sessions":
                reloaded = await uow.sessions.get(original.session_id)
            elif kind == "disputes":
                reloaded = await uow.disputes.get(original.dispute_id)
            elif kind == "predictions":
                reloaded = await uow.predictions.get(original.prediction_id)
            elif kind == "knowledge_graphs":
                reloaded = await uow.knowledge_graphs.get(original.case_id)
            elif kind == "mediations":
                reloaded = await uow.mediations.get(original.mediation_id)
            else:  # evidence_metadata
                reloaded = await uow.evidence.get(original.case_id, original.evidence_id)

        assert reloaded is not None, f"reload returned None for {f.name}"

        # --- Assert identity ---
        orig_dump = original.model_dump(mode="json")
        reloaded_dump = reloaded.model_dump(mode="json")

        # KG nodes/edges have no guaranteed order from Postgres; the repo sorts
        # by ordinal on read (which matches insertion order = source order), but
        # sort explicitly for safety in case source JSON is not sorted.
        if kind == "knowledge_graphs":
            for d in (orig_dump, reloaded_dump):
                d["nodes"] = sorted(
                    d.get("nodes") or [], key=lambda n: n.get("node_id", "")
                )
                d["edges"] = sorted(
                    d.get("edges") or [], key=lambda e: e.get("edge_id", "")
                )

        assert reloaded_dump == orig_dump, (
            f"round-trip mismatch for {f.name}\n"
            f"  orig keys: {set(orig_dump)}\n"
            f"  reload keys: {set(reloaded_dump)}"
        )
