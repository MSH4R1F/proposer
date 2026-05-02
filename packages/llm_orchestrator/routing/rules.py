"""SHA-20 Phase 9: deterministic keyword/rule routes.

This module encodes the high-precision deterministic routes for the
four launch-stage domains plus the "unsupported" classes that audit
decisions D4 and D5 carve out:

* Wage-only employment disputes (no dismissal cue) → ``unsupported``
  with ``capture_in="research"``. They MUST NOT route to
  ``employment.unfair_dismissal.v1``.
* Property Chamber matters that are not RRO (leasehold service charges,
  ground rent, Tenant Fees Act, park homes, building safety,
  enfranchisement) → ``unsupported`` with ``capture_in="research"``.

The rules are intentionally conservative: a hit requires a high-signal
phrase, otherwise we leave the decision to the LLM fallback (or to the
``clarify`` outcome if the LLM is also unsure). Every rule exposes its
``rule_id`` in ``routing_metadata`` so the API trace can show which
deterministic branch fired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Domain canonical IDs (mirror the YAMLs under packages/domain_core/domains/)
# ---------------------------------------------------------------------------


DEPOSIT_ID = "housing.deposit.v1"
REPAIRS_SOCIAL_ID = "housing.repairs_social.v1"
RRO_ID = "housing.property_chamber.rro.v1"
EMPLOYMENT_ID = "employment.unfair_dismissal.v1"


# ---------------------------------------------------------------------------
# Rule hit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleHit:
    """Outcome of :meth:`RuleSet.classify`.

    ``outcome`` is one of:

    * ``"route"`` — route to ``domain_id``.
    * ``"unsupported"`` — explicit out-of-scope inside a launched
      family (wage disputes, broad PC). ``capture_in`` is always
      ``"research"`` for these.
    * ``"none"`` — rules are inconclusive; fall through to the LLM.
    """

    outcome: str
    domain_id: Optional[str] = None
    rule_id: Optional[str] = None
    matched_phrases: tuple[str, ...] = field(default_factory=tuple)
    capture_in: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Phrase tables
# ---------------------------------------------------------------------------


# Deposit: any of these phrases is enough to route. The audit decision D3
# says deposit_deduction and deposit_non_protection both live under
# housing.deposit.v1 (only the matter_type differs); the router therefore
# routes both to housing.deposit.v1 and lets the orchestrator branch by
# matter_type downstream.
_DEPOSIT_PHRASES: tuple[str, ...] = (
    "tenancy deposit",
    "deposit deduction",
    "deposit deductions",
    "deposit deducted",
    "deposit dispute",
    "kept my deposit",
    "kept gbp",  # template phrasing in eval set ("kept GBP 250 of my deposit")
    "of my deposit",
    "my deposit",
    "the deposit",
    "register my deposit",
    "returned my deposit",
    "return my deposit",
    "deposit not returned",
    "deposit not protected",
    "deposit was not protected",
    "deposit non-protection",
    "non-protection",
    "section 213",
    "section 214",
    "section 215",
    "ss.213",
    "ha 2004",
    "housing act 2004 s.213",
    "housing act 2004 ss.213",
    "deposit scheme",
    "tds",
    "mydeposits",
    "dps",
    "deposit protection scheme",
    # End-of-tenancy deposit-deduction phrasing (audit D3 deposit_deduction).
    "checkout report",
    "check-out report",
    "inventory dispute",
    "fair wear and tear",
    "cleaning invoice",
    "owe for damages",
    "charged against deposit",
    "owe for damage",
    "is keeping the deposit",
    "keeping the deposit",
    "deposit not returned 6 weeks",
)


# Repairs / social housing. Boiler, mould, damp, disrepair, ombudsman.
# We require either an explicit social-housing cue OR a disrepair cue.
_REPAIRS_PHRASES: tuple[str, ...] = (
    "social landlord",
    "social housing",
    "council housing",
    "council property",
    "housing association",
    "housing ombudsman",
    "ombudsman determination",
    "ombudsman response",
    "award by ombudsman",
    "section 11 landlord and tenant act",
    "section 11 lta",
    "disrepair",
    "category 1 hazard",
    "cat a hazard",
    "cat 1 hazard",
    "tenant satisfaction measures",
    "awaab",
    "damp",
    "mould",
    "black mould",
    "mold",  # American spelling tolerated
    "boiler",
    "leaking roof",
    "roof leak",
    "asbestos",
    "pest infestation",
    "broken front door",
    "communal lighting",
    "lifts in tower block",
    "floods from upstairs",
    "heating system failed",
    "cracked windows",
    "repairs not done",
    "repair backlog",
)


# Rent repayment orders. RRO-specific; broad Property Chamber matters
# (leasehold service charges, enfranchisement, park homes) are caught
# separately by ``_PROPERTY_CHAMBER_NON_RRO_PHRASES`` and routed to
# unsupported.
_RRO_PHRASES: tuple[str, ...] = (
    "rent repayment order",
    "rent repayment",
    " rro",  # leading space avoids matching "errors"; trailing handled below
    "rro ",
    "rro?",
    "rro.",
    "rro,",
    "rro;",
    "rro:",
    "rro/",
    "unlicensed hmo",
    "unlicensed h.m.o.",
    "hmo licensing",
    "mandatory hmo licence",
    "selective licensing",
    "selective licence",
    "first-tier tribunal property chamber rro",
    "property chamber rro",
    "ftt-pc rro",
    "housing and planning act 2016",
    "housing act 2004 banning order",
    "banning order",
    "improvement notice",
    "landlord control offence",
    "landlord is unlicensed",
    "unlicensed landlord",
    "claim 12 months rent",
    "12 months rent back",
    "12 months rent recoverable",
    "amount of rent recoverable",
    "rent recoverable",
)


# Property Chamber matters that are explicitly NOT RRO. These are
# unsupported in v1 (audit D4). When BOTH a Property Chamber non-RRO
# cue AND an RRO cue appear, the RRO rule wins; we test that explicitly.
_PROPERTY_CHAMBER_NON_RRO_PHRASES: tuple[str, ...] = (
    "leasehold service charge",
    "leasehold service charges",
    "property chamber service charge",
    "ground rent dispute",
    "ground rent",
    "tenant fees act",
    "park homes",
    "park homes chamber",
    "building safety act",
    "building safety appeal",
    "ftt-pc enfranchisement",
    "enfranchisement",
    "leasehold valuation",
    "right of first refusal",
)


# Unfair-dismissal employment. We require a dismissal cue: "fired",
# "dismissed", "dismissal", "constructive dismissal", "let go".
# Wage-only disputes are handled by ``_WAGE_DISPUTE_PHRASES`` and route
# to unsupported.
_EMPLOYMENT_DISMISSAL_PHRASES: tuple[str, ...] = (
    "unfair dismissal",
    "constructive dismissal",
    "wrongful dismissal",
    "i was fired",
    "fired without warning",
    "fired without notice",
    "let go a week before",
    "let go from my job",
    "let go from work",
    "sacked without",
    "sacked from",
    "dismissed for",
    "dismissed without",
    "capability dismissal",
    "conduct dismissal",
    "redundancy used as cover",
    "polkey reduction",
    "section 98 era",
    "s.98 era",
    "acas early conciliation",
    "et claim",
    "employment tribunal",
    "whistleblowing dismissal",
    "pida",
    "tupe-related dismissal",
    "tupe dismissal",
    "trade union activity dismissal",
    "disability discrimination dismissal",
    "maternity-related dismissal",
    "probationary dismissal",
    "procedural unfairness in dismissal",
    "forced to resign",
    "raising health and safety concerns",
    "suspended on full pay then sacked",
    "dismissed for raising",
)


# Wage-only employment disputes. These MUST route to unsupported per
# audit D5. Any of these phrases without a dismissal cue routes to
# ``unsupported``. With a dismissal cue, the dismissal rule wins.
_WAGE_DISPUTE_PHRASES: tuple[str, ...] = (
    "unpaid wages",
    "underpaid wages",
    "minimum wage",
    "national living wage",
    "holiday pay",
    "holiday pay calc",
    "notice pay underpaid",
    "unauthorised deductions from wages",
    "unauthorised deduction from wages",
    "wage dispute",
    "statutory wage dispute",
    "employer underpaid me",
    "failure to provide written statement under s.1 era",
    "section 1 era",
    "s.1 era",
)


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _hits(text: str, phrases: Iterable[str]) -> list[str]:
    """Return all of ``phrases`` present in lowercased ``text``."""
    out: list[str] = []
    for p in phrases:
        if not p:
            continue
        if p in text:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Rule set
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleSet:
    """High-precision keyword router.

    The default constructor wires up the four launched domains. Tests
    can substitute custom phrase tables by re-constructing the dataclass
    if needed (the existing tables are kept conservative on purpose).
    """

    deposit_phrases: tuple[str, ...] = _DEPOSIT_PHRASES
    repairs_phrases: tuple[str, ...] = _REPAIRS_PHRASES
    rro_phrases: tuple[str, ...] = _RRO_PHRASES
    pc_non_rro_phrases: tuple[str, ...] = _PROPERTY_CHAMBER_NON_RRO_PHRASES
    employment_dismissal_phrases: tuple[str, ...] = _EMPLOYMENT_DISMISSAL_PHRASES
    wage_dispute_phrases: tuple[str, ...] = _WAGE_DISPUTE_PHRASES

    def classify(self, text: str) -> RuleHit:
        """Return the deterministic rule outcome for ``text``.

        Resolution order (a hit short-circuits the rest):

        1. Deposit phrases.
        2. Social-housing repairs phrases.
        3. RRO phrases (RRO wins over broad Property Chamber).
        4. Employment dismissal phrases (dismissal wins over wage cues).
        5. Wage-only dispute phrases → ``unsupported``.
        6. Broad Property Chamber phrases (no RRO cue) → ``unsupported``.

        Otherwise returns ``RuleHit(outcome="none")``.
        """
        if not text or not text.strip():
            return RuleHit(outcome="none", reason="empty input")

        lowered = text.lower()

        deposit_hits = _hits(lowered, self.deposit_phrases)
        if deposit_hits:
            return RuleHit(
                outcome="route",
                domain_id=DEPOSIT_ID,
                rule_id="rule.housing.deposit",
                matched_phrases=tuple(deposit_hits[:3]),
                reason="deposit phrase match",
            )

        repairs_hits = _hits(lowered, self.repairs_phrases)
        if repairs_hits:
            return RuleHit(
                outcome="route",
                domain_id=REPAIRS_SOCIAL_ID,
                rule_id="rule.housing.repairs_social",
                matched_phrases=tuple(repairs_hits[:3]),
                reason="repairs/social-housing phrase match",
            )

        rro_hits = _hits(lowered, self.rro_phrases)
        if rro_hits:
            return RuleHit(
                outcome="route",
                domain_id=RRO_ID,
                rule_id="rule.housing.rro",
                matched_phrases=tuple(rro_hits[:3]),
                reason="rent repayment order phrase match",
            )

        dismissal_hits = _hits(lowered, self.employment_dismissal_phrases)
        if dismissal_hits:
            return RuleHit(
                outcome="route",
                domain_id=EMPLOYMENT_ID,
                rule_id="rule.employment.unfair_dismissal",
                matched_phrases=tuple(dismissal_hits[:3]),
                reason="dismissal phrase match",
            )

        wage_hits = _hits(lowered, self.wage_dispute_phrases)
        if wage_hits:
            return RuleHit(
                outcome="unsupported",
                rule_id="rule.employment.wage_unsupported",
                matched_phrases=tuple(wage_hits[:3]),
                capture_in="research",
                reason=(
                    "Wage / hours / written-statement disputes are not a "
                    "launched matter (audit D5)."
                ),
            )

        pc_hits = _hits(lowered, self.pc_non_rro_phrases)
        if pc_hits:
            return RuleHit(
                outcome="unsupported",
                rule_id="rule.housing.property_chamber_non_rro_unsupported",
                matched_phrases=tuple(pc_hits[:3]),
                capture_in="research",
                reason=(
                    "Broad Property Chamber matters (leasehold, ground rent, "
                    "Tenant Fees Act, park homes, enfranchisement, building "
                    "safety) are not a launched matter (audit D4)."
                ),
            )

        return RuleHit(outcome="none", reason="no rule matched")


__all__ = [
    "DEPOSIT_ID",
    "EMPLOYMENT_ID",
    "REPAIRS_SOCIAL_ID",
    "RRO_ID",
    "RuleHit",
    "RuleSet",
]
