#!/usr/bin/env python3
"""
API server runner.

Usage:
    python scripts/api.py
    python scripts/api.py --port 8080
    python scripts/api.py --reload  # Development mode
"""

import argparse
import sys
from pathlib import Path

# Add packages to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages"))
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

# Change to project root for relative paths
import os
os.chdir(project_root)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Run the Legal Mediation System API")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    import uvicorn

    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║         Legal Mediation System API                       ║
    ║                                                          ║
    ║   Server: http://{args.host}:{args.port}                       ║
    ║   Docs:   http://{args.host}:{args.port}/docs                  ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(project_root / "apps" / "api"), str(project_root / "packages")],
    )


if __name__ == "__main__":
    main()
