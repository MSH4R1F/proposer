#!/usr/bin/env python3
"""
RAG Engine CLI runner script.

Run from project root:
    python scripts/rag.py --help
    python scripts/rag.py ingest --pdf-dir data/raw/bailii
    python scripts/rag.py query "tenant deposit not protected"
"""

import sys
from pathlib import Path

# Add packages directory to path so 'rag_engine' can be imported
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages"))

# Change to project root for relative paths to work
import os
os.chdir(str(project_root))

if __name__ == "__main__":
    from rag_engine.cli import cli
    cli()
