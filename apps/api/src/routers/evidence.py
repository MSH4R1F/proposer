"""
Evidence router for file uploads.

Handles evidence file uploads and processing.
"""

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from pydantic import BaseModel
import structlog

from apps.api.src.services.storage_service import StorageService, get_storage_service

logger = structlog.get_logger()
router = APIRouter(prefix="/evidence", tags=["evidence"])


class EvidenceUploadResponse(BaseModel):
    """Response after uploading evidence."""
    evidence_id: str
    file_url: str
    file_type: str
    file_name: str
    extracted_text: Optional[str] = None
    image_description: Optional[str] = None
    evidence_type: str
    processing_status: str


class EvidenceListResponse(BaseModel):
    """Response listing evidence for a case."""
    case_id: str
    evidence_count: int
    evidence: list


@router.post("/upload/{case_id}", response_model=EvidenceUploadResponse)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    evidence_type: str = Form(...),
    description: str = Form(""),
    storage_service: StorageService = Depends(get_storage_service),
):
    """
    Upload an evidence file for a case.

    Supports: PDF, JPG, PNG, HEIC
    Extracts text from PDFs and describes images.

    Evidence types:
    - inventory_checkin
    - inventory_checkout
    - photos_before
    - photos_after
    - receipts
    - invoices
    - correspondence
    - tenancy_agreement
    - deposit_certificate
    - other
    """
    # Validate file type
    logger.debug("upload_evidence_request",
                 case_id=case_id,
                 evidence_type=evidence_type,
                 filename=file.filename,
                 content_type=file.content_type,
                 description_length=len(description))
    
    allowed_types = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/heic",
    ]

    if file.content_type not in allowed_types:
        logger.warning("invalid_file_type_rejected",
                       case_id=case_id,
                       content_type=file.content_type,
                       filename=file.filename)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, JPG, PNG, HEIC"
        )

    try:
        logger.debug("uploading_to_storage", case_id=case_id, evidence_type=evidence_type)
        result = await storage_service.upload_evidence(
            case_id=case_id,
            file=file,
            evidence_type=evidence_type,
            description=description,
        )

        logger.info("evidence_uploaded",
                    case_id=case_id,
                    evidence_id=result["evidence_id"],
                    evidence_type=evidence_type,
                    filename=file.filename,
                    has_extracted_text=bool(result.get("extracted_text")),
                    has_image_description=bool(result.get("image_description")))

        return EvidenceUploadResponse(
            evidence_id=result["evidence_id"],
            file_url=result["file_url"],
            file_type=file.content_type,
            file_name=file.filename,
            extracted_text=result.get("extracted_text"),
            image_description=result.get("image_description"),
            evidence_type=result["evidence_type"],
            processing_status="complete",
        )
    except Exception as e:
        logger.error("evidence_upload_failed",
                     case_id=case_id,
                     evidence_type=evidence_type,
                     filename=file.filename,
                     error=str(e),
                     error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}", response_model=EvidenceListResponse)
async def list_evidence(
    case_id: str,
    storage_service: StorageService = Depends(get_storage_service),
):
    """
    List all evidence for a case.
    """
    logger.debug("list_evidence_request", case_id=case_id)
    try:
        evidence = await storage_service.list_evidence(case_id)

        logger.debug("list_evidence_success",
                     case_id=case_id,
                     evidence_count=len(evidence))

        return EvidenceListResponse(
            case_id=case_id,
            evidence_count=len(evidence),
            evidence=evidence,
        )
    except Exception as e:
        logger.error("list_evidence_failed",
                     case_id=case_id,
                     error=str(e),
                     error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}/{evidence_id}")
async def delete_evidence(
    case_id: str,
    evidence_id: str,
    storage_service: StorageService = Depends(get_storage_service),
):
    """
    Delete an evidence file.
    """
    logger.debug("delete_evidence_request", case_id=case_id, evidence_id=evidence_id)
    try:
        deleted = await storage_service.delete_evidence(case_id, evidence_id)

        if not deleted:
            logger.warning("evidence_not_found_for_delete",
                           case_id=case_id,
                           evidence_id=evidence_id)
            raise HTTPException(status_code=404, detail="Evidence not found")

        logger.info("evidence_deleted", case_id=case_id, evidence_id=evidence_id)
        return {"message": f"Evidence {evidence_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_evidence_failed",
                     case_id=case_id,
                     evidence_id=evidence_id,
                     error=str(e),
                     error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))
