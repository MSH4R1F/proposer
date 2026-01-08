"""
Disputes router for managing linked dispute cases.

Handles dispute creation, invite codes, and joining.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import structlog

from apps.api.src.services.dispute_service import DisputeService, get_dispute_service

logger = structlog.get_logger()
router = APIRouter(prefix="/disputes", tags=["disputes"])


# Request/Response Models

class CreateDisputeRequest(BaseModel):
    """Request to create a new dispute case."""
    session_id: str = Field(..., description="Session ID of the party creating the dispute")
    role: str = Field(..., description="Role of the creator: 'tenant' or 'landlord'")
    property_address: Optional[str] = Field(None, description="Property address if known")
    property_postcode: Optional[str] = Field(None, description="Property postcode if known")
    deposit_amount: Optional[float] = Field(None, description="Deposit amount if known")


class CreateDisputeResponse(BaseModel):
    """Response after creating a dispute."""
    dispute_id: str
    invite_code: str
    status: str
    message: str


class ValidateInviteRequest(BaseModel):
    """Request to validate an invite code."""
    invite_code: str = Field(..., description="The invite code to validate")


class ValidateInviteResponse(BaseModel):
    """Response for invite code validation."""
    valid: bool
    dispute_id: Optional[str] = None
    created_by_role: Optional[str] = None
    expected_role: Optional[str] = None
    property_address: Optional[str] = None
    message: str


class JoinDisputeRequest(BaseModel):
    """Request to join a dispute using invite code."""
    invite_code: str = Field(..., description="The invite code")
    session_id: str = Field(..., description="Session ID of the joining party")
    role: str = Field(..., description="Role of the joining party: 'tenant' or 'landlord'")


class JoinDisputeResponse(BaseModel):
    """Response after joining a dispute."""
    success: bool
    dispute_id: Optional[str] = None
    status: Optional[str] = None
    message: str


class DisputeStatusResponse(BaseModel):
    """Full dispute status response."""
    dispute_id: str
    invite_code: str
    status: str
    created_at: str
    updated_at: str
    created_by_role: str
    tenant_session_id: Optional[str] = None
    landlord_session_id: Optional[str] = None
    property_address: Optional[str] = None
    property_postcode: Optional[str] = None
    deposit_amount: Optional[float] = None
    has_both_parties: bool
    is_ready_for_prediction: bool
    waiting_message: Optional[str] = None


class DisputeListItem(BaseModel):
    """Summary item for dispute list."""
    dispute_id: str
    invite_code: str
    status: str
    created_at: str
    property_address: Optional[str] = None
    has_tenant: bool
    has_landlord: bool


# Endpoints

@router.post("/create", response_model=CreateDisputeResponse)
async def create_dispute(
    request: CreateDisputeRequest,
    dispute_service: DisputeService = Depends(get_dispute_service),
):
    """
    Create a new dispute case and get an invite code.
    
    The creating party's session is automatically linked to the dispute.
    Share the invite code with the other party to link their session.
    """
    logger.debug("create_dispute_request", session_id=request.session_id, role=request.role)
    
    if request.role not in ("tenant", "landlord"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {request.role}. Must be 'tenant' or 'landlord'"
        )
    
    try:
        dispute = await dispute_service.create_dispute(
            session_id=request.session_id,
            role=request.role,
            property_address=request.property_address,
            property_postcode=request.property_postcode,
            deposit_amount=request.deposit_amount,
        )
        
        other_role = "landlord" if request.role == "tenant" else "tenant"
        
        return CreateDisputeResponse(
            dispute_id=dispute.dispute_id,
            invite_code=dispute.invite_code,
            status=dispute.status.value,
            message=f"Dispute created. Share code {dispute.invite_code} with the {other_role}.",
        )
    except Exception as e:
        logger.error("create_dispute_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-invite", response_model=ValidateInviteResponse)
async def validate_invite_code(
    request: ValidateInviteRequest,
    dispute_service: DisputeService = Depends(get_dispute_service),
):
    """
    Validate an invite code before attempting to join.
    
    Returns information about the dispute if the code is valid.
    """
    logger.debug("validate_invite_request", invite_code=request.invite_code)
    
    dispute = await dispute_service.get_dispute_by_invite_code(request.invite_code)
    
    if not dispute:
        return ValidateInviteResponse(
            valid=False,
            message="Invalid invite code. Please check and try again.",
        )
    
    # Determine which role is expected to join
    expected_role = None
    if not dispute.tenant_session_id:
        expected_role = "tenant"
    elif not dispute.landlord_session_id:
        expected_role = "landlord"
    else:
        return ValidateInviteResponse(
            valid=False,
            dispute_id=dispute.dispute_id,
            message="Both parties have already joined this dispute.",
        )
    
    return ValidateInviteResponse(
        valid=True,
        dispute_id=dispute.dispute_id,
        created_by_role=dispute.created_by_role,
        expected_role=expected_role,
        property_address=dispute.property_address,
        message=f"Valid code. You will join as the {expected_role}.",
    )


@router.post("/join", response_model=JoinDisputeResponse)
async def join_dispute(
    request: JoinDisputeRequest,
    dispute_service: DisputeService = Depends(get_dispute_service),
):
    """
    Join an existing dispute using an invite code.
    
    The joining party's session is linked to the dispute.
    """
    logger.debug("join_dispute_request", invite_code=request.invite_code, role=request.role)
    
    if request.role not in ("tenant", "landlord"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {request.role}. Must be 'tenant' or 'landlord'"
        )
    
    try:
        dispute = await dispute_service.join_dispute(
            invite_code=request.invite_code,
            session_id=request.session_id,
            role=request.role,
        )
        
        if not dispute:
            return JoinDisputeResponse(
                success=False,
                message="Could not join dispute. The code may be invalid or this role is already taken.",
            )
        
        return JoinDisputeResponse(
            success=True,
            dispute_id=dispute.dispute_id,
            status=dispute.status.value,
            message=f"Successfully joined the dispute as {request.role}.",
        )
    except Exception as e:
        logger.error("join_dispute_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-session/{session_id}", response_model=Optional[DisputeStatusResponse])
async def get_dispute_by_session(
    session_id: str,
    dispute_service: DisputeService = Depends(get_dispute_service),
):
    """
    Get dispute status for a specific session.
    
    Returns the dispute that the session is linked to, if any.
    """
    logger.debug("get_dispute_by_session", session_id=session_id)
    
    dispute = await dispute_service.get_dispute_by_session(session_id)
    
    if not dispute:
        return None
    
    # Determine which role this session is
    current_role = "tenant" if dispute.tenant_session_id == session_id else "landlord"
    
    return DisputeStatusResponse(
        dispute_id=dispute.dispute_id,
        invite_code=dispute.invite_code,
        status=dispute.status.value,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
        created_by_role=dispute.created_by_role,
        tenant_session_id=dispute.tenant_session_id,
        landlord_session_id=dispute.landlord_session_id,
        property_address=dispute.property_address,
        property_postcode=dispute.property_postcode,
        deposit_amount=dispute.deposit_amount,
        has_both_parties=dispute.has_both_parties,
        is_ready_for_prediction=dispute.is_ready_for_prediction,
        waiting_message=dispute.get_waiting_message(current_role),
    )


@router.get("/{dispute_id}", response_model=DisputeStatusResponse)
async def get_dispute(
    dispute_id: str,
    dispute_service: DisputeService = Depends(get_dispute_service),
):
    """
    Get full dispute status by ID.
    """
    logger.debug("get_dispute", dispute_id=dispute_id)
    
    dispute = await dispute_service.get_dispute(dispute_id)
    
    if not dispute:
        raise HTTPException(status_code=404, detail=f"Dispute not found: {dispute_id}")
    
    return DisputeStatusResponse(
        dispute_id=dispute.dispute_id,
        invite_code=dispute.invite_code,
        status=dispute.status.value,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
        created_by_role=dispute.created_by_role,
        tenant_session_id=dispute.tenant_session_id,
        landlord_session_id=dispute.landlord_session_id,
        property_address=dispute.property_address,
        property_postcode=dispute.property_postcode,
        deposit_amount=dispute.deposit_amount,
        has_both_parties=dispute.has_both_parties,
        is_ready_for_prediction=dispute.is_ready_for_prediction,
        waiting_message=None,
    )


@router.get("/", response_model=List[DisputeListItem])
async def list_disputes(
    status: Optional[str] = None,
    limit: int = 100,
    dispute_service: DisputeService = Depends(get_dispute_service),
):
    """
    List all disputes (for admin dashboard).
    """
    logger.debug("list_disputes", status=status, limit=limit)
    
    from llm_orchestrator.models.dispute import DisputeStatus
    
    status_filter = None
    if status:
        try:
            status_filter = DisputeStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    disputes = await dispute_service.list_disputes(status=status_filter, limit=limit)
    
    return [
        DisputeListItem(
            dispute_id=d.dispute_id,
            invite_code=d.invite_code,
            status=d.status.value,
            created_at=d.created_at,
            property_address=d.property_address,
            has_tenant=d.tenant_session_id is not None,
            has_landlord=d.landlord_session_id is not None,
        )
        for d in disputes
    ]


@router.delete("/{dispute_id}")
async def delete_dispute(
    dispute_id: str,
    dispute_service: DisputeService = Depends(get_dispute_service),
):
    """
    Delete a dispute (admin only).
    """
    logger.debug("delete_dispute", dispute_id=dispute_id)
    
    deleted = await dispute_service.delete_dispute(dispute_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Dispute not found: {dispute_id}")
    
    return {"message": f"Dispute {dispute_id} deleted"}
