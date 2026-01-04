"""
Evidence router for file uploads.

Handles evidence file uploads and processing.
"""

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from pydantic import BaseModel

from ..services.storage_service import StorageService, get_storage_service

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
    allowed_types = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/heic",
    ]

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, JPG, PNG, HEIC"
        )

    try:
        result = await storage_service.upload_evidence(
            case_id=case_id,
            file=file,
            evidence_type=evidence_type,
            description=description,
        )

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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}", response_model=EvidenceListResponse)
async def list_evidence(
    case_id: str,
    storage_service: StorageService = Depends(get_storage_service),
):
    """
    List all evidence for a case.
    """
    try:
        evidence = await storage_service.list_evidence(case_id)

        return EvidenceListResponse(
            case_id=case_id,
            evidence_count=len(evidence),
            evidence=evidence,
        )
    except Exception as e:
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
    try:
        deleted = await storage_service.delete_evidence(case_id, evidence_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Evidence not found")

        return {"message": f"Evidence {evidence_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
