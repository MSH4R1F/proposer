"""
Progress tracking for BAILII scraper using SQLite.

Provides resume capability, statistics, and logging.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiosqlite

from .config import ScraperConfig
from .models import CaseCategory, CaseMetadata, ScrapeStatus, ScrapeProgress

logger = logging.getLogger(__name__)


class ProgressTracker:
    """
    SQLite-based progress tracker for scraping operations.

    Enables:
    - Resume capability after interruption
    - Statistics and reporting
    - Error logging
    """

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.db_path = config.progress_db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def __aenter__(self):
        """Initialize database connection and schema."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def initialize(self) -> None:
        """Initialize the database and create schema if needed."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(str(self.db_path))

        # Enable foreign keys
        await self._db.execute("PRAGMA foreign_keys = ON")

        # Create tables
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                years TEXT,
                status TEXT DEFAULT 'in_progress'
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_reference TEXT UNIQUE NOT NULL,
                year INTEGER NOT NULL,
                html_url TEXT,
                pdf_url TEXT,
                category TEXT DEFAULT 'other',
                status TEXT DEFAULT 'pending',
                title TEXT,
                decision_date TEXT,
                deposit_keywords TEXT,
                adjacent_keywords TEXT,
                html_path TEXT,
                pdf_path TEXT,
                error_message TEXT,
                scraped_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_reference TEXT,
                error_type TEXT,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year);
            CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
            CREATE INDEX IF NOT EXISTS idx_cases_category ON cases(category);
        """)

        await self._db.commit()
        logger.info(f"Progress database initialized at {self.db_path}")

    @property
    def db(self) -> aiosqlite.Connection:
        """Get database connection."""
        if not self._db:
            raise RuntimeError("Database not initialized")
        return self._db

    async def start_run(self, years: List[int]) -> int:
        """
        Record the start of a scrape run.

        Args:
            years: Years being scraped

        Returns:
            Run ID
        """
        cursor = await self.db.execute(
            "INSERT INTO scrape_runs (years) VALUES (?)",
            (json.dumps(years),)
        )
        await self.db.commit()
        return cursor.lastrowid

    async def complete_run(self, run_id: int) -> None:
        """Mark a run as complete."""
        await self.db.execute(
            """UPDATE scrape_runs
               SET completed_at = CURRENT_TIMESTAMP, status = 'complete'
               WHERE id = ?""",
            (run_id,)
        )
        await self.db.commit()

    async def add_case(self, metadata: CaseMetadata) -> None:
        """
        Add or update a case in the database.

        Args:
            metadata: Case metadata
        """
        await self.db.execute(
            """INSERT INTO cases (
                case_reference, year, html_url, pdf_url, category, status,
                title, decision_date, deposit_keywords, adjacent_keywords,
                html_path, pdf_path, error_message, scraped_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(case_reference) DO UPDATE SET
                category = excluded.category,
                status = excluded.status,
                title = excluded.title,
                decision_date = excluded.decision_date,
                deposit_keywords = excluded.deposit_keywords,
                adjacent_keywords = excluded.adjacent_keywords,
                html_path = excluded.html_path,
                pdf_path = excluded.pdf_path,
                error_message = excluded.error_message,
                scraped_at = excluded.scraped_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                metadata.case_reference,
                metadata.year,
                metadata.html_url,
                metadata.pdf_url,
                metadata.category.value if hasattr(metadata.category, 'value') else str(metadata.category),
                metadata.status.value if hasattr(metadata.status, 'value') else str(metadata.status),
                metadata.title,
                metadata.decision_date.isoformat() if metadata.decision_date else None,
                json.dumps(metadata.deposit_keywords_matched),
                json.dumps(metadata.adjacent_keywords_matched),
                metadata.html_path,
                metadata.pdf_path,
                metadata.error_message,
                metadata.scraped_at.isoformat() if metadata.scraped_at else None,
            )
        )
        await self.db.commit()

    async def update_case_status(
        self,
        case_ref: str,
        status: ScrapeStatus,
        html_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update the status of a case."""
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status.value if hasattr(status, 'value') else str(status)]

        if html_path:
            updates.append("html_path = ?")
            params.append(html_path)

        if pdf_path:
            updates.append("pdf_path = ?")
            params.append(pdf_path)

        if status == ScrapeStatus.COMPLETE:
            updates.append("scraped_at = CURRENT_TIMESTAMP")

        if error_message:
            updates.append("error_message = ?")
            params.append(error_message)

        params.append(case_ref)

        await self.db.execute(
            f"UPDATE cases SET {', '.join(updates)} WHERE case_reference = ?",
            tuple(params)
        )
        await self.db.commit()

    async def get_pending_cases(self, year: Optional[int] = None) -> List[dict]:
        """
        Get cases that haven't been fully scraped.

        Args:
            year: Optional year filter

        Returns:
            List of case records
        """
        query = """
            SELECT case_reference, year, html_url, pdf_url, status
            FROM cases
            WHERE status NOT IN ('complete', 'skipped')
        """
        params = []

        if year:
            query += " AND year = ?"
            params.append(year)

        query += " ORDER BY year DESC, case_reference"

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "case_reference": row[0],
                    "year": row[1],
                    "html_url": row[2],
                    "pdf_url": row[3],
                    "status": row[4],
                }
                for row in rows
            ]

    async def case_exists(self, case_ref: str) -> bool:
        """Check if a case already exists in the database."""
        async with self.db.execute(
            "SELECT 1 FROM cases WHERE case_reference = ?",
            (case_ref,)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def get_case_status(self, case_ref: str) -> Optional[str]:
        """Get the status of a specific case."""
        async with self.db.execute(
            "SELECT status FROM cases WHERE case_reference = ?",
            (case_ref,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def log_error(
        self,
        case_ref: str,
        error_type: str,
        error_message: str,
    ) -> None:
        """Log an error for a case."""
        await self.db.execute(
            """INSERT INTO errors (case_reference, error_type, error_message)
               VALUES (?, ?, ?)""",
            (case_ref, error_type, error_message)
        )
        await self.db.commit()

    async def get_statistics(self) -> dict:
        """Get comprehensive scraping statistics."""
        stats = {}

        # Total counts
        async with self.db.execute("SELECT COUNT(*) FROM cases") as cursor:
            stats["total_cases"] = (await cursor.fetchone())[0]

        # By status
        async with self.db.execute(
            "SELECT status, COUNT(*) FROM cases GROUP BY status"
        ) as cursor:
            stats["by_status"] = dict(await cursor.fetchall())

        # By category
        async with self.db.execute(
            "SELECT category, COUNT(*) FROM cases GROUP BY category"
        ) as cursor:
            stats["by_category"] = dict(await cursor.fetchall())

        # By year
        async with self.db.execute(
            "SELECT year, COUNT(*) FROM cases GROUP BY year ORDER BY year DESC"
        ) as cursor:
            stats["by_year"] = dict(await cursor.fetchall())

        # Error count
        async with self.db.execute("SELECT COUNT(*) FROM errors") as cursor:
            stats["total_errors"] = (await cursor.fetchone())[0]

        # Completion rate
        if stats["total_cases"] > 0:
            complete = stats["by_status"].get("complete", 0)
            stats["completion_rate"] = round(complete / stats["total_cases"] * 100, 2)
        else:
            stats["completion_rate"] = 0.0

        return stats

    async def export_to_json(self, output_path: Path) -> None:
        """Export all case metadata to JSON."""
        async with self.db.execute(
            """SELECT case_reference, year, html_url, pdf_url, category, status,
                      title, decision_date, deposit_keywords, adjacent_keywords,
                      html_path, pdf_path, scraped_at
               FROM cases
               ORDER BY year DESC, case_reference"""
        ) as cursor:
            rows = await cursor.fetchall()

        cases = []
        for row in rows:
            cases.append({
                "case_reference": row[0],
                "year": row[1],
                "html_url": row[2],
                "pdf_url": row[3],
                "category": row[4],
                "status": row[5],
                "title": row[6],
                "decision_date": row[7],
                "deposit_keywords": json.loads(row[8]) if row[8] else [],
                "adjacent_keywords": json.loads(row[9]) if row[9] else [],
                "html_path": row[10],
                "pdf_path": row[11],
                "scraped_at": row[12],
            })

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "exported_at": datetime.utcnow().isoformat(),
                    "total_cases": len(cases),
                    "cases": cases,
                },
                f,
                indent=2,
            )

        logger.info(f"Exported {len(cases)} cases to {output_path}")

    async def get_deposit_cases(self) -> List[dict]:
        """Get all deposit-related cases."""
        async with self.db.execute(
            """SELECT case_reference, year, html_url, pdf_url, title,
                      decision_date, deposit_keywords, html_path, pdf_path
               FROM cases
               WHERE category = 'deposit'
               ORDER BY year DESC, case_reference"""
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "case_reference": row[0],
                "year": row[1],
                "html_url": row[2],
                "pdf_url": row[3],
                "title": row[4],
                "decision_date": row[5],
                "deposit_keywords": json.loads(row[6]) if row[6] else [],
                "html_path": row[7],
                "pdf_path": row[8],
            }
            for row in rows
        ]
