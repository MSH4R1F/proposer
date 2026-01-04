"""
Base agent interface.

Defines the abstract interface for conversational agents.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from ..models.conversation import ConversationState


class BaseAgent(ABC):
    """Abstract base class for conversational agents."""

    @abstractmethod
    async def process_message(
        self,
        conversation: ConversationState,
        user_message: str,
    ) -> Tuple[str, ConversationState]:
        """
        Process a user message and generate a response.

        Args:
            conversation: Current conversation state
            user_message: The user's message

        Returns:
            Tuple of (agent_response, updated_conversation_state)
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        pass
