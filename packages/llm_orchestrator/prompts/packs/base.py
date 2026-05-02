"""Prompt pack protocol + base class + canonical hash function.

Packs do NOT own provider/model routing; they only declare which roles they
expect the runtime to fulfil. The runtime (SHA-113/114) decides who fulfils
each role.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Protocol, runtime_checkable

from domain_core.hashing import _canonicalize  # leaf dependency, allowed


# A strict allowlist of roles a pack may declare. The runtime maps each of
# these to a concrete provider+model in a later phase; the pack itself stays
# provider-agnostic.
ALLOWED_LLM_ROLES = {"intake", "predict", "mediate"}


@runtime_checkable
class PromptPack(Protocol):
    """Structural protocol all prompt packs satisfy."""

    id: str
    schema_version: int
    intake_system: str
    prediction_system: str
    mediator_system: str
    output_contract: Dict[str, Any]
    expected_llm_roles: List[str]
    forum_profile_id: str


@dataclass(frozen=True)
class BasePromptPack:
    """Concrete dataclass packs use as their default implementation.

    Domain modules instantiate ``BasePromptPack(...)`` rather than subclassing
    so the data is immutable and trivial to hash.
    """

    id: str
    schema_version: int
    forum_profile_id: str
    intake_system: str
    prediction_system: str
    mediator_system: str
    output_contract: Dict[str, Any]
    expected_llm_roles: List[str] = field(default_factory=lambda: ["intake", "predict", "mediate"])

    # Versions of the cross-cutting scaffolds used to compose this pack. They
    # roll into ``hash_prompt_pack`` so any scaffold change invalidates caches.
    safety_version: str = ""
    cite_or_abstain_version: str = ""
    output_contract_version: str = ""
    forum_policy_version: str = ""

    # Extra prohibited phrases the pack ENFORCES on top of the matched
    # ForumProfile.prohibited_phrases. Use this for hard scope-fence terms
    # that aren't sensible to put on the YAML profile (e.g., the RRO pack's
    # leasehold/Tenant Fees scope fence). Hashed into ``hash_prompt_pack``.
    extra_prohibited_phrases: tuple[str, ...] = ()

    def __post_init__(self) -> None:  # pragma: no cover - validation only
        for role in self.expected_llm_roles:
            if role not in ALLOWED_LLM_ROLES:
                raise ValueError(
                    f"Pack {self.id} declares unknown LLM role {role!r}; "
                    f"allowed: {sorted(ALLOWED_LLM_ROLES)}"
                )


# Pattern for run-specific placeholders that should be normalised before
# hashing. We replace them with a single canonical token so two packs with
# identical templates but different runtime placeholder names still hash
# equally — and so legitimate template changes still invalidate the hash.
_PLACEHOLDER_PATTERN = re.compile(r"\{[a-zA-Z0-9_.]+\}")


def _strip_placeholders(text: str) -> str:
    """Replace ``{foo}``-style format placeholders with ``{__placeholder__}``.

    This keeps the hash stable across cosmetic changes to placeholder NAMES
    (because they're swapped uniformly) while still detecting changes to the
    surrounding template prose.
    """
    return _PLACEHOLDER_PATTERN.sub("{__placeholder__}", text)


def hash_prompt_pack(pack: BasePromptPack) -> str:
    """SHA-256 hex digest of the canonical JSON form of a pack.

    Inputs to the hash:

    - ``id``, ``schema_version``, ``forum_profile_id``
    - rendered prompt templates (with placeholder names normalised)
    - ``output_contract`` (canonicalised)
    - safety / cite-or-abstain / forum-policy / output-contract scaffold versions
    - ``expected_llm_roles`` (sorted)
    """
    payload = {
        "id": pack.id,
        "schema_version": pack.schema_version,
        "forum_profile_id": pack.forum_profile_id,
        "intake_system": _strip_placeholders(pack.intake_system),
        "prediction_system": _strip_placeholders(pack.prediction_system),
        "mediator_system": _strip_placeholders(pack.mediator_system),
        "output_contract": _canonicalize(pack.output_contract),
        "expected_llm_roles": sorted(pack.expected_llm_roles),
        "safety_version": pack.safety_version,
        "cite_or_abstain_version": pack.cite_or_abstain_version,
        "output_contract_version": pack.output_contract_version,
        "forum_policy_version": pack.forum_policy_version,
        "extra_prohibited_phrases": sorted(pack.extra_prohibited_phrases),
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def pack_to_dict(pack: BasePromptPack) -> Dict[str, Any]:
    """Return a plain-dict representation of a pack (for debugging/logging)."""
    return asdict(pack)
