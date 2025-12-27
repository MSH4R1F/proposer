"""
Configuration module for BAILII scraper.

Contains all settings, keywords, and constants used by the scraper.
Environment variables can override defaults.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set


@dataclass
class ScraperConfig:
    """Configuration settings for the BAILII scraper."""

    # Base URLs
    base_url: str = "https://www.bailii.org"
    ukftt_pc_path: str = "/uk/cases/UKFTT/PC/"

    # Rate limiting
    requests_per_second: float = 1.0  # Be polite to BAILII
    max_concurrent_requests: int = 3  # Limit concurrent downloads

    # Retry settings
    max_retries: int = 3
    retry_base_delay: float = 1.0  # seconds
    retry_max_delay: float = 30.0  # seconds
    request_timeout: int = 30  # seconds

    # Output directories (relative to project root)
    output_base_dir: Path = field(default_factory=lambda: Path("data/raw/bailii"))
    deposit_cases_dir: str = "deposit-cases"
    adjacent_cases_dir: str = "adjacent-cases"
    other_cases_dir: str = "other-cases"

    # Progress tracking
    progress_db_name: str = "scrape_progress.db"
    master_index_name: str = "master_index.json"
    log_file_name: str = "scrape_log.json"

    # User agent for requests
    user_agent: str = (
        "ProposerResearchBot/1.0 "
        "(Academic research on UK tenancy law; "
        "contact: github.com/proposer)"
    )

    # Years to scrape by default (recent first)
    default_years: List[int] = field(default_factory=lambda: [
        2025, 2024, 2023, 2022, 2021, 2020
    ])

    # All available years
    all_years: List[int] = field(default_factory=lambda: list(range(2013, 2026)))

    def __post_init__(self):
        """Initialize paths from environment variables if set."""
        if env_base := os.getenv("BAILII_OUTPUT_DIR"):
            self.output_base_dir = Path(env_base)

        if env_rate := os.getenv("BAILII_RATE_LIMIT"):
            self.requests_per_second = float(env_rate)

    @property
    def deposit_dir(self) -> Path:
        return self.output_base_dir / self.deposit_cases_dir

    @property
    def adjacent_dir(self) -> Path:
        return self.output_base_dir / self.adjacent_cases_dir

    @property
    def other_dir(self) -> Path:
        return self.output_base_dir / self.other_cases_dir

    @property
    def progress_db_path(self) -> Path:
        return self.output_base_dir / self.progress_db_name

    @property
    def master_index_path(self) -> Path:
        return self.output_base_dir / self.master_index_name

    @property
    def log_path(self) -> Path:
        return self.output_base_dir / self.log_file_name

    def get_year_url(self, year: int) -> str:
        """Get the URL for a year index page."""
        return f"{self.base_url}{self.ukftt_pc_path}{year}/"

    def get_case_url(self, year: int, case_ref: str) -> str:
        """Get the URL for a case HTML page."""
        return f"{self.base_url}{self.ukftt_pc_path}{year}/{case_ref}.html"

    def get_pdf_url(self, year: int, case_ref: str) -> str:
        """Get the URL for a case PDF."""
        return f"{self.base_url}{self.ukftt_pc_path}{year}/{case_ref}.pdf"


# Priority Keywords - Direct deposit cases (Tier 1)
# These indicate the case is directly about deposit disputes
DEPOSIT_KEYWORDS: Set[str] = {
    # Legislation references
    "section 214",
    "s.214",
    "s214",
    "housing act 2004",

    # Deposit scheme names
    "tenancy deposit scheme",
    "deposit protection scheme",
    "tds",
    "mydeposits",
    "my deposits",
    "dps",
    "deposit protection service",

    # Deposit-specific terms
    "deposit withholding",
    "deposit withheld",
    "deposit deduction",
    "deposit deductions",
    "return of deposit",
    "return the deposit",
    "deposit return",
    "deposit refund",
    "failure to protect",
    "failed to protect",
    "unprotected deposit",
    "deposit not protected",

    # Penalty terms
    "three times the deposit",
    "3 times the deposit",
    "deposit penalty",
    "penalty deposit",
    "prescribed information",
    "failed to provide prescribed information",
}

# Adjacent Keywords - Related cases (Tier 2)
# These cases may involve deposits or be useful context
ADJACENT_KEYWORDS: Set[str] = {
    # Rent Repayment Orders (often involve housing violations)
    "rent repayment order",
    "rro",

    # HMO cases (can involve deposit penalties)
    "unlicensed hmo",
    "hmo licensing",
    "house in multiple occupation",
    "hmo licence",
    "hmo license",

    # Housing conditions (relates to damage claims)
    "disrepair",
    "housing conditions",
    "improvement notice",
    "hazard awareness notice",

    # Eviction (sometimes mention deposits)
    "section 21",
    "s.21",
    "s21",
    "possession order",
    "notice to quit",

    # General tenancy terms
    "assured shorthold tenancy",
    "ast",
    "tenancy agreement",
    "inventory",
    "check-out report",
    "check-in report",
    "end of tenancy",
}

# Case type categories from BAILII structure
CASE_TYPE_CODES: dict = {
    "HNA": "Housing Act 2004",
    "HMF": "Housing and Planning Act 2016",
    "LDC": "Leasehold - Dispute/Complaint",
    "LSC": "Leasehold - Service Charges",
    "LAM": "Leasehold - Administration",
    "LRM": "Leasehold - Right to Manage",
    "LBC": "Leasehold - Breach of Covenant",
    "LEE": "Leasehold - Enfranchisement",
    "LVT": "Leasehold Valuation Tribunal",
    "RRO": "Rent Repayment Order",
    "MHR": "Mobile Homes",
    "RPM": "Residential Property",
    "HBD": "Housing - Band/Disability",
}

# Region codes from BAILII case references
REGION_CODES: dict = {
    "LON": "London",
    "CHI": "Chichester (South East)",
    "MAN": "Manchester (North West)",
    "BIR": "Birmingham (Midlands)",
    "CAM": "Cambridge (East)",
    "HAV": "Havant (South)",
    "KA": "Kent Area",
    "MID": "Midlands",
    "NOR": "Northern",
    "WMI": "West Midlands",
    "EAS": "Eastern",
    "SOU": "Southern",
}


def normalize_keyword(text: str) -> str:
    """Normalize text for keyword matching."""
    return text.lower().strip()


def check_deposit_keywords(text: str) -> List[str]:
    """
    Check if text contains deposit-related keywords.

    Args:
        text: The text to search (case HTML content)

    Returns:
        List of matched deposit keywords
    """
    normalized = normalize_keyword(text)
    matches = []

    for keyword in DEPOSIT_KEYWORDS:
        if keyword in normalized:
            matches.append(keyword)

    return matches


def check_adjacent_keywords(text: str) -> List[str]:
    """
    Check if text contains adjacent keywords.

    Args:
        text: The text to search

    Returns:
        List of matched adjacent keywords
    """
    normalized = normalize_keyword(text)
    matches = []

    for keyword in ADJACENT_KEYWORDS:
        if keyword in normalized:
            matches.append(keyword)

    return matches


def get_case_type_from_code(code: str) -> str:
    """Get human-readable case type from BAILII code."""
    return CASE_TYPE_CODES.get(code.upper(), f"Unknown ({code})")


def get_region_from_code(code: str) -> str:
    """Get region name from BAILII region code."""
    return REGION_CODES.get(code.upper(), f"Unknown ({code})")
