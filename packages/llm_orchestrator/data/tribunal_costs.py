"""
Static UK First-tier Tribunal (Property Chamber) cost data.

Fees sourced from:
- GOV.UK: https://www.gov.uk/courts-tribunals/first-tier-tribunal-property-chamber
- Deposit protection claims are fee-free for tenants under Housing Act 2004 s.214
- Landlord representation costs based on typical UK solicitor rates for property tribunal cases
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TribunalCostComparison(BaseModel):
    """Static cost comparison data for UK First-tier Tribunal (Property Chamber)."""

    # Tenant fees: £0 for deposit protection claims (Housing Act 2004 s.214)
    tenant_costs: int = Field(
        default=0, description="Application fee for tenant (£0 for deposit claims)"
    )

    # Landlord representation costs
    landlord_costs_min: int = Field(
        default=200, description="Minimum typical landlord representation costs (£)"
    )
    landlord_costs_max: int = Field(
        default=500, description="Maximum typical landlord representation costs (£)"
    )

    # Timeline
    timeline_months_min: int = Field(
        default=6, description="Minimum months from application to hearing"
    )
    timeline_months_max: int = Field(
        default=12, description="Maximum months from application to hearing"
    )

    # Qualitative factors
    stress_description: str = Field(
        default="Tribunal proceedings involve formal hearings, document preparation, and waiting periods that can be stressful and time-consuming.",
        description="Description of the stress/time burden of tribunal proceedings",
    )
    risks_of_proceeding: List[str] = Field(
        default=[
            "Outcome is uncertain — tribunals can award any amount from £0 to the full deposit",
            "6-12 month wait before hearing — no money recovered during this period",
            "Must prepare evidence bundles and attend a formal hearing",
            "If landlord wins, tenant receives nothing",
        ],
        description="Key risks of proceeding to tribunal",
    )

    # Role-specific framing text
    party_framing: str = Field(default="", description="Role-specific framing text")


class CostBenefitAnalysis(BaseModel):
    """Complete cost-benefit analysis for a party considering settlement vs tribunal."""

    party_role: str
    tribunal_costs: TribunalCostComparison

    # Settlement option
    settlement_amount: float
    settlement_range_low: float
    settlement_range_high: float
    settlement_framing: str

    # Tribunal option framing
    tribunal_framing: str
    party_framing: str

    # Convenience properties
    @property
    def tenant_costs(self) -> int:
        return self.tribunal_costs.tenant_costs

    @property
    def landlord_costs_min(self) -> int:
        return self.tribunal_costs.landlord_costs_min

    @property
    def landlord_costs_max(self) -> int:
        return self.tribunal_costs.landlord_costs_max

    @property
    def timeline_months_range(self) -> List[int]:
        return [
            self.tribunal_costs.timeline_months_min,
            self.tribunal_costs.timeline_months_max,
        ]


# Static tribunal cost data singleton
_TRIBUNAL_COSTS = TribunalCostComparison()


def get_cost_benefit_analysis(
    role: str,
    prediction_data: Dict[str, Any],
) -> CostBenefitAnalysis:
    """
    Generate a cost-benefit analysis for a party considering settlement vs tribunal.

    Args:
        role: Party role — must be 'tenant' or 'landlord'
        prediction_data: Dict with at minimum 'predicted_settlement_range': [low, high]

    Returns:
        CostBenefitAnalysis with role-specific framing

    Raises:
        ValueError: If role is not 'tenant' or 'landlord'
    """
    if role not in ("tenant", "landlord"):
        raise ValueError(f"Invalid role: '{role}'. Must be 'tenant' or 'landlord'.")

    # Extract settlement range from prediction data. A degraded or "uncertain"
    # prediction may carry no range at all (stored as None) or a list with null
    # bounds, so coerce defensively: drop non-numeric entries and fall back to
    # £0 framing rather than raising. Callers such as the mediation
    # /expectation endpoint must not 500 on an uncertain prediction.
    raw_range = prediction_data.get("predicted_settlement_range")
    numeric_bounds: List[float] = []
    if isinstance(raw_range, (list, tuple)):
        for value in raw_range:
            try:
                numeric_bounds.append(float(value))
            except (TypeError, ValueError):
                continue
    range_low = numeric_bounds[0] if numeric_bounds else 0.0
    range_high = numeric_bounds[1] if len(numeric_bounds) > 1 else range_low
    suggested_amount = (range_low + range_high) / 2

    # Build role-specific framing
    if role == "tenant":
        settlement_framing = (
            f"You would likely recover between £{range_low:.0f} and £{range_high:.0f} "
            f"without the stress and delay of tribunal proceedings. "
            f"Settlement means you get money now — not in 6-12 months."
        )
        tribunal_framing = (
            f"If you proceed to tribunal, you pay £0 in application fees. "
            f"However, you'll wait 6-12 months and the outcome is uncertain — "
            f"the tribunal could award anywhere from £0 to the full deposit amount."
        )
        party_framing = (
            f"Based on similar cases, you would likely recover around £{suggested_amount:.0f}. "
            f"Here's what each path looks like for you:"
        )
    else:  # landlord
        settlement_framing = (
            f"A settlement of £{suggested_amount:.0f} would resolve this dispute now. "
            f"Going to tribunal typically costs landlords £{_TRIBUNAL_COSTS.landlord_costs_min}–"
            f"£{_TRIBUNAL_COSTS.landlord_costs_max} in representation costs, "
            f"plus 6-12 months of uncertainty."
        )
        tribunal_framing = (
            f"If you proceed to tribunal, expect to pay £{_TRIBUNAL_COSTS.landlord_costs_min}–"
            f"£{_TRIBUNAL_COSTS.landlord_costs_max} in representation costs and wait 6-12 months. "
            f"In similar cases, you would likely pay back £{range_low:.0f}–£{range_high:.0f}."
        )
        party_framing = (
            f"Based on similar cases, you would likely pay back around £{suggested_amount:.0f}. "
            f"Here's what each path looks like for you:"
        )

    tribunal_costs = TribunalCostComparison(party_framing=party_framing)

    return CostBenefitAnalysis(
        party_role=role,
        tribunal_costs=tribunal_costs,
        settlement_amount=suggested_amount,
        settlement_range_low=range_low,
        settlement_range_high=range_high,
        settlement_framing=settlement_framing,
        tribunal_framing=tribunal_framing,
        party_framing=party_framing,
    )
