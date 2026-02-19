"""
CaseFile - Central data structure for the mediation system.

This model flows through the entire system:
Intake -> Knowledge Graph -> RAG Retrieval -> Prediction
"""

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field


class PartyRole(str, Enum):
    """Role of the user in the dispute."""

    TENANT = "tenant"
    LANDLORD = "landlord"


class DisputeIssue(str, Enum):
    """Types of issues in a tenancy deposit dispute."""

    CLEANING = "cleaning"
    DAMAGE = "damage"
    RENT_ARREARS = "rent_arrears"
    DEPOSIT_PROTECTION = "deposit_protection"
    INVENTORY_DISPUTE = "inventory_dispute"
    GARDEN_MAINTENANCE = "garden"
    DECORATION = "decoration"
    FAIR_WEAR_AND_TEAR = "fair_wear_and_tear"
    MISSING_ITEMS = "missing_items"
    UTILITIES = "utilities"
    OTHER = "other"


class EvidenceType(str, Enum):
    """Types of evidence that can be submitted."""

    INVENTORY_CHECKIN = "inventory_checkin"
    INVENTORY_CHECKOUT = "inventory_checkout"
    PHOTOS_BEFORE = "photos_before"
    PHOTOS_AFTER = "photos_after"
    RECEIPTS = "receipts"
    INVOICES = "invoices"
    CORRESPONDENCE = "correspondence"
    TENANCY_AGREEMENT = "tenancy_agreement"
    DEPOSIT_CERTIFICATE = "deposit_certificate"
    WITNESS_STATEMENT = "witness_statement"
    OTHER = "other"


class EvidenceItem(BaseModel):
    """A piece of evidence uploaded or described by the user."""

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    type: EvidenceType
    description: str
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None  # MIME type
    extracted_text: Optional[str] = None
    image_description: Optional[str] = None
    date_created: Optional[date] = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: str = Field(default="user_input")  # user_input, uploaded, inferred


class ClaimedAmount(BaseModel):
    """An amount claimed by a party for a specific issue."""

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    issue: DisputeIssue
    amount: float = Field(..., ge=0)
    description: str
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class PropertyDetails(BaseModel):
    """Details about the rental property."""

    address: Optional[str] = None
    postcode: Optional[str] = None
    property_type: Optional[str] = None  # flat, house, HMO, room
    num_bedrooms: Optional[int] = None
    furnished: Optional[bool] = None
    region: Optional[str] = None  # Tribunal region code (LON, MAN, BIR, etc.)

    def infer_region(self) -> Optional[str]:
        """Infer tribunal region from postcode."""
        if not self.postcode:
            return None

        postcode_upper = self.postcode.upper().strip()

        # London postcodes
        london_prefixes = [
            "E",
            "EC",
            "N",
            "NW",
            "SE",
            "SW",
            "W",
            "WC",
            "BR",
            "CR",
            "DA",
            "EN",
            "HA",
            "IG",
            "KT",
            "RM",
            "SM",
            "TW",
            "UB",
            "WD",
        ]
        for prefix in london_prefixes:
            if postcode_upper.startswith(prefix):
                return "LON"

        # Manchester area
        manchester_prefixes = ["M", "OL", "SK", "WA", "WN", "BL", "PR", "L"]
        for prefix in manchester_prefixes:
            if postcode_upper.startswith(prefix):
                return "MAN"

        # Birmingham area
        birmingham_prefixes = ["B", "CV", "DY", "WS", "WV"]
        for prefix in birmingham_prefixes:
            if postcode_upper.startswith(prefix):
                return "BIR"

        # Cambridge/Eastern
        cambridge_prefixes = ["CB", "CO", "IP", "NR", "PE"]
        for prefix in cambridge_prefixes:
            if postcode_upper.startswith(prefix):
                return "CAM"

        # Chichester/Southern
        return "CHI"  # Default fallback

        ## TODO: addd a better way to infer region from postcode


class TenancyDetails(BaseModel):
    """Details about the tenancy agreement."""

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    tenancy_type: Optional[str] = None  # AST, periodic, etc.
    monthly_rent: Optional[float] = None
    deposit_amount: Optional[float] = None
    deposit_protected: Optional[bool] = None
    deposit_scheme: Optional[str] = None  # TDS, DPS, MyDeposits
    protection_date: Optional[date] = None
    prescribed_info_provided: Optional[bool] = None
    prescribed_info_date: Optional[date] = None

    def deposit_protection_valid(self) -> Optional[bool]:
        """Check if deposit was protected within 30 days."""
        if self.start_date and self.protection_date:
            days_to_protect = (self.protection_date - self.start_date).days
            return days_to_protect <= 30
        return None


class CaseFile(BaseModel):
    """
    Complete case file populated during intake.

    This is the central data structure that flows through
    the entire system: Intake -> KG -> RAG -> Prediction.
    """

    case_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    user_role: PartyRole
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Parties
    tenant_name: Optional[str] = None
    landlord_name: Optional[str] = None
    agent_name: Optional[str] = None  # Letting agent if applicable
    multiple_tenants: bool = False
    num_tenants: int = 1

    # Property and tenancy
    property: PropertyDetails = Field(default_factory=PropertyDetails)
    tenancy: TenancyDetails = Field(default_factory=TenancyDetails)

    # Dispute details
    issues: List[DisputeIssue] = Field(default_factory=list)
    dispute_amount: Optional[float] = None  # Total amount in dispute
    tenant_claims: List[ClaimedAmount] = Field(default_factory=list)
    landlord_claims: List[ClaimedAmount] = Field(default_factory=list)

    # Evidence
    evidence: List[EvidenceItem] = Field(default_factory=list)

    # Narrative (free-form description from user)
    tenant_narrative: Optional[str] = None
    landlord_narrative: Optional[str] = None

    # Timeline of key events
    events: List[Dict[str, Any]] = Field(default_factory=list)

    # Intake progress
    intake_complete: bool = False
    completeness_score: float = Field(default=0.0, ge=0, le=1)
    missing_info: List[str] = Field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()

    def add_evidence(self, evidence: EvidenceItem) -> None:
        """Add evidence item to the case."""
        self.evidence.append(evidence)
        self.update_timestamp()

    def add_claim(self, claim: ClaimedAmount, claimant: PartyRole) -> None:
        """Add a claimed amount to the appropriate party's claims."""
        if claimant == PartyRole.TENANT:
            self.tenant_claims.append(claim)
        else:
            self.landlord_claims.append(claim)
        self.update_timestamp()

    def get_total_tenant_claims(self) -> float:
        """Get total amount claimed by tenant."""
        return sum(c.amount for c in self.tenant_claims)

    def get_total_landlord_claims(self) -> float:
        """Get total amount claimed by landlord."""
        return sum(c.amount for c in self.landlord_claims)

    def calculate_completeness(self) -> float:
        """
        Calculate how complete the case file is.

        Returns a score between 0 and 1.
        """
        required_checks = [
            len(self.issues) > 0,
        ]
        required_score = sum(required_checks) / len(required_checks) * 0.3

        recommended_checks = [
            self.property.address is not None,
            self.tenancy.start_date is not None,
            self.tenancy.deposit_amount is not None,
            self.tenancy.deposit_protected is not None,
        ]
        recommended_score = sum(recommended_checks) / len(recommended_checks) * 0.4

        optional_checks = [
            len(self.evidence) > 0,
            len(self.tenant_claims) > 0 or len(self.landlord_claims) > 0,
            self.tenant_narrative is not None or self.landlord_narrative is not None,
            self.tenancy.end_date is not None,
            self.property.postcode is not None,
        ]
        optional_score = sum(optional_checks) / len(optional_checks) * 0.3

        self.completeness_score = required_score + recommended_score + optional_score
        return self.completeness_score

    def get_missing_required_info(self) -> List[str]:
        missing = []
        if not self.issues:
            missing.append("dispute issues")

        self.missing_info = missing
        return missing

    def get_missing_recommended_info(self) -> List[str]:
        missing = []
        if not self.property.address:
            missing.append("property address")
        if not self.tenancy.start_date:
            missing.append("tenancy start date")
        if not self.tenancy.deposit_amount:
            missing.append("deposit amount")
        if self.tenancy.deposit_protected is None:
            missing.append("deposit protection status")
        return missing

    def has_all_required_info(self) -> bool:
        return len(self.get_missing_required_info()) == 0

    def is_ready_for_prediction(self) -> bool:
        return self.has_all_required_info()

    def get_data_quality_tier(self) -> str:
        """
        Classify how much data the case file has for prediction quality.

        Returns 'insufficient', 'minimal', 'partial', or 'full'.
        Cases with >= 50% completeness can still generate predictions
        at 'minimal' or 'partial' quality.
        """
        self.calculate_completeness()

        if self.completeness_score < 0.5:
            return "insufficient"

        if not self.has_all_required_info():
            return "minimal"

        recommended_missing = self.get_missing_recommended_info()
        if len(recommended_missing) == 0:
            return "full"
        if len(recommended_missing) <= 2:
            return "partial"
        return "minimal"

    def to_query_string(self) -> str:
        """
        Convert case file to a query string for RAG retrieval.

        Combines key facts into a searchable string.
        """
        parts = []

        # Add issues
        for issue in self.issues:
            parts.append(issue.value.replace("_", " "))

        # Add deposit protection status
        if self.tenancy.deposit_protected is False:
            parts.append("deposit not protected section 213")

        # Add key amounts
        if self.tenancy.deposit_amount:
            parts.append(f"deposit {self.tenancy.deposit_amount}")

        # Add narrative summary (truncated)
        narrative = self.tenant_narrative or self.landlord_narrative
        if narrative:
            # Take first 300 chars of narrative
            parts.append(narrative[:300])

        # Add evidence types mentioned
        evidence_types = set(e.type.value for e in self.evidence)
        if (
            "inventory_checkin" in evidence_types
            or "inventory_checkout" in evidence_types
        ):
            parts.append("inventory")
        if "photos_before" in evidence_types or "photos_after" in evidence_types:
            parts.append("photographs evidence")

        return " ".join(parts)

    model_config = {"use_enum_values": False}
