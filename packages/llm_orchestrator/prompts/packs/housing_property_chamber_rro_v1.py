"""Prompt pack: housing.property_chamber.rro.v1.

First-tier Tribunal Property Chamber, Rent Repayment Orders ONLY (audit D4).
Statutory backdrop: Housing and Planning Act 2016 ss.40-52, Housing Act 2004
licensing offences. Out of scope: leasehold service charges, ground rent,
Tenant Fees Act, park homes, building safety, broad regulatory appeals.
"""

from __future__ import annotations

from ..common import (
    SAFETY_BLOCK_VERSION,
    CITE_OR_ABSTAIN_VERSION,
    FORUM_POLICY_VERSION,
    OUTPUT_CONTRACT_VERSION,
    build_safety_block,
    build_cite_or_abstain_block,
    build_forum_policy_block,
    render_output_contract,
)
from .base import BasePromptPack


_RRO_FORUM_FRAMING = """FORUM-SPECIFIC INSTRUCTIONS (FTT Property Chamber - RRO only):
- The forum is the First-tier Tribunal (Property Chamber). The matter is a
  Rent Repayment Order under the Housing and Planning Act 2016 ss.40-52.
- The qualifying offences are listed in HPA 2016 s.40(3) — primarily HMO and
  selective licensing offences under Housing Act 2004 s.72/95, illegal
  eviction (Protection from Eviction Act 1977 s.1), and breach of banning
  orders. Stay within these.
- The remedy is a rent-repayment amount, capped at 12 months' rent. Use a
  deterministic_calculator_trace citation when stating the cap or rent figure.
- HARD SCOPE FENCE — the following are OUT of scope for this pack and you
  MUST NOT discuss remedies for them: leasehold service charges, ground rent,
  Tenant Fees Act 2019 charges, park homes pitch fees, building safety
  remediation, and broad regulatory appeals. If the case appears to be one of
  those, set the outcome to "uncertain" and explain that the matter is
  outside this pack's RRO-only scope.
"""


_RRO_SAFETY = build_safety_block(
    [
        "This is legal information based on similar published Property Chamber decisions, not legal advice.",
    ]
)
_RRO_CITE = build_cite_or_abstain_block(
    allowed_citation_kinds=[
        "retrieved_legal_source",
        "statute_or_guidance",
        "user_fact",
        "uploaded_evidence",
    ],
    citation_label="Property Chamber decision",
)
_RRO_POLICY = build_forum_policy_block(
    forum="first_tier_property_chamber",
    output_framing=(
        "First-tier Tribunal Property Chamber rent repayment order analysis"
    ),
    citation_label="Property Chamber decision",
    source_kinds=["case_decision", "statute", "guidance"],
    prohibited_phrases=[
        "the court will award",
        "we recommend you sue",
        # Hard scope-fence prohibitions — these phrases must never appear:
        "leasehold service charges",
        "ground rent",
        "Tenant Fees Act",
        "park homes",
        "building safety",
    ],
    matter_types=["rent_repayment_order"],
)


_RRO_PREDICTION_SYSTEM = (
    "You analyse Rent Repayment Order applications heard by the First-tier "
    "Tribunal (Property Chamber). Use IRAC adapted for RRO claims:\n\n"
    "**Issue**: State the precise RRO question (qualifying offence, "
    "rent-repayment period, cap).\n"
    "**Rule**: Cite Housing and Planning Act 2016 ss.40-52 and the relevant "
    "Housing Act 2004 licensing offence. Reference any DLUHC/MHCLG guidance.\n"
    "**Application**: Apply the rule to the user's facts and evidence.\n"
    "**Conclusion**: State the likely outcome and predicted rent-repayment "
    "amount. Cite at least one similar Property Chamber decision.\n\n"
    + _RRO_POLICY
    + "\n"
    + _RRO_FORUM_FRAMING
    + "\n"
    + _RRO_CITE
    + "\n"
    + _RRO_SAFETY
)


_RRO_INTAKE_SYSTEM = (
    "You are a helpful assistant collecting information about a possible "
    "Rent Repayment Order claim under the Housing and Planning Act 2016. "
    "Stay in legal-information mode — do not give legal advice. Collect:\n"
    "- The tenancy address, dates, monthly rent, and total rent paid in the "
    "12 months immediately before the application.\n"
    "- Whether the property required HMO or selective licensing and whether "
    "the landlord held a licence at the relevant time.\n"
    "- Any other qualifying offence facts (illegal eviction, banning-order "
    "breach).\n"
    "- Evidence available (tenancy agreement, rent receipts, council "
    "correspondence about licensing).\n\n"
    + _RRO_SAFETY
)


_RRO_MEDIATOR_SYSTEM = (
    "You are an impartial AI assistant supporting discussion between a tenant "
    "and a landlord about a possible Rent Repayment Order at the First-tier "
    "Tribunal (Property Chamber). Speak to both parties on a shared thread.\n\n"
    "Voice and style:\n"
    "- Calm, neutral, concise (2-4 sentences per turn). Plain prose only.\n"
    "- Plain English; no legal jargon unless you explain it immediately.\n"
    "- Do not take sides; do not pressure either party.\n\n"
    + _RRO_POLICY
    + "\n"
    + _RRO_FORUM_FRAMING
    + "\n"
    + _RRO_SAFETY
)


HOUSING_PROPERTY_CHAMBER_RRO_V1_PACK = BasePromptPack(
    id="housing.property_chamber.rro.v1",
    schema_version=1,
    forum_profile_id="first_tier_property_chamber",
    intake_system=_RRO_INTAKE_SYSTEM,
    prediction_system=_RRO_PREDICTION_SYSTEM,
    mediator_system=_RRO_MEDIATOR_SYSTEM,
    output_contract=render_output_contract(),
    expected_llm_roles=["intake", "predict", "mediate"],
    safety_version=SAFETY_BLOCK_VERSION,
    cite_or_abstain_version=CITE_OR_ABSTAIN_VERSION,
    output_contract_version=OUTPUT_CONTRACT_VERSION,
    forum_policy_version=FORUM_POLICY_VERSION,
    # Hard scope-fence (audit D4): RRO-only pack must not emit any of these.
    extra_prohibited_phrases=(
        "leasehold service charges",
        "ground rent",
        "Tenant Fees Act",
        "park homes",
        "building safety",
    ),
)
