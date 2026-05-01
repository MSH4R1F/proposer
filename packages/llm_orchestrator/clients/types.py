"""Provider and role enums for the LLM client abstraction.

Introduced for SHA-114 (LLM provider abstraction) so any of the four LLM roles
in the system can be backed by either Anthropic or OpenAI without leaking
provider-specific types into call sites.

See ``docs/superpowers/specs/2026-05-01-llm-provider-abstraction-design.md``
for the full design.
"""

from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class LLMRole(str, Enum):
    """The four LLM roles used across the system.

    Each role can be configured with an independent provider/model pair.
    Defaults are documented in §7 of the abstraction design spec.
    """

    INTAKE = "intake"
    PREDICTION = "prediction"
    MEDIATOR = "mediator"
    EXTRACTION = "extraction"
