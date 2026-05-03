"""Tests for SHA-126 RRO statutory-grounds filter."""

from __future__ import annotations

import pytest

from scripts.scrapers.govuk_property_tribunal.config import RRO_SUB_CATEGORY
from scripts.scrapers.govuk_property_tribunal.filter import classify_rro
from scripts.scrapers.govuk_property_tribunal.models import (
    FilterDecision,
    GovUKSearchHit,
)


def _hit(*, sub_category_match: bool = True, title: str = "RRO Decision") -> GovUKSearchHit:
    return GovUKSearchHit(
        title=title,
        link="/residential-property-tribunal-decisions/example",
        sub_categories=[RRO_SUB_CATEGORY] if sub_category_match else ["other-cat"],
    )


# ---------------------------------------------------------------------------
# POSITIVE fixtures: each statutory ground branch
# ---------------------------------------------------------------------------


POSITIVE_BODIES = [
    (
        "hmo_s72_1",
        "The respondent committed an offence under section 72(1) of the Housing Act 2004 by "
        "having control of an HMO that was required to be licensed but was not licensed.",
        "Housing Act 2004 s.72(1) (unlicensed HMO)",
    ),
    (
        "selective_s95",
        "The applicants seek a rent repayment order under s.95 of the Housing Act 2004 "
        "in respect of a selective licensing area.",
        "Housing Act 2004 s.95 (selective licensing)",
    ),
    (
        "improvement_s30",
        "Failure to comply with an improvement notice constitutes an offence under "
        "section 30 of the Housing Act 2004.",
        "Housing Act 2004 s.30 (improvement notice failure)",
    ),
    (
        "prohibition_s32",
        "The landlord failed to comply with a prohibition order, contrary to s.32 of the "
        "Housing Act 2004.",
        "Housing Act 2004 s.32 (prohibition order failure)",
    ),
    (
        "pea_s12",
        "The tenant was unlawfully evicted contrary to section 1(2) of the Protection from "
        "Eviction Act 1977.",
        "Protection from Eviction Act 1977 s.1(2)",
    ),
    (
        "pea_s13",
        "Harassment under section 1(3) of the Protection from Eviction Act 1977 was made out.",
        "Protection from Eviction Act 1977 s.1(3)",
    ),
    (
        "pea_s13a",
        "We find that the landlord committed an offence under s.1(3A) of the Protection from "
        "Eviction Act 1977.",
        "Protection from Eviction Act 1977 s.1(3A)",
    ),
    (
        "cla_s6",
        "The landlord used violence to enter the property contrary to section 6 of the "
        "Criminal Law Act 1977.",
        "Criminal Law Act 1977 s.6 (violence for securing entry)",
    ),
    (
        "hpa_s40",
        "An RRO is sought under section 41 of the Housing and Planning Act 2016.",
        "Housing and Planning Act 2016 ss.40-52 (RRO regime)",
    ),
    (
        "hpa_s21_banning",
        "The respondent breached a banning order contrary to section 21 of the Housing and "
        "Planning Act 2016.",
        "Housing and Planning Act 2016 s.21 (banning order breach)",
    ),
    (
        "ha1988_s16j",
        "The tribunal considered the new offence under s.16J of the Housing Act 1988 as "
        "introduced by the Renters' Rights Act 2025.",
        "Housing Act 1988 s.16J (Renters' Rights Act 2025)",
    ),
]


@pytest.mark.parametrize("name,body,ground", POSITIVE_BODIES, ids=[p[0] for p in POSITIVE_BODIES])
def test_filter_accepts_known_grounds(name, body, ground):
    decision, grounds, reasons = classify_rro(_hit(), body)
    assert decision == FilterDecision.ACCEPT, (name, reasons)
    assert ground in grounds, (name, grounds)
    assert reasons == []


# ---------------------------------------------------------------------------
# NEGATIVE fixtures: hard rejects + non-RRO categories
# ---------------------------------------------------------------------------


NEGATIVE_BODIES = [
    (
        "leasehold_service_charge",
        "The applicants challenge service charges levied under the lease.",
        "hard_reject:service_charge",
    ),
    (
        "ground_rent",
        "The application concerns ground rent demands of £250 per annum.",
        "hard_reject:ground_rent",
    ),
    (
        "tenant_fees_act",
        "The landlord allegedly took prohibited payments contrary to the Tenant Fees Act 2019.",
        "hard_reject:tenant_fees_act",
    ),
    (
        "building_safety",
        "Remediation contribution order under the Building Safety Act 2022.",
        "hard_reject:building_safety",
    ),
    (
        "park_home",
        "Application for a determination of pitch fees in a park home site.",
        "hard_reject:park_home",
    ),
]


@pytest.mark.parametrize("name,body,reason", NEGATIVE_BODIES, ids=[p[0] for p in NEGATIVE_BODIES])
def test_filter_hard_rejects(name, body, reason):
    decision, grounds, reasons = classify_rro(_hit(), body)
    assert decision == FilterDecision.REJECT, (name, decision)
    assert reason in reasons, (name, reasons)
    assert grounds == []


def test_filter_rejects_civil_penalty_without_rro():
    body = (
        "The local housing authority imposed a civil financial penalty of £5,000 on the "
        "landlord. This appeal concerns the level of that penalty only."
    )
    decision, grounds, reasons = classify_rro(_hit(), body)
    assert decision == FilterDecision.UNCERTAIN
    assert "ground_not_recognised" in reasons
    assert grounds == []


def test_filter_rejects_when_subcategory_missing():
    body = "Section 72(1) of the Housing Act 2004 was made out."
    decision, _grounds, reasons = classify_rro(_hit(sub_category_match=False), body)
    assert decision == FilterDecision.REJECT
    assert "sub_category_not_rro" in reasons


def test_filter_accepts_when_live_search_omits_subcategories():
    body = "Section 72(1) of the Housing Act 2004 was made out."
    hit = GovUKSearchHit(
        title="RRO decision",
        link="/residential-property-tribunal-decisions/example",
        sub_categories=[],
    )
    decision, grounds, reasons = classify_rro(hit, body)
    assert decision == FilterDecision.ACCEPT
    assert grounds
    assert reasons == []


def test_filter_uncertain_on_empty_body():
    decision, grounds, reasons = classify_rro(_hit(), "")
    assert decision == FilterDecision.UNCERTAIN
    assert grounds == []
    assert "no_body_text" in reasons
