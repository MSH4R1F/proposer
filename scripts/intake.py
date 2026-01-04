#!/usr/bin/env python3
"""
CLI runner for the intake agent.

Usage:
    python scripts/intake.py chat
    python scripts/intake.py chat --role tenant
    python scripts/intake.py test-connection
"""

import sys
from pathlib import Path

# Add packages to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages"))

# Change to project root for relative paths
import os
os.chdir(project_root)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import and run CLI
from llm_orchestrator.cli import cli

if __name__ == "__main__":
    cli()
