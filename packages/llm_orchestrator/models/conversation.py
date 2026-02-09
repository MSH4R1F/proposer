"""
Conversation state management for the intake agent.

Tracks the conversation history, current stage, and extracted facts.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .case_file import CaseFile, PartyRole


class IntakeStage(str, Enum):
    """Stages in the intake conversation flow."""
    GREETING = "greeting"
    ROLE_IDENTIFICATION = "role_identification"
    BASIC_DETAILS = "basic_details"
    TENANCY_DETAILS = "tenancy_details"
    DEPOSIT_DETAILS = "deposit_details"
    ISSUE_IDENTIFICATION = "issue_identification"
    EVIDENCE_COLLECTION = "evidence_collection"
    CLAIM_AMOUNTS = "claim_amounts"
    NARRATIVE = "narrative"
    CONFIRMATION = "confirmation"
    COMPLETE = "complete"


class Message(BaseModel):
    """A single message in the conversation."""
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def user(cls, content: str) -> "Message":
        """Create a user message."""
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> "Message":
        """Create an assistant message."""
        return cls(role="assistant", content=content)


class ConversationState(BaseModel):
    """
    Complete state of an intake conversation.

    Tracks messages, current stage, and the evolving case file.
    """
    session_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    case_file: CaseFile
    messages: List[Message] = Field(default_factory=list)
    current_stage: IntakeStage = IntakeStage.GREETING
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Stage tracking
    stages_completed: List[IntakeStage] = Field(default_factory=list)
    current_stage_attempts: int = 0  # Track retries for current stage

    # Extraction tracking
    last_extraction_successful: bool = True
    extraction_errors: List[str] = Field(default_factory=list)

    # Role tracking for button-triggered flows
    role_explicitly_set: bool = False

    @classmethod
    def new(cls, case_id: Optional[str] = None, user_role: Optional[PartyRole] = None) -> "ConversationState":
        """
        Create a new conversation state.

        Args:
            case_id: Optional case ID (auto-generated if not provided)
            user_role: Optional user role. If provided, role_explicitly_set=True
                       and stage can skip ROLE_IDENTIFICATION.
        """
        explicitly_set = user_role is not None
        case_file = CaseFile(
            case_id=case_id or str(uuid4())[:12],
            user_role=user_role or PartyRole.TENANT,
        )
        return cls(case_file=case_file, role_explicitly_set=explicitly_set)

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> Message:
        """Add a message to the conversation."""
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()
        return message

    def add_user_message(self, content: str) -> Message:
        """Add a user message."""
        return self.add_message("user", content)

    def add_assistant_message(self, content: str) -> Message:
        """Add an assistant message."""
        return self.add_message("assistant", content)

    def to_messages(self) -> List[Dict[str, str]]:
        """
        Convert to format expected by LLM APIs.

        Returns list of {"role": ..., "content": ...} dicts.
        """
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def get_last_user_message(self) -> Optional[Message]:
        """Get the most recent user message."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg
        return None

    def get_last_assistant_message(self) -> Optional[Message]:
        """Get the most recent assistant message."""
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg
        return None

    def set_role(self, role: PartyRole) -> None:
        """
        Explicitly set the user's role (for button-triggered flows).

        This marks the role as explicitly set, allowing the intake agent
        to skip role identification and proceed directly to data collection.

        Args:
            role: The user's role (TENANT or LANDLORD)
        """
        self.case_file.user_role = role
        self.role_explicitly_set = True
        self.updated_at = datetime.now().isoformat()

    def advance_stage(self, new_stage: IntakeStage) -> None:
        """Advance to a new stage."""
        if self.current_stage not in self.stages_completed:
            self.stages_completed.append(self.current_stage)
        self.current_stage = new_stage
        self.current_stage_attempts = 0
        self.updated_at = datetime.now().isoformat()

    def mark_complete(self) -> None:
        """Mark the intake as complete."""
        self.current_stage = IntakeStage.COMPLETE
        self.case_file.intake_complete = True
        self.case_file.calculate_completeness()
        self.updated_at = datetime.now().isoformat()

    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation for context."""
        summary_parts = [
            f"Session: {self.session_id}",
            f"Role: {self.case_file.user_role.value}",
            f"Stage: {self.current_stage.value}",
            f"Messages: {len(self.messages)}",
            f"Completeness: {self.case_file.completeness_score:.0%}",
        ]

        if self.case_file.property.address:
            summary_parts.append(f"Property: {self.case_file.property.address}")

        if self.case_file.issues:
            issues_str = ", ".join(i.value for i in self.case_file.issues)
            summary_parts.append(f"Issues: {issues_str}")

        return " | ".join(summary_parts)

    @property
    def message_count(self) -> int:
        """Get total number of messages."""
        return len(self.messages)

    @property
    def is_complete(self) -> bool:
        """Check if intake is complete."""
        return self.current_stage == IntakeStage.COMPLETE
