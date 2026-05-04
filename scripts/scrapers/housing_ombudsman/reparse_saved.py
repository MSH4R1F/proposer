"""Refresh parsed metadata for already-downloaded Housing Ombudsman pages.

Use this after parser fixes when ``decision.html`` files are already on disk.
It rewrites each kept case's ``parsed.json`` and updates date/outcome fields
in ``scrape_summary.json`` without hitting the live Ombudsman site.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from scripts.scrapers.housing_ombudsman.config import ScraperConfig
from scripts.scrapers.housing_ombudsman.parsers import parse_detail_html


def _scraper_config_for_data_dir(data_dir: Optional[str]) -> ScraperConfig:
    if not data_dir:
        return ScraperConfig()
    data_root = Path(data_dir).expanduser().resolve()
    return ScraperConfig(
        output_subdir=str(data_root / "raw" / "housing_ombudsman")
    )


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _entry_paths(master_index: dict) -> dict[Path, tuple[str, dict]]:
    out = {}
    for key, entry in master_index.items():
        raw_storage_path = entry.get("raw_storage_path")
        if not raw_storage_path:
            continue
        out[Path(raw_storage_path).expanduser().resolve()] = (key, entry)
    return out


def _source_url_for(case_dir: Path, old_parsed: dict, path_entries: dict) -> str:
    if old_parsed.get("source_url"):
        return str(old_parsed["source_url"])
    entry = path_entries.get(case_dir.resolve())
    if entry and entry[1].get("source_url"):
        return str(entry[1]["source_url"])
    return f"https://www.housing-ombudsman.org.uk/decisions/{case_dir.name}/"


@click.command()
@click.option(
    "--data-dir",
    type=click.Path(),
    default=None,
    help=(
        "Base data dir. Reads <data-dir>/raw/housing_ombudsman, matching "
        "scrape/ingest --data-dir."
    ),
)
@click.option("--max-docs", type=int, default=None, help="Optional cap for smoke runs.")
@click.option("--dry-run", is_flag=True, default=False, help="Parse but do not write.")
def main(data_dir: Optional[str], max_docs: Optional[int], dry_run: bool) -> None:
    config = _scraper_config_for_data_dir(data_dir)
    master_index = _load_json(config.master_index_path, {})
    path_entries = _entry_paths(master_index)
    summary = _load_json(config.scrape_summary_path, {})

    parsed = 0
    missing_html = 0
    outcome_counts: Counter[str] = Counter()
    earliest = None
    latest = None

    case_dirs = sorted(p for p in config.decisions_dir.iterdir() if p.is_dir())
    for case_dir in case_dirs:
        if max_docs is not None and parsed >= max_docs:
            break
        html_path = case_dir / "decision.html"
        if not html_path.exists():
            missing_html += 1
            continue

        old_parsed = _load_json(case_dir / "parsed.json", {})
        source_url = _source_url_for(case_dir, old_parsed, path_entries)
        html = html_path.read_text(encoding="utf-8")
        metadata, raw_text = parse_detail_html(html, source_url=source_url)

        if not dry_run:
            (case_dir / "parsed.json").write_text(
                json.dumps(
                    metadata.model_dump(mode="json"),
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
                encoding="utf-8",
            )
            (case_dir / "raw.txt").write_text(raw_text, encoding="utf-8")

            entry = path_entries.get(case_dir.resolve())
            if entry is not None:
                _key, payload = entry
                payload["decision_date"] = (
                    metadata.decision_date.isoformat()
                    if metadata.decision_date
                    else None
                )

        outcome_key = (
            metadata.outcome_normalized
            or metadata.outcome_raw
            or "unknown"
        )
        outcome_counts[outcome_key] += 1
        if metadata.decision_date:
            iso = metadata.decision_date.isoformat()
            earliest = iso if earliest is None or iso < earliest else earliest
            latest = iso if latest is None or iso > latest else latest
        parsed += 1

    if not dry_run:
        config.master_index_path.write_text(
            json.dumps(master_index, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        summary["cases_kept"] = parsed
        summary["earliest_decision_date"] = earliest
        summary["latest_decision_date"] = latest
        summary["outcome_counts"] = dict(sorted(outcome_counts.items()))
        notes = list(summary.get("notes") or [])
        notes.append(
            "reparsed_saved_metadata_at="
            f"{datetime.now(timezone.utc).isoformat()}"
        )
        summary["notes"] = notes
        config.scrape_summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "data_dir": str(config.output_dir.parent.parent),
                "raw_dir": str(config.output_dir),
                "parsed": parsed,
                "missing_html": missing_html,
                "earliest_decision_date": earliest,
                "latest_decision_date": latest,
                "outcome_counts": dict(sorted(outcome_counts.items())),
                "dry_run": dry_run,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
