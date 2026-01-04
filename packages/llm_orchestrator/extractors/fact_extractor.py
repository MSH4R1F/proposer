"""
Fact extraction from conversation messages.

Uses LLM to extract structured facts from user messages
and update the case file.
"""

import json
from datetime import date
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

from ..clients.base import BaseLLMClient
from ..models.case_file import (
    CaseFile,
    DisputeIssue,
    EvidenceItem,
    EvidenceType,
    ClaimedAmount,
    PartyRole,
)
from ..models.conversation import IntakeStage
from ..prompts.extraction import (
    FACT_EXTRACTION_PROMPT,
    FACT_EXTRACTION_CONTEXT,
    STAGE_EXTRACTION_FOCUS,
)

logger = structlog.get_logger()


class ExtractionResult(BaseModel):
    """Result of fact extraction from a message."""
    updated_case_file: CaseFile
    extracted_facts: Dict[str, Any] = Field(default_factory=dict)
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    no_new_info: bool = False
    extraction_notes: List[str] = Field(default_factory=list)


class FactExtractor:
    """
    Extracts structured facts from conversation messages.

    Uses an LLM to parse natural language into structured
    data that updates the case file.
    """

    def __init__(self, llm_client: BaseLLMClient):
        """
        Initialize the fact extractor.

        Args:
            llm_client: LLM client for extraction
        """
        self.llm = llm_client

    async def extract_facts(
        self,
        user_message: str,
        case_file: CaseFile,
        current_stage: IntakeStage,
    ) -> ExtractionResult:
        """
        Extract facts from a user message and update the case file.

        Args:
            user_message: The user's message to extract from
            case_file: Current state of the case file
            current_stage: Current conversation stage

        Returns:
            ExtractionResult with updated case file
        """
        # Build context for extraction
        case_summary = self._summarize_case_file(case_file)
        stage_focus = STAGE_EXTRACTION_FOCUS.get(
            current_stage.value,
            "any relevant information about the dispute"
        )

        context = FACT_EXTRACTION_CONTEXT.format(
            case_file_summary=case_summary,
            current_stage=current_stage.value,
            user_message=user_message,
            stage_focus=stage_focus,
        )

        # Call LLM for extraction
        try:
            response = await self.llm.generate(
                messages=[{"role": "user", "content": context}],
                system_prompt=FACT_EXTRACTION_PROMPT,
                max_tokens=2048,
                temperature=0.2,  # Low temperature for consistent extraction
            )

            # Parse the response
            extracted = self._parse_extraction_response(response)

            if extracted.get("no_new_info", False):
                logger.debug("no_new_facts_extracted", stage=current_stage.value)
                return ExtractionResult(
                    updated_case_file=case_file,
                    no_new_info=True,
                )

            # Update case file with extracted facts
            updated_case_file, confidence_scores = self._apply_extractions(
                case_file, extracted
            )

            logger.info(
                "facts_extracted",
                stage=current_stage.value,
                num_facts=len(extracted),
                confidence_avg=sum(confidence_scores.values()) / len(confidence_scores)
                if confidence_scores else 0,
            )

            return ExtractionResult(
                updated_case_file=updated_case_file,
                extracted_facts=extracted,
                confidence_scores=confidence_scores,
            )

        except Exception as e:
            logger.error("fact_extraction_failed", error=str(e))
            return ExtractionResult(
                updated_case_file=case_file,
                extraction_notes=[f"Extraction error: {str(e)}"],
            )

    def _summarize_case_file(self, case_file: CaseFile) -> str:
        """Create a summary of the current case file state."""
        parts = [f"Role: {case_file.user_role.value}"]

        if case_file.property.address:
            parts.append(f"Property: {case_file.property.address}")

        if case_file.tenancy.start_date:
            parts.append(f"Tenancy start: {case_file.tenancy.start_date}")

        if case_file.tenancy.end_date:
            parts.append(f"Tenancy end: {case_file.tenancy.end_date}")

        if case_file.tenancy.deposit_amount:
            parts.append(f"Deposit: £{case_file.tenancy.deposit_amount}")

        if case_file.tenancy.deposit_protected is not None:
            status = "protected" if case_file.tenancy.deposit_protected else "NOT protected"
            parts.append(f"Deposit: {status}")

        if case_file.issues:
            issues_str = ", ".join(i.value for i in case_file.issues)
            parts.append(f"Issues: {issues_str}")

        if case_file.evidence:
            evidence_str = ", ".join(e.type.value for e in case_file.evidence)
            parts.append(f"Evidence: {evidence_str}")

        return "\n".join(parts) if parts else "No information collected yet."

    def _parse_extraction_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM extraction response."""
        try:
            # Try to find JSON in the response
            response = response.strip()

            # Handle markdown code blocks
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            return json.loads(response)

        except json.JSONDecodeError:
            logger.warning("failed_to_parse_extraction_json", response_preview=response[:200])
            return {"no_new_info": True}

    def _apply_extractions(
        self, case_file: CaseFile, extracted: Dict[str, Any]
    ) -> tuple[CaseFile, Dict[str, float]]:
        """Apply extracted facts to the case file."""
        confidence_scores: Dict[str, float] = {}

        # Update property details
        if "property" in extracted:
            prop = extracted["property"]
            if "address" in prop:
                case_file.property.address = self._get_value(prop["address"])
                confidence_scores["property.address"] = self._get_confidence(prop["address"])

            if "postcode" in prop:
                case_file.property.postcode = self._get_value(prop["postcode"])
                confidence_scores["property.postcode"] = self._get_confidence(prop["postcode"])

            if "property_type" in prop:
                case_file.property.property_type = self._get_value(prop["property_type"])

            if "num_bedrooms" in prop:
                case_file.property.num_bedrooms = self._get_value(prop["num_bedrooms"])

            if "furnished" in prop:
                case_file.property.furnished = self._get_value(prop["furnished"])

            # Try to infer region from postcode
            if case_file.property.postcode and not case_file.property.region:
                case_file.property.region = case_file.property.infer_region()

        # Update tenancy details
        if "tenancy" in extracted:
            ten = extracted["tenancy"]

            if "start_date" in ten:
                date_str = self._get_value(ten["start_date"])
                case_file.tenancy.start_date = self._parse_date(date_str)

            if "end_date" in ten:
                date_str = self._get_value(ten["end_date"])
                case_file.tenancy.end_date = self._parse_date(date_str)

            if "monthly_rent" in ten:
                case_file.tenancy.monthly_rent = self._get_value(ten["monthly_rent"])

            if "deposit_amount" in ten:
                case_file.tenancy.deposit_amount = self._get_value(ten["deposit_amount"])
                confidence_scores["tenancy.deposit_amount"] = self._get_confidence(ten["deposit_amount"])

            if "deposit_protected" in ten:
                case_file.tenancy.deposit_protected = self._get_value(ten["deposit_protected"])
                confidence_scores["tenancy.deposit_protected"] = self._get_confidence(ten["deposit_protected"])

            if "deposit_scheme" in ten:
                case_file.tenancy.deposit_scheme = self._get_value(ten["deposit_scheme"])

            if "protection_date" in ten:
                date_str = self._get_value(ten["protection_date"])
                case_file.tenancy.protection_date = self._parse_date(date_str)

            if "prescribed_info_provided" in ten:
                case_file.tenancy.prescribed_info_provided = self._get_value(ten["prescribed_info_provided"])

        # Update issues
        if "issues" in extracted:
            for issue_data in extracted["issues"]:
                issue_type_str = issue_data.get("issue_type", "").lower().replace(" ", "_")
                try:
                    issue_type = DisputeIssue(issue_type_str)
                    if issue_type not in case_file.issues:
                        case_file.issues.append(issue_type)
                except ValueError:
                    # Try to map common variations
                    issue_type = self._map_issue_type(issue_type_str)
                    if issue_type and issue_type not in case_file.issues:
                        case_file.issues.append(issue_type)

        # Update evidence
        if "evidence" in extracted:
            for ev_data in extracted["evidence"]:
                ev_type_str = ev_data.get("evidence_type", "").lower().replace(" ", "_")
                try:
                    ev_type = EvidenceType(ev_type_str)
                    # Check if this evidence type already exists
                    if not any(e.type == ev_type for e in case_file.evidence):
                        evidence = EvidenceItem(
                            type=ev_type,
                            description=ev_data.get("description", ""),
                            confidence=ev_data.get("confidence", 0.8),
                        )
                        case_file.evidence.append(evidence)
                except ValueError:
                    ev_type = self._map_evidence_type(ev_type_str)
                    if ev_type and not any(e.type == ev_type for e in case_file.evidence):
                        evidence = EvidenceItem(
                            type=ev_type,
                            description=ev_data.get("description", ""),
                        )
                        case_file.evidence.append(evidence)

        # Update claims
        if "claims" in extracted:
            for claim_data in extracted["claims"]:
                claimant = claim_data.get("claimant", "").lower()
                issue_str = claim_data.get("issue", "").lower().replace(" ", "_")
                amount = claim_data.get("amount", 0)

                if amount > 0:
                    issue_type = self._map_issue_type(issue_str) or DisputeIssue.OTHER
                    claim = ClaimedAmount(
                        issue=issue_type,
                        amount=float(amount),
                        description=claim_data.get("description", ""),
                    )

                    if claimant == "tenant":
                        case_file.tenant_claims.append(claim)
                    elif claimant == "landlord":
                        case_file.landlord_claims.append(claim)

        # Update narrative
        if "narrative" in extracted:
            narrative = self._get_value(extracted["narrative"])
            if case_file.user_role == PartyRole.TENANT:
                if case_file.tenant_narrative:
                    case_file.tenant_narrative += f"\n{narrative}"
                else:
                    case_file.tenant_narrative = narrative
            else:
                if case_file.landlord_narrative:
                    case_file.landlord_narrative += f"\n{narrative}"
                else:
                    case_file.landlord_narrative = narrative

        # Update completeness
        case_file.calculate_completeness()
        case_file.get_missing_required_info()
        case_file.update_timestamp()

        return case_file, confidence_scores

    def _get_value(self, field: Any) -> Any:
        """Extract value from a field that may be wrapped with confidence."""
        if isinstance(field, dict) and "value" in field:
            return field["value"]
        return field

    def _get_confidence(self, field: Any) -> float:
        """Extract confidence from a field."""
        if isinstance(field, dict) and "confidence" in field:
            return float(field["confidence"])
        return 1.0

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse a date string into a date object."""
        if not date_str:
            return None

        try:
            # Try ISO format first
            if "-" in str(date_str):
                parts = str(date_str).split("-")
                if len(parts) == 3:
                    return date(int(parts[0]), int(parts[1]), int(parts[2]))

            # Try common UK format (DD/MM/YYYY)
            if "/" in str(date_str):
                parts = str(date_str).split("/")
                if len(parts) == 3:
                    return date(int(parts[2]), int(parts[1]), int(parts[0]))

        except (ValueError, IndexError):
            pass

        return None

    def _map_issue_type(self, issue_str: str) -> Optional[DisputeIssue]:
        """Map common issue variations to DisputeIssue enum."""
        mappings = {
            "clean": DisputeIssue.CLEANING,
            "cleaning": DisputeIssue.CLEANING,
            "dirt": DisputeIssue.CLEANING,
            "damage": DisputeIssue.DAMAGE,
            "damages": DisputeIssue.DAMAGE,
            "broken": DisputeIssue.DAMAGE,
            "rent": DisputeIssue.RENT_ARREARS,
            "arrears": DisputeIssue.RENT_ARREARS,
            "rent_arrears": DisputeIssue.RENT_ARREARS,
            "deposit": DisputeIssue.DEPOSIT_PROTECTION,
            "protection": DisputeIssue.DEPOSIT_PROTECTION,
            "unprotected": DisputeIssue.DEPOSIT_PROTECTION,
            "inventory": DisputeIssue.INVENTORY_DISPUTE,
            "garden": DisputeIssue.GARDEN_MAINTENANCE,
            "decoration": DisputeIssue.DECORATION,
            "decorating": DisputeIssue.DECORATION,
            "wear": DisputeIssue.FAIR_WEAR_AND_TEAR,
            "fair_wear": DisputeIssue.FAIR_WEAR_AND_TEAR,
            "missing": DisputeIssue.MISSING_ITEMS,
            "items": DisputeIssue.MISSING_ITEMS,
        }

        for key, value in mappings.items():
            if key in issue_str:
                return value

        return None

    def _map_evidence_type(self, ev_str: str) -> Optional[EvidenceType]:
        """Map common evidence variations to EvidenceType enum."""
        mappings = {
            "checkin": EvidenceType.INVENTORY_CHECKIN,
            "check_in": EvidenceType.INVENTORY_CHECKIN,
            "checkout": EvidenceType.INVENTORY_CHECKOUT,
            "check_out": EvidenceType.INVENTORY_CHECKOUT,
            "photo": EvidenceType.PHOTOS_AFTER,  # Default to after
            "receipt": EvidenceType.RECEIPTS,
            "invoice": EvidenceType.INVOICES,
            "email": EvidenceType.CORRESPONDENCE,
            "message": EvidenceType.CORRESPONDENCE,
            "letter": EvidenceType.CORRESPONDENCE,
            "contract": EvidenceType.TENANCY_AGREEMENT,
            "agreement": EvidenceType.TENANCY_AGREEMENT,
            "certificate": EvidenceType.DEPOSIT_CERTIFICATE,
        }

        for key, value in mappings.items():
            if key in ev_str:
                return value

        return None
