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

# Add packages and project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))  # Add project root for apps.* imports
sys.path.insert(0, str(project_root / "packages"))
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

# Change to project root for relative paths
import os
os.chdir(project_root)

# Cap the open-file-descriptor soft limit before anything imports ChromaDB.
# Chroma derives its HNSW cache size from RLIMIT_NOFILE (cache = nofile // 5).
# Container runtimes (Lightsail/ECS/k8s) frequently expose an effectively
# unlimited nofile (~1e9), which makes Chroma's Rust bindings size an enormous
# cache and fail to initialise on memory-limited hosts — surfacing as the
# masked "'RustBindingsAPI' object has no attribute 'bindings'" and leaving the
# RAG pipeline silently unavailable. Capping to a sane value keeps it small.
try:
    import resource

    _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    _target = 65536
    _new_soft = _target if _hard == resource.RLIM_INFINITY else min(_target, _hard)
    if _soft == resource.RLIM_INFINITY or _soft > _new_soft:
        resource.setrlimit(resource.RLIMIT_NOFILE, (_new_soft, _hard))
except Exception:
    pass

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
