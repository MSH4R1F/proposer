"""
Intake service.

Orchestrates the intake conversation flow and session management.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from llm_orchestrator.config import LLMConfig
from llm_orchestrator.clients.claude_client import ClaudeClient
from llm_orchestrator.agents.intake_agent import IntakeAgent
from llm_orchestrator.models.case_file import CaseFile, PartyRole
from llm_orchestrator.models.conversation import ConversationState

from apps.api.src.config import config

logger = structlog.get_logger()

# Global service instance
_intake_service: Optional["IntakeService"] = None


class IntakeService:
    """
    Service for managing intake conversations.

    Handles session creation, message processing, and persistence.
    """

    def __init__(self):
        """Initialize the intake service."""
        logger.debug("initializing_intake_service")
        
        # Initialize LLM client
        llm_config = LLMConfig.from_env()
        logger.debug("llm_config_loaded", 
                     has_anthropic_key=bool(llm_config.anthropic_api_key),
                     primary_model=llm_config.primary_model,
                     fallback_model=llm_config.fallback_model)
        
        self.llm_client = ClaudeClient(api_key=llm_config.anthropic_api_key)
        logger.debug("claude_client_created")
        
        self.agent = IntakeAgent(self.llm_client)
        logger.debug("intake_agent_created")

        # Session storage (in-memory for now, could use Redis)
        self._sessions: Dict[str, ConversationState] = {}

        # Persistence directory
        self.sessions_dir = config.sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("sessions_dir_ready", path=str(self.sessions_dir))

        logger.info("intake_service_initialized")

    async def start_session(self, role: Optional[str] = None) -> tuple[str, str, str]:
        """
        Start a new intake session with optional role.

        If role is provided, the session will start with the role already set
        and the first question will be role-appropriate.

        Args:
            role: Optional user role ("tenant" or "landlord")

        Returns:
            Tuple of (greeting, session_id, stage)
        """
        logger.debug("starting_new_session", role=role)
        
        # Convert role string to PartyRole if provided
        user_role = PartyRole(role) if role else None
        logger.debug("party_role_parsed", user_role=user_role.value if user_role else None)
        
        # Start conversation with role (agent handles role-specific greeting)
        greeting, conversation = await self.agent.start_conversation(user_role=user_role)
        
        logger.debug("conversation_created",
                     session_id=conversation.session_id,
                     stage=conversation.current_stage.value,
                     role=conversation.case_file.user_role.value if conversation.case_file.user_role else None,
                     greeting_length=len(greeting))

        # Store session
        self._sessions[conversation.session_id] = conversation
        logger.debug("session_stored_in_memory", 
                     session_id=conversation.session_id,
                     total_sessions=len(self._sessions))
        
        self._save_session(conversation)
        logger.debug("session_saved_to_disk", session_id=conversation.session_id)

        logger.info(
            "intake_session_started",
            session_id=conversation.session_id,
            role=role,
        )

        return greeting, conversation.session_id, conversation.current_stage.value

    async def process_message(
        self,
        session_id: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Process a message in an intake session.

        Role must be set via set_role() before processing messages.
        If role is not set, conversation will remain at GREETING stage.

        Args:
            session_id: The session ID
            message: User's message

        Returns:
            Dict with response, stage, completeness, case_file
        """
        logger.debug("processing_message",
                     session_id=session_id,
                     message_length=len(message))
        
        # Get session
        conversation = await self._get_session(session_id)
        if not conversation:
            logger.error("session_not_found_for_message", session_id=session_id)
            raise ValueError(f"Session not found: {session_id}")

        logger.debug("session_retrieved",
                     session_id=session_id,
                     current_stage=conversation.current_stage.value,
                     message_count=len(conversation.messages),
                     user_role=conversation.case_file.user_role.value if conversation.case_file.user_role else None)

        # Process message
        logger.debug("calling_agent_process_message", session_id=session_id)
        response, updated_conversation = await self.agent.process_message(
            conversation, message
        )
        
        logger.debug("agent_response_received",
                     session_id=session_id,
                     response_length=len(response),
                     new_stage=updated_conversation.current_stage.value,
                     completeness=updated_conversation.case_file.completeness_score,
                     is_complete=updated_conversation.is_complete)

        # Update intake_complete flag based on ALL required fields being present
        case_file = updated_conversation.case_file
        case_file.calculate_completeness()
        missing_required = case_file.get_missing_required_info()
        
        # Mark as complete ONLY if ALL required fields are present
        if case_file.has_all_required_info() and not case_file.intake_complete:
            case_file.intake_complete = True
            logger.info("intake_marked_complete_all_required_fields_present",
                       session_id=session_id,
                       completeness=case_file.completeness_score)
        
        logger.debug("intake_validation",
                    session_id=session_id,
                    has_all_required=case_file.has_all_required_info(),
                    missing_required=missing_required,
                    intake_complete=case_file.intake_complete)

        # Update session
        self._sessions[session_id] = updated_conversation
        logger.debug("session_updated_in_memory", session_id=session_id)
        
        self._save_session(updated_conversation)
        logger.debug("session_saved_after_message", session_id=session_id)

        # CRITICAL: Sync dispute status when party completes required fields
        # This enables the prediction button when BOTH parties are ready
        try:
            from apps.api.src.services.dispute_service import get_dispute_service
            dispute_service = get_dispute_service()
            await dispute_service.update_dispute_from_session(
                session_id=session_id,
                property_address=case_file.property.address,
                property_postcode=case_file.property.postcode,
                deposit_amount=case_file.tenancy.deposit_amount,
                intake_complete=case_file.intake_complete,
                role=case_file.user_role.value if case_file.user_role else None,
            )
            logger.debug("dispute_status_synced", 
                        session_id=session_id, 
                        intake_complete=case_file.intake_complete)
        except Exception as e:
            logger.warning("dispute_sync_failed", session_id=session_id, error=str(e))

        return {
            "response": response,
            "stage": updated_conversation.current_stage.value,
            "completeness": updated_conversation.case_file.completeness_score,
            "is_complete": updated_conversation.is_complete,
            "case_file": updated_conversation.case_file.model_dump(mode="json"),
            "suggested_actions": self._get_suggested_actions(updated_conversation),
        }

    async def set_role(
        self,
        session_id: str,
        role: str,
    ) -> Dict[str, Any]:
        """
        Explicitly set the user's role (for button-triggered UI flows).

        This method supports UI flows where the user clicks a button
        to identify as tenant or landlord.

        Args:
            session_id: The session ID
            role: User role ("tenant" or "landlord")

        Returns:
            Dict with response, stage, completeness, case_file
        """
        logger.debug("setting_role", session_id=session_id, role=role)
        
        conversation = await self._get_session(session_id)
        print(f"conversation: {conversation}")
        if not conversation:
            logger.error("session_not_found_for_role", session_id=session_id)
            raise ValueError(f"Session not found: {session_id}")

        logger.debug("session_retrieved_for_role",
                     session_id=session_id,
                     current_stage=conversation.current_stage.value)

        user_role = PartyRole(role)
        logger.debug("party_role_created", session_id=session_id, party_role=user_role.value)

        # Use agent method to set role and generate appropriate response
        logger.debug("calling_agent_set_user_role", session_id=session_id)
        response, updated_conversation = await self.agent.set_user_role(
            conversation, user_role
        )
        
        logger.debug("agent_role_response_received",
                     session_id=session_id,
                     response_length=len(response),
                     new_stage=updated_conversation.current_stage.value)

        # Update session
        self._sessions[session_id] = updated_conversation
        logger.debug("session_updated_after_role", session_id=session_id)
        
        self._save_session(updated_conversation)
        logger.debug("session_saved_after_role", session_id=session_id)

        logger.info(
            "intake_role_set",
            session_id=session_id,
            role=role,
            stage=updated_conversation.current_stage.value,
        )

        return {
            "response": response,
            "stage": updated_conversation.current_stage.value,
            "completeness": updated_conversation.case_file.completeness_score,
            "is_complete": updated_conversation.is_complete,
            "case_file": updated_conversation.case_file.model_dump(mode="json"),
            "role_set": True,
        }

    async def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Get the status of a session."""
        conversation = await self._get_session(session_id)
        if not conversation:
            return None

        # Convert messages to API format
        messages = []
        for msg in conversation.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp if hasattr(msg, 'timestamp') else None,
            })

        return {
            "session_id": session_id,
            "stage": conversation.current_stage.value,
            "completeness": conversation.case_file.completeness_score,
            "is_complete": conversation.is_complete,
            "message_count": len(conversation.messages),
            "case_file": conversation.case_file.model_dump(mode="json"),
            "messages": messages,
        }

    async def get_case_file(self, case_id: str) -> Optional[CaseFile]:
        """Get a case file by case ID."""
        # Look through sessions for matching case
        for session in self._sessions.values():
            if session.case_file.case_id == case_id:
                return session.case_file

        # Try loading from disk
        for path in self.sessions_dir.glob("session_*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("case_file", {}).get("case_id") == case_id:
                    return CaseFile.model_validate(data["case_file"])
            except Exception:
                continue

        return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]

        path = self.sessions_dir / f"session_{session_id}.json"
        if path.exists():
            path.unlink()
            return True

        return False

    async def delete_case(self, case_id: str) -> bool:
        """Delete a case and its session."""
        # Find session with this case
        session_id = None
        for sid, session in self._sessions.items():
            if session.case_file.case_id == case_id:
                session_id = sid
                break

        if session_id:
            return await self.delete_session(session_id)

        # Try disk
        for path in self.sessions_dir.glob("session_*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("case_file", {}).get("case_id") == case_id:
                    path.unlink()
                    return True
            except Exception:
                continue

        return False

    async def list_sessions(self) -> List[Dict]:
        """List all sessions."""
        sessions = []

        # In-memory sessions
        for session in self._sessions.values():
            sessions.append({
                "session_id": session.session_id,
                "case_id": session.case_file.case_id,
                "stage": session.current_stage.value,
                "is_complete": session.is_complete,
            })

        return sessions

    async def list_cases(self) -> List[Dict]:
        """List all cases."""
        cases = []
        seen_case_ids = set()

        # In-memory
        for session in self._sessions.values():
            cf = session.case_file
            if cf.case_id not in seen_case_ids:
                cases.append({
                    "case_id": cf.case_id,
                    "user_role": cf.user_role.value,
                    "intake_complete": cf.intake_complete,
                    "completeness_score": cf.completeness_score,
                    "created_at": cf.created_at,
                })
                seen_case_ids.add(cf.case_id)

        # From disk
        for path in self.sessions_dir.glob("session_*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                cf_data = data.get("case_file", {})
                case_id = cf_data.get("case_id")
                if case_id and case_id not in seen_case_ids:
                    cases.append({
                        "case_id": case_id,
                        "user_role": cf_data.get("user_role", "tenant"),
                        "intake_complete": cf_data.get("intake_complete", False),
                        "completeness_score": cf_data.get("completeness_score", 0),
                        "created_at": cf_data.get("created_at", ""),
                    })
                    seen_case_ids.add(case_id)
            except Exception:
                continue

        return cases

    async def _get_session(self, session_id: str) -> Optional[ConversationState]:
        """Get a session by ID."""
        logger.debug("getting_session", session_id=session_id)
        
        if session_id in self._sessions:
            logger.debug("session_found_in_memory", session_id=session_id)
            return self._sessions[session_id]

        # Try loading from disk
        logger.debug("session_not_in_memory_trying_disk", session_id=session_id)
        return self._load_session(session_id)

    def _save_session(self, conversation: ConversationState) -> None:
        """Save a session to disk."""
        path = self.sessions_dir / f"session_{conversation.session_id}.json"
        data = conversation.model_dump(mode="json")

        logger.debug("saving_session_to_disk",
                     session_id=conversation.session_id,
                     path=str(path),
                     data_size=len(str(data)))

        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.debug("session_file_written", session_id=conversation.session_id)

    def _load_session(self, session_id: str) -> Optional[ConversationState]:
        """Load a session from disk."""
        path = self.sessions_dir / f"session_{session_id}.json"
        
        logger.debug("attempting_load_session", session_id=session_id, path=str(path))
        
        if not path.exists():
            logger.debug("session_file_not_found", session_id=session_id, path=str(path))
            return None

        try:
            logger.debug("reading_session_file", session_id=session_id)
            with open(path) as f:
                data = json.load(f)
            
            logger.debug("validating_session_data", session_id=session_id)
            conversation = ConversationState.model_validate(data)
            
            self._sessions[session_id] = conversation
            logger.debug("session_loaded_successfully", 
                         session_id=session_id,
                         stage=conversation.current_stage.value,
                         message_count=len(conversation.messages))
            return conversation
        except Exception as e:
            logger.error("session_load_failed", 
                         session_id=session_id, 
                         error=str(e),
                         error_type=type(e).__name__)
            return None

    def _get_suggested_actions(self, conversation: ConversationState) -> List[str]:
        """
        Get suggested actions based on current state.
        
        Now strictly validates that ALL required fields are present before
        suggesting prediction generation.
        """
        actions = []
        cf = conversation.case_file

        # Only suggest prediction if ALL required fields are present
        if cf.has_all_required_info():
            actions.append("Generate prediction")
            actions.append("Upload additional evidence")
        else:
            # Show what's still needed
            missing = cf.get_missing_required_info()
            if missing:
                actions.append(f"Complete required info: {', '.join(missing)}")

        return actions


def get_intake_service() -> IntakeService:
    """Dependency injection for intake service."""
    global _intake_service
    if _intake_service is None:
        _intake_service = IntakeService()
    return _intake_service
