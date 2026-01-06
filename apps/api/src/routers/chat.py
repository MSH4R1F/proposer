"""
Chat router for conversational intake.

Handles the intake conversation flow.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import structlog

from apps.api.src.services.intake_service import IntakeService, get_intake_service

logger = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""
    session_id: str = Field(..., description="Session ID for the conversation")
    message: str = Field(..., description="User's message")


class ChatMessageResponse(BaseModel):
    """Response from the chat endpoint."""
    session_id: str
    response: str
    stage: str
    completeness: float
    is_complete: bool
    case_file: Dict
    suggested_actions: List[str] = Field(default_factory=list)


class StartSessionRequest(BaseModel):
    """Request to start a new chat session."""
    role: str = Field(..., description="User role: 'tenant' or 'landlord'")


class StartSessionResponse(BaseModel):
    """Response when starting a new session."""
    session_id: str
    response: str
    stage: str
    completeness: float
    is_complete: bool
    case_file: Dict
    role_set: bool


class SetRoleRequest(BaseModel):
    """Request to explicitly set user role."""
    session_id: str = Field(..., description="Session ID for the conversation")
    role: str = Field(..., description="User role: 'tenant' or 'landlord'")


class SetRoleResponse(BaseModel):
    """Response from setting user role."""
    session_id: str
    response: str
    stage: str
    completeness: float
    is_complete: bool
    case_file: Dict
    role_set: bool


class MessageData(BaseModel):
    """Message data for API responses."""
    role: str
    content: str
    timestamp: Optional[str] = None


class SessionStatusResponse(BaseModel):
    """Response with session status."""
    session_id: str
    stage: str
    completeness: float
    is_complete: bool
    message_count: int
    case_file: Dict
    messages: List[MessageData] = Field(default_factory=list)


@router.post("/start", response_model=StartSessionResponse)
async def start_session(
    request: StartSessionRequest,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Start a new intake conversation session with the user's role.

    The role must be provided when creating the session. The session will
    be created with the role already set, and the first response will be
    a role-appropriate question.

    Flow:
        1. Frontend shows role selector ("I'm a tenant" / "I'm a landlord")
        2. POST /chat/start with role -> get session_id and first question
        3. POST /chat/message -> continue conversation

    The role must be either "tenant" or "landlord".
    """
    logger.debug("start_session_request_received", role=request.role)
    
    # Validate role first
    if request.role not in ("tenant", "landlord"):
        logger.warning("invalid_role_attempted", invalid_role=request.role)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {request.role}. Must be 'tenant' or 'landlord'"
        )
    
    try:
        # Create session with role - this returns a role-appropriate first question
        greeting, session_id, stage = await intake_service.start_session(role=request.role)
        
        # Get the session to return full state
        session_status = await intake_service.get_session_status(session_id)
        
        logger.debug("start_session_success", 
                     session_id=session_id, 
                     role=request.role,
                     stage=stage,
                     response_length=len(greeting))

        return StartSessionResponse(
            session_id=session_id,
            response=greeting,
            stage=stage,
            completeness=session_status["completeness"],
            is_complete=session_status["is_complete"],
            case_file=session_status["case_file"],
            role_set=True,
        )
    except Exception as e:
        logger.error("start_session_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: ChatMessageRequest,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Send a message in the intake conversation.

    The user's role must be set via POST /chat/set-role before sending
    messages. If role is not set, the conversation will remain at the
    GREETING stage.

    Returns the agent's response and updated case file state.
    """
    logger.debug("send_message_request", 
                 session_id=request.session_id, 
                 message_length=len(request.message),
                 message_preview=request.message[:100] if len(request.message) > 100 else request.message)
    try:
        result = await intake_service.process_message(
            session_id=request.session_id,
            message=request.message,
        )

        logger.debug("send_message_success",
                     session_id=request.session_id,
                     stage=result["stage"],
                     completeness=result["completeness"],
                     is_complete=result["is_complete"],
                     response_length=len(result["response"]),
                     num_suggested_actions=len(result.get("suggested_actions", [])))

        return ChatMessageResponse(
            session_id=request.session_id,
            response=result["response"],
            stage=result["stage"],
            completeness=result["completeness"],
            is_complete=result["is_complete"],
            case_file=result["case_file"],
            suggested_actions=result.get("suggested_actions", []),
        )
    except ValueError as e:
        logger.error("send_message_not_found", session_id=request.session_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("send_message_failed", session_id=request.session_id, 
                     error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-role", response_model=SetRoleResponse)
async def set_role(
    request: SetRoleRequest,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Set or change the user's role in an existing session.

    NOTE: In most cases, you should use POST /chat/start with the role parameter
    instead of this endpoint. This endpoint is mainly useful for:
    - Changing the role in an existing/resumed session
    - Legacy compatibility

    The role must be either "tenant" or "landlord".
    """
    logger.debug("set_role_request", session_id=request.session_id, role=request.role)
    
    if request.role not in ("tenant", "landlord"):
        logger.warning("invalid_role_attempted", 
                       session_id=request.session_id, 
                       invalid_role=request.role)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {request.role}. Must be 'tenant' or 'landlord'"
        )

    try:
        result = await intake_service.set_role(
            session_id=request.session_id,
            role=request.role,
        )

        logger.debug("set_role_success",
                     session_id=request.session_id,
                     role=request.role,
                     stage=result["stage"],
                     response_length=len(result["response"]))

        return SetRoleResponse(
            session_id=request.session_id,
            response=result["response"],
            stage=result["stage"],
            completeness=result["completeness"],
            is_complete=result["is_complete"],
            case_file=result["case_file"],
            role_set=result["role_set"],
        )
    except ValueError as e:
        logger.error("set_role_not_found", session_id=request.session_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("set_role_failed", session_id=request.session_id, 
                     role=request.role, error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session(
    session_id: str,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Get the current state of a chat session.
    """
    logger.debug("get_session_request", session_id=session_id)
    try:
        status = await intake_service.get_session_status(session_id)

        if not status:
            logger.warning("session_not_found", session_id=session_id)
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        logger.debug("get_session_success", 
                     session_id=session_id,
                     stage=status.get("stage"),
                     message_count=status.get("message_count"))

        return SessionStatusResponse(**status)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_session_failed", session_id=session_id, 
                     error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Delete a chat session and associated data.
    """
    logger.debug("delete_session_request", session_id=session_id)
    try:
        deleted = await intake_service.delete_session(session_id)

        if not deleted:
            logger.warning("delete_session_not_found", session_id=session_id)
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        logger.info("session_deleted", session_id=session_id)
        return {"message": f"Session {session_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_session_failed", session_id=session_id, 
                     error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    List all active sessions.
    """
    logger.debug("list_sessions_request")
    try:
        sessions = await intake_service.list_sessions()
        logger.debug("list_sessions_success", session_count=len(sessions))
        return {"sessions": sessions}
    except Exception as e:
        logger.error("list_sessions_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e))
