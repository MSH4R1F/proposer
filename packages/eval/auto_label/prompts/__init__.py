"""Prompt templates for the LLM labeling pipeline.

Templates here are hashed (``prompt_template_hash``) and the hash is
recorded per case in ``LabelingProvenance.prompt_template_hash`` so a
gold row can be replayed against the exact prompt that produced it.
Bumping a template forces a new ``run_id``.
"""
from eval.auto_label.prompts.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_PACK_VERSION,
    prompt_template_hash,
    render_extraction_prompt,
)

__all__ = [
    "EXTRACTION_SYSTEM_PROMPT",
    "PROMPT_PACK_VERSION",
    "prompt_template_hash",
    "render_extraction_prompt",
]
