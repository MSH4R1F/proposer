"""Provider-neutral exception hierarchy for LLM clients.

Call sites should catch these neutral types rather than provider-specific
SDK exceptions. Provider adapters are responsible for wrapping/chaining
their native exceptions into these.

Introduced for SHA-114 (LLM provider abstraction). See
``docs/superpowers/specs/2026-05-01-llm-provider-abstraction-design.md`` §10.
"""


class LLMError(Exception):
    """Base class for all LLM-client errors."""


class LLMRateLimitError(LLMError):
    """Provider returned a rate-limit / quota error (HTTP 429-ish)."""


class LLMAPIError(LLMError):
    """Generic provider API error after retries are exhausted."""


class LLMStructuredOutputError(LLMError):
    """Structured output failed to parse / validate against schema."""


class LLMRefusalError(LLMError):
    """Model refused to answer (e.g. OpenAI Responses API refusal)."""


class LLMIncompleteResponseError(LLMError):
    """Model returned an incomplete response (truncated, hit max_tokens, etc.)."""
