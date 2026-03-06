"""
Mediation router for AI-powered mediation sessions.

Handles negotiation flow between tenant and landlord parties,
including offer submission, responses, and settlement generation.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
import structlog

from apps.api.src.services.mediation_service import (
    MediationService,
    get_mediation_service,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/mediation", tags=["mediation"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class StartMediationRequest(BaseModel):
    """Request to start a mediation session."""

    session_id: str = Field(
        ..., description="Session ID of the party starting mediation"
    )


class AddMessageRequest(BaseModel):
    """Request to add a message to an active mediation session."""

    session_id: str = Field(
        ..., description="Session ID of the party sending the message"
    )
    content: str = Field(..., description="Message content")


class SubmitOfferRequest(BaseModel):
    """Request to submit a settlement offer."""

    session_id: str = Field(..., description="Session ID of the party making the offer")
    amount: float = Field(..., description="Offer amount in GBP", ge=0)


class RespondToOfferRequest(BaseModel):
    """Request to respond to an existing settlement offer."""

    session_id: str = Field(..., description="Session ID of the responding party")
    offer_id: str = Field(..., description="ID of the offer to respond to")
    action: str = Field(
        ..., description="Response action: 'accept', 'reject', or 'counter'"
    )
    counter_amount: Optional[float] = Field(
        None, description="Counter offer amount in GBP (required when action='counter')"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{dispute_id}/start")
async def start_mediation(
    dispute_id: str,
    request: StartMediationRequest,
    svc: MediationService = Depends(get_mediation_service),
) -> Dict[str, Any]:
    """
    Start a mediation session for a dispute.

    Creates or re-activates a mediation session and returns the opening AI
    mediator message. Requires a prediction to exist for the dispute.

    On ValueError → 400 (e.g. dispute not found, prediction missing).
    """
    logger.debug(
        "start_mediation_request",
        dispute_id=dispute_id,
        session_id=request.session_id,
    )
    try:
        result = await svc.start_mediation(dispute_id, request.session_id)
        logger.info(
            "mediation_started",
            dispute_id=dispute_id,
            mediation_id=result.get("mediation_id"),
        )
        return result
    except ValueError as e:
        logger.warning(
            "start_mediation_bad_request", dispute_id=dispute_id, error=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "start_mediation_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dispute_id}/expectation/{session_id}")
async def get_expectation(
    dispute_id: str,
    session_id: str,
    svc: MediationService = Depends(get_mediation_service),
) -> Dict[str, Any]:
    """
    Get expectation data (prediction + cost-benefit analysis) for a party.

    Returns role-specific framing of the predicted outcome to calibrate
    each party's expectations before negotiation begins.

    On ValueError → 404 (prediction not found, dispute not found).
    """
    logger.debug(
        "get_expectation_request",
        dispute_id=dispute_id,
        session_id=session_id,
    )
    try:
        result = await svc.get_expectation_data(dispute_id, session_id)
        logger.debug(
            "get_expectation_success",
            dispute_id=dispute_id,
            session_id=session_id,
            party_role=result.get("party_role"),
        )
        return result
    except ValueError as e:
        logger.warning(
            "get_expectation_not_found",
            dispute_id=dispute_id,
            session_id=session_id,
            error=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_expectation_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dispute_id}/messages")
async def get_messages(
    dispute_id: str,
    since: Optional[str] = Query(
        None, description="ISO timestamp — only return messages after this point"
    ),
    svc: MediationService = Depends(get_mediation_service),
) -> List[Dict[str, Any]]:
    """
    Get messages for a mediation session.

    Optionally filter by ISO timestamp via the `since` query parameter
    to poll for new messages only.
    """
    logger.debug("get_messages_request", dispute_id=dispute_id, since=since)
    try:
        messages = await svc.get_messages(dispute_id, since)
        logger.debug(
            "get_messages_success",
            dispute_id=dispute_id,
            message_count=len(messages),
        )
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_messages_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dispute_id}/message")
async def add_message(
    dispute_id: str,
    request: AddMessageRequest,
    svc: MediationService = Depends(get_mediation_service),
) -> Dict[str, Any]:
    """
    Send a message in an active mediation session.

    Stores the party's message and triggers an AI mediator response.
    Returns both the stored user message and the AI response.

    On ValueError → 400 (session not active, session not linked).
    """
    logger.debug(
        "add_message_request",
        dispute_id=dispute_id,
        session_id=request.session_id,
        content_length=len(request.content),
    )
    try:
        result = await svc.add_message(dispute_id, request.session_id, request.content)
        logger.debug(
            "add_message_success",
            dispute_id=dispute_id,
            session_id=request.session_id,
        )
        return result
    except ValueError as e:
        logger.warning("add_message_bad_request", dispute_id=dispute_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "add_message_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dispute_id}/offer")
async def submit_offer(
    dispute_id: str,
    request: SubmitOfferRequest,
    svc: MediationService = Depends(get_mediation_service),
) -> Dict[str, Any]:
    """
    Submit a settlement offer.

    Amount must be between 0 and the dispute's deposit amount.
    Returns the created StructuredOffer.

    On ValueError → 400 (invalid amount, session not active).
    """
    logger.debug(
        "submit_offer_request",
        dispute_id=dispute_id,
        session_id=request.session_id,
        amount=request.amount,
    )
    try:
        offer = await svc.submit_offer(dispute_id, request.session_id, request.amount)
        logger.info(
            "offer_submitted",
            dispute_id=dispute_id,
            offer_id=offer.id,
            amount=request.amount,
        )
        return offer.model_dump(mode="json")
    except ValueError as e:
        logger.warning("submit_offer_bad_request", dispute_id=dispute_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "submit_offer_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dispute_id}/respond")
async def respond_to_offer(
    dispute_id: str,
    request: RespondToOfferRequest,
    svc: MediationService = Depends(get_mediation_service),
) -> Dict[str, Any]:
    """
    Respond to an existing settlement offer.

    Actions:
    - `accept` — settles the dispute at the offered amount.
    - `reject` — rejects the offer; negotiation continues.
    - `counter` — counter-offer at `counter_amount`.

    Returns updated offer details and settlement info when applicable.

    On ValueError → 400 (invalid action, self-acceptance, invalid amount).
    """
    logger.debug(
        "respond_to_offer_request",
        dispute_id=dispute_id,
        session_id=request.session_id,
        offer_id=request.offer_id,
        action=request.action,
    )
    try:
        result = await svc.respond_to_offer(
            dispute_id,
            request.session_id,
            request.offer_id,
            request.action,
            request.counter_amount,
        )
        logger.info(
            "offer_responded",
            dispute_id=dispute_id,
            offer_id=request.offer_id,
            action=request.action,
        )
        return result
    except ValueError as e:
        logger.warning(
            "respond_to_offer_bad_request", dispute_id=dispute_id, error=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "respond_to_offer_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dispute_id}/settlement")
async def get_settlement(
    dispute_id: str,
    svc: MediationService = Depends(get_mediation_service),
) -> Dict[str, Any]:
    """
    Get the settlement summary for a completed mediation.

    Returns amount, timestamps, message/offer counts and status.

    On ValueError → 404 (session not found or not yet settled).
    """
    logger.debug("get_settlement_request", dispute_id=dispute_id)
    try:
        result = await svc.get_settlement(dispute_id)
        logger.debug(
            "get_settlement_success",
            dispute_id=dispute_id,
            settlement_amount=result.get("settlement_amount"),
        )
        return result
    except ValueError as e:
        logger.warning("get_settlement_not_found", dispute_id=dispute_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_settlement_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dispute_id}/settlement/pdf")
async def get_settlement_pdf(
    dispute_id: str,
    svc: MediationService = Depends(get_mediation_service),
) -> Response:
    """
    Generate and download the settlement agreement as a PDF.

    Returns the PDF binary with `application/pdf` content type.

    On ValueError → 404 (mediation session not found).
    """
    logger.debug("get_settlement_pdf_request", dispute_id=dispute_id)
    try:
        pdf_bytes = await svc.generate_settlement_pdf(dispute_id)
        logger.info(
            "settlement_pdf_generated",
            dispute_id=dispute_id,
            pdf_size=len(pdf_bytes),
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="settlement_{dispute_id}.pdf"'
            },
        )
    except ValueError as e:
        logger.warning(
            "get_settlement_pdf_not_found", dispute_id=dispute_id, error=str(e)
        )
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_settlement_pdf_failed",
            dispute_id=dispute_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))
