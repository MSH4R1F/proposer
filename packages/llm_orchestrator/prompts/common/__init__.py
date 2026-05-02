"""Shared prompt scaffolding used by all SHA-20 prompt packs.

These modules carry the cross-domain text that every pack composes onto the
domain-specific prediction/intake/mediator system prompts. Each scaffold
declares an explicit ``VERSION`` constant so changes flow into the
``hash_prompt_pack`` digest.
"""

from .safety import SAFETY_BLOCK_VERSION, build_safety_block
from .cite_or_abstain import CITE_OR_ABSTAIN_VERSION, build_cite_or_abstain_block
from .output_contracts import (
    OUTPUT_CONTRACT_VERSION,
    PREDICTION_OUTPUT_CONTRACT,
    render_output_contract,
)
from .forum_policy import FORUM_POLICY_VERSION, build_forum_policy_block

__all__ = [
    "SAFETY_BLOCK_VERSION",
    "build_safety_block",
    "CITE_OR_ABSTAIN_VERSION",
    "build_cite_or_abstain_block",
    "OUTPUT_CONTRACT_VERSION",
    "PREDICTION_OUTPUT_CONTRACT",
    "render_output_contract",
    "FORUM_POLICY_VERSION",
    "build_forum_policy_block",
]
