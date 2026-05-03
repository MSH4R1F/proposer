"""Resume / idempotency state for the Housing Ombudsman scraper.

Two artefacts:

* **Per-run JSONL log** (``_runs/<run_id>.jsonl``): append-only event
  stream of fetches/decisions. Useful for post-hoc audit; not load-bearing
  for resume.
* **Master index** (``master_index.json``): durable dict keyed by
  ``case_reference`` describing what we have on disk. Loaded on start so
  the same case isn't re-fetched in a follow-up run.

The dedup key is ``(case_ref, source_url, content_sha256)`` — content
hash means a re-published page with new wording is treated as new and
re-ingested.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


@dataclass
class MasterIndexEntry:
    source_url: str
    content_sha256: str
    decision_date: Optional[str] = None  # ISO string for JSON friendliness
    kept: bool = False
    raw_storage_path: Optional[str] = None
    matter_types: list = field(default_factory=list)


class RunLog:
    """Append-only run log + persistent master index.

    The master index drives dedup across runs: on construction we read
    it and prime ``_dedup_seen`` so a resumed scrape skips cases we
    already processed. ``upsert`` mutates the in-memory index;
    ``save_master_index`` (also exposed as ``flush``) atomically
    serialises to disk. Without periodic flushes a process killed mid-run
    would lose every upsert since the last save and re-fetch every case
    on resume — defeating the dedup mechanism.

    The JSONL run log written by ``record`` is line-appended directly
    to disk and is therefore safe regardless of flush cadence.
    """

    #: Default master-index flush interval (in upserts). The scraper can
    #: override per-run via ``flush_every``. ``0`` disables periodic
    #: flushing — callers are then responsible for an explicit final
    #: ``save_master_index()``.
    DEFAULT_FLUSH_EVERY = 5

    def __init__(
        self,
        runs_dir: Path,
        master_index_path: Path,
        *,
        run_id: Optional[str] = None,
        flush_every: Optional[int] = None,
    ) -> None:
        self.runs_dir = Path(runs_dir)
        self.master_index_path = Path(master_index_path)
        self.run_id = run_id or _new_run_id()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.master_index_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path = self.runs_dir / f"{self.run_id}.jsonl"
        self._master_index: Dict[str, MasterIndexEntry] = self._load_master_index()
        self._dedup_seen: set = {
            self._dedup_tuple(ref, e.source_url, e.content_sha256)
            for ref, e in self._master_index.items()
        }
        self._flush_every = (
            self.DEFAULT_FLUSH_EVERY if flush_every is None else int(flush_every)
        )
        self._upserts_since_flush = 0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_master_index(self) -> Dict[str, MasterIndexEntry]:
        if not self.master_index_path.exists():
            return {}
        try:
            with self.master_index_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        out: Dict[str, MasterIndexEntry] = {}
        for case_ref, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            out[case_ref] = MasterIndexEntry(
                source_url=str(payload.get("source_url") or ""),
                content_sha256=str(payload.get("content_sha256") or ""),
                decision_date=payload.get("decision_date"),
                kept=bool(payload.get("kept", False)),
                raw_storage_path=payload.get("raw_storage_path"),
                matter_types=list(payload.get("matter_types") or []),
            )
        return out

    def save_master_index(self) -> None:
        serial = {
            case_ref: {
                "source_url": e.source_url,
                "content_sha256": e.content_sha256,
                "decision_date": e.decision_date,
                "kept": e.kept,
                "raw_storage_path": e.raw_storage_path,
                "matter_types": e.matter_types,
            }
            for case_ref, e in self._master_index.items()
        }
        tmp = self.master_index_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(serial, f, indent=2, sort_keys=True)
        tmp.replace(self.master_index_path)

    # ------------------------------------------------------------------
    # Logging API
    # ------------------------------------------------------------------

    def record(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        line = {
            "run_id": self.run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
        }
        if payload:
            line.update(payload)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")

    # ------------------------------------------------------------------
    # Dedup / master index
    # ------------------------------------------------------------------

    @staticmethod
    def _dedup_tuple(case_ref: str, source_url: str, content_sha256: str) -> tuple:
        return (case_ref, source_url, content_sha256)

    def dedup_key(self, case_ref: str, source_url: str, content_sha256: str) -> bool:
        """Return True iff we've already processed this exact case+content.

        Side-effect: marks the tuple as seen for this process. Callers
        normally check this *before* doing any work, then call
        :meth:`upsert` to persist the outcome.
        """
        key = self._dedup_tuple(case_ref, source_url, content_sha256)
        seen = key in self._dedup_seen
        if not seen:
            self._dedup_seen.add(key)
        return seen

    def upsert(
        self,
        case_ref: str,
        *,
        source_url: str,
        content_sha256: str,
        decision_date: Optional[str] = None,
        kept: bool = False,
        raw_storage_path: Optional[str] = None,
        matter_types: Optional[Iterable[str]] = None,
    ) -> None:
        self._master_index[case_ref] = MasterIndexEntry(
            source_url=source_url,
            content_sha256=content_sha256,
            decision_date=decision_date,
            kept=kept,
            raw_storage_path=raw_storage_path,
            matter_types=list(matter_types or []),
        )
        # Periodic flush so an interrupt mid-run loses at most
        # ``flush_every`` upserts, not the whole batch. The scraper
        # still calls ``save_master_index`` explicitly at end-of-run
        # for the final commit.
        self._upserts_since_flush += 1
        if (
            self._flush_every
            and self._upserts_since_flush >= self._flush_every
        ):
            self.save_master_index()
            self._upserts_since_flush = 0

    # Alias matching the docstring's `flush()` reference.
    def flush(self) -> None:
        """Persist the in-memory master index to disk now."""
        self.save_master_index()
        self._upserts_since_flush = 0

    def kept_entries(self) -> Dict[str, MasterIndexEntry]:
        return {k: v for k, v in self._master_index.items() if v.kept}

    def all_entries(self) -> Dict[str, MasterIndexEntry]:
        return dict(self._master_index)

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _new_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


__all__ = ["RunLog", "MasterIndexEntry"]
