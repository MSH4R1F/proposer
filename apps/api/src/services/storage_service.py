"""
Storage service for file uploads.

Handles evidence file storage (Supabase or local fallback).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from fastapi import UploadFile

from ..config import config

logger = structlog.get_logger()

# Global service instance
_storage_service: Optional["StorageService"] = None


class StorageService:
    """
    Service for managing file storage.

    Uses Supabase Storage when configured, falls back to local storage.
    """

    def __init__(self):
        """Initialize the storage service."""
        self.use_supabase = bool(config.supabase_url and config.supabase_key)

        if self.use_supabase:
            self._init_supabase()
        else:
            self._init_local()

        # Evidence metadata storage
        self.metadata_dir = config.data_dir / "evidence_metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "storage_service_initialized",
            backend="supabase" if self.use_supabase else "local",
        )

    def _init_supabase(self) -> None:
        """Initialize Supabase client."""
        try:
            from supabase import create_client
            self.supabase = create_client(config.supabase_url, config.supabase_key)
            self.bucket = config.supabase_bucket
        except Exception as e:
            logger.warning("supabase_init_failed", error=str(e))
            self.use_supabase = False
            self._init_local()

    def _init_local(self) -> None:
        """Initialize local storage."""
        self.local_storage_dir = config.data_dir / "evidence_files"
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)

    async def upload_evidence(
        self,
        case_id: str,
        file: UploadFile,
        evidence_type: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Upload an evidence file.

        Args:
            case_id: The case ID
            file: Uploaded file
            evidence_type: Type of evidence
            description: User description

        Returns:
            Dict with evidence_id, file_url, evidence_type, etc.
        """
        evidence_id = str(uuid4())[:8]
        file_ext = Path(file.filename).suffix
        storage_path = f"{case_id}/{evidence_id}{file_ext}"

        # Read file content
        content = await file.read()

        # Upload
        if self.use_supabase:
            file_url = await self._upload_supabase(storage_path, content, file.content_type)
        else:
            file_url = await self._upload_local(storage_path, content)

        # Process file (extract text, describe image)
        extracted_text = None
        image_description = None

        if file.content_type == "application/pdf":
            extracted_text = await self._extract_pdf_text(content)
        elif file.content_type.startswith("image/"):
            image_description = f"Image evidence: {description}"

        # Save metadata
        metadata = {
            "evidence_id": evidence_id,
            "case_id": case_id,
            "file_url": file_url,
            "file_name": file.filename,
            "file_type": file.content_type,
            "evidence_type": evidence_type,
            "description": description,
            "extracted_text": extracted_text,
            "image_description": image_description,
        }
        self._save_metadata(case_id, evidence_id, metadata)

        logger.info(
            "evidence_uploaded",
            case_id=case_id,
            evidence_id=evidence_id,
            file_type=file.content_type,
        )

        return metadata

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

    def _save_metadata(self, case_id: str, evidence_id: str, metadata: Dict) -> None:
        """Save evidence metadata."""
        case_dir = self.metadata_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        path = case_dir / f"{evidence_id}.json"
        with open(path, "w") as f:
            json.dump(metadata, f, indent=2)

    async def list_evidence(self, case_id: str) -> List[Dict]:
        """List all evidence for a case."""
        case_dir = self.metadata_dir / case_id
        if not case_dir.exists():
            return []

        evidence = []
        for path in case_dir.glob("*.json"):
            with open(path) as f:
                evidence.append(json.load(f))

        return evidence

    async def delete_evidence(self, case_id: str, evidence_id: str) -> bool:
        """Delete an evidence file."""
        # Delete metadata
        metadata_path = self.metadata_dir / case_id / f"{evidence_id}.json"
        if not metadata_path.exists():
            return False

        # Get file path from metadata
        with open(metadata_path) as f:
            metadata = json.load(f)

        file_url = metadata.get("file_url", "")

        # Delete file
        if self.use_supabase and not file_url.startswith("file://"):
            try:
                path = f"{case_id}/{evidence_id}"
                self.supabase.storage.from_(self.bucket).remove([path])
            except Exception as e:
                logger.warning("supabase_delete_failed", error=str(e))
        elif file_url.startswith("file://"):
            local_path = Path(file_url.replace("file://", ""))
            if local_path.exists():
                local_path.unlink()

        # Delete metadata
        metadata_path.unlink()

        logger.info("evidence_deleted", case_id=case_id, evidence_id=evidence_id)
        return True


def get_storage_service() -> StorageService:
    """Dependency injection for storage service."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
