"""Prompt pack: housing.deposit.v1.

Compatibility baseline. Wraps the existing IRAC/intake/mediator prompts
verbatim so existing deposit predictions remain schema-compatible. Adds
matter-type-aware framing so deposit_deduction (deposit-scheme adjudication)
and deposit_non_protection (county court) emit the right language.
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
from ..mediator import MEDIATOR_SYSTEM_PROMPT
from ..prediction_v2 import IRAC_JSON_SCHEMA, IRAC_SYSTEM_PROMPT
from ..tenant_intake import TENANT_SYSTEM_PROMPT
from .base import BasePromptPack


_DEPOSIT_FORUM_FRAMING = """MATTER-TYPE FRAMING (deposit dispute domain):
- For matter_type=deposit_deduction: frame the analysis as a deposit-scheme
  adjudication outcome. Use the citation label "Tribunal decision". Discuss
  recovery issue-by-issue (cleaning, damage, etc.). DO NOT apply the 1x-3x
  Housing Act 2004 s.214 penalty here — that branch is for non-protection only.
- For matter_type=deposit_non_protection: frame the analysis as a county court
  Housing Act 2004 s.214 non-protection penalty matter. The remedy is the
  statutory penalty (1x-3x deposit) and any return of the deposit itself.
  Use a deterministic_calculator_trace citation when stating the multiplier
  range.
"""


_DEPOSIT_SAFETY = build_safety_block(
    [
        "This is legal information based on similar published decisions, not legal advice.",
    ]
)
_DEPOSIT_CITE = build_cite_or_abstain_block(
    allowed_citation_kinds=[
        "retrieved_legal_source",
        "user_fact",
        "uploaded_evidence",
        "statute_or_guidance",
    ],
    citation_label="Tribunal decision",
)
_DEPOSIT_POLICY = build_forum_policy_block(
    forum="deposit_scheme_adjudication",
    output_framing=(
        "deposit-scheme adjudication outcome analysis based on tribunal decisions"
    ),
    citation_label="Tribunal decision",
    source_kinds=["case_decision", "guidance", "statute"],
    prohibited_phrases=[
        "the court will award",
        "we recommend you sue",
        "you should accept",
    ],
    matter_types=["deposit_deduction", "deposit_non_protection"],
)


HOUSING_DEPOSIT_V1_PREDICTION_SYSTEM = (
    IRAC_SYSTEM_PROMPT
    + "\n\n"
    + _DEPOSIT_POLICY
    + "\n"
    + _DEPOSIT_FORUM_FRAMING
    + "\n"
    + _DEPOSIT_CITE
    + "\n"
    + _DEPOSIT_SAFETY
    + "\n"
    + IRAC_JSON_SCHEMA
)


HOUSING_DEPOSIT_V1_INTAKE_SYSTEM = (
    TENANT_SYSTEM_PROMPT
    + "\n\nFORUM/MATTER FRAMING DURING INTAKE:\n"
    "- Identify whether the user's story is a deposit_deduction matter "
    "(disputed deductions: cleaning, damage, etc.) or a deposit_non_protection "
    "matter (deposit was never protected in TDS/DPS/MyDeposits). They are "
    "distinct matters with different forums and different remedies.\n"
    "- Stay in legal-information mode. Do not advise the user what to do.\n"
)


HOUSING_DEPOSIT_V1_MEDIATOR_SYSTEM = (
    MEDIATOR_SYSTEM_PROMPT
    + "\n\nDOMAIN GUARD (housing.deposit.v1):\n"
    "- Do not discuss leasehold service charges, building safety, RRO, "
    "ombudsman complaints, or employment matters. Those belong to other "
    "domains.\n"
)


HOUSING_DEPOSIT_V1_PACK = BasePromptPack(
    id="housing.deposit.v1",
    schema_version=1,
    forum_profile_id="deposit_scheme_adjudication",
    intake_system=HOUSING_DEPOSIT_V1_INTAKE_SYSTEM,
    prediction_system=HOUSING_DEPOSIT_V1_PREDICTION_SYSTEM,
    mediator_system=HOUSING_DEPOSIT_V1_MEDIATOR_SYSTEM,
    output_contract=render_output_contract(),
    expected_llm_roles=["intake", "predict", "mediate"],
    safety_version=SAFETY_BLOCK_VERSION,
    cite_or_abstain_version=CITE_OR_ABSTAIN_VERSION,
    output_contract_version=OUTPUT_CONTRACT_VERSION,
    forum_policy_version=FORUM_POLICY_VERSION,
)
