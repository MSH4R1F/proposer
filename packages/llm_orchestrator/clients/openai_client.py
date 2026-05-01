"""OpenAI Responses-API LLM client.

Implements :class:`BaseLLMClient` against OpenAI's *Responses API* — NOT the
Chat Completions API. The Responses API is the surface that supports the
``reasoning``/``text.verbosity`` controls used by GPT-5-class models, and it
exposes structured output via :meth:`AsyncOpenAI.responses.parse` (passing a
Pydantic model directly as ``text_format``).

Key design points (see SHA-114 spec §6.1, §6.2, §10):

- ``store=False`` is hard-coded; we never opt in to server-side storage.
- ``previous_response_id`` is *never* sent — we always replay explicit input
  items so no conversation state lives on OpenAI's side.
- ``responses.parse`` is the default path for structured outputs. The manual
  ``text.format=json_schema`` strict-mode path is a conservative fallback for
  models / SDK versions that don't accept ``text_format``.
- Errors are mapped to the provider-neutral types in
  :mod:`llm_orchestrator.clients.exceptions` so call sites don't import
  ``openai`` exception classes.
- Cost accounting handles BOTH the tiered OpenAI pricing schema (e.g.
  ``input_short_context``/``output_short_context``) and the flat schema (e.g.
  ``input``/``output``). For tiered models we currently use short-context
  rates only — long-context detection is a follow-up (spec §9 simplification).

``run_agent_turn`` (SHA-114 Task 4) implements the
:class:`~llm_orchestrator.agent_loop.loop.AgentTurnClient` protocol on top of
the Responses API. The conversion between the agent loop's canonical
Anthropic-flavoured content blocks and OpenAI Responses *Items* is
deliberately verbose (see ``_internal_to_openai_input`` /
``_openai_response_to_blocks``) — getting ``call_id`` plumbing wrong silently
breaks tool round-trips, so the helpers favour explicit shape checks over
"clever" passthrough. NO factory wiring yet — that lands in Task 5.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import structlog
from openai import (
    APIError,
    APIStatusError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from ..agent_loop.loop import AgentTurnResponse
from ._pricing import get_model_pricing
from ._schema import strict_json_schema
from .base import BaseLLMClient
from .exceptions import (
    LLMAPIError,
    LLMIncompleteResponseError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMStructuredOutputError,
)
from .types import LLMProvider

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


# Sentinel used to detect SDK builds that don't expose ``responses.parse``.
# We treat AttributeError + a small set of "model doesn't support text_format"
# API errors as the trigger for the manual ``text.format`` JSON-schema fallback.
#
# Note: ``json_schema`` was intentionally dropped from this list — it's too
# generic and would match unrelated errors that happen to mention json_schema
# in their message. Prefer the structural ``exc.body.error.param/code`` check
# in :meth:`OpenAIClient._is_text_format_unsupported`; this substring tuple is
# only the message-only fallback for SDK errors that don't expose ``body``.
_FALLBACK_PARSE_HINTS = (
    "text_format",
    "response_format",
    "structured outputs",
)


class OpenAIClient(BaseLLMClient):
    """Async client for the OpenAI Responses API.

    See the module docstring for the full design. Constructor knobs:

    Args:
        api_key: OpenAI API key. Required even when a pre-built ``client`` is
            injected, because the SDK's ``AsyncOpenAI`` ctor refuses an empty
            key — tests pass any non-empty placeholder.
        model: Primary model id (e.g. ``"gpt-5.5"``).
        fallback_model: Optional cheaper model used only on a
            :class:`openai.RateLimitError`. ``None`` means the rate-limit
            surfaces as :class:`LLMRateLimitError` immediately.
        max_retries: Total attempts (incl. the first call) on transient 5xx
            errors. The default of 3 means 1 try + 2 retries.
        reasoning_effort: One of ``low|medium|high|xhigh|none`` (or ``None``
            to omit the field entirely). Forwarded as
            ``reasoning={"effort": ...}``. We omit rather than send ``None``
            so models that don't support reasoning don't reject the request.
        text_verbosity: One of ``low|medium|high`` (or ``None`` to omit).
            Forwarded as ``text={"verbosity": ...}``.
        store: Reserved; MUST be ``False``. The argument exists so the
            constructor signature matches what ``LLMConfig.OpenAIControls``
            carries, but passing ``True`` is a privacy-invariant violation
            and will raise :class:`ValueError`. Task 5's factory will pass
            ``False`` always.
        client: Optional pre-built ``AsyncOpenAI`` for tests. When provided,
            ``api_key`` is unused for SDK construction.
        retry_base_delay: Base delay (seconds) for the exponential backoff
            on transient 5xx errors. Tests can patch this to ``0`` to keep
            unit tests fast.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: Optional[str] = None,
        max_retries: int = 3,
        reasoning_effort: Optional[str] = None,
        text_verbosity: Optional[str] = None,
        store: bool = False,
        *,
        client: Optional[AsyncOpenAI] = None,
        retry_base_delay: float = 0.1,
    ) -> None:
        # We construct AsyncOpenAI with the supplied key only when no client is
        # injected; tests that mock ``responses.create`` typically pass their
        # own ``AsyncOpenAI`` so this branch is skipped.
        if store:
            raise ValueError(
                "OpenAIClient does not support store=True; the privacy invariant "
                "for legal/PII workflows requires stateless requests. "
                "If you need stateful Responses, route through a separate adapter "
                "after a documented data-retention review."
            )
        # Track whether we own the underlying SDK client so ``aclose`` only
        # closes connections we created (an injected mock/AsyncOpenAI is the
        # caller's responsibility).
        self._owns_client = client is None
        self.client = client if client is not None else AsyncOpenAI(api_key=api_key)
        self.model = model
        self.fallback_model = fallback_model
        self.max_retries = max(1, int(max_retries))
        self.reasoning_effort = reasoning_effort
        self.text_verbosity = text_verbosity
        # Hard-coded for privacy. The constructor arg exists for symmetry only;
        # ``store=True`` is rejected above.
        self.store = False
        self._retry_base_delay = retry_base_delay

        self._stats: Dict[str, int] = {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cached_tokens_in": 0,
            "reasoning_tokens_out": 0,
            "errors": 0,
            "fallback_uses": 0,
        }

        logger.info(
            "openai_client_initialized",
            model=model,
            fallback_model=fallback_model,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
        )

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Generate plain text via ``responses.create``.

        ``temperature`` is intentionally ignored — GPT-5-class reasoning models
        reject it on the Responses API and we'd rather honour the role's
        ``reasoning_effort`` knob. Argument is kept for ``BaseLLMClient`` parity.
        """
        self._stats["calls"] += 1

        kwargs = self._build_request_kwargs(
            input_items=self._convert_messages(messages),
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

        response = await self._call_with_retries_and_fallback(
            self.client.responses.create, kwargs
        )

        self._record_usage(response)
        self._raise_if_refused_or_incomplete(response)

        return self._extract_text(response)

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        response_model: Type[T],
        max_tokens: int = 4096,
    ) -> T:
        """Return a ``response_model`` instance via ``responses.parse``.

        Strategy:
          1. Try ``responses.parse(text_format=response_model, ...)``.
          2. If the SDK / model rejects ``text_format``, fall back to a manual
             ``responses.create`` with
             ``text={"format": {"type": "json_schema", "strict": True, ...}}``
             and parse the text output.
          3. On Pydantic ``ValidationError`` / JSON decode failure, retry ONCE
             with a repair message appended; if that also fails, raise
             :class:`LLMStructuredOutputError`.

        Retry-budget caveat: each iteration of the validation-retry loop
        delegates to :meth:`_call_with_retries_and_fallback`, which itself
        does up to ``max_retries`` attempts on transient 5xx errors and may
        also swap to ``fallback_model`` once on rate-limit. Worst-case
        fan-out for a single ``generate_structured`` call is therefore
        ``2 * max_retries`` SDK calls plus (potentially) one fallback-model
        swap per iteration. Acceptable per spec §10 (single repair retry on
        validation failure) but worth knowing under outage conditions.
        """
        input_items = self._convert_messages(messages)
        last_error: Optional[Exception] = None
        # Cache the strict-mode JSON schema lazily — only the manual
        # fallback path needs it, and the rewrite can be expensive on
        # complex models. Computing once here means a validation-retry
        # doesn't pay the cost twice (and a schema-rewrite error surfaces
        # only once, on the first attempt).
        cached_schema: Optional[Dict[str, Any]] = None

        # NOTE: each iteration here delegates to _call_with_retries_and_fallback,
        # which itself does up to max_retries on transient 5xx. See docstring
        # for full retry-budget caveat.
        for attempt in range(2):  # one retry on validation failure
            try:
                parsed, cached_schema = await self._attempt_structured_call(
                    input_items=input_items,
                    system_prompt=system_prompt,
                    response_model=response_model,
                    max_tokens=max_tokens,
                    cached_schema=cached_schema,
                )
                return parsed
            except (ValidationError, json.JSONDecodeError, LLMStructuredOutputError) as exc:
                last_error = exc
                if attempt == 0:
                    # Append a repair message instructing the model to fix the
                    # output. This goes into the *user* turn so the system
                    # prompt stays clean.
                    repair_text = (
                        "The previous response failed schema validation: "
                        f"{exc}. Respond again with valid JSON that matches "
                        "the requested schema EXACTLY."
                    )
                    input_items = list(input_items) + [
                        {"role": "user", "content": repair_text}
                    ]
                    logger.warning(
                        "openai_structured_validation_retry",
                        error=str(exc)[:200],
                    )
                    continue
                # Second failure — give up.
                self._stats["errors"] += 1
                logger.error(
                    "openai_structured_validation_failed",
                    error=str(exc)[:200],
                )
                raise LLMStructuredOutputError(
                    f"Structured output validation failed after retry: {exc}"
                ) from exc

        # Unreachable — both branches above either return or raise.
        assert last_error is not None  # pragma: no cover
        raise LLMStructuredOutputError(
            f"Structured output validation failed: {last_error}"
        )

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> AgentTurnResponse:
        """One LLM turn for the AgentLoop, against the Responses API.

        Implements :class:`~llm_orchestrator.agent_loop.loop.AgentTurnClient`.

        Conversion contract (see SHA-114 spec §6.3):
          - Input ``messages`` use the loop's canonical Anthropic-flavoured
            shape (``tool_use`` / ``tool_result`` content blocks). They are
            translated to typed Responses *Items* —
            ``function_call`` / ``function_call_output`` — preserving order
            and ``call_id`` linkage.
          - The Responses output is walked once: ``output_text`` parts become
            ``{"type": "text", ...}`` blocks; ``function_call`` Items become
            ``{"type": "tool_use", ...}`` blocks with ``input`` parsed from
            the JSON-string ``arguments``.

        Stop-reason normalisation:
          - Any ``function_call`` Item in the output ⇒ ``"tool_use"`` (wins
            over ``end_turn``).
          - ``status == "incomplete"`` ⇒ ``"max_tokens"`` (we do NOT raise
            here — the agent loop owns termination policy and should be
            allowed to end gracefully on truncation).
          - ``status == "failed"`` ⇒ raise :class:`LLMAPIError`.
          - Otherwise ⇒ ``"end_turn"``.

        Refusal during an agent turn raises :class:`LLMRefusalError` and does
        NOT swap to ``fallback_model`` (parity with ``generate``).

        Note: ``tool_schemas`` is forwarded verbatim as ``tools=...``. Today
        the loop hands us **Anthropic-shaped** schemas (it currently calls
        ``ToolSet.anthropic_schemas()`` unconditionally — see
        ``agent_loop/loop.py:150``). Task 5 will branch on provider and pass
        ``ToolSet.openai_response_tools()`` here. Until then, integration
        with the real loop will fail at the OpenAI API boundary; *unit*
        tests pass OpenAI-shaped schemas directly. This is a deliberate
        Task 5 hand-off point.
        """
        self._stats["calls"] += 1

        kwargs = self._build_request_kwargs(
            input_items=self._internal_to_openai_input(messages),
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            model=model,
        )
        kwargs["tools"] = tool_schemas

        response = await self._call_with_retries_and_fallback(
            self.client.responses.create, kwargs
        )

        self._record_usage(response)

        # Refusal must raise; an "incomplete" response must NOT raise here
        # (the agent loop handles termination). We therefore inline the
        # refusal/failed checks instead of calling
        # _raise_if_refused_or_incomplete which would also raise on incomplete.
        for item in getattr(response, "output", None) or []:
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "refusal":
                    refusal_text = getattr(part, "refusal", "") or ""
                    self._stats["errors"] += 1
                    logger.error(
                        "openai_run_agent_turn_refusal",
                        refusal=refusal_text[:200],
                    )
                    raise LLMRefusalError(
                        f"Model refused to answer: {refusal_text or '<no refusal text>'}"
                    )

        status = getattr(response, "status", None)
        if status == "failed":
            self._stats["errors"] += 1
            err = getattr(response, "error", None)
            err_msg = (
                getattr(err, "message", None) or str(err)
                if err
                else "unknown error"
            )
            raise LLMAPIError(
                f"OpenAI Responses API returned failed status: {err_msg}"
            )

        content_blocks = self._openai_response_to_blocks(response)
        has_tool_calls = any(
            b.get("type") == "tool_use" for b in content_blocks
        )
        stop_reason = self._normalize_stop_reason(response, has_tool_calls)

        # ``model`` may have been swapped to ``fallback_model`` mid-call by
        # the rate-limit branch of ``_call_with_retries_and_fallback``; the
        # SDK response carries the actual model used, so prefer that.
        model_used = getattr(response, "model", None) or kwargs["model"]

        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
        tokens_out = (
            int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
        )

        logger.debug(
            "openai_run_agent_turn_success",
            model=model_used,
            stop_reason=stop_reason,
            block_count=len(content_blocks),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        return AgentTurnResponse(
            content_blocks=content_blocks,
            stop_reason=stop_reason,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_used=model_used,
        )

    # ------------------------------------------------------------------ #
    # Agent-turn helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _internal_to_openai_input(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Translate canonical agent-loop messages into Responses Items.

        The loop hands us ``[{"role": ..., "content": ...}, ...]`` where
        ``content`` is either a flat string OR a list of typed blocks
        (``text`` / ``tool_use`` for replayed assistant turns, ``tool_result``
        inside a user message after tool dispatch).

        Mapping (per SHA-114 spec §6.3):
          - ``role=user, content=<str>``                     → ``{"role":"user","content":<str>}``
          - ``role=assistant, content=<str>``                → ``{"role":"assistant","content":<str>}``
          - ``role=user, content=[{"type":"tool_result", ...}]`` → one or more
            ``{"type":"function_call_output","call_id":...,"output":<str>}`` Items
          - ``role=assistant, content=[{"type":"text"|"tool_use", ...}]`` →
            text parts collapse into a flat assistant message; each
            ``tool_use`` becomes a ``{"type":"function_call",...}`` Item with
            ``arguments`` JSON-encoded as a string.
        """
        out: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content")

            # Flat string content — passthrough (text-only message).
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue

            # Structured content list.
            if isinstance(content, list):
                if role == "user":
                    # Either a tool-result reply (one or more tool_result
                    # blocks) or a regular user message with input_text parts.
                    text_parts: List[str] = []
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "tool_result":
                            tool_use_id = str(block.get("tool_use_id", ""))
                            inner = block.get("content", "")
                            output_str = (
                                inner if isinstance(inner, str) else json.dumps(
                                    inner, ensure_ascii=True, default=str
                                )
                            )
                            out.append(
                                {
                                    "type": "function_call_output",
                                    "call_id": tool_use_id,
                                    "output": output_str,
                                }
                            )
                        elif btype in ("input_text", "text"):
                            t = block.get("text", "")
                            if isinstance(t, str) and t:
                                text_parts.append(t)
                        # Unknown block types are dropped — adding them as
                        # opaque items would surprise the API.
                    if text_parts:
                        out.append(
                            {"role": "user", "content": "".join(text_parts)}
                        )
                    continue

                if role == "assistant":
                    # Assistant replay: text + tool_use blocks. Text parts
                    # become a flat assistant message; tool_use blocks each
                    # become a function_call Item. Order is preserved by
                    # emitting each text-run before any subsequent function_calls.
                    pending_text: List[str] = []

                    def _flush_text() -> None:
                        if pending_text:
                            out.append(
                                {
                                    "role": "assistant",
                                    "content": "".join(pending_text),
                                }
                            )
                            pending_text.clear()

                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "text":
                            t = block.get("text", "")
                            if isinstance(t, str) and t:
                                pending_text.append(t)
                        elif btype == "tool_use":
                            _flush_text()
                            tool_input = block.get("input", {}) or {}
                            try:
                                args_str = json.dumps(
                                    tool_input,
                                    ensure_ascii=True,
                                    default=str,
                                )
                            except (TypeError, ValueError):
                                args_str = "{}"
                            out.append(
                                {
                                    "type": "function_call",
                                    "call_id": str(block.get("id", "")),
                                    "name": str(block.get("name", "")),
                                    "arguments": args_str,
                                }
                            )
                        # Unknown block types dropped (see above).
                    _flush_text()
                    continue

            # Fallback — pass through unchanged. The SDK will surface any
            # error naturally; better than silently dropping.
            out.append({"role": role, "content": content})

        return out

    @staticmethod
    def _openai_response_to_blocks(response: Any) -> List[Dict[str, Any]]:
        """Walk ``response.output`` and build the canonical content_blocks list.

        - ``output_text`` parts → ``{"type":"text","text":...}``
        - ``function_call`` Items → ``{"type":"tool_use","id":<call_id>,
          "name":...,"input":<parsed dict>}``

        Order is preserved exactly as in ``response.output``. Refusal parts
        are NOT handled here — the caller checks for them earlier and raises.

        Raises :class:`LLMStructuredOutputError` if a function_call Item has
        malformed JSON in ``arguments``.
        """
        blocks: List[Dict[str, Any]] = []
        for item in getattr(response, "output", None) or []:
            item_type = getattr(item, "type", None)

            if item_type == "function_call":
                call_id = str(getattr(item, "call_id", "") or "")
                name = str(getattr(item, "name", "") or "")
                raw_args = getattr(item, "arguments", "") or ""
                if isinstance(raw_args, dict):
                    parsed_args = raw_args
                else:
                    try:
                        parsed_args = json.loads(raw_args) if raw_args else {}
                    except (json.JSONDecodeError, TypeError) as exc:
                        raise LLMStructuredOutputError(
                            f"OpenAI function_call '{call_id}' had malformed "
                            f"arguments JSON: {exc}; raw={raw_args!r}"
                        ) from exc
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": name,
                        "input": parsed_args,
                    }
                )
                continue

            # message Item — walk content parts.
            for part in getattr(item, "content", None) or []:
                part_type = getattr(part, "type", None)
                if part_type == "output_text":
                    text = getattr(part, "text", "")
                    if text:
                        blocks.append({"type": "text", "text": text})
                # refusal parts handled in run_agent_turn before we get here

        return blocks

    @staticmethod
    def _normalize_stop_reason(response: Any, has_tool_calls: bool) -> str:
        """Map Responses status + output shape to the agent-loop vocab.

        Priority: tool_use > max_tokens > end_turn. ``failed`` is handled
        by the caller (raises) so it never reaches this function.
        """
        if has_tool_calls:
            return "tool_use"
        status = getattr(response, "status", None)
        if status == "incomplete":
            # Map any incomplete reason to max_tokens — the agent loop
            # treats it as a terminal stop and we surface whatever text
            # we got.
            return "max_tokens"
        return "end_turn"

    def get_stats(self) -> Dict[str, Any]:
        """Provider-neutral stats dict (spec §9)."""
        stats: Dict[str, Any] = dict(self._stats)
        stats["provider"] = LLMProvider.OPENAI.value
        stats["model"] = self.model
        stats["estimated_cost_usd"] = self._estimate_cost(
            tokens_in=stats["tokens_in"],
            tokens_out=stats["tokens_out"],
        )
        return stats

    def reset_stats(self) -> None:
        """Zero every counter while preserving the dict shape."""
        for key in self._stats:
            self._stats[key] = 0

    async def aclose(self) -> None:
        """Close the underlying ``AsyncOpenAI`` client iff we created it.

        Tests/CLI that construct ``OpenAIClient(api_key=...)`` directly leak
        the SDK's connection pool without this. An *injected* client is the
        caller's responsibility — closing it here would surprise tests that
        share a single ``AsyncOpenAI`` across many client instances.

        Idempotent if the underlying SDK supports it; otherwise a second call
        will surface the SDK's own error.
        """
        if self._owns_client:
            await self.client.close()

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #

    def _convert_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Translate ``[{"role": ..., "content": ...}, ...]`` to Responses input items.

        For Task 3 (text + structured only) flat-string content is sufficient.
        Tool-result content blocks are tolerated unchanged but not yet
        translated — Task 4 will handle that path.
        """
        out: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            # Pass through string content as-is; structured content (e.g.
            # tool-result blocks) is left unchanged and will surface any
            # SDK errors naturally. Task 4 will translate
            # ``{"type": "tool_result", ...}`` blocks into Responses Items.
            out.append({"role": role, "content": content})
        return out

    def _build_request_kwargs(
        self,
        *,
        input_items: List[Dict[str, Any]],
        system_prompt: str,
        max_tokens: int,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assemble the kwargs dict for ``responses.create`` / ``responses.parse``.

        Only includes ``reasoning`` / ``text`` when configured — sending
        ``None`` would trip up models that don't support those controls.
        """
        kwargs: Dict[str, Any] = {
            "model": model or self.model,
            "instructions": system_prompt,
            "input": input_items,
            "max_output_tokens": max_tokens,
            "store": False,
        }
        if self.reasoning_effort is not None:
            kwargs["reasoning"] = {"effort": self.reasoning_effort}
        if self.text_verbosity is not None:
            kwargs["text"] = {"verbosity": self.text_verbosity}
        return kwargs

    async def _call_with_retries_and_fallback(
        self,
        sdk_callable: Any,
        base_kwargs: Dict[str, Any],
    ) -> Any:
        """Run an SDK call with rate-limit fallback + 5xx exponential backoff.

        - :class:`openai.RateLimitError` → swap ``model`` to ``fallback_model``
          (if configured) and retry once. If no fallback or already on
          fallback, raise :class:`LLMRateLimitError`.
        - :class:`openai.APIStatusError` with 5xx status → retry up to
          ``max_retries`` total attempts with exponential backoff.
        - :class:`openai.APIError` (no status) at the last attempt → raise
          :class:`LLMAPIError`.

        Any non-API exception (e.g. ``LLMRefusalError`` re-raised after
        partial processing) propagates unchanged.
        """
        kwargs = dict(base_kwargs)
        attempted_fallback = False
        attempt = 0

        while True:
            try:
                return await sdk_callable(**kwargs)

            except RateLimitError as e:
                # On rate-limit we don't count it as an "error" until we've
                # actually given up — the fallback path is expected to succeed.
                if (
                    self.fallback_model
                    and not attempted_fallback
                    and kwargs.get("model") != self.fallback_model
                ):
                    logger.warning(
                        "openai_rate_limit_falling_back",
                        from_model=kwargs.get("model"),
                        to_model=self.fallback_model,
                    )
                    kwargs["model"] = self.fallback_model
                    attempted_fallback = True
                    self._stats["fallback_uses"] += 1
                    continue
                self._stats["errors"] += 1
                logger.error(
                    "openai_rate_limit_exhausted",
                    model=kwargs.get("model"),
                )
                raise LLMRateLimitError(str(e)) from e

            except APIStatusError as e:
                status = getattr(e, "status_code", None)
                if status is not None and 500 <= int(status) < 600:
                    attempt += 1
                    if attempt < self.max_retries:
                        delay = self._retry_base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            "openai_api_5xx_retry",
                            status=status,
                            attempt=attempt,
                            delay=delay,
                        )
                        if delay > 0:
                            await asyncio.sleep(delay)
                        continue
                    self._stats["errors"] += 1
                    logger.error(
                        "openai_api_5xx_exhausted",
                        status=status,
                        attempts=attempt,
                    )
                    raise LLMAPIError(str(e)) from e
                # Non-5xx status (4xx other than 429) — not retryable.
                self._stats["errors"] += 1
                raise LLMAPIError(str(e)) from e

            except APIError as e:
                self._stats["errors"] += 1
                raise LLMAPIError(str(e)) from e

    async def _attempt_structured_call(
        self,
        *,
        input_items: List[Dict[str, Any]],
        system_prompt: str,
        response_model: Type[T],
        max_tokens: int,
        cached_schema: Optional[Dict[str, Any]] = None,
    ) -> tuple[T, Optional[Dict[str, Any]]]:
        """Single attempt: try ``responses.parse``, fall back to manual schema.

        Increments ``calls`` once per attempt (matching ``generate``).

        Returns ``(parsed, cached_schema)``; ``cached_schema`` is the
        strict-mode JSON schema computed for the manual fallback path, or
        ``None`` if the SDK ``responses.parse`` path succeeded and the
        rewrite was never needed. Caller passes it back on the validation
        retry to avoid recomputing (and re-raising on rewrite errors).
        """
        self._stats["calls"] += 1

        # ---- Path A: SDK structured parse --------------------------------
        if hasattr(self.client.responses, "parse"):
            kwargs = self._build_request_kwargs(
                input_items=input_items,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
            )
            kwargs["text_format"] = response_model
            try:
                response = await self._call_with_retries_and_fallback(
                    self.client.responses.parse, kwargs
                )
                self._record_usage(response)
                self._raise_if_refused_or_incomplete(response)
                parsed = getattr(response, "output_parsed", None)
                if parsed is not None:
                    if isinstance(parsed, response_model):
                        return parsed, cached_schema
                    # SDK returned a dict-like — coerce via model_validate.
                    return response_model.model_validate(parsed), cached_schema
                # SDK returned no parsed object — try to recover from
                # output_text, otherwise fall through to manual path.
                text = self._extract_text(response)
                return self._parse_text_into_model(text, response_model), cached_schema

            except LLMAPIError as exc:
                # Detect "this model doesn't support text_format" and retry
                # via the manual JSON-schema path. Be conservative: only fall
                # back when the message clearly hints at the structured-output
                # surface.
                if not self._is_text_format_unsupported(exc):
                    raise
                logger.info(
                    "openai_text_format_unsupported_falling_back",
                    error=str(exc)[:200],
                )

        # ---- Path B: manual text.format = json_schema (strict) -----------
        kwargs = self._build_request_kwargs(
            input_items=input_items,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        # Replace any existing ``text`` block — strict-mode JSON schema is
        # mutually exclusive with verbosity here. Compute the schema lazily
        # and reuse it across the validation retry (cheap, but a schema
        # rewrite that raises should only raise once).
        if cached_schema is None:
            cached_schema = strict_json_schema(response_model)
        kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": response_model.__name__,
                "strict": True,
                "schema": cached_schema,
            }
        }
        response = await self._call_with_retries_and_fallback(
            self.client.responses.create, kwargs
        )
        self._record_usage(response)
        self._raise_if_refused_or_incomplete(response)
        text = self._extract_text(response)
        return self._parse_text_into_model(text, response_model), cached_schema

    @staticmethod
    def _is_text_format_unsupported(exc: BaseException) -> bool:
        """Heuristic: did this error tell us the model can't take ``text_format``?

        Prefers the *structural* signal — OpenAI's API typically populates
        ``exc.body = {"error": {"param": ..., "code": ..., "message": ...}}``
        — and only falls back to substring matching on the stringified error
        when ``body`` is missing or malformed. The structural path is robust
        against OpenAI rewording the human-readable message; the substring
        path is a last-resort safety net.
        """
        # Walk through the underlying chain in case the exception was
        # wrapped (e.g. LLMAPIError(...) from APIStatusError).
        candidates: List[BaseException] = []
        cursor: Optional[BaseException] = exc
        while cursor is not None and cursor not in candidates:
            candidates.append(cursor)
            cursor = cursor.__cause__ or cursor.__context__

        for candidate in candidates:
            body = getattr(candidate, "body", None)
            if isinstance(body, dict):
                err = body.get("error") or {}
                if isinstance(err, dict):
                    if err.get("param") in ("text_format", "response_format"):
                        return True
                    if err.get("code") in ("unsupported_parameter", "invalid_parameter"):
                        msg = (err.get("message") or "")
                        if any(h in msg.lower() for h in _FALLBACK_PARSE_HINTS):
                            return True

        # Fallback: the SDK didn't expose a structured body, or the body
        # didn't match — sniff the stringified error.
        msg = str(exc).lower()
        return any(hint in msg for hint in _FALLBACK_PARSE_HINTS)

    @staticmethod
    def _parse_text_into_model(text: str, response_model: Type[T]) -> T:
        """Best-effort parse of model output text into ``response_model``.

        Tolerates Markdown code fences (``"```json ... ```"``) which some
        models still emit even with strict mode.
        """
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        json_str = m.group(1) if m else text.strip()
        data = json.loads(json_str)
        return response_model.model_validate(data)

    def _record_usage(self, response: Any) -> None:
        """Pull ``usage`` from the Responses object into ``self._stats``."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        tokens_in = getattr(usage, "input_tokens", 0) or 0
        tokens_out = getattr(usage, "output_tokens", 0) or 0
        self._stats["tokens_in"] += int(tokens_in)
        self._stats["tokens_out"] += int(tokens_out)

        in_details = getattr(usage, "input_tokens_details", None)
        if in_details is not None:
            cached = getattr(in_details, "cached_tokens", 0) or 0
            self._stats["cached_tokens_in"] += int(cached)

        out_details = getattr(usage, "output_tokens_details", None)
        if out_details is not None:
            reasoning = getattr(out_details, "reasoning_tokens", 0) or 0
            self._stats["reasoning_tokens_out"] += int(reasoning)

    def _raise_if_refused_or_incomplete(self, response: Any) -> None:
        """Translate Responses-API status flags into our neutral exceptions.

        Refusal: any output message whose content list contains a
        ``ResponseOutputRefusal`` part. We surface the refusal text so the
        caller knows what was refused — and we explicitly do NOT fall back
        to another model (per spec §10).

        Incomplete: ``status == "incomplete"`` or
        ``incomplete_details.reason == "max_output_tokens"``.
        """
        status = getattr(response, "status", None)
        incomplete_details = getattr(response, "incomplete_details", None)

        # Refusal detection — walk output items.
        for item in getattr(response, "output", None) or []:
            content = getattr(item, "content", None) or []
            for part in content:
                part_type = getattr(part, "type", None)
                if part_type == "refusal":
                    refusal_text = getattr(part, "refusal", "") or ""
                    self._stats["errors"] += 1
                    logger.error("openai_refusal", refusal=refusal_text[:200])
                    raise LLMRefusalError(
                        f"Model refused to answer: {refusal_text or '<no refusal text>'}"
                    )

        if status == "incomplete":
            reason = getattr(incomplete_details, "reason", None) if incomplete_details else None
            self._stats["errors"] += 1
            tokens_out = getattr(getattr(response, "usage", None), "output_tokens", None)
            logger.error(
                "openai_incomplete_response",
                reason=reason,
                tokens_out=tokens_out,
            )
            # Tailor the actionable hint to the actual reason. We keep the
            # exception type as LLMIncompleteResponseError even for
            # ``content_filter`` — the response was cut short by the
            # moderation layer rather than flat-out refused mid-stream, so
            # "incomplete" semantics fit better than LLMRefusalError (which
            # is reserved for explicit refusal parts emitted by the model).
            if reason == "max_output_tokens":
                hint = "increase max_output_tokens"
            elif reason == "content_filter":
                hint = "the response was filtered by moderation"
            else:
                hint = "see reason field"
            raise LLMIncompleteResponseError(
                f"Response incomplete (reason={reason}, tokens_out={tokens_out}); "
                f"{hint}"
            )

        if status == "failed":
            self._stats["errors"] += 1
            err = getattr(response, "error", None)
            err_msg = getattr(err, "message", None) or str(err) if err else "unknown error"
            raise LLMAPIError(f"OpenAI Responses API returned failed status: {err_msg}")

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Concatenate every ``output_text`` content part in the response.

        Walks ``response.output`` (a list of Items), and for each
        ``ResponseOutputMessage`` sums up the ``text`` of every
        ``output_text`` part. Refusal parts are skipped here — they're
        already raised in :meth:`_raise_if_refused_or_incomplete`.
        """
        # If the SDK gives us a top-level ``output_text`` convenience attr,
        # prefer it for simple single-message responses.
        convenience = getattr(response, "output_text", None)
        if isinstance(convenience, str) and convenience:
            return convenience

        chunks: List[str] = []
        for item in getattr(response, "output", None) or []:
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "output_text":
                    text = getattr(part, "text", "")
                    if text:
                        chunks.append(text)
        return "".join(chunks)

    # ------------------------------------------------------------------ #
    # Cost                                                                #
    # ------------------------------------------------------------------ #

    def _estimate_cost(self, *, tokens_in: int, tokens_out: int) -> Optional[float]:
        """Estimate USD cost from the YAML pricing table.

        Handles both pricing shapes:
          - **Flat**: ``input``/``output`` (e.g. ``gpt-5.4-mini``).
          - **Tiered**: ``input_short_context``/``output_short_context``
            (e.g. ``gpt-5.5``); long-context detection is deferred (spec §9).

        Returns ``None`` for unknown models OR for malformed pricing entries
        (logs a warning rather than crashing — silently dropping cost from
        stats is preferable to taking down a request just because the YAML
        is in an inconsistent state).
        """
        pricing = get_model_pricing(LLMProvider.OPENAI, self.model)
        if pricing is None:
            return None

        try:
            if "input" in pricing and "output" in pricing:
                input_rate = float(pricing["input"])
                output_rate = float(pricing["output"])
            elif (
                "input_short_context" in pricing
                and "output_short_context" in pricing
            ):
                input_rate = float(pricing["input_short_context"])
                output_rate = float(pricing["output_short_context"])
            else:
                logger.warning(
                    "openai_pricing_malformed",
                    model=self.model,
                    keys=list(pricing.keys()),
                )
                return None
        except (TypeError, ValueError) as exc:
            logger.warning(
                "openai_pricing_unparseable",
                model=self.model,
                error=str(exc),
            )
            return None

        return (tokens_in * input_rate + tokens_out * output_rate) / 1_000_000
