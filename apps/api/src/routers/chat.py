"""
Chat router for conversational intake.

Handles the intake conversation flow.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..services.intake_service import IntakeService, get_intake_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""
    session_id: str = Field(..., description="Session ID for the conversation")
    message: str = Field(..., description="User's message")
    role: Optional[str] = Field(None, description="User role (tenant/landlord) - required for first message")


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
    role: Optional[str] = Field(None, description="User role (tenant/landlord)")


class StartSessionResponse(BaseModel):
    """Response when starting a new session."""
    session_id: str
    greeting: str
    stage: str


class SessionStatusResponse(BaseModel):
    """Response with session status."""
    session_id: str
    stage: str
    completeness: float
    is_complete: bool
    message_count: int
    case_file: Dict


@router.post("/start", response_model=StartSessionResponse)
async def start_session(
    request: StartSessionRequest,
    intake_service: IntakeService = Depends(get_intake_service),
):
    """
    Start a new intake conversation session.

    Optionally specify the user role (tenant/landlord).
    Returns a session ID and initial greeting.
    """
    try:
        greeting, session_id, stage = await intake_service.start_session(
            role=request.role
        )

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

    First message should include role (tenant/landlord) if not set in start.
    Returns the agent's response and updated case file state.
    """
    try:
        result = await intake_service.process_message(
            session_id=request.session_id,
            message=request.message,
            role=request.role,
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
