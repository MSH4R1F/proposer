"""
Data models for BAILII scraper.

Pydantic models for validating and serializing scraped case data.
"""

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class CaseCategory(str, Enum):
    """Category of case based on keyword matching."""

    DEPOSIT = "deposit"  # Direct deposit dispute cases
    ADJACENT = "adjacent"  # Related cases (RRO, HMO, etc.)
    OTHER = "other"  # All other tribunal cases


class ScrapeStatus(str, Enum):
    """Status of a case in the scraping pipeline."""

    PENDING = "pending"  # Not yet scraped
    INDEX_SCRAPED = "index_scraped"  # Found in year index
    HTML_DOWNLOADED = "html_downloaded"  # HTML content saved
    PDF_DOWNLOADED = "pdf_downloaded"  # PDF saved
    COMPLETE = "complete"  # Fully scraped and categorized
    FAILED = "failed"  # Scraping failed
    SKIPPED = "skipped"  # Skipped (e.g., already exists)


class CaseMetadata(BaseModel):
    """Metadata for a tribunal case scraped from BAILII."""

    # Core identifiers
    case_reference: str = Field(
        ...,
        description="Full BAILII case reference, e.g., LON_00BK_HMF_2022_0043",
    )
    neutral_citation: Optional[str] = Field(
        None,
        description="Neutral citation, e.g., [2023] UKFTT LON_00BK_HMF_2022_0043",
    )
    year: int = Field(..., ge=2013, le=2030, description="Decision year")

    # URLs
    html_url: str = Field(..., description="Full URL to HTML version")
    pdf_url: str = Field(..., description="Full URL to PDF version")

    # Parsed components
    region_code: Optional[str] = Field(None, description="Region code, e.g., LON")
    region_name: Optional[str] = Field(None, description="Region name, e.g., London")
    case_type_code: Optional[str] = Field(
        None, description="Case type code, e.g., HNA"
    )
    case_type_name: Optional[str] = Field(
        None, description="Case type, e.g., Housing Act 2004"
    )

    # Decision info
    title: Optional[str] = Field(None, description="Case title from page")
    parties: Optional[str] = Field(None, description="Parties involved")
    decision_date: Optional[date] = Field(None, description="Date of decision")
    judge: Optional[str] = Field(None, description="Judge name if available")

    # Categorization
    category: CaseCategory = Field(
        default=CaseCategory.OTHER,
        description="Category based on keyword matching",
    )
    deposit_keywords_matched: List[str] = Field(
        default_factory=list,
        description="Deposit keywords found in content",
    )
    adjacent_keywords_matched: List[str] = Field(
        default_factory=list,
        description="Adjacent keywords found in content",
    )

    # Scraping metadata
    status: ScrapeStatus = Field(
        default=ScrapeStatus.PENDING,
        description="Current scraping status",
    )
    scraped_at: Optional[datetime] = Field(None, description="When scraped")
    html_path: Optional[str] = Field(None, description="Local path to HTML file")
    pdf_path: Optional[str] = Field(None, description="Local path to PDF file")
    error_message: Optional[str] = Field(None, description="Error if failed")

    @field_validator("case_reference")
    @classmethod
    def validate_case_reference(cls, v: str) -> str:
        """Ensure case reference is clean."""
        return v.strip().replace(".html", "").replace(".pdf", "")

    @property
    def is_deposit_case(self) -> bool:
        """Check if this is a deposit-related case."""
        return self.category == CaseCategory.DEPOSIT

    @property
    def is_adjacent_case(self) -> bool:
        """Check if this is an adjacent case."""
        return self.category == CaseCategory.ADJACENT

    @property
    def all_keywords_matched(self) -> List[str]:
        """Get all matched keywords."""
        return self.deposit_keywords_matched + self.adjacent_keywords_matched

    def get_output_dir(self, base_dir: Path) -> Path:
        """Get the output directory for this case."""
        if self.category == CaseCategory.DEPOSIT:
            category_dir = "deposit-cases"
        elif self.category == CaseCategory.ADJACENT:
            category_dir = "adjacent-cases"
        else:
            category_dir = "other-cases"

        return base_dir / category_dir / str(self.year) / self.case_reference

    class Config:
        use_enum_values = True


class YearIndex(BaseModel):
    """Index of cases for a single year."""

    year: int
    total_cases: int = 0
    deposit_cases: int = 0
    adjacent_cases: int = 0
    other_cases: int = 0
    cases: List[CaseMetadata] = Field(default_factory=list)
    scraped_at: Optional[datetime] = None

    @property
    def completion_rate(self) -> float:
        """Calculate scraping completion rate."""
        if not self.cases:
            return 0.0
        completed = sum(
            1 for c in self.cases if c.status == ScrapeStatus.COMPLETE
        )
        return completed / len(self.cases)


class ScrapeProgress(BaseModel):
    """Overall scraping progress tracker."""

    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    total_years: int = 0
    years_completed: int = 0
    total_cases_found: int = 0
    cases_scraped: int = 0
    cases_failed: int = 0

    deposit_cases_found: int = 0
    adjacent_cases_found: int = 0
    other_cases_found: int = 0

    current_year: Optional[int] = None
    current_case: Optional[str] = None

    errors: List[dict] = Field(default_factory=list)

    @property
    def completion_percentage(self) -> float:
        """Calculate overall completion percentage."""
        if self.total_cases_found == 0:
            return 0.0
        return (self.cases_scraped / self.total_cases_found) * 100

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total_attempted = self.cases_scraped + self.cases_failed
        if total_attempted == 0:
            return 0.0
        return (self.cases_scraped / total_attempted) * 100

    def add_error(self, case_ref: str, error: str) -> None:
        """Record an error."""
        self.errors.append({
            "case_reference": case_ref,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def update_timestamp(self) -> None:
        """Update the last_updated timestamp."""
        self.last_updated = datetime.utcnow()


class MasterIndex(BaseModel):
    """Master index of all scraped cases."""

    version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    total_cases: int = 0
    years: dict = Field(default_factory=dict)  # year -> YearIndex summary

    deposit_cases: List[str] = Field(
        default_factory=list, description="Case references"
    )
    adjacent_cases: List[str] = Field(default_factory=list)
    other_cases: List[str] = Field(default_factory=list)

    def add_case(self, case: CaseMetadata) -> None:
        """Add a case to the master index."""
        ref = case.case_reference
        if case.category == CaseCategory.DEPOSIT:
            if ref not in self.deposit_cases:
                self.deposit_cases.append(ref)
        elif case.category == CaseCategory.ADJACENT:
            if ref not in self.adjacent_cases:
                self.adjacent_cases.append(ref)
        else:
            if ref not in self.other_cases:
                self.other_cases.append(ref)

        self.total_cases = (
            len(self.deposit_cases)
            + len(self.adjacent_cases)
            + len(self.other_cases)
        )
        self.last_updated = datetime.utcnow()


class CaseIndexEntry(BaseModel):
    """Lightweight entry for case index (used in year listings)."""

    case_reference: str
    title: Optional[str] = None
    decision_date: Optional[str] = None
    category_text: Optional[str] = None
    html_url: str
    pdf_url: str

    @classmethod
    def from_metadata(cls, metadata: CaseMetadata) -> "CaseIndexEntry":
        """Create an index entry from full metadata."""
        return cls(
            case_reference=metadata.case_reference,
            title=metadata.title,
            decision_date=metadata.decision_date.isoformat()
            if metadata.decision_date
            else None,
            category_text=metadata.case_type_name,
            html_url=metadata.html_url,
            pdf_url=metadata.pdf_url,
        )
