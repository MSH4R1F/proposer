"""
Base LLM client interface.

Defines the abstract interface for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a text response from the LLM.

        Args:
            messages: Conversation history as list of {"role": ..., "content": ...}
            system_prompt: System prompt to guide the model
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        response_model: Type[T],
        max_tokens: int = 4096,
    ) -> T:
        """
        Generate a structured response parsed into a Pydantic model.

        Args:
            messages: Conversation history
            system_prompt: System prompt
            response_model: Pydantic model class to parse response into
            max_tokens: Maximum tokens in response

        Returns:
            Parsed Pydantic model instance
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        pass

    @abstractmethod
    def reset_stats(self) -> None:
        """Reset usage statistics."""
        pass
