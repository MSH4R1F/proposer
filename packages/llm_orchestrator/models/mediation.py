"""
MediationSession - Data models for the mediation phase of a dispute.

Tracks offers, messages, and the negotiation lifecycle between tenant and landlord.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..agent_loop.trace import TraceSummary


class MediationStatus(str, Enum):
    """Status of the mediation session."""

    EXPECTATION_ADJUSTMENT = "expectation_adjustment"
    ACTIVE_NEGOTIATION = "active_negotiation"
    SETTLED = "settled"
    ESCALATED = "escalated"


class OfferStatus(str, Enum):
    """Status of a structured offer."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"
    EXPIRED = "expired"


class MessageType(str, Enum):
    """Type of mediation message."""

    TEXT = "text"
    OFFER = "offer"
    SYSTEM = "system"
    AI_MEDIATOR = "ai_mediator"


class MediationMessage(BaseModel):
    """A single message in the mediation conversation."""

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    sender_role: str  # "tenant", "landlord", or "ai_mediator"
    content: str
    message_type: MessageType = MessageType.TEXT
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)
    offer_id: Optional[str] = None
    reasoning_trace: Optional[TraceSummary] = None


class StructuredOffer(BaseModel):
    """A structured offer made during mediation."""

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    amount: float
    proposed_by_role: str  # "tenant" or "landlord"
    status: OfferStatus = OfferStatus.PENDING
    proposed_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    responded_at: Optional[str] = None
    counter_amount: Optional[float] = None


class MediationSession(BaseModel):
    """
    A mediation session between tenant and landlord.

    Tracks the full negotiation lifecycle including messages, offers,
    and the final outcome (settled or escalated).
    """

    mediation_id: str = Field(default_factory=lambda: f"MED-{str(uuid4())[:8].upper()}")
    dispute_id: str
    status: MediationStatus = MediationStatus.EXPECTATION_ADJUSTMENT
    messages: List[MediationMessage] = Field(default_factory=list)
    offers: List[StructuredOffer] = Field(default_factory=list)
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    settled_at: Optional[str] = None
    settlement_amount: Optional[float] = None
    escalated_at: Optional[str] = None

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()

    def add_message(
        self,
        sender_role: str,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        offer_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        reasoning_trace: Optional[TraceSummary] = None,
    ) -> MediationMessage:
        """Add a message to the session and return it."""
        message = MediationMessage(
            sender_role=sender_role,
            content=content,
            message_type=message_type,
            offer_id=offer_id,
            metadata=metadata or {},
            reasoning_trace=reasoning_trace,
        )
        self.messages.append(message)
        self.update_timestamp()
        return message

    def submit_offer(
        self,
        proposed_by_role: str,
        amount: float,
        deposit_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
    ) -> StructuredOffer:
        """
        Submit a new offer during mediation.

        Validates amount >= 0 (and <= max_amount/deposit_amount if provided).
        Creates a StructuredOffer, appends to self.offers, creates an OFFER message.
        """
        if amount < 0:
            raise ValueError(f"Offer amount must be >= 0, got {amount}")
        limit = max_amount if max_amount is not None else deposit_amount
        if limit is not None and amount > limit:
            raise ValueError(f"Offer amount {amount} exceeds allowed amount {limit}")

        offer = StructuredOffer(
            amount=amount,
            proposed_by_role=proposed_by_role,
        )
        self.offers.append(offer)
        self.add_message(
            sender_role=proposed_by_role,
            content=f"Offer submitted: £{amount:.2f}",
            message_type=MessageType.OFFER,
            offer_id=offer.id,
        )
        self.update_timestamp()
        return offer

    def accept_offer(self, offer_id: str, responder_role: str) -> StructuredOffer:
        """
        Accept an offer by ID.

        Validates responder_role != offer.proposed_by_role (cannot accept own offer).
        Sets status=ACCEPTED, responded_at, and calls settle(offer.amount).
        """
        offer = self._find_offer(offer_id)
        if responder_role == offer.proposed_by_role:
            raise ValueError("Cannot accept own offer")
        if offer.status != OfferStatus.PENDING:
            raise ValueError(f"Cannot accept offer with status: {offer.status.value}")

        offer.status = OfferStatus.ACCEPTED
        offer.responded_at = datetime.now().isoformat()
        self.settle(offer.amount)
        return offer

    def reject_offer(self, offer_id: str, responder_role: str) -> StructuredOffer:
        """
        Reject an offer by ID.

        Validates responder_role != offer.proposed_by_role (cannot reject own offer).
        Sets status=REJECTED, responded_at.
        """
        offer = self._find_offer(offer_id)
        if responder_role == offer.proposed_by_role:
            raise ValueError("Cannot reject own offer")
        if offer.status != OfferStatus.PENDING:
            raise ValueError(f"Cannot reject offer with status: {offer.status.value}")

        offer.status = OfferStatus.REJECTED
        offer.responded_at = datetime.now().isoformat()
        self.update_timestamp()
        return offer

    def counter_offer(
        self,
        offer_id: str,
        responder_role: str,
        counter_amount: float,
    ) -> StructuredOffer:
        """
        Counter an offer by ID.

        Sets original offer status=COUNTERED with counter_amount,
        then creates and returns a new StructuredOffer with counter_amount.
        """
        offer = self._find_offer(offer_id)
        if responder_role == offer.proposed_by_role:
            raise ValueError("Cannot counter own offer")
        if offer.status != OfferStatus.PENDING:
            raise ValueError(f"Cannot counter offer with status: {offer.status.value}")

        offer.status = OfferStatus.COUNTERED
        offer.counter_amount = counter_amount
        offer.responded_at = datetime.now().isoformat()

        new_offer = self.submit_offer(
            proposed_by_role=responder_role,
            amount=counter_amount,
        )
        return new_offer

    def settle(self, amount: float) -> None:
        """Settle the mediation session at the given amount."""
        self.status = MediationStatus.SETTLED
        self.settlement_amount = amount
        self.settled_at = datetime.now().isoformat()
        self.update_timestamp()

    def escalate(self) -> None:
        """Escalate the mediation (to tribunal)."""
        self.status = MediationStatus.ESCALATED
        self.escalated_at = datetime.now().isoformat()
        self.update_timestamp()

    def get_pending_offer(self) -> Optional[StructuredOffer]:
        """Return the latest offer with PENDING status."""
        for offer in reversed(self.offers):
            if offer.status == OfferStatus.PENDING:
                return offer
        return None

    def _find_offer(self, offer_id: str) -> StructuredOffer:
        """Find an offer by ID, raising ValueError if not found."""
        for offer in self.offers:
            if offer.id == offer_id:
                return offer
        raise ValueError(f"Offer not found: {offer_id}")
