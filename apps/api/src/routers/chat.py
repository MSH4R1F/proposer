"""
Chat router for conversational intake.

Handles the intake conversation flow.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from apps.api.src.services.intake_service import IntakeService, get_intake_service

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
    pass  # No parameters needed - role is set via /chat/set-role


class StartSessionResponse(BaseModel):
    """Response when starting a new session."""
    session_id: str
    greeting: str
    stage: str


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
    Start a new intake conversation session.

    Returns a session ID and initial greeting. After receiving the greeting,
    the frontend should display role selection buttons ("I'm a tenant" /
    "I'm a landlord") and call POST /chat/set-role when clicked.

    Flow:
        1. POST /chat/start -> get session_id and greeting
        2. POST /chat/set-role -> set tenant/landlord, get first question
        3. POST /chat/message -> continue conversation
    """
    try:
        greeting, session_id, stage = await intake_service.start_session()

        return StartSessionResponse(
            session_id=session_id,
            greeting=greeting,
            stage=stage,
        )
    except Exception as e:
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
    try:
        result = await intake_service.process_message(
            session_id=request.session_id,
            message=request.message,
        )

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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-role", response_model=SetRoleResponse)
async def set_role(
    request: SetRoleRequest,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Set the user's role (required before data collection can begin).

    This endpoint MUST be called after starting a session and before
    sending messages. The frontend should display "I'm a tenant" and
    "I'm a landlord" buttons, and call this endpoint when clicked.

    The role is always set explicitly from the frontend - there is no
    automatic role detection from natural language.

    Flow:
        1. POST /chat/start -> get session_id and greeting
        2. POST /chat/set-role -> set tenant/landlord, get first question
        3. POST /chat/message -> continue conversation

    The role must be either "tenant" or "landlord".
    """
    if request.role not in ("tenant", "landlord"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {request.role}. Must be 'tenant' or 'landlord'"
        )

    try:
        result = await intake_service.set_role(
            session_id=request.session_id,
            role=request.role,
        )

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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session(
    session_id: str,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Get the current state of a chat session.
    """
    try:
        status = await intake_service.get_session_status(session_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        return SessionStatusResponse(**status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Delete a chat session and associated data.
    """
    try:
        deleted = await intake_service.delete_session(session_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        return {"message": f"Session {session_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    List all active sessions.
    """
    try:
        sessions = await intake_service.list_sessions()
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
