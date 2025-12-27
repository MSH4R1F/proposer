"""
HTML parsers for BAILII scraper.

Parses year index pages and individual case pages to extract structured data.
"""

import re
import logging
from datetime import date, datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import (
    ScraperConfig,
    check_deposit_keywords,
    check_adjacent_keywords,
    get_case_type_from_code,
    get_region_from_code,
)
from .models import CaseCategory, CaseMetadata, CaseIndexEntry

logger = logging.getLogger(__name__)


class YearIndexParser:
    """Parser for BAILII year index pages."""

    def __init__(self, config: ScraperConfig):
        self.config = config

    def parse(self, html: str, year: int) -> List[CaseIndexEntry]:
        """
        Parse a year index page and extract case entries.

        Args:
            html: Raw HTML content of year index page
            year: The year being parsed

        Returns:
            List of CaseIndexEntry objects
        """
        soup = BeautifulSoup(html, "lxml")
        entries = []

        # Find all links that look like case references
        # Pattern: .html files in the current year directory
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")

            # Match case links: /uk/cases/UKFTT/PC/YEAR/CASE_REF.html
            # or relative: CASE_REF.html
            if not href.endswith(".html"):
                continue

            # Skip navigation links
            if href.startswith("/") and f"/{year}/" not in href:
                continue

            # Extract case reference from href
            case_ref = self._extract_case_ref(href)
            if not case_ref:
                continue

            # Get surrounding text for metadata
            title = self._extract_title(link)
            decision_date = self._extract_date_from_context(link)
            category_text = self._extract_category(link)

            # Build URLs
            html_url = self.config.get_case_url(year, case_ref)
            pdf_url = self.config.get_pdf_url(year, case_ref)

            entry = CaseIndexEntry(
                case_reference=case_ref,
                title=title,
                decision_date=decision_date,
                category_text=category_text,
                html_url=html_url,
                pdf_url=pdf_url,
            )
            entries.append(entry)

        logger.info(f"Parsed {len(entries)} cases from year {year} index")
        return entries

    def _extract_case_ref(self, href: str) -> Optional[str]:
        """Extract case reference from href."""
        # Remove path components and extension
        filename = href.split("/")[-1]
        if not filename:
            return None

        case_ref = filename.replace(".html", "").replace(".pdf", "")

        # Validate it looks like a case reference
        # Pattern: REGION_CODE_TYPE_YEAR_NUMBER
        if not re.match(r"^[A-Z]{2,4}_", case_ref):
            return None

        return case_ref

    def _extract_title(self, link_element) -> Optional[str]:
        """Extract case title from link and surrounding context."""
        # Get the link text itself
        text = link_element.get_text(strip=True)
        if text and len(text) > 3:
            return text

        # Check parent element
        parent = link_element.parent
        if parent:
            parent_text = parent.get_text(strip=True)
            if parent_text:
                return parent_text[:200]  # Limit length

        return None

    def _extract_date_from_context(self, link_element) -> Optional[str]:
        """Extract decision date from surrounding text."""
        # Look for date patterns in parent/sibling elements
        parent = link_element.parent
        if not parent:
            return None

        text = parent.get_text()

        # Common date patterns
        patterns = [
            r"(\d{1,2}\s+\w+\s+\d{4})",  # 15 March 2023
            r"(\d{1,2}/\d{1,2}/\d{4})",  # 15/03/2023
            r"(\d{4}-\d{2}-\d{2})",  # 2023-03-15
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def _extract_category(self, link_element) -> Optional[str]:
        """Extract case category from context."""
        parent = link_element.parent
        if not parent:
            return None

        text = parent.get_text()

        # Look for category in parentheses
        match = re.search(r"\(([^)]+)\)", text)
        if match:
            return match.group(1)

        return None


class CasePageParser:
    """Parser for individual BAILII case pages."""

    def __init__(self, config: ScraperConfig):
        self.config = config

    def parse(
        self,
        html: str,
        case_ref: str,
        year: int,
    ) -> CaseMetadata:
        """
        Parse a case page and extract full metadata.

        Args:
            html: Raw HTML content of case page
            case_ref: Case reference
            year: Decision year

        Returns:
            CaseMetadata with all extracted information
        """
        soup = BeautifulSoup(html, "lxml")

        # Extract components from case reference
        region_code, case_type_code = self._parse_case_ref_components(case_ref)

        # Extract metadata from various sources
        title = self._extract_title(soup)
        parties = self._extract_parties(soup, title)
        decision_date = self._extract_decision_date(soup)
        judge = self._extract_judge(soup)
        neutral_citation = self._extract_neutral_citation(soup, case_ref, year)

        # Get full text for keyword matching
        full_text = soup.get_text(separator=" ", strip=True)

        # Check keywords
        deposit_keywords = check_deposit_keywords(full_text)
        adjacent_keywords = check_adjacent_keywords(full_text)

        # Determine category
        if deposit_keywords:
            category = CaseCategory.DEPOSIT
        elif adjacent_keywords:
            category = CaseCategory.ADJACENT
        else:
            category = CaseCategory.OTHER

        metadata = CaseMetadata(
            case_reference=case_ref,
            neutral_citation=neutral_citation,
            year=year,
            html_url=self.config.get_case_url(year, case_ref),
            pdf_url=self.config.get_pdf_url(year, case_ref),
            region_code=region_code,
            region_name=get_region_from_code(region_code) if region_code else None,
            case_type_code=case_type_code,
            case_type_name=get_case_type_from_code(case_type_code)
            if case_type_code
            else None,
            title=title,
            parties=parties,
            decision_date=decision_date,
            judge=judge,
            category=category,
            deposit_keywords_matched=deposit_keywords,
            adjacent_keywords_matched=adjacent_keywords,
        )

        logger.debug(
            f"Parsed case {case_ref}: category={category.value if hasattr(category, 'value') else category}, "
            f"deposit_keywords={len(deposit_keywords)}, "
            f"adjacent_keywords={len(adjacent_keywords)}"
        )

        return metadata

    def _parse_case_ref_components(
        self, case_ref: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse region and case type from case reference.

        Example: LON_00BK_HMF_2022_0043
        - Region: LON
        - Type: HMF
        """
        parts = case_ref.split("_")
        if len(parts) < 3:
            return None, None

        region_code = parts[0]

        # Case type is typically the 3rd component
        # Pattern: REGION_CODE_TYPE_YEAR_NUMBER
        case_type_code = None
        for part in parts[1:]:
            # Look for known case type codes (3 letters)
            if len(part) == 3 and part.isalpha():
                case_type_code = part
                break

        return region_code, case_type_code

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract case title."""
        # Try meta tag first
        meta_title = soup.find("meta", {"name": "DC.title"})
        if meta_title and meta_title.get("content"):
            return meta_title["content"]

        # Try HTML title
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Clean up BAILII suffix
            title = re.sub(r"\s*\[?\d{4}\]?\s*UK\w+\s*\S+$", "", title)
            if title:
                return title

        # Look for heading elements
        for heading in soup.find_all(["h1", "h2"]):
            text = heading.get_text(strip=True)
            if text and not text.lower().startswith("bailii"):
                return text

        return None

    def _extract_parties(
        self, soup: BeautifulSoup, title: Optional[str]
    ) -> Optional[str]:
        """Extract party names from title or content."""
        if not title:
            return None

        # Look for "v" or "vs" pattern
        match = re.search(r"(.+?)\s+(?:v\.?|vs\.?)\s+(.+)", title, re.IGNORECASE)
        if match:
            return f"{match.group(1).strip()} v {match.group(2).strip()}"

        # Look for "and" pattern (e.g., "Smith and Jones")
        match = re.search(r"(.+?)\s+(?:and|&)\s+(.+)", title, re.IGNORECASE)
        if match:
            return f"{match.group(1).strip()} & {match.group(2).strip()}"

        return None

    def _extract_decision_date(self, soup: BeautifulSoup) -> Optional[date]:
        """Extract decision date."""
        # Try meta tag
        meta_date = soup.find("meta", {"name": "DC.date"})
        if meta_date and meta_date.get("content"):
            try:
                return datetime.strptime(
                    meta_date["content"], "%Y-%m-%d"
                ).date()
            except ValueError:
                pass

        # Search for date patterns in text
        text = soup.get_text()

        # Common patterns in tribunal decisions
        patterns = [
            (r"(?:dated?|decided?)\s*:?\s*(\d{1,2}\s+\w+\s+\d{4})", "%d %B %Y"),
            (r"(?:dated?|decided?)\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})", "%d/%m/%Y"),
            (r"decision\s+date\s*:?\s*(\d{1,2}\s+\w+\s+\d{4})", "%d %B %Y"),
        ]

        for pattern, date_format in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return datetime.strptime(match.group(1), date_format).date()
                except ValueError:
                    continue

        return None

    def _extract_judge(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract judge name."""
        text = soup.get_text()

        patterns = [
            r"(?:Judge|Tribunal Judge|Deputy Judge)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            r"(?:Before|Presided by):\s*(?:Judge\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def _extract_neutral_citation(
        self,
        soup: BeautifulSoup,
        case_ref: str,
        year: int,
    ) -> str:
        """Extract or construct neutral citation."""
        # Try meta tag
        meta_cit = soup.find("meta", {"name": "DC.identifier"})
        if meta_cit and meta_cit.get("content"):
            return meta_cit["content"]

        # Try finding citation in text
        text = soup.get_text()
        match = re.search(
            rf"\[{year}\]\s*UKFTT\s+{re.escape(case_ref)}",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(0)

        # Construct from components
        return f"[{year}] UKFTT {case_ref}"


def extract_pdf_link(html: str, base_url: str = "") -> Optional[str]:
    """
    Extract PDF download link from case page.

    Args:
        html: HTML content
        base_url: Base URL for resolving relative links

    Returns:
        Full URL to PDF or None
    """
    soup = BeautifulSoup(html, "lxml")

    # Look for explicit PDF links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text().lower()

        if href.endswith(".pdf"):
            return urljoin(base_url, href)

        if "pdf" in text and ("printable" in text or "download" in text):
            if href.endswith(".pdf"):
                return urljoin(base_url, href)

    return None
