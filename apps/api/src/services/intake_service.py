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

from ..config import config

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
        # Initialize LLM client
        llm_config = LLMConfig.from_env()
        self.llm_client = ClaudeClient(api_key=llm_config.anthropic_api_key)
        self.agent = IntakeAgent(self.llm_client)

        # Session storage (in-memory for now, could use Redis)
        self._sessions: Dict[str, ConversationState] = {}

        # Persistence directory
        self.sessions_dir = config.sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        logger.info("intake_service_initialized")

    async def start_session(
        self, role: Optional[str] = None
    ) -> tuple[str, str, str]:
        """
        Start a new intake session.

        Args:
            role: Optional user role (tenant/landlord)

        Returns:
            Tuple of (greeting, session_id, stage)
        """
        user_role = PartyRole(role) if role else None

        greeting, conversation = await self.agent.start_conversation(user_role)

        # Store session
        self._sessions[conversation.session_id] = conversation
        self._save_session(conversation)

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
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a message in an intake session.

        Args:
            session_id: The session ID
            message: User's message
            role: Optional role (for first message if not set)

        Returns:
            Dict with response, stage, completeness, case_file
        """
        # Get session
        conversation = await self._get_session(session_id)
        if not conversation:
            raise ValueError(f"Session not found: {session_id}")

        # Set role if provided and not already set
        if role and not conversation.case_file.user_role:
            conversation.case_file.user_role = PartyRole(role)

        # Process message
        response, updated_conversation = await self.agent.process_message(
            conversation, message
        )

        # Update session
        self._sessions[session_id] = updated_conversation
        self._save_session(updated_conversation)

        return {
            "response": response,
            "stage": updated_conversation.current_stage.value,
            "completeness": updated_conversation.case_file.completeness_score,
            "is_complete": updated_conversation.is_complete,
            "case_file": updated_conversation.case_file.model_dump(mode="json"),
            "suggested_actions": self._get_suggested_actions(updated_conversation),
        }

    async def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Get the status of a session."""
        conversation = await self._get_session(session_id)
        if not conversation:
            return None

        return {
            "session_id": session_id,
            "stage": conversation.current_stage.value,
            "completeness": conversation.case_file.completeness_score,
            "is_complete": conversation.is_complete,
            "message_count": len(conversation.messages),
            "case_file": conversation.case_file.model_dump(mode="json"),
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
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try loading from disk
        return self._load_session(session_id)

    def _save_session(self, conversation: ConversationState) -> None:
        """Save a session to disk."""
        path = self.sessions_dir / f"session_{conversation.session_id}.json"
        data = conversation.model_dump(mode="json")

        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load_session(self, session_id: str) -> Optional[ConversationState]:
        """Load a session from disk."""
        path = self.sessions_dir / f"session_{session_id}.json"
        if not path.exists():
            return None

        try:
            with open(path) as f:
                data = json.load(f)
            conversation = ConversationState.model_validate(data)
            self._sessions[session_id] = conversation
            return conversation
        except Exception as e:
            logger.error("session_load_failed", session_id=session_id, error=str(e))
            return None

    def _get_suggested_actions(self, conversation: ConversationState) -> List[str]:
        """Get suggested actions based on current state."""
        actions = []
        cf = conversation.case_file

        if conversation.is_complete:
            actions.append("Generate prediction")
            actions.append("Upload additional evidence")
        else:
            missing = cf.get_missing_required_info()
            if "deposit protection status" in missing:
                actions.append("Clarify deposit protection status")
            if "dispute issues" in missing:
                actions.append("Describe what's being disputed")

        return actions


def get_intake_service() -> IntakeService:
    """Dependency injection for intake service."""
    global _intake_service
    if _intake_service is None:
        _intake_service = IntakeService()
    return _intake_service
