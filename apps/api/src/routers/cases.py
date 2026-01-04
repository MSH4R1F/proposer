"""
Cases router.

Handles case management endpoints.
"""

from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..services.intake_service import IntakeService, get_intake_service

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseResponse(BaseModel):
    """Response with case details."""
    case_id: str
    user_role: str
    created_at: str
    updated_at: str
    intake_complete: bool
    completeness_score: float
    property_address: Optional[str] = None
    deposit_amount: Optional[float] = None
    issues: list = []
    missing_info: list = []


class CaseSummaryResponse(BaseModel):
    """Brief case summary."""
    case_id: str
    user_role: str
    intake_complete: bool
    completeness_score: float
    created_at: str


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Get full case details.
    """
    try:
        case_file = await intake_service.get_case_file(case_id)

        if not case_file:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

        return CaseResponse(
            case_id=case_file.case_id,
            user_role=case_file.user_role.value,
            created_at=case_file.created_at,
            updated_at=case_file.updated_at,
            intake_complete=case_file.intake_complete,
            completeness_score=case_file.completeness_score,
            property_address=case_file.property.address,
            deposit_amount=case_file.tenancy.deposit_amount,
            issues=[i.value for i in case_file.issues],
            missing_info=case_file.missing_info,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}/full")
async def get_case_full(
    case_id: str,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Get the complete case file as JSON.
    """
    try:
        case_file = await intake_service.get_case_file(case_id)

        if not case_file:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

        return case_file.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_cases(
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    List all cases.
    """
    try:
        cases = await intake_service.list_cases()
        return {"cases": cases, "total": len(cases)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Delete a case and all associated data.
    """
    try:
        deleted = await intake_service.delete_case(case_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

        return {"message": f"Case {case_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
