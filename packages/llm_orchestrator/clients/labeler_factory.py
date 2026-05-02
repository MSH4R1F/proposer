"""Dual-provider factory helper for the LLM-assisted gold labeling pipeline.

Implements ``LabelerModelSpec`` + ``build_labeler_client`` for SHA-28
Phase 4 of ``docs/superpowers/plans/2026-05-02-llm-labeling-pipeline.md``.

This is intentionally NOT a re-skin of :func:`get_llm_client`. The role-
keyed factory in :mod:`llm_orchestrator.clients.factory` reads a single
``LLMConfig`` whose ``LLM_<ROLE>_PROVIDER`` env var resolves to one provider
per role at boot time — it cannot prove provider independence at the call
site. Codex finding [4] in
``.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md`` flags this directly:
the labeling runner builds *two* concrete clients, one per provider, in the
same process, from a per-case run sheet rather than env vars. So we wire
``ClaudeClient`` and ``OpenAIClient`` constructors directly here.

See sparring plan §2 ("Dual-LLM extraction").
"""

from __future__ import annotations

from typing import Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import BaseLLMClient
from .claude_client import ClaudeClient
from .openai_client import OpenAIClient

__all__ = ["LabelerModelSpec", "build_labeler_client"]


class LabelerModelSpec(BaseModel):
    """A single labeling pass's provider/model/version triple.

    Carried in the per-case run sheet and persisted into
    ``LabelingProvenance.labeler_models`` so a published gold set can be
    re-derived from raw outputs even after the live model is retired.

    OpenAI-only knobs (``reasoning_effort``, ``text_verbosity``, ``store``)
    are tolerated on Anthropic specs at their defaults — they're simply
    ignored by ``build_labeler_client`` when the provider is ``anthropic``.
    ``store=True`` is rejected at construction to mirror the OpenAIClient
    privacy invariant; doing so at the spec layer means a misconfigured run
    sheet fails fast, before any client object exists.
    """

    # Forbid extras so a typo (``"providor"``) is caught at run-sheet load
    # time rather than silently ignored. Mirror the strict posture of the
    # eval-side StrictBaseModel.
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["anthropic", "openai"]
    model: str = Field(min_length=1)
    api_version: Optional[str] = None

    # OpenAI-only knobs. None = "let the client default decide".
    reasoning_effort: Optional[Literal["low", "medium", "high", "xhigh", "none"]] = None
    text_verbosity: Optional[Literal["low", "medium", "high"]] = None
    store: bool = False

    @field_validator("store")
    @classmethod
    def _reject_store_true(cls, value: bool) -> bool:
        # Privacy invariant: legal/PII workflows require stateless requests.
        # Mirrors ``OpenAIClient.__init__``'s explicit refusal so the failure
        # surfaces at run-sheet validation rather than client construction.
        if value:
            raise ValueError(
                "LabelerModelSpec.store=True is rejected: the privacy invariant "
                "for legal/PII labeling requires stateless requests. Remove the "
                "field from the run sheet."
            )
        return value


def build_labeler_client(
    spec: LabelerModelSpec,
    *,
    api_keys: Mapping[str, str],
) -> BaseLLMClient:
    """Construct the concrete ``BaseLLMClient`` for a labeler spec.

    Args:
        spec: A validated :class:`LabelerModelSpec` from the run sheet.
        api_keys: Mapping with ``"anthropic"`` and/or ``"openai"`` keys.
            Only the entry for ``spec.provider`` is read; missing keys raise
            ``KeyError`` so an incomplete environment fails fast.

    Returns:
        A configured :class:`ClaudeClient` for Anthropic specs or
        :class:`OpenAIClient` (with ``store=False``) for OpenAI specs.

    Raises:
        KeyError: ``api_keys`` is missing the required provider key.

    Note:
        This intentionally does NOT delegate to
        :func:`llm_orchestrator.clients.factory.get_llm_client` — that
        factory is keyed on :class:`LLMRole` and reads from a single
        :class:`LLMConfig`, which can't prove provider independence at the
        call site (see Codex finding [4]).
    """
    if spec.provider == "anthropic":
        api_key = api_keys["anthropic"]
        # The labeler doesn't need a fallback model — runs are short, costs
        # are bounded, and silently swapping models would muddy provenance.
        # Pass primary as fallback so the existing rate-limit branch is a
        # no-op rather than swapping to a different model behind our back.
        return ClaudeClient(
            api_key=api_key,
            model=spec.model,
            fallback_model=spec.model,
        )

    if spec.provider == "openai":
        api_key = api_keys["openai"]
        return OpenAIClient(
            api_key=api_key,
            model=spec.model,
            fallback_model=None,
            reasoning_effort=spec.reasoning_effort,
            text_verbosity=spec.text_verbosity,
            # ``store`` is hard-coded False inside ``OpenAIClient.__init__``
            # too, but pass explicitly so a future refactor that loosens the
            # client default still gets caught here.
            store=False,
        )

    # Defensive — Pydantic Literal validation already guards against this,
    # but keep a clear runtime guard in case the spec is bypassed.
    raise ValueError(f"Unknown provider: {spec.provider!r}")
