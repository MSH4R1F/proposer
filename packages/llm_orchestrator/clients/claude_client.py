"""
Claude (Anthropic) LLM client implementation.

Provides async access to Claude models with structured output support.
"""

import json
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import structlog
from anthropic import AsyncAnthropic, APIError, RateLimitError
from pydantic import BaseModel, ValidationError

from .base import BaseLLMClient

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


class ClaudeClient(BaseLLMClient):
    """
    Anthropic Claude API client.

    Handles:
    - Async message generation with retry logic
    - Structured output parsing into Pydantic models
    - Token counting and cost tracking
    - Fallback to cheaper model on rate limits
    """

    # Pricing per 1M tokens (as of Jan 2025)
    PRICING = {
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    }

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        fallback_model: str = "claude-3-5-haiku-20241022",
        max_retries: int = 3,
    ):
        """
        Initialize the Claude client.

        Args:
            api_key: Anthropic API key
            model: Primary model to use
            fallback_model: Model to use on rate limits
            max_retries: Maximum retry attempts
        """
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.fallback_model = fallback_model
        self.max_retries = max_retries

        # Usage tracking
        self._stats = {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "errors": 0,
            "fallback_uses": 0,
        }

        logger.info(
            "claude_client_initialized",
            model=model,
            fallback_model=fallback_model,
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a text response from Claude.

        Args:
            messages: Conversation history
            system_prompt: System prompt to guide the model
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Generated text response
        """
        self._stats["calls"] += 1
        current_model = self.model

        for attempt in range(self.max_retries):
            try:
                response = await self.client.messages.create(
                    model=current_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=messages,
                )

                # Track usage
                self._stats["tokens_in"] += response.usage.input_tokens
                self._stats["tokens_out"] += response.usage.output_tokens

                # Extract text from response
                text = response.content[0].text

                logger.debug(
                    "claude_generate_success",
                    model=current_model,
                    tokens_in=response.usage.input_tokens,
                    tokens_out=response.usage.output_tokens,
                )

                return text

            except RateLimitError as e:
                logger.warning(
                    "claude_rate_limit",
                    model=current_model,
                    attempt=attempt + 1,
                )
                if current_model != self.fallback_model:
                    current_model = self.fallback_model
                    self._stats["fallback_uses"] += 1
                    continue
                raise

            except APIError as e:
                self._stats["errors"] += 1
                logger.error(
                    "claude_api_error",
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt == self.max_retries - 1:
                    raise

        raise RuntimeError("Max retries exceeded")

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        response_model: Type[T],
        max_tokens: int = 4096,
    ) -> T:
        """
        Generate a structured response parsed into a Pydantic model.

        Instructs Claude to output JSON and parses the response.

        Args:
            messages: Conversation history
            system_prompt: System prompt
            response_model: Pydantic model class to parse response into
            max_tokens: Maximum tokens in response

        Returns:
            Parsed Pydantic model instance
        """
        # Get the JSON schema from the Pydantic model
        schema = response_model.model_json_schema()

        # Augment system prompt with JSON instruction
        structured_prompt = f"""{system_prompt}

IMPORTANT: You must respond with valid JSON that matches this schema:
{json.dumps(schema, indent=2)}

Output ONLY the JSON object, no additional text or markdown formatting."""

        # Generate response
        response_text = await self.generate(
            messages=messages,
            system_prompt=structured_prompt,
            max_tokens=max_tokens,
            temperature=0.3,  # Lower temp for structured output
        )

        # Parse JSON from response
        try:
            # Try to extract JSON if wrapped in markdown
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text.strip()

            # Parse and validate
            data = json.loads(json_str)
            return response_model.model_validate(data)

        except json.JSONDecodeError as e:
            logger.error(
                "claude_json_parse_error",
                error=str(e),
                response_preview=response_text[:200],
            )
            raise ValueError(f"Failed to parse JSON response: {e}")

        except ValidationError as e:
            logger.error(
                "claude_validation_error",
                error=str(e),
                response_preview=response_text[:200],
            )
            raise ValueError(f"Response validation failed: {e}")

    async def generate_with_tools(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Generate a response with tool use capability.

        Args:
            messages: Conversation history
            system_prompt: System prompt
            tools: Tool definitions
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Returns:
            Response with potential tool use
        """
        self._stats["calls"] += 1

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        self._stats["tokens_in"] += response.usage.input_tokens
        self._stats["tokens_out"] += response.usage.output_tokens

        # Process response content
        result = {
            "text": None,
            "tool_use": None,
            "stop_reason": response.stop_reason,
        }

        for block in response.content:
            if hasattr(block, "text"):
                result["text"] = block.text
            elif hasattr(block, "type") and block.type == "tool_use":
                result["tool_use"] = {
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }

        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        stats = dict(self._stats)

        # Calculate costs
        if self.model in self.PRICING:
            pricing = self.PRICING[self.model]
            stats["estimated_cost_usd"] = (
                (stats["tokens_in"] / 1_000_000) * pricing["input"]
                + (stats["tokens_out"] / 1_000_000) * pricing["output"]
            )
        else:
            stats["estimated_cost_usd"] = None

        return stats

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._stats = {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "errors": 0,
            "fallback_uses": 0,
        }
