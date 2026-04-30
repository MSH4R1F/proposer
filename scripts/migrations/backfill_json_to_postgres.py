"""Backfill JSON state directories into Postgres."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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

log = logging.getLogger(__name__)

VALIDATORS: dict[str, Any] = {
    "sessions": ConversationState,
    "disputes": DisputeCase,
    "predictions": PredictionResult,
    "mediations": MediationSession,
    "evidence_metadata": EvidenceMetadata,
}


def _validate_kg_payload(data: dict[str, Any]) -> Any:
    kg = deserialize_knowledge_graph(data)
    serialized = serialize_knowledge_graph(kg)
    if len(serialized.get("nodes", [])) != len(data.get("nodes", [])):
        raise ValueError("KG node count changed during polymorphic round-trip")
    if len(serialized.get("edges", [])) != len(data.get("edges", [])):
        raise ValueError("KG edge count changed during polymorphic round-trip")
    return kg


def _safe_error(exc: Exception) -> str:
    """Avoid writing PII-bearing Pydantic input values into migration reports."""
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


def dry_run(data_dir: Path) -> dict[str, Any]:
    planned: dict[str, int] = {}
    invalid: list[dict[str, Any]] = []
    seen: dict[str, dict[str, str]] = {}

    def _track_unique(kind: str, key: Any, file: Path) -> None:
        if key in (None, ""):
            return
        key_str = str(key)
        bucket = seen.setdefault(kind, {})
        if key_str in bucket:
            invalid.append({
                "dir": "duplicates",
                "file": str(file),
                "error": "DuplicateSourceKey",
                "kind": kind,
                "key": key_str,
                "first_file": bucket[key_str],
            })
        else:
            bucket[key_str] = str(file)

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
                if d == "evidence_metadata":
                    raw = _prepare_evidence_payload(raw, f)
                obj = model.model_validate(raw)
                if d == "sessions":
                    _track_unique("session_id", obj.session_id, f)
                    _track_unique("session_case_id", obj.case_file.case_id, f)
                elif d == "disputes":
                    _track_unique("dispute_id", obj.dispute_id, f)
                    _track_unique("invite_code", obj.invite_code, f)
                elif d == "predictions":
                    _track_unique("prediction_id", obj.prediction_id, f)
                elif d == "mediations":
                    _track_unique("mediation_id", obj.mediation_id, f)
                    _track_unique("mediation_dispute_id", obj.dispute_id, f)
                elif d == "evidence_metadata":
                    _track_unique("evidence_metadata_key", f"{obj.case_id}/{obj.evidence_id}", f)
                planned[d] += 1
            except Exception as exc:
                invalid.append({"dir": d, "file": str(f), "error": _safe_error(exc)})

    planned["knowledge_graphs"] = 0
    for f in _json_files("knowledge_graphs"):
        try:
            kg = _validate_kg_payload(json.loads(f.read_text()))
            _track_unique("knowledge_graph_case_id", kg.case_id, f)
            _track_unique("knowledge_graph_graph_id", kg.graph_id, f)
            planned["knowledge_graphs"] += 1
        except Exception as exc:
            invalid.append({"dir": "knowledge_graphs", "file": str(f), "error": _safe_error(exc)})

    planned["dispute_predictions"] = 0
    dispute_ids: set[str] = set()
    prediction_ids: set[str] = set()
    for f in _json_files("disputes"):
        try:
            did = _read_json(f).get("dispute_id")
            if did:
                dispute_ids.add(did)
        except Exception:
            pass
    for f in _json_files("predictions"):
        try:
            pid = _read_json(f).get("prediction_id")
            if pid:
                prediction_ids.add(pid)
        except Exception:
            pass
    for f in _json_files("dispute_predictions"):
        try:
            mapping = _read_json(f)
            did = mapping["dispute_id"]
            pid = mapping["prediction_id"]
            if did not in dispute_ids:
                raise ValueError("mapping references missing dispute")
            if pid not in prediction_ids:
                raise ValueError("mapping references missing prediction")
            _track_unique("dispute_prediction_dispute_id", did, f)
            planned["dispute_predictions"] += 1
        except Exception as exc:
            invalid.append({"dir": "dispute_predictions", "file": str(f), "error": _safe_error(exc)})

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
    allow_overwrite: bool = False,
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
    report_events: list[dict[str, Any]] = []
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
    from apps.api.src.db.models import (
        DisputeRow,
        EvidenceMetadataRow,
        KnowledgeGraphRow,
        MediationSessionRow,
        PredictionRow,
        IntakeSessionRow,
    )
    from sqlalchemy import func, select

    def _glob(dirname: str) -> list[Path]:
        sub = data_dir / dirname
        return sorted(sub.glob("*.json")) if sub.is_dir() else []

    async with sessionmaker() as session:
        if not allow_overwrite:
            row_classes = (
                IntakeSessionRow,
                PredictionRow,
                DisputeRow,
                KnowledgeGraphRow,
                MediationSessionRow,
                EvidenceMetadataRow,
            )
            for row_class in row_classes:
                count = await session.scalar(select(func.count()).select_from(row_class))
                if count:
                    raise BackfillError(
                        "Target database is not empty; rerun with --force-overwrite "
                        "only after verifying the source JSON is authoritative"
                    )

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
            report_events.append(dict(
                dir="sessions",
                file=f.name,
                status="saved",
                id=state.session_id,
            ))
            log.debug("session saved: %s", state.session_id)

        # 2) predictions (with children)
        for f in _glob("predictions"):
            p = PredictionResult.model_validate(_read_json(f))
            await predictions_repo.save(p)
            counts["predictions"] += 1
            report_events.append(dict(
                dir="predictions",
                file=f.name,
                status="saved",
                id=p.prediction_id,
            ))
            log.debug("prediction saved: %s", p.prediction_id)

        # 3) disputes (without cached_prediction_id — FK safe)
        for f in _glob("disputes"):
            d = DisputeCase.model_validate(_read_json(f))
            await disputes_repo.save(d)
            counts["disputes"] += 1
            report_events.append(dict(
                dir="disputes",
                file=f.name,
                status="saved",
                id=d.dispute_id,
            ))
            log.debug("dispute saved: %s", d.dispute_id)

        # 4) dispute_predictions mappings
        for f in _glob("dispute_predictions"):
            mapping = _read_json(f)
            did = mapping["dispute_id"]
            pid = mapping["prediction_id"]
            cache_key = mapping.get("cache_key")
            await disputes_repo.set_cached_prediction_id(did, pid, cache_key=cache_key)
            counts["dispute_predictions"] += 1
            report_events.append(dict(
                dir="dispute_predictions",
                file=f.name,
                status="mapped",
                dispute_id=did,
                prediction_id=pid,
            ))
            log.debug("dispute_prediction mapped: %s -> %s", did, pid)

        # 5) knowledge_graphs
        for f in _glob("knowledge_graphs"):
            data = _read_json(f)
            kg = deserialize_knowledge_graph(data)
            await kg_repo.save(kg)
            counts["knowledge_graphs"] += 1
            report_events.append(dict(
                dir="knowledge_graphs",
                file=f.name,
                status="saved",
                case_id=kg.case_id,
            ))
            log.debug("knowledge_graph saved: %s", kg.case_id)

        # 6) mediations
        for f in _glob("mediations"):
            m = MediationSession.model_validate(_read_json(f))
            await mediations_repo.save(m)
            counts["mediations"] += 1
            report_events.append(dict(
                dir="mediations",
                file=f.name,
                status="saved",
                id=m.mediation_id,
            ))
            log.debug("mediation saved: %s", m.mediation_id)

        # 7) evidence_metadata (nested per case_id)
        ev_dir = data_dir / "evidence_metadata"
        if ev_dir.is_dir():
            for f in sorted(ev_dir.rglob("*.json")):
                data = _prepare_evidence_payload(_read_json(f), f)
                em = EvidenceMetadata.model_validate(data)
                await evidence_repo.save(em)
                counts["evidence_metadata"] += 1
                report_events.append(dict(
                    dir="evidence_metadata",
                    file=str(f.relative_to(data_dir)),
                    status="saved",
                    case_id=em.case_id,
                    evidence_id=em.evidence_id,
                ))
                log.debug("evidence saved: %s/%s", em.case_id, em.evidence_id)

        await session.commit()

    for event in report_events:
        _log_event(report_path, **event)
    _log_event(report_path, status="committed", counts=counts)
    return counts


async def verify(
    data_dir: Path,
    sessionmaker: Any,
    *,
    report_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Read every JSON file and assert round-trip identity vs DB."""
    report_path = report_path or (data_dir / "_verify_report.jsonl")
    verified: dict[str, int] = {k: 0 for k in (
        "sessions", "predictions", "disputes", "dispute_predictions",
        "knowledge_graphs", "mediations", "evidence_metadata",
    )}
    mismatches: list[dict[str, Any]] = []

    from apps.api.src.db.repositories import (
        DisputesRepo,
        EvidenceRepo,
        KnowledgeGraphRepo,
        MediationsRepo,
        PredictionsRepo,
        SessionsRepo,
    )
    from apps.api.src.db.models import (
        DisputeRow,
        EvidenceMetadataRow,
        IntakeSessionRow,
        KnowledgeGraphRow,
        MediationSessionRow,
        PredictionRow,
    )
    from sqlalchemy import select

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
        expected_sessions: set[str] = set()
        expected_predictions: set[str] = set()
        expected_disputes: set[str] = set()
        expected_kgs: set[str] = set()
        expected_mediations: set[str] = set()
        expected_evidence: set[tuple[str, str]] = set()
        expected_dispute_predictions: dict[str, tuple[Optional[str], Optional[str]]] = {}

        def _compare(
            *,
            dir_name: str,
            file_name: str,
            key: str,
            src_model: Any,
            loaded_model: Any,
        ) -> bool:
            """Return True and increment verified count when models match.

            Returns False and appends a mismatch entry when they differ.
            A None loaded_model means the row is missing in the DB.
            A string loaded_model is treated as a "diff" kind (used to surface
            deserialization errors from the repo layer without raw PII).
            """
            if loaded_model is None:
                mismatches.append({"dir": dir_name, "file": file_name, "key": key, "kind": "missing"})
                return False
            if isinstance(loaded_model, str):
                # Sentinel: repo raised an exception; string holds kind
                mismatches.append({"dir": dir_name, "file": file_name, "key": key, "kind": loaded_model})
                return False
            src_dump = src_model.model_dump(mode="json")
            loaded_dump = loaded_model.model_dump(mode="json")
            if loaded_dump != src_dump:
                mismatches.append({"dir": dir_name, "file": file_name, "key": key, "kind": "diff"})
                return False
            return True

        # 1) sessions
        for f in _glob("sessions"):
            src = ConversationState.model_validate(_read_json(f))
            expected_sessions.add(src.session_id)
            try:
                loaded = await sessions_repo.get(src.session_id)
            except Exception:
                loaded = "diff"  # repo deserialization failed — treat as mismatch
            if _compare(dir_name="sessions", file_name=f.name, key=src.session_id,
                        src_model=src, loaded_model=loaded):
                verified["sessions"] += 1
                _log_event(report_path, dir="sessions", file=f.name, status="ok", id=src.session_id)

        # 2) predictions
        for f in _glob("predictions"):
            src = PredictionResult.model_validate(_read_json(f))
            expected_predictions.add(src.prediction_id)
            try:
                loaded = await predictions_repo.get(src.prediction_id)
            except Exception:
                loaded = "diff"
            if _compare(
                dir_name="predictions",
                file_name=f.name,
                key=src.prediction_id,
                src_model=src,
                loaded_model=loaded,
            ):
                projection_diffs = await predictions_repo.projection_mismatches(src.prediction_id)
                if projection_diffs:
                    mismatches.append({
                        "dir": "predictions",
                        "file": f.name,
                        "key": src.prediction_id,
                        "kind": "projection_diff",
                        "projections": projection_diffs,
                    })
                    continue
                verified["predictions"] += 1
                _log_event(report_path, dir="predictions", file=f.name, status="ok", id=src.prediction_id)

        # 3) disputes
        for f in _glob("disputes"):
            src = DisputeCase.model_validate(_read_json(f))
            expected_disputes.add(src.dispute_id)
            try:
                loaded = await disputes_repo.get(src.dispute_id)
            except Exception:
                loaded = "diff"
            if _compare(dir_name="disputes", file_name=f.name, key=src.dispute_id,
                        src_model=src, loaded_model=loaded):
                verified["disputes"] += 1
                _log_event(report_path, dir="disputes", file=f.name, status="ok", id=src.dispute_id)

        # 4) dispute_predictions: check dispute.cached_prediction_id matches mapping
        for f in _glob("dispute_predictions"):
            mapping = _read_json(f)
            did = mapping["dispute_id"]
            expected_pid = mapping["prediction_id"]
            expected_cache_key = mapping.get("cache_key")
            expected_dispute_predictions[did] = (expected_pid, expected_cache_key)
            row = await session.get(DisputeRow, did)
            if row is None:
                mismatches.append({
                    "dir": "dispute_predictions", "file": f.name,
                    "key": did, "kind": "missing_dispute",
                })
            elif row.cached_prediction_id != expected_pid:
                mismatches.append({
                    "dir": "dispute_predictions", "file": f.name,
                    "key": did, "kind": "cached_prediction_id_diff",
                })
            elif row.prediction_cache_key != expected_cache_key:
                mismatches.append({
                    "dir": "dispute_predictions", "file": f.name,
                    "key": did, "kind": "prediction_cache_key_diff",
                })
            else:
                verified["dispute_predictions"] += 1
                _log_event(report_path, dir="dispute_predictions", file=f.name, status="ok", dispute_id=did)

        # 5) knowledge_graphs
        for f in _glob("knowledge_graphs"):
            src_data = _read_json(f)
            src_kg = deserialize_knowledge_graph(src_data)
            expected_kgs.add(src_kg.case_id)
            try:
                loaded = await kg_repo.get(src_kg.case_id)
            except Exception:
                loaded = "diff"
            if _compare(dir_name="knowledge_graphs", file_name=f.name, key=src_kg.case_id,
                        src_model=src_kg, loaded_model=loaded):
                verified["knowledge_graphs"] += 1
                _log_event(report_path, dir="knowledge_graphs", file=f.name, status="ok", case_id=src_kg.case_id)

        # 6) mediations
        for f in _glob("mediations"):
            src = MediationSession.model_validate(_read_json(f))
            expected_mediations.add(src.mediation_id)
            try:
                loaded = await mediations_repo.get(src.mediation_id)
            except Exception:
                loaded = "diff"
            if _compare(dir_name="mediations", file_name=f.name, key=src.mediation_id,
                        src_model=src, loaded_model=loaded):
                verified["mediations"] += 1
                _log_event(report_path, dir="mediations", file=f.name, status="ok", id=src.mediation_id)

        # 7) evidence_metadata (nested per case_id directory)
        ev_dir = data_dir / "evidence_metadata"
        if ev_dir.is_dir():
            for f in sorted(ev_dir.rglob("*.json")):
                data = _prepare_evidence_payload(_read_json(f), f)
                src = EvidenceMetadata.model_validate(data)
                expected_evidence.add((src.case_id, src.evidence_id))
                try:
                    loaded = await evidence_repo.get(src.case_id, src.evidence_id)
                except Exception:
                    loaded = "diff"
                key = f"{src.case_id}/{src.evidence_id}"
                if _compare(
                    dir_name="evidence_metadata",
                    file_name=str(f.relative_to(data_dir)),
                    key=key,
                    src_model=src,
                    loaded_model=loaded,
                ):
                    verified["evidence_metadata"] += 1
                    _log_event(
                        report_path,
                        dir="evidence_metadata",
                        file=str(f.relative_to(data_dir)),
                        status="ok",
                        key=key,
                    )

        async def _scalar_set(column: Any) -> set[str]:
            result = await session.execute(select(column))
            return {value for (value,) in result.all()}

        extra_checks = [
            ("sessions", expected_sessions, await _scalar_set(IntakeSessionRow.session_id)),
            ("predictions", expected_predictions, await _scalar_set(PredictionRow.prediction_id)),
            ("disputes", expected_disputes, await _scalar_set(DisputeRow.dispute_id)),
            ("knowledge_graphs", expected_kgs, await _scalar_set(KnowledgeGraphRow.case_id)),
            ("mediations", expected_mediations, await _scalar_set(MediationSessionRow.mediation_id)),
        ]
        for dir_name, source_keys, db_keys in extra_checks:
            for key in sorted(db_keys - source_keys):
                mismatches.append({"dir": dir_name, "key": key, "kind": "extra_db_row"})

        evidence_rows = await session.execute(
            select(EvidenceMetadataRow.case_id, EvidenceMetadataRow.evidence_id)
        )
        db_evidence = {(case_id, evidence_id) for case_id, evidence_id in evidence_rows.all()}
        for case_id, evidence_id in sorted(db_evidence - expected_evidence):
            mismatches.append({
                "dir": "evidence_metadata",
                "key": f"{case_id}/{evidence_id}",
                "kind": "extra_db_row",
            })

        cached_rows = await session.execute(
            select(
                DisputeRow.dispute_id,
                DisputeRow.cached_prediction_id,
                DisputeRow.prediction_cache_key,
            ).where(DisputeRow.cached_prediction_id.is_not(None))
        )
        for dispute_id, prediction_id, cache_key in cached_rows.all():
            expected = expected_dispute_predictions.get(dispute_id)
            if expected is None:
                mismatches.append({
                    "dir": "dispute_predictions",
                    "key": dispute_id,
                    "kind": "extra_db_row",
                })
            elif expected != (prediction_id, cache_key):
                mismatches.append({
                    "dir": "dispute_predictions",
                    "key": dispute_id,
                    "kind": "cache_projection_diff",
                })

    return {"verified": verified, "mismatches": mismatches}


async def archive_json(
    data_dir: Path,
    archive_dir: Path,
    *,
    sessionmaker: Optional[Any] = None,  # for verify if not pre-run
    skip_verify: bool = False,
) -> dict[str, Any]:
    """Archive migrated JSON dirs to a private archive root.

    Atomic-ish: refuses to start if anything looks wrong, moves dirs one at
    a time with shutil.move (POSIX rename when same filesystem). Writes a
    manifest summarizing what moved.
    """
    import shutil
    from datetime import datetime, timezone

    # 1. Path containment safety
    data_resolved = data_dir.resolve()
    archive_resolved = archive_dir.resolve()
    try:
        if archive_resolved.is_relative_to(data_resolved):
            raise BackfillError(
                f"archive-dir {archive_resolved} is inside data dir {data_resolved}; "
                f"choose an archive root outside the repo's data/ tree"
            )
    except AttributeError:
        # Python 3.8 fallback
        if str(archive_resolved).startswith(str(data_resolved) + "/"):
            raise BackfillError(
                f"archive-dir {archive_resolved} is inside data dir {data_resolved}; "
                f"choose an archive root outside the repo's data/ tree"
            )

    # 2. Refuse if audit report contains unresolved errors
    audit_report_path = data_dir / "_migration_audit_report.json"
    if audit_report_path.exists():
        report = json.loads(audit_report_path.read_text())
        if report.get("validation_errors"):
            raise BackfillError("audit report contains unresolved validation_errors")
        if report.get("orphans"):
            raise BackfillError("audit report contains unresolved orphans")

    # 3. Run verify unless skipped
    if not skip_verify and sessionmaker is not None:
        verify_result = await verify(data_dir, sessionmaker)
        if verify_result["mismatches"]:
            raise BackfillError(
                f"verify reported {len(verify_result['mismatches'])} mismatches; refusing to archive"
            )

    # 4. Move each entity dir
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_root = archive_dir / timestamp
    target_root.mkdir(parents=True, exist_ok=True)

    moved: dict[str, str] = {}
    for entity_dir_name in (
        "sessions", "disputes", "predictions", "dispute_predictions",
        "knowledge_graphs", "mediations", "evidence_metadata",
    ):
        src = data_dir / entity_dir_name
        if not src.is_dir():
            continue
        dst = target_root / entity_dir_name
        shutil.move(str(src), str(dst))
        moved[entity_dir_name] = str(dst)

    # 5. chmod 700 (best-effort)
    try:
        os.chmod(archive_dir, 0o700)
        os.chmod(target_root, 0o700)
    except OSError:
        pass

    # 6. Write redacted manifest in the repo
    manifest = {
        "timestamp": timestamp,
        "source": str(data_dir),
        "archive_root": str(target_root),
        "moved_dirs": list(moved.keys()),
    }
    (data_dir / f"_archive_manifest_{timestamp}.json").write_text(
        json.dumps(manifest, indent=2)
    )

    return manifest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--archive-json", action="store_true")
    p.add_argument("--archive-dir", type=Path, default=None,
                   help="destination root for --archive-json (must be outside data-dir)")
    p.add_argument(
        "--force-overwrite",
        action="store_true",
        help="allow commit into a non-empty target DB after manual verification",
    )
    p.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="override DATABASE_URL env var",
    )
    args = p.parse_args()
    modes = [args.dry_run, args.commit, args.verify, args.archive_json]
    if sum(bool(m) for m in modes) != 1:
        raise SystemExit("choose exactly one of --dry-run, --commit, --verify, --archive-json")

    if args.dry_run:
        report = dry_run(args.data_dir)
        print(json.dumps(report, indent=2))
        if report["invalid"]:
            sys.exit(1)
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
            counts = asyncio.run(
                commit(args.data_dir, sm, allow_overwrite=args.force_overwrite)
            )
            print(json.dumps({"committed": counts}, indent=2))
        finally:
            asyncio.run(engine.dispose())
        return

    if args.verify:
        import os

        from sqlalchemy.ext.asyncio import async_sessionmaker
        from apps.api.src.db.engine import create_engine_from_url

        url = args.database_url or os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("--verify requires DATABASE_URL or --database-url")
        engine = create_engine_from_url(url)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            report = asyncio.run(verify(args.data_dir, sm))
            print(json.dumps(report, indent=2))
            sys.exit(1 if report["mismatches"] else 0)
        finally:
            asyncio.run(engine.dispose())
        return

    if args.archive_json:
        import os

        if not args.archive_dir:
            raise SystemExit("--archive-json requires --archive-dir")
        # If DATABASE_URL is provided, run an internal verify first
        url = args.database_url or os.getenv("DATABASE_URL")
        if url:
            from sqlalchemy.ext.asyncio import async_sessionmaker
            from apps.api.src.db.engine import create_engine_from_url

            engine = create_engine_from_url(url)
            sm = async_sessionmaker(engine, expire_on_commit=False)
            try:
                manifest = asyncio.run(
                    archive_json(args.data_dir, args.archive_dir, sessionmaker=sm)
                )
            finally:
                asyncio.run(engine.dispose())
        else:
            manifest = asyncio.run(
                archive_json(args.data_dir, args.archive_dir, skip_verify=True)
            )
        print(json.dumps(manifest, indent=2))
        return


if __name__ == "__main__":
    main()
