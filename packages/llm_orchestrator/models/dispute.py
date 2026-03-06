"""
DisputeCase - Links tenant and landlord sessions for the same dispute.

This model represents a complete dispute case that can have both parties'
sessions linked together for mediation.
"""

import random
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# Word lists for generating human-readable invite codes
ADJECTIVES = [
    "blue", "green", "red", "swift", "calm", "bright", "golden", "silver",
    "bold", "wise", "kind", "fair", "warm", "cool", "fresh", "clear",
    "proud", "brave", "gentle", "noble", "quick", "steady", "strong", "keen"
]

NOUNS = [
    "tiger", "falcon", "oak", "river", "mountain", "bridge", "garden", "harbor",
    "meadow", "forest", "eagle", "dolphin", "lion", "phoenix", "cedar", "maple",
    "summit", "valley", "horizon", "compass", "anchor", "beacon", "shield", "crown"
]


def generate_invite_code() -> str:
    """
    Generate a human-readable invite code.
    
    Format: ADJECTIVE-NOUN-NUMBER (e.g., "BLUE-TIGER-42")
    This is easy to share verbally and type correctly.
    """
    adjective = random.choice(ADJECTIVES).upper()
    noun = random.choice(NOUNS).upper()
    number = random.randint(10, 99)
    return f"{adjective}-{noun}-{number}"


class DisputeStatus(str, Enum):
    """Status of the dispute case."""
    WAITING_FOR_TENANT = "waiting_for_tenant"
    WAITING_FOR_LANDLORD = "waiting_for_landlord"
    TENANT_IN_PROGRESS = "tenant_in_progress"
    LANDLORD_IN_PROGRESS = "landlord_in_progress"
    BOTH_IN_PROGRESS = "both_in_progress"
    TENANT_COMPLETE = "tenant_complete"
    LANDLORD_COMPLETE = "landlord_complete"
    BOTH_COMPLETE = "both_complete"
    READY_FOR_MEDIATION = "ready_for_mediation"
    IN_MEDIATION = "in_mediation"
    SETTLED = "settled"
    CLOSED = "closed"


class DisputeCase(BaseModel):
    """
    A dispute case that links tenant and landlord sessions.
    
    This is the parent container that holds references to both parties'
    individual intake sessions, allowing them to be matched and compared
    during the mediation process.
    """
    dispute_id: str = Field(default_factory=lambda: f"DISP-{str(uuid4())[:8].upper()}")
    invite_code: str = Field(default_factory=generate_invite_code)
    status: DisputeStatus = DisputeStatus.WAITING_FOR_LANDLORD
    
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # Party who created this dispute
    created_by_role: str = "tenant"  # "tenant" or "landlord"
    
    # Linked session IDs (one or both may be present)
    tenant_session_id: Optional[str] = None
    landlord_session_id: Optional[str] = None
    
    # Shared property info (for display and validation)
    property_address: Optional[str] = None
    property_postcode: Optional[str] = None
    
    # Quick reference to deposit amount (both parties should agree)
    deposit_amount: Optional[float] = None
    
    # Metadata
    notes: Optional[str] = None
    
    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()
    
    def link_tenant_session(self, session_id: str) -> None:
        """Link a tenant session to this dispute."""
        self.tenant_session_id = session_id
        self._update_status()
        self.update_timestamp()
    
    def link_landlord_session(self, session_id: str) -> None:
        """Link a landlord session to this dispute."""
        self.landlord_session_id = session_id
        self._update_status()
        self.update_timestamp()
    
    def _update_status(self) -> None:
        """Update status based on linked sessions."""
        has_tenant = self.tenant_session_id is not None
        has_landlord = self.landlord_session_id is not None
        
        if has_tenant and has_landlord:
            self.status = DisputeStatus.BOTH_IN_PROGRESS
        elif has_tenant:
            self.status = DisputeStatus.WAITING_FOR_LANDLORD
        elif has_landlord:
            self.status = DisputeStatus.WAITING_FOR_TENANT
    
    def mark_party_complete(self, role: str) -> None:
        """
        Mark a party's intake as complete.
        
        This method is IDEMPOTENT - calling it multiple times for the same party
        will not change the status once both parties are complete.
        """
        # Already fully complete - don't change status
        if self.status in (DisputeStatus.BOTH_COMPLETE, DisputeStatus.READY_FOR_MEDIATION, 
                           DisputeStatus.IN_MEDIATION, DisputeStatus.SETTLED, DisputeStatus.CLOSED):
            self.update_timestamp()
            return
        
        if role == "tenant":
            # Don't regress if tenant already marked complete
            if self.status == DisputeStatus.TENANT_COMPLETE:
                self.update_timestamp()
                return
            # Check if landlord already complete -> both complete
            if self.status == DisputeStatus.LANDLORD_COMPLETE:
                self.status = DisputeStatus.BOTH_COMPLETE
            else:
                self.status = DisputeStatus.TENANT_COMPLETE
        elif role == "landlord":
            # Don't regress if landlord already marked complete
            if self.status == DisputeStatus.LANDLORD_COMPLETE:
                self.update_timestamp()
                return
            # Check if tenant already complete -> both complete
            if self.status == DisputeStatus.TENANT_COMPLETE:
                self.status = DisputeStatus.BOTH_COMPLETE
            else:
                self.status = DisputeStatus.LANDLORD_COMPLETE
        
        # Transition to ready for mediation when both complete
        if self.status == DisputeStatus.BOTH_COMPLETE:
            self.status = DisputeStatus.READY_FOR_MEDIATION
        
        self.update_timestamp()
    
    def recalculate_status(self, tenant_complete: bool, landlord_complete: bool) -> None:
        """
        Recalculate dispute status based on actual completion state.
        
        This fixes disputes that may have been corrupted by previous bugs.
        Call this to sync the dispute status with the actual session data.
        """
        has_tenant = self.tenant_session_id is not None
        has_landlord = self.landlord_session_id is not None
        
        # Already in a final state - don't change
        if self.status in (DisputeStatus.IN_MEDIATION, DisputeStatus.SETTLED, DisputeStatus.CLOSED):
            return
        
        # Both complete -> ready for mediation
        if tenant_complete and landlord_complete and has_tenant and has_landlord:
            self.status = DisputeStatus.READY_FOR_MEDIATION
        # Only tenant complete
        elif tenant_complete and has_tenant:
            if landlord_complete and has_landlord:
                self.status = DisputeStatus.READY_FOR_MEDIATION
            else:
                self.status = DisputeStatus.TENANT_COMPLETE
        # Only landlord complete
        elif landlord_complete and has_landlord:
            if tenant_complete and has_tenant:
                self.status = DisputeStatus.READY_FOR_MEDIATION
            else:
                self.status = DisputeStatus.LANDLORD_COMPLETE
        # Both in progress
        elif has_tenant and has_landlord:
            self.status = DisputeStatus.BOTH_IN_PROGRESS
        # Waiting for one party
        elif has_tenant:
            self.status = DisputeStatus.WAITING_FOR_LANDLORD
        elif has_landlord:
            self.status = DisputeStatus.WAITING_FOR_TENANT
        
        self.update_timestamp()
    
    @property
    def has_both_parties(self) -> bool:
        """Check if both parties have joined."""
        return self.tenant_session_id is not None and self.landlord_session_id is not None
    
    @property
    def is_ready_for_prediction(self) -> bool:
        """Check if ready for AI prediction."""
        return self.status in (
            DisputeStatus.BOTH_COMPLETE,
            DisputeStatus.READY_FOR_MEDIATION,
        )
    
    def get_other_party_role(self, current_role: str) -> str:
        """Get the role of the other party."""
        return "landlord" if current_role == "tenant" else "tenant"
    
    def get_waiting_message(self, current_role: str) -> str:
        """Get a user-friendly waiting message."""
        other_role = self.get_other_party_role(current_role)
        
        if current_role == "tenant":
            if not self.landlord_session_id:
                return f"Waiting for the landlord to join using code: {self.invite_code}"
            elif self.status != DisputeStatus.LANDLORD_COMPLETE:
                return "Waiting for the landlord to complete their intake"
        else:
            if not self.tenant_session_id:
                return f"Waiting for the tenant to join using code: {self.invite_code}"
            elif self.status != DisputeStatus.TENANT_COMPLETE:
                return "Waiting for the tenant to complete their intake"
        
        return "Both parties have completed intake. Ready for prediction."

    def start_mediation(self) -> None:
        """Transition dispute to IN_MEDIATION status. IDEMPOTENT."""
        if self.status == DisputeStatus.IN_MEDIATION:
            return
        if self.status not in (DisputeStatus.READY_FOR_MEDIATION, DisputeStatus.BOTH_COMPLETE):
            raise ValueError(f"Cannot start mediation from status: {self.status.value}")
        self.status = DisputeStatus.IN_MEDIATION
        self.update_timestamp()

    def settle(self) -> None:
        """Transition dispute to SETTLED status."""
        if self.status == DisputeStatus.SETTLED:
            return
        self.status = DisputeStatus.SETTLED
        self.update_timestamp()

    def escalate(self) -> None:
        """Transition dispute to CLOSED status (escalated to tribunal)."""
        if self.status == DisputeStatus.CLOSED:
            return
        self.status = DisputeStatus.CLOSED
        self.update_timestamp()
