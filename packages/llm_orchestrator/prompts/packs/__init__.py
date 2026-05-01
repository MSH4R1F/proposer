"""SHA-20 prompt packs.

Each pack composes the cross-domain scaffolds (safety, cite-or-abstain,
output contract, forum policy) with domain-specific text into a
``PromptPack`` instance. Packs do NOT own provider/model routing —
``LLMRole``/provider factories (SHA-113/114) decide who fulfils which role.

The ``REGISTRY`` maps domain ids to their packs. Use ``get_prompt_pack`` for
lookup so the registry stays the single source of truth.
"""

from __future__ import annotations

from typing import Dict

from .base import PromptPack, BasePromptPack, hash_prompt_pack
from .housing_deposit_v1 import HOUSING_DEPOSIT_V1_PACK
from .housing_repairs_social_v1 import HOUSING_REPAIRS_SOCIAL_V1_PACK
from .housing_property_chamber_rro_v1 import HOUSING_PROPERTY_CHAMBER_RRO_V1_PACK
from .employment_unfair_dismissal_v1 import EMPLOYMENT_UNFAIR_DISMISSAL_V1_PACK


REGISTRY: Dict[str, BasePromptPack] = {
    HOUSING_DEPOSIT_V1_PACK.id: HOUSING_DEPOSIT_V1_PACK,
    HOUSING_REPAIRS_SOCIAL_V1_PACK.id: HOUSING_REPAIRS_SOCIAL_V1_PACK,
    HOUSING_PROPERTY_CHAMBER_RRO_V1_PACK.id: HOUSING_PROPERTY_CHAMBER_RRO_V1_PACK,
    EMPLOYMENT_UNFAIR_DISMISSAL_V1_PACK.id: EMPLOYMENT_UNFAIR_DISMISSAL_V1_PACK,
}


def get_prompt_pack(domain_id: str) -> BasePromptPack:
    """Return the prompt pack for a registered domain id.

    Raises ``KeyError`` if the domain has no registered pack.
    """
    if domain_id not in REGISTRY:
        raise KeyError(
            f"No prompt pack registered for domain {domain_id!r}; "
            f"registered: {sorted(REGISTRY)}"
        )
    return REGISTRY[domain_id]


__all__ = [
    "PromptPack",
    "BasePromptPack",
    "hash_prompt_pack",
    "REGISTRY",
    "get_prompt_pack",
    "HOUSING_DEPOSIT_V1_PACK",
    "HOUSING_REPAIRS_SOCIAL_V1_PACK",
    "HOUSING_PROPERTY_CHAMBER_RRO_V1_PACK",
    "EMPLOYMENT_UNFAIR_DISMISSAL_V1_PACK",
]
