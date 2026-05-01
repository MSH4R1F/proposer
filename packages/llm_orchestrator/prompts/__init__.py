"""Prompt templates for LLM agents."""

from .tenant_intake import TENANT_SYSTEM_PROMPT, TENANT_STAGE_PROMPTS
from .landlord_intake import LANDLORD_SYSTEM_PROMPT, LANDLORD_STAGE_PROMPTS
from .prediction import PREDICTION_SYSTEM_PROMPT
from .extraction import FACT_EXTRACTION_PROMPT

# SHA-20 Phase 6: prompt-pack registry. Importing the packs module here is
# safe — packs only depend on prompt scaffolding and the existing prompt
# templates above. Callers reach packs via ``llm_orchestrator.prompts.packs``.
from . import packs  # noqa: F401  re-export for downstream callers

__all__ = [
    "TENANT_SYSTEM_PROMPT",
    "TENANT_STAGE_PROMPTS",
    "LANDLORD_SYSTEM_PROMPT",
    "LANDLORD_STAGE_PROMPTS",
    "PREDICTION_SYSTEM_PROMPT",
    "FACT_EXTRACTION_PROMPT",
    "packs",
]
