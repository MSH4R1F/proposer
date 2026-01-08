"""
Dispute service.

Manages dispute cases that link tenant and landlord sessions.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from llm_orchestrator.models.dispute import DisputeCase, DisputeStatus, generate_invite_code
from apps.api.src.config import config

logger = structlog.get_logger()

# Global service instance
_dispute_service: Optional["DisputeService"] = None


class DisputeService:
    """
    Service for managing dispute cases.
    
    Handles dispute creation, invite code validation, and linking sessions.
    """
    
    def __init__(self):
        """Initialize the dispute service."""
        logger.debug("initializing_dispute_service")
        
        # Dispute storage (in-memory + disk persistence)
        self._disputes: Dict[str, DisputeCase] = {}
        self._invite_code_index: Dict[str, str] = {}  # invite_code -> dispute_id
        
        # Persistence directory
        self.disputes_dir = config.data_dir / "disputes"
        self.disputes_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing disputes from disk
        self._load_disputes()
        
        logger.info("dispute_service_initialized", dispute_count=len(self._disputes))
    
    def _load_disputes(self) -> None:
        """Load disputes from disk on startup."""
        for path in self.disputes_dir.glob("dispute_*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                dispute = DisputeCase.model_validate(data)
                self._disputes[dispute.dispute_id] = dispute
                self._invite_code_index[dispute.invite_code] = dispute.dispute_id
                logger.debug("loaded_dispute", dispute_id=dispute.dispute_id)
            except Exception as e:
                logger.error("failed_to_load_dispute", path=str(path), error=str(e))
    
    def _save_dispute(self, dispute: DisputeCase) -> None:
        """Save a dispute to disk."""
        path = self.disputes_dir / f"dispute_{dispute.dispute_id}.json"
        data = dispute.model_dump(mode="json")
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.debug("saved_dispute", dispute_id=dispute.dispute_id, path=str(path))
    
    async def create_dispute(
        self,
        session_id: str,
        role: str,
        property_address: Optional[str] = None,
        property_postcode: Optional[str] = None,
        deposit_amount: Optional[float] = None,
    ) -> DisputeCase:
        """
        Create a new dispute case.
        
        Args:
            session_id: The session ID of the party creating the dispute
            role: The role of the creator ("tenant" or "landlord")
            property_address: Optional property address
            property_postcode: Optional postcode
            deposit_amount: Optional deposit amount
            
        Returns:
            The created DisputeCase
        """
        logger.debug("creating_dispute", session_id=session_id, role=role)
        
        # Create dispute with unique invite code
        dispute = DisputeCase(
            created_by_role=role,
            property_address=property_address,
            property_postcode=property_postcode,
            deposit_amount=deposit_amount,
        )
        
        # Ensure invite code is unique
        while dispute.invite_code in self._invite_code_index:
            dispute.invite_code = generate_invite_code()
        
        # Link the creator's session
        if role == "tenant":
            dispute.link_tenant_session(session_id)
            dispute.status = DisputeStatus.WAITING_FOR_LANDLORD
        else:
            dispute.link_landlord_session(session_id)
            dispute.status = DisputeStatus.WAITING_FOR_TENANT
        
        # Store
        self._disputes[dispute.dispute_id] = dispute
        self._invite_code_index[dispute.invite_code] = dispute.dispute_id
        self._save_dispute(dispute)
        
        logger.info(
            "dispute_created",
            dispute_id=dispute.dispute_id,
            invite_code=dispute.invite_code,
            created_by=role,
        )
        
        return dispute
    
    async def get_dispute(self, dispute_id: str) -> Optional[DisputeCase]:
        """Get a dispute by ID."""
        return self._disputes.get(dispute_id)
    
    async def get_dispute_by_invite_code(self, invite_code: str) -> Optional[DisputeCase]:
        """Get a dispute by invite code."""
        # Normalize invite code (uppercase, strip whitespace)
        normalized_code = invite_code.upper().strip()
        
        dispute_id = self._invite_code_index.get(normalized_code)
        if dispute_id:
            return self._disputes.get(dispute_id)
        
        return None
    
    async def get_dispute_by_session(self, session_id: str) -> Optional[DisputeCase]:
        """Get a dispute by one of its linked session IDs."""
        for dispute in self._disputes.values():
            if dispute.tenant_session_id == session_id or dispute.landlord_session_id == session_id:
                return dispute
        return None
    
    async def join_dispute(
        self,
        invite_code: str,
        session_id: str,
        role: str,
    ) -> Optional[DisputeCase]:
        """
        Join an existing dispute using an invite code.
        
        Args:
            invite_code: The invite code to join with
            session_id: The session ID of the joining party
            role: The role of the joining party ("tenant" or "landlord")
            
        Returns:
            The updated DisputeCase, or None if join failed
        """
        logger.debug("joining_dispute", invite_code=invite_code, session_id=session_id, role=role)
        
        dispute = await self.get_dispute_by_invite_code(invite_code)
        if not dispute:
            logger.warning("dispute_not_found_for_code", invite_code=invite_code)
            return None
        
        # Validate role matches what's expected
        if role == "tenant":
            if dispute.tenant_session_id:
                logger.warning("tenant_already_joined", dispute_id=dispute.dispute_id)
                return None
            dispute.link_tenant_session(session_id)
        else:
            if dispute.landlord_session_id:
                logger.warning("landlord_already_joined", dispute_id=dispute.dispute_id)
                return None
            dispute.link_landlord_session(session_id)
        
        self._save_dispute(dispute)
        
        logger.info(
            "party_joined_dispute",
            dispute_id=dispute.dispute_id,
            role=role,
            session_id=session_id,
        )
        
        return dispute
    
    async def update_dispute_from_session(
        self,
        session_id: str,
        property_address: Optional[str] = None,
        property_postcode: Optional[str] = None,
        deposit_amount: Optional[float] = None,
        intake_complete: bool = False,
        role: Optional[str] = None,
    ) -> Optional[DisputeCase]:
        """
        Update dispute info from a session's case file.
        
        Called when session data changes to keep dispute in sync.
        Uses robust status recalculation to fix any inconsistencies.
        """
        dispute = await self.get_dispute_by_session(session_id)
        if not dispute:
            return None
        
        # Update shared property info (first one wins, or can be merged)
        if property_address and not dispute.property_address:
            dispute.property_address = property_address
        if property_postcode and not dispute.property_postcode:
            dispute.property_postcode = property_postcode
        if deposit_amount and not dispute.deposit_amount:
            dispute.deposit_amount = deposit_amount
        
        # Update completion status using idempotent method
        if intake_complete and role:
            dispute.mark_party_complete(role)
            logger.info("dispute_party_marked_complete",
                       dispute_id=dispute.dispute_id,
                       role=role,
                       new_status=dispute.status.value,
                       is_ready=dispute.is_ready_for_prediction)
        
        dispute.update_timestamp()
        self._save_dispute(dispute)
        
        return dispute
    
    async def sync_dispute_status_from_sessions(
        self,
        dispute_id: str,
        tenant_complete: bool,
        landlord_complete: bool,
    ) -> Optional[DisputeCase]:
        """
        Sync dispute status based on actual session completion data.
        
        This fixes disputes that may be stuck in incorrect states.
        """
        dispute = await self.get_dispute(dispute_id)
        if not dispute:
            return None
        
        old_status = dispute.status
        dispute.recalculate_status(tenant_complete, landlord_complete)
        
        if old_status != dispute.status:
            logger.info("dispute_status_recalculated",
                       dispute_id=dispute_id,
                       old_status=old_status.value,
                       new_status=dispute.status.value,
                       tenant_complete=tenant_complete,
                       landlord_complete=landlord_complete)
        
        self._save_dispute(dispute)
        return dispute
    
    async def list_disputes(
        self,
        status: Optional[DisputeStatus] = None,
        limit: int = 100,
    ) -> List[DisputeCase]:
        """List disputes with optional filtering."""
        disputes = list(self._disputes.values())
        
        if status:
            disputes = [d for d in disputes if d.status == status]
        
        # Sort by created_at descending
        disputes.sort(key=lambda d: d.created_at, reverse=True)
        
        return disputes[:limit]
    
    async def delete_dispute(self, dispute_id: str) -> bool:
        """Delete a dispute."""
        if dispute_id not in self._disputes:
            return False
        
        dispute = self._disputes[dispute_id]
        
        # Remove from indices
        if dispute.invite_code in self._invite_code_index:
            del self._invite_code_index[dispute.invite_code]
        del self._disputes[dispute_id]
        
        # Remove from disk
        path = self.disputes_dir / f"dispute_{dispute_id}.json"
        if path.exists():
            path.unlink()
        
        logger.info("dispute_deleted", dispute_id=dispute_id)
        return True


def get_dispute_service() -> DisputeService:
    """Dependency injection for dispute service."""
    global _dispute_service
    if _dispute_service is None:
        _dispute_service = DisputeService()
    return _dispute_service
