"""
Storage service for file uploads.

Handles evidence file storage (Supabase or local fallback).
Blob upload/download stay on Supabase or local file; evidence METADATA is
persisted through EvidenceRepo (Postgres) via a UnitOfWork (Phase 8.1).
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.config import config
from apps.api.src.db.uow import UnitOfWork
from llm_orchestrator.models.case_file import EvidenceType
from llm_orchestrator.models.evidence import EvidenceMetadata

logger = structlog.get_logger()

# Global service instance (legacy singleton — kept for rollback compatibility)
_storage_service: Optional["StorageService"] = None


class StorageService:
    """
    Service for managing file storage.

    Uses Supabase Storage when configured, falls back to local storage.
    Evidence metadata is persisted through EvidenceRepo (Postgres).
    Blob upload/download helpers are unchanged.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        supabase_client: Optional[Any] = None,
    ) -> None:
        """
        Initialise the storage service.

        Args:
            sessionmaker: SQLAlchemy async sessionmaker bound to the app engine.
            supabase_client: Optional pre-built Supabase client (injected in
                tests to avoid network calls).
        """
        self._sm = sessionmaker

        if supabase_client is not None:
            self.supabase = supabase_client
            self.use_supabase = True
        else:
            self.use_supabase = bool(config.supabase_url and config.supabase_key)
            if self.use_supabase:
                self._init_supabase()
            else:
                self._init_local()

        logger.info(
            "storage_service_initialized",
            backend="supabase" if self.use_supabase else "local",
        )

    # ------------------------------------------------------------------
    # Blob backend init helpers (unchanged from original)
    # ------------------------------------------------------------------

    def _init_supabase(self) -> None:
        """Initialize Supabase client."""
        try:
            from supabase import create_client
            self.supabase = create_client(config.supabase_url, config.supabase_key)
            self.bucket = config.supabase_bucket
        except Exception as e:
            logger.warning("supabase_init_failed", error=str(e))
            if config.app_env == "production":
                raise
            self.use_supabase = False
            self._init_local()

    def _init_local(self) -> None:
        """Initialize local storage."""
        self.local_storage_dir = config.data_dir / "evidence_files"
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def upload_evidence(
        self,
        case_id: str,
        file: UploadFile,
        evidence_type: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Upload an evidence file.

        Blob is written first; metadata is then persisted to Postgres.
        If the metadata write fails the blob is deleted (compensation).

        Args:
            case_id: The case ID
            file: Uploaded file
            evidence_type: Type of evidence
            description: User description

        Returns:
            Dict with evidence_id, file_url, evidence_type, etc.
        """
        evidence_type_value = EvidenceType(evidence_type).value
        evidence_id = str(uuid.uuid4())[:8]
        file_ext = Path(file.filename).suffix
        storage_path = f"{case_id}/{evidence_id}{file_ext}"

        # Read file content
        content = await file.read()

        # Step 1: upload the blob (succeeds or raises)
        if self.use_supabase:
            file_url = await self._upload_supabase(storage_path, content, file.content_type)
        else:
            file_url = await self._upload_local(storage_path, content)

        # Step 2: extract optional text outside any transaction (best-effort)
        extracted_text = None
        image_description = None

        if file.content_type == "application/pdf":
            try:
                extracted_text = await self._extract_pdf_text(content)
            except Exception:
                extracted_text = None  # best effort
        elif file.content_type.startswith("image/"):
            image_description = f"Image evidence: {description}"

        # Step 3: write metadata via the repo. On failure, compensate by
        # deleting the blob we just uploaded.
        metadata = EvidenceMetadata(
            case_id=case_id,
            evidence_id=evidence_id,
            evidence_type=evidence_type_value,
            file_url=file_url,
            storage_path=storage_path,
            file_name=file.filename,
            file_type=file.content_type,
            description=description,
            extracted_text=extracted_text,
            image_description=image_description,
        )
        correlation_id = uuid.uuid4().hex[:12]
        try:
            async with UnitOfWork(self._sm) as uow:
                await uow.evidence.save(metadata)
        except Exception as exc:
            # Compensation: delete the orphan blob
            try:
                await self._delete_blob(file_url, storage_path=storage_path)
                logger.warning(
                    "evidence_upload_compensation_succeeded",
                    case_id=case_id,
                    evidence_id=evidence_id,
                    correlation_id=correlation_id,
                    error_type=type(exc).__name__,
                )
            except Exception as compensation_exc:
                logger.error(
                    "evidence_upload_orphan",
                    case_id=case_id,
                    evidence_id=evidence_id,
                    correlation_id=correlation_id,
                    error_type=type(exc).__name__,
                    compensation_error_type=type(compensation_exc).__name__,
                )
            raise

        logger.info(
            "evidence_uploaded",
            case_id=case_id,
            evidence_id=evidence_id,
            file_type=file.content_type,
        )

        return metadata.model_dump(mode="json")

    async def list_evidence(self, case_id: str) -> List[Dict]:
        """List all evidence for a case."""
        async with UnitOfWork(self._sm) as uow:
            rows = await uow.evidence.get_by_case_id(case_id)
        return [r.model_dump(mode="json") for r in rows]

    async def delete_evidence(self, case_id: str, evidence_id: str) -> bool:
        """
        Delete an evidence file.

        DB row is removed first; if the blob delete subsequently fails the
        orphan blob is logged but the method still returns True (the row is
        already gone and there is no useful compensating action).
        """
        # Step 1: load metadata to get file_url
        async with UnitOfWork(self._sm) as uow:
            metadata = await uow.evidence.get(case_id, evidence_id)
        if metadata is None:
            return False

        # Step 2: delete DB row first
        async with UnitOfWork(self._sm) as uow:
            await uow.evidence.delete(case_id, evidence_id)

        # Step 3: delete blob; on failure log orphan blob (row is already gone)
        correlation_id = uuid.uuid4().hex[:12]
        try:
            await self._delete_blob(metadata.file_url, storage_path=metadata.storage_path)
        except Exception as exc:
            logger.error(
                "evidence_delete_orphan_blob",
                case_id=case_id,
                evidence_id=evidence_id,
                correlation_id=correlation_id,
                file_url=metadata.file_url,
                error_type=type(exc).__name__,
            )
            # Don't re-raise; the row is already gone, blob is best-effort

        logger.info("evidence_deleted", case_id=case_id, evidence_id=evidence_id)
        return True

    # ------------------------------------------------------------------
    # Blob helpers (unchanged from original)
    # ------------------------------------------------------------------

    async def _upload_supabase(
        self, path: str, content: bytes, content_type: str
    ) -> str:
        """Upload to Supabase Storage."""
        try:
            response = self.supabase.storage.from_(self.bucket).upload(
                path,
                content,
                {"content-type": content_type},
            )
            # Get public URL
            url = self.supabase.storage.from_(self.bucket).get_public_url(path)
            return url
        except Exception as e:
            logger.error("supabase_upload_failed", error=str(e))
            if config.app_env == "production":
                raise
            # Fall back to local
            return await self._upload_local(path, content)

    async def _upload_local(self, path: str, content: bytes) -> str:
        """Upload to local storage."""
        full_path = self.local_storage_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "wb") as f:
            f.write(content)

        return f"file://{full_path}"

    async def _extract_pdf_text(self, content: bytes) -> Optional[str]:
        """Extract text from PDF content."""
        try:
            import fitz  # PyMuPDF
            import io

            doc = fitz.open(stream=content, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()

            return text.strip() if text.strip() else None
        except Exception as e:
            logger.warning("pdf_extraction_failed", error=str(e))
            return None

    async def _delete_blob(self, file_url: Optional[str], storage_path: Optional[str] = None) -> None:
        """Delete the blob identified by *file_url*.

        Called both from delete_evidence (normal flow) and from upload_evidence
        compensation.  Mirrors the blob-removal block that previously lived
        inline inside delete_evidence.

        When *storage_path* is provided (from EvidenceMetadata.storage_path) it
        is used directly for Supabase deletes, avoiding fragile URL parsing.
        """
        if not file_url:
            return

        if self.use_supabase and not file_url.startswith("file://"):
            try:
                if storage_path:
                    # Prefer the authoritative storage_path from metadata.
                    resolved_path = storage_path
                else:
                    # Legacy fallback: derive storage_path from URL via best-effort parsing.
                    bucket_marker = f"/{self.bucket}/"
                    idx = file_url.find(bucket_marker)
                    if idx != -1:
                        resolved_path = file_url[idx + len(bucket_marker):]
                    else:
                        resolved_path = file_url.split("/")[-1]
                self.supabase.storage.from_(self.bucket).remove([resolved_path])
            except Exception as e:
                logger.warning("supabase_delete_failed", error=str(e))
                if config.app_env == "production":
                    raise
        elif file_url.startswith("file://"):
            local_path = Path(file_url.replace("file://", ""))
            if local_path.exists():
                local_path.unlink()


# ---------------------------------------------------------------------------
# Legacy singleton getter — kept for rollback compatibility.
# Real requests always go through dependencies.get_storage_service() which
# injects the app engine's sessionmaker.
# ---------------------------------------------------------------------------

def get_storage_service() -> "StorageService":
    """Legacy process-singleton getter. Kept for rollback compatibility."""
    raise RuntimeError(
        "legacy singleton not supported in DB mode; use dependencies.get_storage_service"
    )
