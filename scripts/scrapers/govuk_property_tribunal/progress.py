"""SHA-126: progress + master_index for the GOV.UK RRO scraper.

Append-only JSONL run log with a small in-memory dedup set keyed by
``content_id`` or content hash; resume-friendly. Master index is loaded
once and kept in memory, then written atomically at the end of a run.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from pydantic import BaseModel

from .models import ScrapeRecord


class RunLog:
    """Append-only JSONL run log + in-memory dedup set.

    The log is intentionally append-only so a stalled run can be resumed
    by replaying the JSONL: ``record(...)`` is idempotent at the JSON
    layer (same input -> same output) and ``seen(...)`` checks the
    in-memory set populated from the master index.
    """

    def __init__(self, log_path: Path) -> None:
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    def record(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Append ``{ts, event_type, payload}`` to the run log."""
        envelope = {
            "ts": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "payload": _jsonable(payload),
        }
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(envelope, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    def mark_seen(self, key: str) -> None:
        if key:
            self._seen.add(key)

    def seen(self, key: str) -> bool:
        return bool(key) and key in self._seen


# ---------------------------------------------------------------------------
# Master index
# ---------------------------------------------------------------------------


class MasterIndex:
    """In-memory wrapper over ``master_index.json`` keyed by case_reference.

    Methods are intentionally explicit (load / upsert / save) rather than
    a magic dict subclass — re-runs that crash mid-write must not corrupt
    the on-disk state, so :meth:`save` always writes via tempfile +
    rename.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._records: Dict[str, ScrapeRecord] = {}

    @classmethod
    def load(cls, path: Path) -> "MasterIndex":
        idx = cls(path)
        if idx._path.is_file():
            try:
                data = json.loads(idx._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return idx
            rows = data.get("records") or data.get("cases") or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    rec = ScrapeRecord.model_validate(row)
                except Exception:
                    # Skip rows that pre-date the current schema. The new
                    # run will overwrite them on upsert.
                    continue
                idx._records[rec.case_reference] = rec
        return idx

    # ------------------------------------------------------------------
    def upsert(self, record: ScrapeRecord) -> None:
        self._records[record.case_reference] = record

    def has(self, case_reference: str) -> bool:
        return case_reference in self._records

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> List[ScrapeRecord]:
        return list(self._records.values())

    # ------------------------------------------------------------------
    def save(self) -> None:
        """Atomic write of the index to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.utcnow().isoformat(),
            "total": len(self._records),
            "records": [r.model_dump(mode="json") for r in self._records.values()],
        }
        # Tempfile + rename for atomicity.
        fd, tmp_path = tempfile.mkstemp(prefix=".master_index.", suffix=".tmp", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    """Best-effort coerce arbitrary objects to JSON-serialisable shapes."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    return obj


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    """Convenience used by scraper for excluded.jsonl / unsupported.jsonl."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_jsonable(payload), ensure_ascii=False) + "\n")


__all__ = ["RunLog", "MasterIndex", "append_jsonl"]
